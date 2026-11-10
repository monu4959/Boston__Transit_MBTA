import re
import requests

ACCESS_EFFECTS = {"ELEVATOR_CLOSURE", "ESCALATOR_CLOSURE", "ACCESS_ISSUE"}
SERVICE_EFFECTS = {"SUSPENSION", "SHUTTLE"}            # no trains between some stations
CLOSURE_EFFECTS = {"STATION_CLOSURE", "STOP_CLOSURE"}  # trains don't stop at a station

# Words in alert text that tell us which line/platform a facility serves
LINE_WORDS = {
    "Red": ["red line", "alewife", "ashmont", "braintree"],
    "Orange": ["orange line", "oak grove", "forest hills"],
    "Blue": ["blue line", "bowdoin", "wonderland"],
    "Green": ["green line", "boston college", "cleveland circle", "riverside",
              "heath street", "medford", "union square"],
    "Mattapan": ["mattapan"],
    "Other": ["commuter rail", "silver line", "bus", "ferry"],
}


def get_live_alerts(mbta_key):
    """Every MBTA alert active right now: accessibility (elevators, escalators) and
    service changes (suspensions, shuttles, closures). One call serves a whole trip check."""
    r = requests.get(
        "https://api-v3.mbta.com/alerts",
        params={"filter[activity]": "ALL", "filter[datetime]": "NOW"},
        headers={"x-api-key": mbta_key} if mbta_key else {},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["data"]


def access_alerts(alerts):
    """Only the elevator/escalator/access alerts."""
    return [a for a in alerts if a["attributes"]["effect"] in ACCESS_EFFECTS]


def lines_mentioned(text):
    t = text.lower()
    return {line for line, words in LINE_WORDS.items() if any(w in t for w in words)}


def serves_rider(alert_text, rider_lines, station_name=None):
    """True if the facility may serve the rider's line. Unclear → True (safe default).
    The station's own name is removed first: "Forest Hills Elevator 841 (Commuter Rail
    platform)" is about Commuter Rail, not the Orange Line's Forest Hills terminal."""
    if station_name:
        alert_text = re.sub(re.escape(station_name), " ", alert_text, flags=re.I)
    mentioned = lines_mentioned(alert_text)
    if not mentioned or not rider_lines:
        return True
    rider = {line.split("-")[0] for line in rider_lines}   # Green-B → Green
    return bool(mentioned & rider)


def _stops(alert):
    return {e.get("stop") for e in alert["attributes"].get("informed_entity", []) if e.get("stop")}


def _is_platform(stop_id):
    return not stop_id.startswith(("place-", "door-", "node-"))


def service_disruptions(alerts):
    """Suspended line segments and closed stops, in the form planner_agent() expects."""
    segments, closed = [], []
    for a in alerts:
        at = a["attributes"]
        effect = at.get("effect")
        ents = at.get("informed_entity", [])
        if effect in SERVICE_EFFECTS:
            by_route = {}
            for e in ents:
                if e.get("route") and e.get("route_type") in (0, 1, None):
                    stop = e.get("stop") or ""
                    stations = by_route.setdefault(e["route"], set())
                    if stop.startswith("place-"):
                        stations.add(stop)
                    elif not stop:
                        by_route[e["route"]] = None        # whole line
            for route, stations in by_route.items():
                if stations is None or len(stations) >= 2:
                    segments.append({"route": route, "stations": stations, "effect": effect,
                                     "alert_id": a["id"], "alert": at["header"]})
        elif effect in CLOSURE_EFFECTS:
            for e in ents:
                if (e.get("stop") or "").startswith("place-"):
                    closed.append({"station": e["stop"], "route": e.get("route"), "effect": effect,
                                   "alert_id": a["id"], "alert": at["header"]})
    return {"segments": segments, "closed": closed}


def _access_verdict(alert, sid, station_name, plan):
    """Does this elevator/escalator alert at station sid affect the platforms the rider uses?
    Returns (affects, basis)."""
    stops = _stops(alert)
    platform_stops = {s for s in stops if _is_platform(s)}
    use = plan.get("platform_use", {}).get(sid, {})
    mine = set(use.get("in", [])) | set(use.get("out", []))
    # MBTA lists the platforms an elevator serves; trust that when we know the rider's platform
    if mine & platform_stops:
        return True, "platform"
    parents = {s for s in stops if s.startswith("place-")}
    if mine and platform_stops and parents <= {sid}:
        return False, "platform"
    # Otherwise fall back to the alert text
    return serves_rider(alert["attributes"]["header"], plan.get("station_lines", {}).get(sid, []),
                        station_name), "text"


def checker_agent(plan, mbta_key, alerts=None):
    """Check a planned route against live alerts. Pass `alerts` to reuse one fetch."""
    if not plan.get("ok"):
        return {"ok": False, "reason": "No route to check"}
    if alerts is None:
        alerts = get_live_alerts(mbta_key)

    path = plan["path"]
    name_of = dict(zip(path, plan["stations"]))
    station_lines = plan.get("station_lines", {})
    roles = {path[0]: "origin", path[-1]: "destination"}
    for sid in plan.get("transfer_ids", []):
        roles[sid] = "transfer"
    closed_elevators = {e.get("facility") for a in alerts
                        if a["attributes"]["effect"] == "ELEVATOR_CLOSURE"
                        for e in a["attributes"].get("informed_entity", []) if e.get("facility")}

    issues = []

    # 1. Elevators and escalators at the stations where the rider boards, exits or transfers
    for alert in access_alerts(alerts):
        attrs = alert["attributes"]
        stops = _stops(alert)
        for sid in path:
            use = plan.get("platform_use", {}).get(sid, {})
            if sid not in stops and not (set(use.get("in", [])) | set(use.get("out", []))) & stops:
                continue
            role = roles.get(sid, "pass-through")
            affects, basis = _access_verdict(alert, sid, name_of[sid], plan)
            issue = {
                "kind": "access",
                "station_id": sid,
                "station": name_of[sid],
                "role": role,
                "lines": station_lines.get(sid, []),
                "effect": attrs["effect"],
                "alert": attrs["header"],
                "alert_id": alert["id"],
                "serves_your_line": affects,
                "basis": basis,
            }
            # A working elevator straight between the two platforms keeps a transfer step-free
            if role == "transfer" and affects:
                working = [e for e in plan.get("transfer_elevators", {}).get(sid, [])
                           if e["facility_id"] not in closed_elevators]
                if working:
                    issue["serves_your_line"] = False
                    issue["note"] = f"Use {working[0]['name']} to change platforms"
            issue["blocks"] = (role != "pass-through" and attrs["effect"] != "ESCALATOR_CLOSURE"
                               and issue["serves_your_line"])
            issues.append(issue)

    # 2. Service changes: trains not running on a segment you ride, or not stopping where you need
    disruptions = service_disruptions(alerts)
    seen = set()
    for seg in disruptions["segments"]:
        hit = [(a, b) for a, b, line in plan.get("ride_edges", [])
               if line == seg["route"]
               and (seg["stations"] is None or (a in seg["stations"] and b in seg["stations"]))]
        if hit and (seg["alert_id"], seg["route"]) not in seen:
            seen.add((seg["alert_id"], seg["route"]))
            issues.append({
                "kind": "service", "station_id": hit[0][0],
                "station": f"{name_of[hit[0][0]]} → {name_of[hit[-1][1]]}",
                "role": "suspended segment", "lines": [seg["route"]],
                "effect": seg["effect"], "alert": seg["alert"], "alert_id": seg["alert_id"],
                "serves_your_line": True, "blocks": True,
            })
    for c in disruptions["closed"]:
        sid = c["station"]
        if sid not in name_of or (c["route"] and c["route"] not in station_lines.get(sid, [])):
            continue
        role = roles.get(sid, "pass-through")
        issues.append({
            "kind": "closure", "station_id": sid, "station": name_of[sid], "role": role,
            "lines": [c["route"]] if c["route"] else station_lines.get(sid, []),
            "effect": c["effect"], "alert": c["alert"], "alert_id": c["alert_id"],
            "serves_your_line": True, "blocks": role != "pass-through",
        })

    # One entry per (alert, station): an alert can list a station under several routes
    unique = {}
    for p in issues:
        unique.setdefault((p["alert_id"], p["station_id"], p["role"]), p)
    issues = list(unique.values())
    blocking = [p for p in issues if p["blocks"]]
    return {"ok": True, "safe": len(blocking) == 0,
            "blocking": blocking, "all_issues": issues}
