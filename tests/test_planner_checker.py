"""Planner and Checker on the real network and real alerts captured on 2026-11-10."""
import itertools
import random

import agents.planner as planner
import agents.checker as checker
from agents.planner import planner_agent
from agents.checker import checker_agent, service_disruptions, serves_rider
from conftest import find

SUSPENSION = "1039322"     # Green Line: no trains North Station - Babcock/Cleveland Circle/Kenmore/Heath
DTX_869 = "1031518"        # Downtown Crossing Elevator 869 (Alewife platform to concourse)
FOREST_HILLS_841 = "1044436"   # Forest Hills Elevator 841 (Commuter Rail platform to lobby)
REVERE_885 = "1042373"     # Revere Beach Elevator 885 (Wonderland platform to lobby)
STATE_803 = "1031519"      # State Elevator 803 (MBTA lists all four platforms)
SYMPHONY = "1026060"       # Green Line E: Symphony closed


def check(o, d, alerts, **kw):
    plan = planner_agent(None, o, d, **kw)
    assert plan["ok"], plan
    return plan, checker_agent(plan, None, alerts=alerts)


def blocked_at(result):
    return {p["station"] for p in result["blocking"]}


# ---------- Planner ----------

def test_planner_routes_sampled_step_free_pairs(graph):
    G, names, accessible, lines_at = graph
    ok = [s for s in names if accessible.get(s)]
    pairs = random.Random(7).sample(list(itertools.permutations(ok, 2)), 300)
    for a, b in pairs:
        plan = planner_agent(None, names[a], names[b])
        assert plan["ok"], (names[a], names[b], plan)
        assert all(accessible[s] for s in plan["transfer_ids"]), "transfer at an inaccessible station"
        back = planner_agent(None, names[b], names[a])
        assert back["minutes"] == plan["minutes"]


def test_legs_carry_direction_and_platforms():
    plan = planner_agent(None, "Harvard", "Back Bay")
    assert [(l["line"], l["toward"]) for l in plan["legs"]] == [("Red", "Ashmont/Braintree"),
                                                                ("Orange", "Forest Hills")]
    assert plan["platform_use"]["place-dwnxg"] == {"in": ["70077"], "out": ["70020"]}


def test_red_line_branches_meet_at_jfk():
    plan = planner_agent(None, "Ashmont", "North Quincy")
    assert "JFK/UMass" in plan["stations"]


def test_exclude_avoids_station_completely():
    plan = planner_agent(None, "Back Bay", "Davis", exclude=["place-pktrm"])
    assert "place-pktrm" not in plan["path"] or plan.get("passes_through_avoided")
    # Alewife to Ashmont can't avoid Park Street: it may pass through, and says so
    plan = planner_agent(None, "Alewife", "Ashmont", exclude=["place-pktrm"])
    assert plan["ok"] and plan["passes_through_avoided"] == ["Park Street"]
    assert "place-pktrm" not in plan["transfer_ids"]


# ---------- Issue 2: service changes ----------

def test_suspension_is_flagged_on_usual_route(alerts):
    plan, result = check("Wonderland", "Park Street", alerts)
    service = [p for p in result["blocking"] if p["kind"] == "service"]
    assert service and service[0]["alert_id"] == SUSPENSION
    assert not result["safe"]


def test_planner_never_rides_a_suspended_segment(graph, alerts):
    G, names, accessible, lines_at = graph
    dis = service_disruptions(alerts)
    suspended = {(seg["route"], s) for seg in dis["segments"] for s in seg["stations"]}
    for o, d in [("Wonderland", "Park Street"), ("Kenmore", "Government Center"),
                 ("Harvard", "Copley"), ("North Station", "Hynes Convention Center")]:
        plan = planner_agent(None, o, d, disruptions=dis)
        if not plan["ok"]:
            continue
        for a, b, line in plan["ride_edges"]:
            assert not ((line, a) in suspended and (line, b) in suspended), (o, d, a, b, line)


