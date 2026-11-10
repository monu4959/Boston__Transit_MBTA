"""Offline test setup: the agents run on a snapshot of the real network and real alerts
(tests/fixtures, made by tests/make_fixtures.py). No Snowflake, MBTA or LLM calls."""
import copy
import json
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
FIXTURES = os.path.join(ROOT, "tests", "fixtures")

import agents.planner as planner
import agents.checker as checker

with open(os.path.join(FIXTURES, "network.json"), encoding="utf-8") as f:
    NETWORK = {k: pd.DataFrame(v) for k, v in json.load(f).items()}
with open(os.path.join(FIXTURES, "alerts.json"), encoding="utf-8") as f:
    REAL_ALERTS = json.load(f)["alerts"]


def fake_query_df(conn, sql, params=None):
    for table, key in (("ROUTE_STOPS", "route_stops"), ("PLATFORMS", "platforms"),
                       ("FACILITIES", "facilities"), ("STATIONS", "stations")):
        if table in sql:
            return NETWORK[key].copy()
    raise AssertionError("unexpected SQL in test: " + sql[:60])


class OfflineConn:
    """Stands in for Snowflake. Anything beyond the Planner's reads (logging) fails,
    which exercises the logger's never-raise path."""
    def cursor(self):
        raise RuntimeError("offline test connection")


@pytest.fixture(scope="session", autouse=True)
def graph():
    planner.query_df = fake_query_df
    planner._cache = planner.build_graph(OfflineConn())
    return planner._cache


@pytest.fixture
def conn():
    return OfflineConn()


@pytest.fixture
def alerts():
    return copy.deepcopy(REAL_ALERTS)


@pytest.fixture
def live(monkeypatch, alerts):
    """Make every 'live' alert fetch return the real snapshot, and count the fetches."""
    calls = {"n": 0}

    def fetch(key):
        calls["n"] += 1
        return copy.deepcopy(alerts)
    monkeypatch.setattr(checker, "get_live_alerts", fetch)
    return calls


def find(alerts, alert_id):
    return next(a for a in alerts if a["id"] == alert_id)
