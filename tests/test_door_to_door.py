"""Door-to-door trips on recorded OpenTripPlanner answers (tests/fixtures/otp_trips.json).
No OTP, MBTA, Snowflake or LLM calls unless TW_OTP=1 / TW_LIVE=1."""
import json
import os
from datetime import datetime, timedelta

import pytest

import agents.checker as checker
import agents.door_to_door as d2d
import agents.monitor as monitor
import agents.otp as otp
import agents.places as places
from agents.checker import check_door_trip
from agents.request_parser import CURRENT, keyword_trip_parse
from conftest import OTP_FIXTURE, place

POLICY = [{"source": "access_in_motion.pdf", "chunk": "If an elevator is out, ask staff or use a "
           "nearby accessible station. Buses are accessible.", "score": 0.7, "vector_score": 0.7,
           "keyword_boost": 0.0}]


def best(o, d, **kw):
    r = otp.plan_options(place(o), place(d), **kw)
    assert r["ok"], r
    return r["options"][0]


def transit(trip):
    return [l for l in trip["legs"] if l["transit"]]


def elevator(alert_id, stops, header="Elevator 999 is unavailable", effect="ELEVATOR_CLOSURE", facility=None):
    ents = [{"stop": s} for s in stops] + ([{"stop": stops[0], "facility": facility}] if facility else [])
    return {"id": alert_id, "attributes": {"effect": effect, "header": header, "informed_entity": ents}}


def service(alert_id, effect, route, stops=(), trip=None, header="Service change"):
    ents = [{"route": route, "stop": s} for s in stops] or [{"route": route}]
    if trip:
        ents = [{**e, "trip": trip} for e in ents]
    return {"id": alert_id, "attributes": {"effect": effect, "header": header, "informed_entity": ents}}


class FakeLLM:
    def __init__(self, answer="Take the recommended trip. [access_in_motion.pdf]",
                 verdict='{"supported": true, "unsupported_claims": []}'):
        self.answer, self.verdict, self.prompts = answer, verdict, []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return self.answer if len(self.prompts) == 1 else self.verdict


@pytest.fixture
def llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(d2d.rp, "ask_llm", fake)
    monkeypatch.setattr(d2d.rp, "search_policies", lambda conn, q, k=4: POLICY)
    return fake


def run(conn, o, d, alerts, **kw):
    return d2d.plan_door_to_door(conn, place(o), place(d), "key", alerts=alerts, log_source="test", **kw)


# ---------- OTP connector ----------

def test_decode_polyline():
    assert otp.decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@") == \
        [[38.5, -120.2], [40.7, -120.95], [43.252, -126.453]]


@pytest.mark.parametrize("text, seconds", [("PT0S", 0), ("PT1M30S", 90), ("-PT45S", -45),
                                           ("PT1H2M", 3720), (None, 0)])
def test_delay_parsing(text, seconds):
    assert otp._delay_seconds(text) == seconds


def test_trip_format(otp_fake):
    t = best("Harvard Yard", "Mass General Hospital")
    red = transit(t)
    assert [l["route_id"] for l in red] == ["Red"] and red[0]["route_name"] == "Red Line"
    leg = red[0]
    assert leg["from"]["station_id"] == "place-harsq" and leg["to"]["station_id"] == "place-chmnl"
    assert not leg["from"]["stop_id"].startswith("mbta:")
    assert leg["stops"][0]["stop_id"] == leg["from"]["stop_id"] and len(leg["geometry"]) > 5
    assert t["legs"][0]["mode"] == "ROLL" and t["transfers"] == 0


def test_options_are_ranked_and_distinct(otp_fake):
    r = otp.plan_options(place("Fields Corner"), place("Boston Medical Center"))
    scores = [t["score"] for t in r["options"]]
    assert scores == sorted(scores)
    assert len({t["key"] for t in r["options"]}) == len(r["options"])
    assert ("roll only",) not in {t["key"] for t in r["options"]}       # 60+ min roll is never offered
    assert len(otp_fake) == 2                                           # both search profiles


def test_rolling_counts_more_than_riding():
    base = {"minutes": 40, "rolling_minutes": 5, "transfers": 1,
            "legs": [{"mode": "ROLL", "minutes": 5}]}
    rolly = {**base, "minutes": 35, "rolling_minutes": 18, "legs": [{"mode": "ROLL", "minutes": 18}]}
    assert otp.score(base) < otp.score(rolly)
    fewer = {**base, "transfers": 0, "minutes": 46}
    assert otp.score(fewer, {"transfer_penalty": 15}) < otp.score(base, {"transfer_penalty": 15})


