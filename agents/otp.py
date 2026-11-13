"""OpenTripPlanner connector: door-to-door step-free trip options (roll + bus + train).

OTP (otp/setup_otp.py) plans with MBTA timetables, live MBTA trip updates and OpenStreetMap
sidewalks, in wheelchair mode. This module turns its itineraries into one trip format and ranks
them by what matters to a wheelchair user: less rolling, fewer transfers, then speed.
"""
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests

OTP_URL = os.getenv("OTP_URL", "http://localhost:8080/otp/gtfs/v1")
FEED = "mbta:"
ROLL_SPEED = 1.2           # m/s, a steady wheelchair pace

DEFAULT_PREFS = {
    "transfer_penalty": 5.0,   # minutes a transfer "costs" (15 = rider wants fewer transfers)
    "max_roll_min": 10.0,      # longest single roll the rider is comfortable with
    "max_total_roll_min": 20.0,
}
ROLL_EXTRA = 1.0           # each rolling minute counts double in the ranking
OVER_LIMIT = 4.0           # each minute over the rider's roll limit costs 4 more

# Two searches, merged: one balanced, one that tries hard to keep rolling short
PROFILES = [
    {"name": "balanced", "reluctance": 4, "max_transfers": 3},
    {"name": "less-rolling", "reluctance": 10, "max_transfers": 2},
]

QUERY = """
query($o: PlanLabeledLocationInput!, $d: PlanLabeledLocationInput!, $t: PlanDateTimeInput,
      $p: PlanPreferencesInput, $n: Int) {
  planConnection(origin: $o, destination: $d, dateTime: $t, first: $n, preferences: $p) {
    routingErrors { code description }
    edges { node {
      start end duration walkTime walkDistance waitingTime numberOfTransfers
      legs {
        id mode transitLeg realTime duration distance headsign
        start { scheduledTime estimated { time delay } }
        end { scheduledTime estimated { time delay } }
        from { name lat lon stop { gtfsId parentStation { gtfsId name } } }
        to   { name lat lon stop { gtfsId parentStation { gtfsId name } } }
        route { gtfsId shortName longName color }
        trip { gtfsId directionId }
        legGeometry { points }
        stopCalls { stopLocation { ... on Stop { gtfsId name parentStation { gtfsId name } } } }
      }
    } }
  }
}"""

LEG_QUERY = """
query($id: String!) { leg(id: $id) {
  realTime
  start { scheduledTime estimated { time delay } }
  end { scheduledTime estimated { time delay } }
} }"""

MODE_WORDS = {"BUS": "bus", "SUBWAY": "subway", "TRAM": "light rail", "RAIL": "Commuter Rail",
              "FERRY": "ferry", "ROLL": "roll"}


class OTPUnavailable(RuntimeError):
    pass


# ---------- small helpers ----------

def _strip(gtfs_id):
    return gtfs_id[len(FEED):] if gtfs_id and gtfs_id.startswith(FEED) else gtfs_id


