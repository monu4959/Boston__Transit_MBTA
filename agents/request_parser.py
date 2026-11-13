import difflib
import json
import re
import time

import numpy as np

from agents.llm import ask_llm
from agents.retriever import embed

THRESHOLD = 0.6            # paper's activation threshold T
K_EXAMPLES = 5             # paper retrieves the top-5 most similar examples
DEFAULT_TRANSFER_MIN = 5.0
FEWER_TRANSFERS_MIN = 15.0

# ---------- Node 2: map rider wording to official station names ----------
ALIASES = {
    "dtx": "downtown crossing", "downtown": "downtown crossing",
    "kendall": "kendall/mit", "mit": "kendall/mit", "mgh": "charles/mgh",
    "jfk": "jfk/umass", "umass boston": "jfk/umass",
    "logan": "airport", "logan airport": "airport",
    "park st": "park street", "gov center": "government center",
    "govt center": "government center", "tufts medical": "tufts medical center",
    "bc": "boston college", "mfa": "museum of fine arts",
    "northeastern": "northeastern university", "hynes": "hynes convention center",
    "harvard square": "harvard", "central square": "central",
    "porter square": "porter", "davis square": "davis",
    "td garden": "north station", "quincy": "quincy center",
}


def normalize_station(name, station_names):
    """Return the official station name for whatever the rider typed, or None."""
    if not name or not isinstance(name, str):
        return None
    by_lower = {s.lower(): s for s in station_names}
    key = re.sub(r"^the ", "", name.strip().lower())
    key = ALIASES.get(key, key)
    if key in by_lower:                                   # exact match first
        return by_lower[key]
    short = re.sub(r" (station|stop)$", "", key)          # then try without "station"
    short = ALIASES.get(short, short)
    if short in by_lower:
        return by_lower[short]
    hits = [s for s in station_names if short in s.lower()]
    if len(hits) == 1:
        return hits[0]
    close = difflib.get_close_matches(short, list(by_lower), n=1, cutoff=0.8)
    return by_lower[close[0]] if close else None


# ---------- RAG example bank (kept separate from the test set) ----------
EXAMPLES = [
    ("I need to go from Harvard to Back Bay",
     {"origin": "Harvard", "destination": "Back Bay", "fewer_transfers": 0.5, "avoid": []}),
    ("Get me from Alewife to South Station, I really don't want to switch trains",
     {"origin": "Alewife", "destination": "South Station", "fewer_transfers": 0.9, "avoid": []}),
    ("wheelchair user here, Park Street to Airport please",
     {"origin": "Park Street", "destination": "Airport", "fewer_transfers": 0.5, "avoid": []}),
    ("Heading from Wonderland to Forest Hills tonight, avoid Downtown Crossing, the elevator there is broken",
     {"origin": "Wonderland", "destination": "Forest Hills", "fewer_transfers": 0.5, "avoid": ["Downtown Crossing"]}),
    ("Davis to Kendall/MIT",
     {"origin": "Davis", "destination": "Kendall/MIT", "fewer_transfers": 0.5, "avoid": []}),
    ("I'm on crutches so the fewer changes the better, Oak Grove to Ruggles",
     {"origin": "Oak Grove", "destination": "Ruggles", "fewer_transfers": 0.85, "avoid": []}),
    ("from north station to quincy center, a single train would be ideal",
     {"origin": "North Station", "destination": "Quincy Center", "fewer_transfers": 0.9, "avoid": []}),
    ("Take me to Copley from Kenmore",
     {"origin": "Kenmore", "destination": "Copley", "fewer_transfers": 0.5, "avoid": []}),
    ("traveling with a stroller, Government Center to Maverick, skip State if possible",
     {"origin": "Government Center", "destination": "Maverick", "fewer_transfers": 0.5, "avoid": ["State"]}),
    ("Boston College to Heath Street, I don't mind changing lines",
     {"origin": "Boston College", "destination": "Heath Street", "fewer_transfers": 0.2, "avoid": []}),
    ("Need to reach Ashmont from JFK/UMass",
     {"origin": "JFK/UMass", "destination": "Ashmont", "fewer_transfers": 0.5, "avoid": []}),
    ("Chinatown to Alewife, one seat ride if you can",
     {"origin": "Chinatown", "destination": "Alewife", "fewer_transfers": 0.9, "avoid": []}),
    ("My mom uses a walker; Lechmere to Back Bay with as few transfers as possible",
     {"origin": "Lechmere", "destination": "Back Bay", "fewer_transfers": 0.95, "avoid": []}),
    ("Haymarket to Jackson Square, whatever's fastest",
     {"origin": "Haymarket", "destination": "Jackson Square", "fewer_transfers": 0.2, "avoid": []}),
    ("I'm going between Porter and Tufts Medical Center",
     {"origin": "Porter", "destination": "Tufts Medical Center", "fewer_transfers": 0.5, "avoid": []}),
    ("Cleveland Circle to Park Street but please not through Kenmore",
     {"origin": "Cleveland Circle", "destination": "Park Street", "fewer_transfers": 0.5, "avoid": ["Kenmore"]}),
    ("Get from Riverside to Government Center",
     {"origin": "Riverside", "destination": "Government Center", "fewer_transfers": 0.5, "avoid": []}),
    ("Broadway to Charles/MGH, transfers are fine",
     {"origin": "Broadway", "destination": "Charles/MGH", "fewer_transfers": 0.2, "avoid": []}),
    ("I'd like to get to Wonderland from Aquarium, keep it simple, no changes",
     {"origin": "Aquarium", "destination": "Wonderland", "fewer_transfers": 0.9, "avoid": []}),
    ("Medford/Tufts to Union Square",
     {"origin": "Medford/Tufts", "destination": "Union Square", "fewer_transfers": 0.5, "avoid": []}),
]