def test_otp_down_is_reported(monkeypatch, conn):
    def down(*a, **k):
        raise otp.OTPUnavailable("not reachable")
    monkeypatch.setattr(otp, "query_itineraries", down)
    r = run(conn, "Harvard Yard", "Mass General Hospital", [])
    assert not r["ok"] and r["guardrails"] == ["planner_unavailable"]


# ---------- Checker on every leg ----------

def test_no_alerts_is_safe(otp_fake):
    assert check_door_trip(best("Union Square, Somerville", "Boston Convention Center"), [])["safe"]


def test_elevator_at_exit_platform_blocks(otp_fake):
    t = best("Harvard Yard", "Mass General Hospital")
    exit_ = transit(t)[-1]["to"]
    c = check_door_trip(t, [elevator("e1", [exit_["station_id"], exit_["stop_id"]])])
    assert not c["safe"]
    p = c["blocking"][0]
    assert (p["role"], p["basis"], p["fault_routes"]) == ("exit", "platform", ["Red"])


def test_elevator_for_other_platform_does_not_block(otp_fake):
    t = best("Harvard Yard", "Mass General Hospital")
    exit_ = transit(t)[-1]["to"]
    c = check_door_trip(t, [elevator("e1", [exit_["station_id"], "99999"])])
    assert c["safe"] and c["warnings"][0]["basis"] == "platform"


def test_escalator_never_blocks(otp_fake):
    t = best("Harvard Yard", "Mass General Hospital")
    exit_ = transit(t)[-1]["to"]
    c = check_door_trip(t, [elevator("s1", [exit_["station_id"], exit_["stop_id"]], effect="ESCALATOR_CLOSURE")])
    assert c["safe"] and c["warnings"]


def test_vague_station_alert_uses_text(otp_fake):
    t = best("Harvard Yard", "Mass General Hospital")
    sid = transit(t)[-1]["to"]["station_id"]
    unclear = elevator("v1", [sid], header="Charles/MGH Elevator 999 is unavailable")
    other_line = elevator("v2", [sid], header="Charles/MGH Elevator 998 (Commuter Rail platform) is unavailable")
    assert not check_door_trip(t, [unclear])["safe"]                 # unclear -> safe default: block
    assert check_door_trip(t, [other_line])["safe"]


def test_moved_bus_stop_blocks_boarding(otp_fake):
    t = best("Fields Corner", "Boston Medical Center")
    bus = transit(t)[0]
    c = check_door_trip(t, [service("m1", "STOP_MOVE", bus["route_id"], [bus["from"]["stop_id"]])])
    assert not c["safe"] and c["blocking"][0]["role"] == "board"
    assert "may not be accessible" in c["blocking"][0]["note"]


def test_detour_elsewhere_is_only_a_warning(otp_fake):
    t = best("Fields Corner", "Boston Medical Center")
    bus = transit(t)[0]
    c = check_door_trip(t, [service("d1", "DETOUR", bus["route_id"])])
    assert c["safe"] and c["warnings"][0]["role"] == "detour"


def test_suspended_stretch_blocks_only_where_ridden(otp_fake):
    t = best("Revere Beach", "Downtown Crossing")
    leg = next(l for l in transit(t) if len(l["stops"]) >= 3)
    on = [s["station_id"] for s in leg["stops"][:2]]
    assert not check_door_trip(t, [service("s1", "SUSPENSION", leg["route_id"], on)])["safe"]
    assert check_door_trip(t, [service("s2", "SUSPENSION", leg["route_id"], ["place-nowhere", "place-other"])])["safe"]


def test_cancellation_of_another_trip_is_ignored(otp_fake):
    t = best("Harvard Yard", "Mass General Hospital")
    leg = transit(t)[0]
    assert check_door_trip(t, [service("c1", "CANCELLATION", "Red", trip="other-trip")])["safe"]
    assert not check_door_trip(t, [service("c2", "CANCELLATION", "Red", trip=leg["trip_id"])])["safe"]


def test_long_roll_is_a_warning(otp_fake):
    t = best("Harvard Yard", "Mass General Hospital")
    c = check_door_trip(t, [], prefs={"max_roll_min": 2})
    assert c["safe"] and any(w["kind"] == "rolling" for w in c["warnings"])


def test_transfer_uses_direct_platform_elevator(otp_fake):
    t = best("Back Bay station", "Harvard station")
    stops = [p["stop_id"] for p in checker._points(t) if p["role"] == "transfer"]
    assert stops and transit(t)[0]["to"]["station_id"] == "place-dwnxg"
    out = elevator("x869", ["place-dwnxg", stops[-1]], header="Downtown Crossing Elevator 869 (Alewife platform to Summer Street Concourse) is unavailable")
    c = check_door_trip(t, [out])
    assert c["safe"] and "platform to Alewife platform" in c["warnings"][0]["note"]
    links = [elevator(f"x{f}", ["place-dwnxg"], facility=f) for f in ("998", "999")]
    assert not check_door_trip(t, [out] + links)["safe"]


