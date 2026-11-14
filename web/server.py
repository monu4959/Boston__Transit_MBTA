"""TransitWise website: a JSON API around the door-to-door agents, plus the static site.

    py -3.12 -m uvicorn web.server:app --port 8000      then open http://localhost:8000

Needs the OpenTripPlanner server (py -3.12 otp/setup_otp.py serve). Snowflake is used for the
station graph, policy search and logging; without it the site still plans trips (from the
offline station snapshot) and explanations fall back to the data-only text.
"""
import os
import sys
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from agents import otp, planner  # noqa: E402
from agents.door_to_door import _explain, plan_door_to_door  # noqa: E402
from agents.monitor import check_door_watch, start_door_trip  # noqa: E402
from agents.places import CURRENT_LOCATION, _short, geocode, in_area, resolve_place, station_places  # noqa: E402
from agents.replanner import _ids  # noqa: E402
from agents.request_parser import THRESHOLD, parse_trip_request  # noqa: E402
from pipeline.load_alerts import clean_mbta_key  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
MBTA_KEY = clean_mbta_key(os.getenv("MBTA_KEY") or os.getenv("MBTA_API_KEY"))
LOCK = threading.RLock()          # one Snowflake connection, shared by request threads
STATE = {"conn": None, "db": False, "model": False}
RESULTS, WATCHES = {}, {}         # in-memory, per server process (fine for one site instance)


class NoDB:
    def cursor(self):
        raise RuntimeError("Snowflake not connected")


def _startup():
    try:
        from agents.db import get_connection
        STATE["conn"], STATE["db"] = get_connection(), True
        planner._cache = planner.build_graph(STATE["conn"])
    except Exception as e:                                   # offline: station snapshot from tests
        print(f"web: Snowflake unavailable ({e.__class__.__name__}); using the offline station snapshot")
        sys.path.insert(0, str(ROOT / "tests"))
        import conftest
        planner.query_df = conftest.fake_query_df
        STATE["conn"], STATE["db"] = NoDB(), False
        planner._cache = planner.build_graph(STATE["conn"])

    def load_model():                                        # policy search + request parser
        try:
            from agents.retriever import get_model
            get_model()
            STATE["model"] = True
        except Exception as e:
            print("web: embedding model not loaded:", e)
    threading.Thread(target=load_model, daemon=True).start()


@asynccontextmanager
async def lifespan(app):
    _startup()
    yield


app = FastAPI(title="TransitWise Boston", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"otp": otp.is_available(), "mbta": bool(MBTA_KEY), "db": STATE["db"],
            "llm": bool(os.getenv("LLM_API_KEY")), "model": STATE["model"]}


# ---------- places ----------

@app.get("/api/stations")
def stations():
    return sorted(set(planner._cache[1].values())) if planner._cache else []


@app.get("/api/places")
def places(q: str = "", address: bool = False):
    """Station matches as you type. Addresses only when asked (address=true): OpenStreetMap's
    Nominatim does not allow search-as-you-type."""
    q = q.strip()[:120]
    if len(q) < 2:
        return []
    low = q.lower()
    stations = station_places()
    hits = sorted((n for n in stations if low in n.lower()), key=lambda n: (not n.lower().startswith(low), n))
    out = [{"name": n, "sub": "MBTA station", "kind": "station", "lat": stations[n][0], "lon": stations[n][1]}
           for n in hits[:5]]
    if address and len(q) >= 3:
        try:
            for h in geocode(q):
                rest = h["name"].split(", ")[3:6]
                out.append({"name": _short(h["name"]), "sub": ", ".join(rest), "kind": "address",
                            "lat": h["lat"], "lon": h["lon"]})
        except Exception:
            pass
    return out[:9]


# ---------- planning ----------

class Spot(BaseModel):
    text: str | None = None
    name: str | None = None
    lat: float | None = None
    lon: float | None = None


class PlanRequest(BaseModel):
    origin: Spot
    destination: Spot
    here: list[float] | None = None
    depart_at: str | None = None
    fewer_transfers: bool = False
    max_roll: float = Field(10, ge=2, le=30)
    avoid: list[str] = []


def _resolve(spot, here):
    if spot.lat is not None and spot.lon is not None:
        if not in_area(spot.lat, spot.lon):
            return {"ok": False, "reason": f"{spot.name or 'That place'} is outside the MBTA bus and subway area."}
        return {"ok": True, "name": spot.name or f"{spot.lat:.4f}, {spot.lon:.4f}", "lat": spot.lat, "lon": spot.lon}
    return resolve_place(spot.text or "", current=tuple(here) if here else None)


