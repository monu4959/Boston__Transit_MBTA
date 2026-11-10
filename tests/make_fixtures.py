"""Snapshot the network tables and today's real MBTA alerts into tests/fixtures/.

The tests run offline against these files, so they test the agents on real alert data
(a Green Line suspension, platform-specific elevators, a station closure) instead of
alerts written to fit the code. Re-run to refresh:  py -3.12 tests/make_fixtures.py
"""
import json
import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agents.db import get_connection, query_df
from agents.checker import (get_live_alerts, ACCESS_EFFECTS, SERVICE_EFFECTS, CLOSURE_EFFECTS)

OUT = os.path.join(ROOT, "tests", "fixtures")
ENTITY_KEYS = ("stop", "route", "route_type", "direction_id", "facility", "activities")


def records(df):
    return json.loads(df.to_json(orient="records"))


def main():
    os.makedirs(OUT, exist_ok=True)
    conn = get_connection()
    try:
        network = {
            "route_stops": records(query_df(conn, """
                SELECT rs.ROUTE_ID, rs.STOP_SEQUENCE, rs.STATION_ID, rs.STATION_NAME
                FROM ROUTE_STOPS rs JOIN ROUTES r ON r.ROUTE_ID = rs.ROUTE_ID
                WHERE r.ROUTE_TYPE IN (0, 1) ORDER BY rs.ROUTE_ID, rs.STOP_SEQUENCE""")),
            "stations": records(query_df(conn, """
                SELECT STATION_ID, NAME, LATITUDE, LONGITUDE, WHEELCHAIR_BOARDING FROM STATIONS""")),
            "platforms": records(query_df(conn, """
                SELECT STATION_ID, ROUTE_ID, DIRECTION_ID, STOP_ID, PLATFORM_NAME FROM PLATFORMS""")),
            "facilities": records(query_df(conn, """
                SELECT FACILITY_ID, STATION_ID, LONG_NAME, TYPE FROM FACILITIES WHERE TYPE = 'ELEVATOR'""")),
        }
    finally:
        conn.close()
    subway = {r["STATION_ID"] for r in network["route_stops"]}
    network["stations"] = [s for s in network["stations"] if s["STATION_ID"] in subway]
    network["facilities"] = [f for f in network["facilities"] if f["STATION_ID"] in subway]

    keep = ACCESS_EFFECTS | SERVICE_EFFECTS | CLOSURE_EFFECTS
    alerts = []
    for a in get_live_alerts(os.getenv("MBTA_KEY") or os.getenv("MBTA_API_KEY")):
        at = a["attributes"]
        ents = at.get("informed_entity", [])
        if at["effect"] in keep and any(e.get("stop") in subway for e in ents):
            alerts.append({"id": a["id"], "attributes": {
                "effect": at["effect"], "header": at["header"],
                "informed_entity": [{k: e[k] for k in ENTITY_KEYS if k in e} for e in ents]}})

    with open(os.path.join(OUT, "network.json"), "w", encoding="utf-8") as f:
        json.dump(network, f, separators=(",", ":"))
    with open(os.path.join(OUT, "alerts.json"), "w", encoding="utf-8") as f:
        json.dump({"captured": date.today().isoformat(), "alerts": alerts}, f, indent=1)
    print(f"network: {len(network['route_stops'])} route stops, {len(network['stations'])} stations, "
          f"{len(network['platforms'])} platforms, {len(network['facilities'])} elevators")
    print(f"alerts: {len(alerts)} ({', '.join(sorted({a['attributes']['effect'] for a in alerts}))})")


if __name__ == "__main__":
    main()