# ---------- Replanner ----------

def test_clear_trip_needs_no_llm(otp_fake, llm, conn):
    r = run(conn, "Union Square, Somerville", "Boston Convention Center", [])
    assert r["ok"] and not r["changed"] and r["trip"] is r["usual"]
    assert llm.prompts == []


def test_blocked_exit_is_rerouted_without_that_line(otp_fake, llm, conn):
    t = best("Harvard Yard", "Mass General Hospital")
    exit_ = transit(t)[-1]["to"]
    alerts = [elevator("e1", [exit_["station_id"], exit_["stop_id"]])]
    r = run(conn, "Harvard Yard", "Mass General Hospital", alerts)
    assert r["changed"] and r["problems"][0]["station_id"] == exit_["station_id"]
    if r["trip"]:
        assert check_door_trip(r["trip"], alerts)["safe"]
    assert any(k.endswith("|Red") for k in otp_fake)                   # follow-up search without Red


def test_real_alerts_snapshot(otp_fake, llm, conn):
    """The alerts live when the trips were recorded: every recommended trip passes the Checker."""
    alerts = OTP_FIXTURE["alerts"]
    for o, d in [("Wonderland station", "Back Bay station"), ("Fields Corner", "Boston Medical Center"),
                 ("Back Bay station", "Harvard station")]:
        r = run(conn, o, d, alerts, explain=False)
        assert r["ok"]
        if r["trip"]:
            assert check_door_trip(r["trip"], alerts)["safe"], (o, d)


def test_mbta_down_never_claims_safe(otp_fake, conn, monkeypatch):
    def down(key):
        raise RuntimeError("MBTA API down")
    monkeypatch.setattr(checker, "get_live_alerts", down)
    r = d2d.plan_door_to_door(conn, place("Harvard Yard"), place("Mass General Hospital"), "key")
    assert not r["ok"] and r["guardrails"] == ["mbta_unavailable"]


def test_avoided_station_is_skipped(otp_fake, conn):
    r = run(conn, "Back Bay station", "Harvard station", [], avoid_ids=["place-dwnxg"], explain=False)
    assert "place-dwnxg" not in otp.stations_used(r["trip"]) or r["trip"].get("uses_avoided")


def test_prompt_lists_changes_and_pass_throughs(otp_fake, llm, conn):
    t = best("Harvard Yard", "Mass General Hospital")
    exit_ = transit(t)[-1]["to"]
    run(conn, "Harvard Yard", "Mass General Hospital", [elevator("e1", [exit_["station_id"], exit_["stop_id"]])])
    assert "Change at:" in llm.prompts[0] and "Stay on board through (NOT transfers)" in llm.prompts[0]


@pytest.mark.parametrize("answer, verdict, guardrail", [
    ("No citation here", None, "citation_check_failed"),
    (None, json.dumps({"supported": False, "unsupported_claims": ["Take the 99 bus"]}), "claim_check_failed"),
    (None, "looks fine", "claim_check_unavailable"),
])
def test_guardrails_fall_back_to_data(otp_fake, llm, conn, answer, verdict, guardrail):
    if answer:
        llm.answer = answer
    if verdict:
        llm.verdict = verdict
    t = best("Harvard Yard", "Mass General Hospital")
    exit_ = transit(t)[-1]["to"]
    r = run(conn, "Harvard Yard", "Mass General Hospital", [elevator("e1", [exit_["station_id"], exit_["stop_id"]])])
    assert guardrail in r["guardrails"] and r["explanation"].startswith("Problems on the usual trip")


def test_supported_answer_is_kept(otp_fake, llm, conn):
    t = best("Harvard Yard", "Mass General Hospital")
    exit_ = transit(t)[-1]["to"]
    r = run(conn, "Harvard Yard", "Mass General Hospital", [elevator("e1", [exit_["station_id"], exit_["stop_id"]])])
    assert r["explanation"] == llm.answer and len(llm.prompts) == 2


# ---------- Monitor ----------

@pytest.fixture
def same_times(monkeypatch):
    monkeypatch.setattr(otp, "refresh_leg", lambda leg: leg)
    monkeypatch.setattr(checker, "get_live_alerts", lambda key: [])


def _watch(conn, o, d):
    return monitor.start_door_trip(run(conn, o, d, [], explain=False))