def _options(r):
    """Trip cards in display order: recommended, alternatives, then the blocked usual trip."""
    opts = []
    if r.get("trip"):
        opts.append({"role": "recommended", "trip": r["trip"]})
    opts += [{"role": "option", "trip": t} for t in r.get("alternatives", [])]
    if r.get("changed") and r.get("usual"):
        opts.append({"role": "blocked", "trip": r["usual"]})
    return opts


@app.post("/api/plan")
def plan(req: PlanRequest):
    o, d = _resolve(req.origin, req.here), _resolve(req.destination, req.here)
    bad = [p["reason"] for p in (o, d) if not p["ok"]]
    if bad:
        return {"ok": False, "reason": " ".join(dict.fromkeys(bad)), "stage": "places"}
    prefs = {"transfer_penalty": 15.0 if req.fewer_transfers else 5.0, "max_roll_min": req.max_roll,
             "max_total_roll_min": max(20.0, 2 * req.max_roll)}
    with LOCK:
        r = plan_door_to_door(STATE["conn"], o, d, MBTA_KEY, depart_at=req.depart_at, prefs=prefs,
                              avoid_ids=_ids(STATE["conn"], req.avoid[:10]), explain=False,
                              log_source="web")
    rid = uuid.uuid4().hex[:12]
    RESULTS[rid] = r
    while len(RESULTS) > 200:
        RESULTS.pop(next(iter(RESULTS)))
    return {"id": rid, **r, "options": _options(r)}


@app.post("/api/explain/{rid}")
def explain(rid: str):
    """The plain-English explanation (LLM + guardrails), fetched after the trip is on screen."""
    r = RESULTS.get(rid)
    if not r:
        raise HTTPException(404, "Plan not found; plan the trip again.")
    if not r.get("changed"):
        return {"explanation": r.get("explanation"), "sources": [], "guardrails": r.get("guardrails", [])}
    guard = list(r.get("guardrails", []))
    with LOCK:
        text, sources, claims = _explain(STATE["conn"], r["usual"], r["problems"], r["trip"], guard, True)
    r.update(explanation=text, sources=sources, guardrails=guard, claim_issues=claims)
    return {"explanation": text, "sources": sources, "guardrails": guard}


class ParseRequest(BaseModel):
    text: str = Field(..., max_length=500)


@app.post("/api/parse")
def parse(req: ParseRequest):
    names = sorted(set(planner._cache[1].values())) if planner._cache else []
    p = parse_trip_request(req.text, names)
    return {"origin": p["origin"], "destination": p["destination"], "avoid": p["avoid"],
            "fewer_transfers": p["fewer_transfers"] >= THRESHOLD, "max_roll": p["max_roll_minutes"],
            "current": CURRENT_LOCATION, "seconds": p["seconds"], "method": p["method"]}


# ---------- live monitoring ----------

class WatchRequest(BaseModel):
    id: str
    option: int = 0


class CheckRequest(BaseModel):
    simulate: bool = False
    here: list[float] | None = None


@app.post("/api/monitor/start")
def monitor_start(req: WatchRequest):
    r = RESULTS.get(req.id)
    opts = _options(r) if r else []
    if not opts or not 0 <= req.option < len(opts):
        raise HTTPException(404, "Trip not found; plan the trip again.")
    watch = start_door_trip({**r, "trip": opts[req.option]["trip"]})
    if not watch["ok"]:
        return watch
    wid = uuid.uuid4().hex[:12]
    WATCHES[wid] = watch
    return {"ok": True, "watch_id": wid}


@app.post("/api/monitor/{wid}/check")
def monitor_check(wid: str, req: CheckRequest):
    watch = WATCHES.get(wid)
    if not watch:
        raise HTTPException(404, "Monitor not found; start monitoring again.")
    with LOCK:
        ev = check_door_watch(STATE["conn"], watch, MBTA_KEY, simulate=req.simulate,
                              current=tuple(req.here) if req.here else None)
    rep = ev.get("replan") or {}
    return {"time": ev["time"], "new_problems": ev["new_problems"], "resolved": ev["resolved"],
            "live_times": ev["live_times"], "switched": bool(ev["switched_to"]),
            "trip": watch["trip"],
            "explanation": rep.get("explanation") if rep.get("changed") else None}
