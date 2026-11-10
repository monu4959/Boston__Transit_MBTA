"""Build (or rebuild) TRANSITWISE_DB from the MBTA API and the policy PDFs.

Prerequisite: run sql/01_setup.sql once in a Snowsight worksheet.
Run from the repo root:  py -3.12 pipeline/build_db.py
Safe to re-run: reference tables are overwritten and the RAG index is rebuilt.
ALERTS_HISTORY is only appended to (one new snapshot per run).
"""
import glob
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pandas as pd
import requests
from snowflake.connector.pandas_tools import write_pandas

from agents.db import get_connection
from pipeline.load_alerts import clean_mbta_key, load_alerts_snapshot

MBTA = "https://api-v3.mbta.com"
ACCESS_LABELS = {0: "unknown", 1: "accessible", 2: "not accessible"}


def mbta(path, **params):
    key = clean_mbta_key(os.getenv("MBTA_KEY") or os.getenv("MBTA_API_KEY"))
    r = requests.get(MBTA + path, params=params, headers={"x-api-key": key} if key else {}, timeout=30)
    r.raise_for_status()
    return r.json()


def write(conn, df, table):
    """Replace a RAW reference table with this DataFrame."""
    df = df.copy()
    df["loaded_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
    df.columns = [c.upper() for c in df.columns]
    ok, _, n, _ = write_pandas(conn, df, table, database="TRANSITWISE_DB", schema="RAW",
                               auto_create_table=True, overwrite=True, use_logical_type=True)
    if not ok:
        raise RuntimeError(f"Loading {table} failed")
    print(f"  RAW.{table:<12} {n:>5} rows")


# ---------- Reference tables (moved here from 01_mbta_test.ipynb) ----------

def load_routes():
    """Light rail (0), subway (1) and commuter rail (2) routes."""
    return pd.DataFrame([{
        "route_id": r["id"],
        "long_name": r["attributes"]["long_name"],
        "short_name": r["attributes"]["short_name"],
        "route_type": r["attributes"]["type"],
        "description": r["attributes"]["description"],
        "color": r["attributes"]["color"],
        "direction_names": ", ".join(r["attributes"]["direction_names"] or []),
    } for r in mbta("/routes", **{"filter[type]": "0,1,2"})["data"]])


def load_stations():
    """One row per parent station (platforms and entrances are collapsed into it)."""
    data = mbta("/stops", **{"filter[route_type]": "0,1,2", "include": "parent_station"})
    parents = {p["id"]: p for p in data.get("included", []) if p["type"] == "stop"}
    for s in data["data"]:
        if not s["relationships"]["parent_station"]["data"]:
            parents.setdefault(s["id"], s)      # stops that are already a station
    return pd.DataFrame([{
        "station_id": s["id"],
        "name": s["attributes"]["name"],
        "municipality": s["attributes"]["municipality"],
        "address": s["attributes"]["address"],
        "latitude": s["attributes"]["latitude"],
        "longitude": s["attributes"]["longitude"],
        "wheelchair_boarding": s["attributes"]["wheelchair_boarding"],
        "wheelchair_status": ACCESS_LABELS.get(s["attributes"]["wheelchair_boarding"], "unknown"),
    } for s in parents.values()])


def load_route_stops(routes):
    """Stations on each route, in order (direction 0)."""
    rows = []
    for route_id in routes["route_id"]:
        stops = mbta("/stops", **{"filter[route]": route_id, "filter[direction_id]": "0"})["data"]
        rows += [{"route_id": route_id, "stop_sequence": seq, "station_id": s["id"],
                  "station_name": s["attributes"]["name"]} for seq, s in enumerate(stops, start=1)]
    return pd.DataFrame(rows)


def load_platforms(routes):
    """Which platform (child stop) a rider uses at each station, per line and direction.
    Taken from the stop list of each route pattern's representative trip."""
    subway = routes.loc[routes["route_type"].isin([0, 1]), "route_id"]
    data = mbta("/route_patterns", **{"filter[route]": ",".join(subway),
                                      "include": "representative_trip.stops"})
    trips = {x["id"]: x for x in data.get("included", []) if x["type"] == "trip"}
    stops = {x["id"]: x for x in data.get("included", []) if x["type"] == "stop"}
    rows = set()
    for pattern in data["data"]:
        if pattern["attributes"]["typicality"] not in (1, 2):   # skip diversions and shuttles
            continue
        route = pattern["relationships"]["route"]["data"]["id"]
        direction = pattern["attributes"]["direction_id"]
        trip = trips.get((pattern["relationships"]["representative_trip"]["data"] or {}).get("id"))
        for ref in (trip or {}).get("relationships", {}).get("stops", {}).get("data", []):
            stop = stops.get(ref["id"])
            parent = ((stop or {}).get("relationships", {}).get("parent_station", {}).get("data") or {}).get("id")
            if parent:
                rows.add((parent, route, direction, stop["id"], stop["attributes"]["platform_name"]))
    return pd.DataFrame(sorted(rows), columns=["station_id", "route_id", "direction_id",
                                               "stop_id", "platform_name"])


def load_facilities(stations):
    """Elevators, escalators and lifts at the stations above."""
    data = mbta("/facilities", **{"filter[type]": "ELEVATOR,ESCALATOR,PORTABLE_BOARDING_LIFT,ELEVATED_SUBPLATFORM"})
    df = pd.DataFrame([{
        "facility_id": f["id"],
        "type": f["attributes"]["type"],
        "short_name": f["attributes"]["short_name"],
        "long_name": f["attributes"]["long_name"],
        "station_id": (f["relationships"]["stop"]["data"] or {}).get("id"),
    } for f in data["data"]])
    return df[df["station_id"].isin(stations["station_id"])].reset_index(drop=True)


# ---------- RAG index (moved here from rag_setup.ipynb) ----------

def chunk_text(text, size=1000, overlap=200):
    """Split text into ~size-character chunks without cutting words in half."""
    words = text.split()
    chunks, start = [], 0
    while start < len(words):
        length, end = 0, start
        while end < len(words) and length + len(words[end]) + 1 <= size:
            length += len(words[end]) + 1
            end += 1
        end = max(end, start + 1)
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        # step back about `overlap` characters, measured in whole words
        back, back_len = end, 0
        while back > start + 1 and back_len < overlap:
            back -= 1
            back_len += len(words[back]) + 1
        start = back
    return chunks


# Browser chrome printed into the saved web pages: print headers, menus and footer links.
PAGE_CHROME = [
    r"^\d{1,2}/\d{1,2}/\d{2}, \d{1,2}:\d{2} [AP]M ",                  # print header with date
    r"^https?://\S+ \d+/\d+$",                                         # print footer URL + page
    r"^(Menu|Massachusetts Bay|›|⌄|English)$",
    r"^Transportation Authority Search for routes",
    r"^An official website of the City of Boston",
    r"^© Massachusetts Bay Transportation Authority",
    r"^Privacy Policy\s+Terms of Use$",
    r"^(Customer Support|Send Us Feedback|Lost & Found|Request Public Records|Language Services|"
    r"Get to Know Us|Leadership|History|Financials|Public Meetings|Media Relations|"
    r"Policies & Civil Rights|Safety|Performance|Work With Us|Careers|Institutional Sales|"
    r"Business Opportunities|Engineering Design Standards|Developers)$",
    r"(?i:\((https?:|/|mailto:|tel:))|%3A",                              # link-only lines
    r"^(PAGE SECTIONS|1 CITY HALL SQUARE|ROOM \d+|BOSTON, MA \d{5}-\d{4}|CONTACT INFORMATION|"
    r"Still have questions\? Contact:|REETS-CABINET-CONTACT-INFORMATION\)|DIGITAL\)|ACCOMMODATIONS\)|"
    r"VULNERABILITY DISCLOSURE|PROVIDE YOUR FEEDBACK|SOURCE_ENTITY_TYPE=.*)$",
]
_CHROME = re.compile("|".join(f"(?:{p})" for p in PAGE_CHROME))


def clean_page(text):
    """Drop page chrome lines so chunks only hold the document's own text."""
    text = unicodedata.normalize("NFKC", text)                       # "ﬁ" -> "fi"
    text = "".join(c for c in text if not 0xE000 <= ord(c) <= 0xF8FF)  # icon-font glyphs
    return "\n".join(line for line in text.splitlines() if not _CHROME.search(line.strip()))


def load_policy_chunks(conn):
    from pypdf import PdfReader
    from agents.retriever import embed

    docs = []
    for path in sorted(glob.glob(os.path.join(ROOT, "policy_docs", "*.pdf"))):
        text = " ".join(clean_page(page.extract_text() or "") for page in PdfReader(path).pages)
        for i, ch in enumerate(chunk_text(" ".join(text.split()))):
            docs.append((os.path.basename(path), i, ch))

    cur = conn.cursor()
    cur.execute("TRUNCATE TABLE TRANSITWISE_DB.RAG.POLICY_CHUNKS")
    for source, n, ch in docs:
        cur.execute("""
            INSERT INTO TRANSITWISE_DB.RAG.POLICY_CHUNKS
            SELECT %s, %s, %s, PARSE_JSON(%s)::ARRAY::VECTOR(FLOAT, 384)
        """, (source, n, ch, json.dumps(embed(ch))))
    print(f"  RAG.POLICY_CHUNKS  {len(docs):>5} rows from {len({d[0] for d in docs})} PDFs")


def main():
    conn = get_connection()
    try:
        print("Reference tables (MBTA API):")
        routes = load_routes()
        stations = load_stations()
        write(conn, routes, "ROUTES")
        write(conn, stations, "STATIONS")
        write(conn, load_route_stops(routes), "ROUTE_STOPS")
        write(conn, load_platforms(routes), "PLATFORMS")
        write(conn, load_facilities(stations), "FACILITIES")

        print("Alert snapshot:")
        print(f"  RAW.ALERTS_HISTORY {load_alerts_snapshot(conn):>5} rows appended")

        print("Views (sql/02_clean_views.sql):")
        with open(os.path.join(ROOT, "sql", "02_clean_views.sql"), encoding="utf-8") as f:
            conn.execute_string(f.read())
        print("  CLEAN.CURRENT_ELEVATOR_OUTAGES created")

        print("RAG index (policy_docs/*.pdf):")
        load_policy_chunks(conn)
    finally:
        conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