_example_vecs = None


def retrieve_examples(text, k=K_EXAMPLES):
    """RAG: the k most similar labeled examples, by cosine similarity."""
    global _example_vecs
    if k <= 0:
        return []
    if _example_vecs is None:
        _example_vecs = np.array([embed(t) for t, _ in EXAMPLES])
    sims = _example_vecs @ np.array(embed(text))     # vectors are normalized, so dot = cosine
    return [EXAMPLES[i] for i in np.argsort(-sims)[:k]]


# ---------- Node 1: LLM parses the request into JSON ----------
def build_prompt(text, examples):
    shots = "\n\n".join(f"Request: {t}\nJSON: {json.dumps(y)}" for t, y in examples)
    return f"""You convert MBTA subway trip requests into JSON. Do not plan a route.
Return only a JSON object with these keys:
- "origin": the station the rider starts from
- "destination": the station the rider is going to
- "fewer_transfers": a number from 0 to 1 for how strongly the rider wants to avoid changing trains (0.5 if not mentioned)
- "avoid": a list of stations the rider wants to avoid (empty if none)
Use official MBTA station names where you can.

{("Examples:" + chr(10) + chr(10) + shots) if shots else ""}

Request: {text}
JSON:"""


def _extract_json(reply):
    m = re.search(r"\{.*\}", reply or "", re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        data = {}
    return data if isinstance(data, dict) else {}


def _finish(raw, station_names, t0, method):
    try:
        ft = float(raw.get("fewer_transfers", 0.5))
    except (TypeError, ValueError):
        ft = 0.5
    avoid = [normalize_station(a, station_names) for a in (raw.get("avoid") or [])]
    return {
        "origin": normalize_station(raw.get("origin"), station_names),
        "destination": normalize_station(raw.get("destination"), station_names),
        "fewer_transfers": max(0.0, min(1.0, ft)),
        "avoid": [a for a in avoid if a],
        "raw": raw,
        "method": method,
        "seconds": round(time.perf_counter() - t0, 2),
    }


def parse_request(text, station_names, k=K_EXAMPLES):
    """LLM + RAG parser (k=0 gives the zero-shot version)."""
    t0 = time.perf_counter()
    try:
        raw = _extract_json(ask_llm(build_prompt(text, retrieve_examples(text, k))))
    except Exception:
        raw = {}
    return _finish(raw, station_names, t0, "llm_rag" if k else "llm_zero_shot")


# ---------- Baseline: keyword / regex parser ----------
TRANSFER_WORDS = ["transfer", "change trains", "changing trains", "switch lines", "switching",
                  "direct", "one train", "single train", "one seat", "no changes"]


def keyword_parse(text, station_names):
    t0 = time.perf_counter()
    s = text.lower()
    origin = dest = None
    end = r"(?:[,.!?;]| and | but | by | because |$)"
    m = re.search(rf"from (.+?) to (.+?){end}", s) or re.search(rf"between (.+?) and (.+?){end}", s)
    if m:
        origin, dest = m.group(1), m.group(2)
    else:
        m = re.search(rf"(?:get|go|travel|head|going) to (.+?) from (.+?){end}", s)
        if m:
            dest, origin = m.group(1), m.group(2)
        else:
            m = re.search(rf"([a-z/ ]+?) (?:to|→) ([a-z/ ]+?){end}", s)
            if m:
                origin, dest = m.group(1), m.group(2)
    avoid = re.findall(r"(?:avoid|avoiding|not through|skip|stay away from) ([a-z/ ]+?)(?:[,.!?;]| if | and |$)", s)
    raw = {"origin": origin, "destination": dest,
           "fewer_transfers": 1.0 if any(w in s for w in TRANSFER_WORDS) else 0.0,
           "avoid": avoid}
    return _finish(raw, station_names, t0, "keyword")


# ---------- Node 3: preference -> routing objective ----------
def penalty_for(parsed):
    return FEWER_TRANSFERS_MIN if parsed["fewer_transfers"] >= THRESHOLD else DEFAULT_TRANSFER_MIN


# ---------- Door-to-door requests: places, not just stations ----------
CURRENT = "CURRENT_LOCATION"
HERE_WORDS = r"(?:my (?:current )?location|where i am|here|my place|current location)"

DOOR_EXAMPLES = [
    ("from my location to Boston Children's Hospital",
     {"origin": CURRENT, "destination": "Boston Children's Hospital", "fewer_transfers": 0.5,
      "avoid": [], "max_roll_minutes": None}),
    ("I need to get to Fenway Park from 120 Brookline Ave, as few transfers as possible",
     {"origin": "120 Brookline Ave", "destination": "Fenway Park", "fewer_transfers": 0.9,
      "avoid": [], "max_roll_minutes": None}),
    ("wheelchair user, Northeastern University to Logan Airport Terminal B, I can only roll about 5 minutes at a time",
     {"origin": "Northeastern University", "destination": "Logan Airport Terminal B",
      "fewer_transfers": 0.5, "avoid": [], "max_roll_minutes": 5}),
    ("take me home to 45 Centre St Jamaica Plain from here, avoid Downtown Crossing",
     {"origin": CURRENT, "destination": "45 Centre St, Jamaica Plain", "fewer_transfers": 0.5,
      "avoid": ["Downtown Crossing"], "max_roll_minutes": None}),
    ("Harvard to Mass General Hospital",
     {"origin": "Harvard", "destination": "Mass General Hospital", "fewer_transfers": 0.5,
      "avoid": [], "max_roll_minutes": None}),
    ("going from Union Square Somerville to the Boston Convention Center, whatever is fastest",
     {"origin": "Union Square, Somerville", "destination": "Boston Convention Center",
      "fewer_transfers": 0.2, "avoid": [], "max_roll_minutes": None}),
    ("Chelsea City Hall to Boston Medical Center, keep the rolling short",
     {"origin": "Chelsea City Hall", "destination": "Boston Medical Center", "fewer_transfers": 0.5,
      "avoid": [], "max_roll_minutes": 5}),
    ("my mom uses a walker; from Coolidge Corner to the Museum of Science with one bus or train if possible",
     {"origin": "Coolidge Corner", "destination": "Museum of Science", "fewer_transfers": 0.95,
      "avoid": [], "max_roll_minutes": None}),
]

_door_vecs = None


def _door_examples(text, k):
    global _door_vecs
    if k <= 0:
        return []
    if _door_vecs is None:
        _door_vecs = np.array([embed(t) for t, _ in DOOR_EXAMPLES])
    sims = _door_vecs @ np.array(embed(text))
    return [DOOR_EXAMPLES[i] for i in np.argsort(-sims)[:k]]


def build_trip_prompt(text, examples):
    shots = "\n\n".join(f"Request: {t}\nJSON: {json.dumps(y)}" for t, y in examples)
    return f"""You convert door-to-door trip requests in the Boston area into JSON. Do not plan a route.
Return only a JSON object with these keys:
- "origin": the place the rider starts from, as written (address, place, or station), or "{CURRENT}" if they mean where they are now
- "destination": the place the rider is going to, as written, or "{CURRENT}"
- "fewer_transfers": a number from 0 to 1 for how strongly the rider wants to avoid changing buses or trains (0.5 if not mentioned)
- "avoid": a list of MBTA stations the rider wants to avoid (empty if none)
- "max_roll_minutes": the longest the rider wants to walk or roll at one time, in minutes, or null if not mentioned

{("Examples:" + chr(10) + chr(10) + shots) if shots else ""}

Request: {text}
JSON:"""


def _place_text(value):
    if not isinstance(value, str) or not value.strip():
        return None
    v = value.strip()
    return CURRENT if v.upper() == CURRENT or re.fullmatch(HERE_WORDS, v.lower()) else v


def _finish_trip(raw, station_names, t0, method):
    base = _finish(raw, station_names, t0, method)
    roll = raw.get("max_roll_minutes")
    try:
        roll = max(2.0, min(30.0, float(roll))) if roll is not None else None
    except (TypeError, ValueError):
        roll = None
    return {**base, "origin": _place_text(raw.get("origin")),
            "destination": _place_text(raw.get("destination")), "max_roll_minutes": roll}


def parse_trip_request(text, station_names, k=K_EXAMPLES):
    """LLM + RAG parser for door-to-door requests. Origin/destination stay as the rider wrote
    them (agents/places.py resolves them); "my location" becomes CURRENT_LOCATION."""
    t0 = time.perf_counter()
    try:
        raw = _extract_json(ask_llm(build_trip_prompt(text, _door_examples(text, k))))
    except Exception:
        raw = {}
    if not raw.get("origin") and not raw.get("destination"):
        return keyword_trip_parse(text, station_names)
    return _finish_trip(raw, station_names, t0, "llm_rag")


def keyword_trip_parse(text, station_names):
    """Baseline / fallback when the LLM is unavailable."""
    t0 = time.perf_counter()
    s = text.strip()
    end = r"(?:[,.!?;]| and | but | because |$)"
    origin = dest = None
    m = re.search(rf"from (.+?) to (.+?){end}", s, re.I)
    if m:
        origin, dest = m.group(1), m.group(2)
    else:
        m = re.search(rf"(?:to|get to|go to|going to) (.+?) from (.+?){end}", s, re.I)
        if m:
            dest, origin = m.group(1), m.group(2)
        else:
            m = re.search(rf"^(.+?) to (.+?){end}", s, re.I)
            if m:
                origin, dest = m.group(1), m.group(2)
    low = s.lower()
    avoid = re.findall(r"(?:avoid|avoiding|not through|skip|stay away from) ([a-z/ ]+?)(?:[,.!?;]| if | and |$)", low)
    roll = re.search(r"(\d+)\s*min(?:ute)?s?\s*(?:of\s*)?(?:rolling|walking|at a time)", low)
    raw = {"origin": origin, "destination": dest, "avoid": avoid,
           "fewer_transfers": 1.0 if any(w in low for w in TRANSFER_WORDS) else 0.0,
           "max_roll_minutes": float(roll.group(1)) if roll else None}
    return _finish_trip(raw, station_names, t0, "keyword")