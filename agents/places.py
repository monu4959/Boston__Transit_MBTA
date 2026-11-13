"""Turn what the rider typed into a point on the map: a station name, "lat, lon", or an address.

Addresses are looked up with OpenStreetMap's Nominatim service, limited to the Boston area.
Nominatim's usage policy: identify the app, at most one request per second, cache results.
Only the typed text is sent; current location (GPS) never goes to Nominatim.
"""
import re
import threading
import time
from functools import lru_cache

import requests

from agents.request_parser import normalize_station

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "TransitWise-Boston/0.2 (step-free MBTA trip planner; student project)"
# The area the trip planner covers (same box as otp/setup_otp.py)
WEST, SOUTH, EAST, NORTH = -71.40, 42.05, -70.80, 42.60
CURRENT_LOCATION = "CURRENT_LOCATION"

_lock = threading.Lock()
_last_call = [0.0]


def in_area(lat, lon):
    return SOUTH <= lat <= NORTH and WEST <= lon <= EAST


def parse_latlon(text):
    m = re.fullmatch(r"\s*(-?\d{1,2}\.\d+)\s*[, ]\s*(-?\d{1,3}\.\d+)\s*", text or "")
    return (float(m.group(1)), float(m.group(2))) if m else None


def station_places():
    """{station name: (lat, lon)} from the subway graph (needs planner._cache)."""
    from agents import planner
    if planner._cache is None:
        return {}
    G, names = planner._cache[0], planner._cache[1]
    coords = G.graph.get("coords", {})
    return {names[sid]: coords[sid] for sid in names if sid in coords}


@lru_cache(maxsize=512)
def _nominatim(text):
    with _lock:                                   # one request per second, app-wide
        wait = 1.05 - (time.monotonic() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.monotonic()
        r = requests.get(NOMINATIM_URL, timeout=10, headers={"User-Agent": USER_AGENT}, params={
            "q": text, "format": "jsonv2", "limit": 5, "countrycodes": "us",
            "viewbox": f"{WEST},{NORTH},{EAST},{SOUTH}", "bounded": 1})
    r.raise_for_status()
    return tuple((h["display_name"], float(h["lat"]), float(h["lon"])) for h in r.json())


def geocode(text):
    """Up to 5 matches inside the service area: [{"name", "lat", "lon"}]."""
    return [{"name": n, "lat": la, "lon": lo} for n, la, lo in _nominatim(text.strip()) if in_area(la, lo)]


def _short(display_name):
    """'Fenway Park, 4, Jersey Street, ..., Boston, ...' -> 'Fenway Park, 4, Jersey Street'."""
    return ", ".join(display_name.split(", ")[:3])


def resolve_place(text, current=None):
    """{"ok", "name", "lat", "lon", "source", "candidates"} for what the rider typed.
    `current` is (lat, lon) from the browser, used when text is CURRENT_LOCATION / "my location"."""
    t = (text or "").strip()
    if not t:
        return {"ok": False, "reason": "Enter a starting point and a destination."}
    if t == CURRENT_LOCATION or t.lower() in ("my location", "current location", "here", "me"):
        if not current:
            return {"ok": False, "reason": "Your current location isn't available. Allow location "
                                           "access in the browser, or type an address."}
        lat, lon = current
        if not in_area(lat, lon):
            return {"ok": False, "reason": "Your location is outside the area this planner covers "
                                           "(the MBTA bus and subway area)."}
        return {"ok": True, "name": "Your location", "lat": lat, "lon": lon, "source": "location"}
    ll = parse_latlon(t)
    if ll:
        if not in_area(*ll):
            return {"ok": False, "reason": f"{t} is outside the MBTA bus and subway area."}
        return {"ok": True, "name": t, "lat": ll[0], "lon": ll[1], "source": "coordinates"}
    stations = station_places()
    station = normalize_station(t, list(stations)) if stations else None
    if station:
        lat, lon = stations[station]
        return {"ok": True, "name": f"{station} station", "lat": lat, "lon": lon, "source": "station"}
    try:
        hits = geocode(t)
    except requests.RequestException:
        return {"ok": False, "reason": "Address search is unavailable right now. Try a station "
                                       "name or coordinates."}
    if not hits:
        return {"ok": False, "reason": f"Couldn't find \"{t}\" in the Boston area. Try adding a "
                                       "street, town or ZIP code."}
    top = hits[0]
    return {"ok": True, "name": _short(top["name"]), "full_name": top["name"], "lat": top["lat"],
            "lon": top["lon"], "source": "address",
            "candidates": [{**h, "name": _short(h["name"])} for h in hits[1:]]}
