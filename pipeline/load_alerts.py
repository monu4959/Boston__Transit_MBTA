"""Append one snapshot of all current MBTA alerts to RAW.ALERTS_HISTORY.

Runs every 30 minutes on GitHub Actions (.github/workflows/load_alerts.yml).
Run by hand from the repo root:  python pipeline/load_alerts.py
"""
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import requests
from snowflake.connector.pandas_tools import write_pandas

from agents.db import get_connection


def ids(entities, key):
    return ",".join(sorted({e[key] for e in entities if e.get(key)}))


def clean_mbta_key(value):
    """MBTA keys are 32 hex characters. Pull the key out of however it was pasted
    (extra lines, quotes, "MBTA_KEY=" prefix). None means call the API without a key,
    which works at a lower rate limit."""
    if not value or not value.strip():
        return None
    m = re.search(r"(?<![0-9a-fA-F])[0-9a-fA-F]{32}(?![0-9a-fA-F])", value)
    if not m:
        print("Warning: MBTA_API_KEY is not a 32-character key; calling the MBTA API without it.")
        return None
    return m.group(0)


def fetch_alerts(mbta_key):
    """Extract + transform: every current alert, flattened into one row each."""
    resp = requests.get(
        "https://api-v3.mbta.com/alerts",
        params={"filter[activity]": "ALL"},
        headers={"x-api-key": mbta_key} if mbta_key else {},
        timeout=30,
    )
    resp.raise_for_status()

    rows = []
    for a in resp.json()["data"]:
        attr = a["attributes"]
        ents = attr.get("informed_entity") or []
        periods = attr.get("active_period") or []
        rows.append({
            "id": a["id"],
            "effect": attr.get("effect"),
            "cause": attr.get("cause"),
            "severity": attr.get("severity"),
            "lifecycle": attr.get("lifecycle"),
            "header": attr.get("header"),
            "description": attr.get("description"),
            "facility_ids": ids(ents, "facility"),
            "station_ids": ids(ents, "stop"),
            "route_ids": ids(ents, "route"),
            "active_start": periods[0]["start"] if periods else None,
            "active_end": periods[-1]["end"] if periods else None,
            "updated_at": attr.get("updated_at"),
        })

    alerts = pd.DataFrame(rows)
    alerts["loaded_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
    alerts.columns = [c.upper() for c in alerts.columns]
    return alerts


def load_alerts_snapshot(conn, mbta_key=None):
    """Load: append this snapshot. Returns the number of rows written."""
    alerts = fetch_alerts(mbta_key or clean_mbta_key(os.getenv("MBTA_API_KEY") or os.getenv("MBTA_KEY")))
    success, _, rows_loaded, _ = write_pandas(
        conn, alerts, "ALERTS_HISTORY",
        database="TRANSITWISE_DB", schema="RAW",
        auto_create_table=True,
        use_logical_type=True,
    )
    if not success:
        raise RuntimeError("write_pandas reported failure")
    return rows_loaded


if __name__ == "__main__":
    # Which settings this run can see (names only, never values) -- helps debug CI secrets.
    names = ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_ROLE", "SNOWFLAKE_WAREHOUSE",
             "SNOWFLAKE_DATABASE", "SNOWFLAKE_PRIVATE_KEY", "SNOWFLAKE_PRIVATE_KEY_FILE", "MBTA_API_KEY"]
    print("Settings present:", ", ".join(n for n in names if (os.getenv(n) or "").strip()) or "none")
    conn = get_connection()
    try:
        n = load_alerts_snapshot(conn)
    finally:
        conn.close()
    print(f"{datetime.now():%Y-%m-%d %H:%M} | Loaded {n} alerts")