def test_closed_station_blocks_boarding_and_transfers(alerts):
    closure = {"id": "c1", "attributes": {"effect": "STATION_CLOSURE",
               "header": "Downtown Crossing Orange Line platforms are closed",
               "informed_entity": [{"stop": "place-dwnxg", "route": "Orange"}]}}
    dis = service_disruptions([closure])
    plan = planner_agent(None, "Harvard", "Back Bay", disruptions=dis)
    assert "place-dwnxg" not in plan["transfer_ids"]
    usual = planner_agent(None, "Harvard", "Back Bay")
    result = checker_agent(usual, None, alerts=[closure])
    assert blocked_at(result) == {"Downtown Crossing"}


def test_real_symphony_closure_is_parsed(alerts):
    closed = service_disruptions(alerts)["closed"]
    assert {(c["station"], c["route"]) for c in closed} == {("place-symcl", "Green-E")}


# ---------- Issue 3: platform-aware elevator checks ----------

def test_alewife_platform_elevator_does_not_block_southbound_transfer(alerts):
    plan, result = check("Harvard", "Back Bay", alerts)
    assert result["safe"], result["blocking"]
    issue = next(p for p in result["all_issues"] if p["alert_id"] == DTX_869)
    assert issue["basis"] == "platform" and not issue["blocks"]


def test_northbound_transfer_uses_direct_platform_elevator(alerts):
    plan, result = check("Back Bay", "Davis", alerts)
    assert result["safe"]
    issue = next(p for p in result["all_issues"] if p["alert_id"] == DTX_869)
    assert "Oak Grove platform to Alewife platform" in issue["note"]


def test_northbound_transfer_blocked_when_platform_links_are_out_too(alerts):
    for fid in ("998", "999"):
        alerts.append({"id": f"x{fid}", "attributes": {
            "effect": "ELEVATOR_CLOSURE",
            "header": f"Downtown Crossing Elevator {fid} (Oak Grove platform to Alewife platform) is unavailable",
            "informed_entity": [{"stop": s, "facility": fid} for s in ("place-dwnxg", "70021", "70078")]}})
    plan, result = check("Back Bay", "Davis", alerts)
    assert "Downtown Crossing" in blocked_at(result)


def test_commuter_rail_elevator_does_not_block_orange_line_rider(alerts):
    plan, result = check("Ruggles", "Forest Hills", alerts)
    assert result["safe"]
    assert any(p["alert_id"] == FOREST_HILLS_841 for p in result["all_issues"])


def test_platform_elevator_blocks_only_its_direction(alerts):
    _, arriving = check("Airport", "Revere Beach", alerts)     # arrives on Wonderland-bound platform
    _, leaving = check("Revere Beach", "Airport", alerts)      # departs from Bowdoin-bound platform
    assert blocked_at(arriving) == {"Revere Beach"}
    assert leaving["safe"]


def test_elevator_listing_all_platforms_blocks_transfer(alerts):
    plan = planner_agent(None, "Wonderland", "Back Bay")
    assert "place-state" in plan["transfer_ids"]
    result = checker_agent(plan, None, alerts=[find(alerts, STATE_803)])
    assert blocked_at(result) == {"State"}


def test_station_name_is_not_read_as_a_line():
    text = "Forest Hills Elevator 841 (Commuter Rail platform to lobby) is unavailable"
    assert serves_rider(text, ["Orange"])                       # old behaviour: "forest hills" = Orange
    assert not serves_rider(text, ["Orange"], station_name="Forest Hills")


def test_escalators_and_pass_throughs_never_block(alerts):
    plan, result = check("Alewife", "Ashmont", alerts)
    assert result["safe"]
    assert {p["role"] for p in result["all_issues"] if p["effect"] == "ELEVATOR_CLOSURE"} <= {"pass-through"}


def test_unclear_alert_without_platforms_still_blocks():
    """Alerts that name only the station (no platforms) fall back to the safe default."""
    plan = planner_agent(None, "Harvard", "Back Bay")
    vague = {"id": "v", "attributes": {"effect": "ELEVATOR_CLOSURE",
             "header": "Downtown Crossing Elevator 999 is unavailable",
             "informed_entity": [{"stop": "place-dwnxg"}]}}
    assert blocked_at(checker_agent(plan, None, alerts=[vague])) == {"Downtown Crossing"}


def test_live_fetch_happens_once_when_alerts_are_passed(live):
    plan = planner_agent(None, "Harvard", "Back Bay")
    alerts = checker.get_live_alerts(None)
    for _ in range(3):
        checker_agent(plan, None, alerts=alerts)
    assert live["n"] == 1