def decode_polyline(points):
    """Google encoded polyline -> [[lat, lon], ...]."""
    coords, index, lat, lon = [], 0, 0, 0
    while points and index < len(points):
        for is_lon in (False, True):
            shift = result = 0
            while True:
                b = ord(points[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if is_lon:
                lon += delta
            else:
                lat += delta
        coords.append([lat / 1e5, lon / 1e5])
    return coords


def _parse_time(s):
    return datetime.fromisoformat(s) if s else None


def _delay_seconds(duration):
    """ISO-8601 duration such as 'PT1M30S' or '-PT45S' -> seconds."""
    if not duration:
        return 0
    m = re.fullmatch(r"(-)?PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", duration)
    if not m:
        return 0
    sign = -1 if m.group(1) else 1
    h, mi, s = (float(g) if g else 0 for g in m.groups()[1:])
    return int(sign * (h * 3600 + mi * 60 + s))


def _time(lt):
    """(best time, scheduled time, delay seconds) for an OTP LegTime."""
    est = lt.get("estimated") or {}
    return (est.get("time") or lt["scheduledTime"], lt["scheduledTime"], _delay_seconds(est.get("delay")))


def route_name(mode, route):
    if not route:
        return "Roll"
    short, long_ = route.get("shortName"), route.get("longName")
    if mode == "BUS":
        name = short or long_ or ""
        if name.startswith("SL"):
            return f"Silver Line {name}"
        return name if "shuttle" in name.lower() else f"Bus {name}"
    if mode == "RAIL":
        return f"{long_} (Commuter Rail)"
    return long_ or short or "Train"


def _place(p):
    stop = p.get("stop") or {}
    parent = stop.get("parentStation") or {}
    return {"name": p["name"], "lat": p["lat"], "lon": p["lon"],
            "stop_id": _strip(stop.get("gtfsId")), "station_id": _strip(parent.get("gtfsId")),
            "station_name": parent.get("name")}


def _leg(raw):
    mode = "ROLL" if raw["mode"] == "WALK" else raw["mode"]
    start, sched_start, delay = _time(raw["start"])
    end, sched_end, _ = _time(raw["end"])
    route = raw.get("route")
    leg = {
        "mode": mode,
        "transit": bool(raw.get("transitLeg")),
        "route_id": _strip(route["gtfsId"]) if route else None,
        "route_name": route_name(mode, route),
        "color": "#" + route["color"] if route and route.get("color") else None,
        "headsign": raw.get("headsign"),
        "from": _place(raw["from"]),
        "to": _place(raw["to"]),
        "start": start, "end": end,
        "scheduled_start": sched_start, "scheduled_end": sched_end,
        "delay_s": delay,
        "minutes": round(raw["duration"] / 60, 1),
        "meters": round(raw.get("distance") or 0),
        "realtime": bool(raw.get("realTime")),
        "trip_id": _strip((raw.get("trip") or {}).get("gtfsId")),
        "direction_id": (raw.get("trip") or {}).get("directionId"),
        "leg_id": raw.get("id"),
        "geometry": decode_polyline((raw.get("legGeometry") or {}).get("points") or ""),
        "stops": [],
    }
    for call in raw.get("stopCalls") or []:
        s = call.get("stopLocation") or {}
        if s.get("gtfsId"):
            parent = s.get("parentStation") or {}
            leg["stops"].append({"stop_id": _strip(s["gtfsId"]), "name": s.get("name"),
                                 "station_id": _strip(parent.get("gtfsId")),
                                 "station_name": parent.get("name")})
    return leg


def trip_key(trip):
    """Same route, same stops = same trip option (ignores which departure)."""
    return tuple((l["route_id"], l["from"]["stop_id"], l["to"]["stop_id"])
                 for l in trip["legs"] if l["transit"]) or ("roll only",)


def to_trip(itinerary, origin=None, dest=None):
    legs = [_leg(l) for l in itinerary["legs"]]
    rolls = [l["minutes"] for l in legs if l["mode"] == "ROLL"]
    transit = [l for l in legs if l["transit"]]
    trip = {
        "ok": True,
        "kind": "door_to_door",
        "origin": origin, "dest": dest,
        "departs": legs[0]["start"], "arrives": legs[-1]["end"],
        "minutes": round(itinerary["duration"] / 60),
        "rolling_minutes": round(itinerary["walkTime"] / 60, 1),
        "rolling_meters": round(itinerary.get("walkDistance") or 0),
        "longest_roll": max(rolls, default=0.0),
        "wait_minutes": round((itinerary.get("waitingTime") or 0) / 60, 1),
        "transfers": max(len(transit) - 1, 0),
        "legs": legs,
        "live": any(l["realtime"] for l in transit),
    }
    trip["key"] = trip_key(trip)
    return trip


def score(trip, prefs=None):
    """Lower is better: time + extra weight on rolling, transfers, and rolls over the limit."""
    p = {**DEFAULT_PREFS, **(prefs or {})}
    over = sum(max(0.0, l["minutes"] - p["max_roll_min"]) for l in trip["legs"] if l["mode"] == "ROLL")
    over_total = max(0.0, trip["rolling_minutes"] - p["max_total_roll_min"])
    return (trip["minutes"] + ROLL_EXTRA * trip["rolling_minutes"]
            + p["transfer_penalty"] * trip["transfers"]
            + OVER_LIMIT * (over + over_total))


def within_limits(trip, prefs=None):
    p = {**DEFAULT_PREFS, **(prefs or {})}
    return trip["longest_roll"] <= p["max_roll_min"] and trip["rolling_minutes"] <= p["max_total_roll_min"]


def stations_used(trip):
    """Station (or stop) IDs where the rider boards, gets off or changes."""
    used = []
    for l in trip["legs"]:
        if l["transit"]:
            for p in (l["from"], l["to"]):
                used.append(p["station_id"] or p["stop_id"])
    return used


# ---------- talking to OTP ----------

def _post(query, variables, timeout=30):
    try:
        r = requests.post(OTP_URL, json={"query": query, "variables": variables}, timeout=timeout)
        r.raise_for_status()
    except requests.RequestException as e:
        raise OTPUnavailable(f"Trip planner server not reachable at {OTP_URL} ({e.__class__.__name__}). "
                             "Start it with: py -3.12 otp/setup_otp.py serve") from e
    body = r.json()
    if body.get("errors"):
        raise OTPUnavailable("Trip planner error: " + str(body["errors"])[:300])
    return body["data"]


def _location(place):
    return {"location": {"coordinate": {"latitude": place["lat"], "longitude": place["lon"]}},
            "label": place.get("name")}


def query_itineraries(origin, dest, depart_at=None, profile=PROFILES[0], exclude_routes=(), n=5):
    """Raw OTP itineraries for one search profile. Tests replace this with recorded answers."""
    prefs = {
        "accessibility": {"wheelchair": {"enabled": True}},
        "street": {"walk": {"reluctance": profile["reluctance"], "speed": ROLL_SPEED}},
        "transit": {"transfer": {"maximumTransfers": profile["max_transfers"]}},
    }
    if exclude_routes:
        prefs["transit"]["filters"] = [{"exclude": [{"routes": [FEED + r for r in sorted(exclude_routes)]}]}]
    data = _post(QUERY, {"o": _location(origin), "d": _location(dest), "p": prefs, "n": n,
                         "t": {"earliestDeparture": depart_at} if depart_at else None})
    pc = data["planConnection"]
    return [e["node"] for e in pc["edges"]], pc.get("routingErrors") or []


def plan_options(origin, dest, depart_at=None, prefs=None, exclude_routes=()):
    """All step-free trip options from both search profiles, best first.
    origin/dest: {"name", "lat", "lon"}. depart_at: ISO time with offset, or None for now."""
    t0 = time.perf_counter()
    with ThreadPoolExecutor(len(PROFILES)) as pool:
        answers = list(pool.map(lambda pr: query_itineraries(origin, dest, depart_at, pr, tuple(exclude_routes)),
                                PROFILES))
    seen, options, errors = set(), [], []
    for itineraries, errs in answers:
        errors += [e for e in errs if e not in errors]
        for it in itineraries:
            trip = to_trip(it, origin, dest)
            k = (trip["key"], trip["departs"])
            if k not in seen:
                seen.add(k)
                options.append(trip)
    for t in options:
        t["score"] = round(score(t, prefs), 1)
    # A roll-only "trip" is only an option when it is short
    options = [t for t in options if t["key"] != ("roll only",) or within_limits(t, prefs)]
    options.sort(key=lambda t: t["score"])
    # Keep the earliest departure of each distinct route
    best, keys = [], set()
    for t in options:
        if t["key"] not in keys:
            keys.add(t["key"])
            best.append(t)
    return {"ok": bool(best), "options": best, "errors": errors,
            "ms": round((time.perf_counter() - t0) * 1000)}


def refresh_leg(leg):
    """Latest live times for one bus/train leg. Returns None if OTP no longer has that trip
    (for example, it was cancelled)."""
    if not leg.get("leg_id"):
        return leg
    data = _post(LEG_QUERY, {"id": leg["leg_id"]}, timeout=15)
    raw = data.get("leg")
    if not raw:
        return None
    start, _, delay = _time(raw["start"])
    end, _, _ = _time(raw["end"])
    return {**leg, "start": start, "end": end, "delay_s": delay, "realtime": bool(raw.get("realTime"))}


def is_available():
    try:
        _post("{ feeds { feedId } }", {}, timeout=5)
        return True
    except OTPUnavailable:
        return False