def _before(trip):
    return datetime.fromisoformat(trip["departs"]) - timedelta(minutes=5)


def test_monitor_quiet_when_nothing_changes(otp_fake, same_times, conn):
    w = _watch(conn, "Back Bay station", "Harvard station")
    ev = monitor.check_door_watch(conn, w, "key", now=_before(w["trip"]))
    assert not ev["new_problems"] and ev["live_times"]


def test_monitor_switches_on_new_outage(otp_fake, same_times, conn):
    w = _watch(conn, "Back Bay station", "Harvard station")
    old = w["trip"]["key"]
    ev = monitor.check_door_watch(conn, w, "key", simulate=True, now=_before(w["trip"]))
    assert ev["new_problems"] and ev["new_problems"][0]["station_id"] == "place-dwnxg"
    if ev["switched_to"]:
        assert w["trip"]["key"] != old and "place-dwnxg" not in otp.stations_used(w["trip"])


def test_monitor_spots_missed_connection(otp_fake, same_times, conn):
    w = _watch(conn, "Back Bay station", "Harvard station")
    legs = w["trip"]["legs"]
    first, second = transit(w["trip"])
    late = (datetime.fromisoformat(second["start"]) + timedelta(minutes=1)).isoformat()
    first["end"] = late                                   # first train now arrives after the second leaves
    risks = monitor.connection_risks(w["trip"])
    assert risks and risks[0]["effect"] == "MISSED_CONNECTION"
    assert legs                                           # legs edited in place


def test_monitor_reports_cancelled_trip(otp_fake, conn, monkeypatch):
    monkeypatch.setattr(checker, "get_live_alerts", lambda key: [])
    monkeypatch.setattr(otp, "refresh_leg", lambda leg: None)
    w = _watch(conn, "Harvard Yard", "Mass General Hospital")
    ev = monitor.check_door_watch(conn, w, "key", now=_before(w["trip"]))
    assert any(p["effect"] == "TRIP_NOT_FOUND" for p in ev["new_problems"])


def test_replan_starts_from_next_leg_once_travelling(otp_fake, same_times, conn):
    w = _watch(conn, "Back Bay station", "Harvard station")
    second = transit(w["trip"])[1]
    mid = datetime.fromisoformat(second["start"]) - timedelta(minutes=1)
    start = monitor._restart_point(w, mid, None)
    assert start["name"] != "Back Bay station"
    assert monitor._restart_point(w, mid, (42.36, -71.06))["name"] == "Your location"


# ---------- Places and the request parser ----------

def test_station_names_and_coordinates_resolve_offline():
    assert places.resolve_place("Harvard")["source"] == "station"
    ll = places.resolve_place("42.3601, -71.0589")
    assert ll["ok"] and ll["source"] == "coordinates"
    assert not places.resolve_place("40.7128, -74.0060")["ok"]           # New York: outside the area


def test_current_location():
    assert places.resolve_place(CURRENT, current=(42.35, -71.06))["name"] == "Your location"
    assert not places.resolve_place(CURRENT)["ok"]


def test_addresses_use_the_geocoder(monkeypatch):
    sent = []

    def fake(text):
        sent.append(text)
        return (("Fenway Park, 4, Jersey Street, Fenway, Boston, Massachusetts, 02215", 42.3467, -71.0972),)
    monkeypatch.setattr(places, "_nominatim", fake)
    p = places.resolve_place("Fenway Park")
    assert p["ok"] and p["name"] == "Fenway Park, 4, Jersey Street" and sent == ["Fenway Park"]


def test_geocoder_down_is_explained(monkeypatch):
    import requests

    def down(text):
        raise requests.ConnectionError("offline")
    monkeypatch.setattr(places, "_nominatim", down)
    assert "unavailable" in places.resolve_place("1 Main St")["reason"]


def test_keyword_trip_parser(graph):
    names = sorted(set(graph[1].values()))
    p = keyword_trip_parse("from my location to Fenway Park, avoid Kenmore, 5 minutes at a time", names)
    assert (p["origin"], p["destination"], p["avoid"], p["max_roll_minutes"]) == \
        (CURRENT, "Fenway Park", ["Kenmore"], 5.0)


# ---------- Live (optional) ----------

@pytest.mark.skipif(os.getenv("TW_OTP") != "1", reason="needs the OTP server; set TW_OTP=1")
def test_live_otp_plans_a_trip():
    r = otp.plan_options({"name": "a", "lat": 42.3744, "lon": -71.1169}, {"name": "b", "lat": 42.3632, "lon": -71.0686})
    assert r["ok"] and r["options"][0]["legs"]
