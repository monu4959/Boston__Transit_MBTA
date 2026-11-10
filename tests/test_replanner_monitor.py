"""Replanner, guardrails and Monitor on real alerts. LLM and retrieval are stubbed."""
import json

import pytest

import agents.replanner as rp
import agents.monitor as monitor
from agents.checker import checker_agent
from agents.planner import planner_agent

POLICY = [{"source": "access_in_motion.pdf", "chunk": "If an elevator is out, ask staff or use a "
           "nearby accessible station. Shuttle buses are accessible.", "score": 0.7,
           "vector_score": 0.7, "keyword_boost": 0.0}]


class FakeLLM:
    """First call writes the answer, later calls are the claim checker."""
    def __init__(self, answer="Take the recommended route. [access_in_motion.pdf]",
                 verdict='{"supported": true, "unsupported_claims": []}'):
        self.answer, self.verdict, self.prompts = answer, verdict, []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return self.answer if len(self.prompts) == 1 else self.verdict


@pytest.fixture
def llm(monkeypatch, live):
    fake = FakeLLM()
    monkeypatch.setattr(rp, "ask_llm", fake)
    monkeypatch.setattr(rp, "search_policies", lambda conn, q, k=4: POLICY)
    return fake


def run(conn, o, d, **kw):
    return rp.replanner_agent(conn, o, d, "key", log_source="test", **kw)


# ---------- Issue 2: suspensions ----------

def test_suspended_route_is_rerouted(conn, llm):
    r = run(conn, "Wonderland", "Park Street")
    assert r["changed"]
    assert any(p["kind"] == "service" for p in r["problems"])
    if r["new_plan"]:
        assert checker_agent(r["new_plan"], None, alerts=rp.checker_module.get_live_alerts(None))["safe"]


def test_clear_route_stays_clear(conn, llm, live):
    r = run(conn, "Harvard", "Back Bay")
    assert r["ok"] and not r["changed"]          # elevator 869 serves the other platform
    assert live["n"] == 1
    assert llm.prompts == []


# ---------- Issue 7: origin/destination outages stop at once ----------

def test_destination_outage_stops_without_retrying(conn, llm, live, monkeypatch):
    calls = {"plan": 0}
    real = rp.planner_agent

    def counting(*a, **k):
        calls["plan"] += 1
        return real(*a, **k)
    monkeypatch.setattr(rp, "planner_agent", counting)
    r = run(conn, "Airport", "Revere Beach")
    assert r["new_plan"] is None
    assert calls["plan"] == 2                    # usual route + one replan that can't exit there
    assert live["n"] == 1                        # alerts fetched once
    assert "exit at Revere Beach" in r["stop_reason"]


def test_fallback_explains_destination_outage(conn, llm):
    llm.answer = "No citation here"              # forces the data-only fallback
    r = run(conn, "Airport", "Revere Beach")
    assert "citation_check_failed" in r["guardrails"]
    assert "leave the train at Revere Beach" in r["explanation"]


# ---------- Issue 4: prompt and claim check ----------

def test_prompt_separates_transfers_from_pass_throughs(conn, llm):
    run(conn, "Wonderland", "Park Street")
    prompt = llm.prompts[0]
    assert "Change trains at: Government Center" in prompt
    assert "Stay on the train through (NOT transfers):" in prompt
    assert "only source of" in prompt.lower().replace("\n", " ") or "ONLY source" in prompt


def test_unsupported_claim_falls_back(conn, llm):
    llm.verdict = json.dumps({"supported": False,
                              "unsupported_claims": ["It says to transfer at Haymarket"]})
    r = run(conn, "Wonderland", "Park Street")
    assert "claim_check_failed" in r["guardrails"]
    assert r["claim_issues"] == ["It says to transfer at Haymarket"]
    assert r["explanation"].startswith("Problems on your usual route")


def test_unreadable_claim_check_falls_back(conn, llm):
    llm.verdict = "looks fine to me"
    r = run(conn, "Wonderland", "Park Street")
    assert "claim_check_unavailable" in r["guardrails"]


def test_supported_answer_is_kept(conn, llm):
    r = run(conn, "Wonderland", "Park Street")
    assert r["guardrails"] == []
    assert r["explanation"] == llm.answer
    assert len(llm.prompts) == 2                 # answer + claim check


def test_mbta_down_never_claims_safe(conn, monkeypatch):
    def down(key):
        raise RuntimeError("MBTA API down")
    monkeypatch.setattr(rp.checker_module, "get_live_alerts", down)
    r = run(conn, "Harvard", "Back Bay")
    assert not r["ok"] and r["guardrails"] == ["mbta_unavailable"]


# ---------- Issue 6: avoid means avoid ----------

def test_avoided_station_is_not_on_the_route(conn, llm):
    r = run(conn, "Back Bay", "Davis", avoid_names=["Downtown Crossing"])
    plan = r.get("plan") or r.get("new_plan") or r["original_plan"]
    assert "place-dwnxg" not in plan["path"] or plan.get("passes_through_avoided")


# ---------- Issue 5: the Monitor watches the route being ridden ----------

def test_monitor_watches_the_given_route(conn, live):
    detour = planner_agent(None, "Harvard", "Back Bay", avoid=["place-dwnxg"])
    trip = monitor.start_trip(conn, "Harvard", "Back Bay", "key", plan=detour)
    assert trip["plan"]["path"] == detour["path"]


def test_monitor_keeps_preferences(conn, live, monkeypatch):
    seen = {}

    def fake_replanner(conn, o, d, key, **kw):
        seen.update(kw)
        return {"ok": True, "changed": True, "new_plan": None}
    monkeypatch.setattr(monitor, "replanner_agent", fake_replanner)
    trip = monitor.start_trip(conn, "Back Bay", "Davis", "key", transfer_penalty=15.0,
                              avoid_names=["Park Street"])
    monitor.check_trip(conn, trip, "key", simulate=True)
    assert seen["transfer_penalty"] == 15.0 and seen["avoid_names"] == ["Park Street"]


def test_monitor_switches_to_the_replanned_route(conn, llm, alerts):
    # Without this week's Green Line suspension there is a detour (via Park Street and Haymarket)
    alerts[:] = [a for a in alerts if a["attributes"]["effect"] != "SUSPENSION"]
    trip = monitor.start_trip(conn, "Harvard", "Back Bay", "key")
    assert trip["plan"]["transfer_ids"] == ["place-dwnxg"]
    event = monitor.check_trip(conn, trip, "key", simulate=True)   # demo outage at the transfer
    assert event["new_problems"] and event["switched_to"]
    assert "place-dwnxg" not in trip["plan"]["transfer_ids"]
    # the next real check watches the new route and finds nothing new
    event = monitor.check_trip(conn, trip, "key")
    assert not event["new_problems"]


def test_monitor_reports_no_detour_during_suspension(conn, llm):
    """With the Green Line suspended, Harvard -> Back Bay has no detour around Downtown Crossing."""
    trip = monitor.start_trip(conn, "Harvard", "Back Bay", "key")
    event = monitor.check_trip(conn, trip, "key", simulate=True)
    assert event["new_problems"] and event["switched_to"] is None
    assert event["replan"]["new_plan"] is None
