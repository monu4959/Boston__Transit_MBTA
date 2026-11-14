import time
from datetime import datetime, timezone

from agents import checker as checker_module
from agents import otp
from agents.planner import planner_agent
from agents.checker import checker_agent
from agents.replanner import replanner_agent, _ids, _route_key


def start_trip(conn, origin, dest, mbta_key, plan=None, transfer_penalty=None, avoid_names=None):
    """Start watching a trip. Pass `plan` (the route the rider is actually taking, e.g. the
    Replanner's recommended route) so the Monitor checks that route, not the usual one."""
    if plan is None:
        plan = planner_agent(conn, origin, dest, exclude=_ids(conn, avoid_names),
                             transfer_penalty=transfer_penalty)
    if not plan.get("ok"):
        return {"ok": False, "reason": plan.get("reason", "No route to monitor")}

    check = checker_agent(plan, mbta_key)
    return {
        "ok": True,
        "origin": origin,
        "dest": dest,
        "plan": plan,
        "prefs": {"transfer_penalty": transfer_penalty, "avoid_names": avoid_names},
        "known_alerts": {p["alert_id"] for p in check["blocking"]},
        "history": [],
    }


def demo_outage(plan):
    """A made-up elevator outage on the watched route, for demos: at the first transfer,
    or at the destination when there is no transfer. Uses the rider's own platforms."""
    sid = (plan.get("transfer_ids") or [plan["path"][-1]])[0]
    name = plan["stations"][plan["path"].index(sid)]
    use = plan.get("platform_use", {}).get(sid, {})
    stops = [sid] + use.get("in", []) + use.get("out", [])
    links = plan.get("transfer_elevators", {}).get(sid, [])   # close the platform-to-platform ones too
    return {"id": f"demo-{sid}", "attributes": {
        "effect": "ELEVATOR_CLOSURE",
        "header": f"(Demo) {name} elevators to your platforms are unavailable.",
        "informed_entity": [{"stop": s} for s in stops]
                           + [{"stop": sid, "facility": e["facility_id"]} for e in links]}}


def check_trip(conn, trip, mbta_key, simulate=False):
    """Re-check the watched route once. If a NEW blocking problem appeared, replan with the
    rider's preferences and start watching the new route."""
    alerts = checker_module.get_live_alerts(mbta_key)
    if simulate:
        alerts = alerts + [demo_outage(trip["plan"])]
    check = checker_agent(trip["plan"], mbta_key, alerts=alerts)
    current = {p["alert_id"]: p for p in check["blocking"]}

    new_problems = [p for aid, p in current.items() if aid not in trip["known_alerts"]]
    resolved = [aid for aid in trip["known_alerts"] if aid not in current]
    trip["known_alerts"] = set(current.keys())

    event = {
        "time": time.strftime("%H:%M:%S"),
        "new_problems": new_problems,
        "resolved": resolved,
        "replan": None,
        "switched_to": None,
    }
    if new_problems:
        replan = replanner_agent(conn, trip["origin"], trip["dest"], mbta_key, log_source="monitor",
                                 alerts=alerts, **trip.get("prefs", {}))
        event["replan"] = replan
        better = None
        if replan.get("ok"):
            better = replan.get("new_plan") if replan.get("changed") else replan.get("plan")
        if better and _route_key(better) != _route_key(trip["plan"]):
            trip["plan"] = better
            event["switched_to"] = better["stations"]
            trip["known_alerts"] = {p["alert_id"] for p in
                                    checker_agent(better, mbta_key, alerts=alerts)["blocking"]}

    trip["history"].append(event)
    return event


# ---------- Door-to-door trips (agents/door_to_door.py) ----------

MIN_CONNECTION_S = 60      # less than this to make a connection = likely missed


def _t(iso):
    return datetime.fromisoformat(iso)


def start_door_trip(result):
    """Start watching the recommended trip from plan_door_to_door()."""
    trip = result.get("trip")
    if not result.get("ok") or not trip:
        return {"ok": False, "reason": result.get("reason", "No step-free trip to monitor")}
    return {"ok": True, "kind": "door_to_door", "origin": result["origin"], "dest": result["dest"],
            "prefs": result.get("prefs"), "trip": trip,
            "known_alerts": {p["alert_id"] for p in trip.get("check", {}).get("blocking", [])},
            "history": []}


def demo_door_outage(trip):
    """A made-up elevator outage for demos, on the rider's own platform: at the first station
    (not a street bus stop) where the rider changes, else gets off, else boards."""
    from agents import planner
    points = checker_module._points(trip)
    at_station = [p for p in points if (p["station_id"] or "").startswith("place-")]
    pt = next((p for role in ("transfer", "exit", "board") for p in at_station if p["role"] == role),
              next((p for p in points if p["role"] == "transfer"), points[-1]))
    stops = [p["stop_id"] for p in points if p["station_id"] == pt["station_id"] and p["role"] == pt["role"]]
    links = []        # close the direct platform-to-platform elevators too
    if pt["role"] == "transfer" and planner._cache is not None and len(stops) > 1 \
            and "platform_names" in planner._cache[0].graph:
        links = planner._transfer_elevators(planner._cache[0], pt["station_id"], stops[:1], stops[1:])
    return {"id": f"demo-{pt['station_id']}", "attributes": {
        "effect": "ELEVATOR_CLOSURE",
        "header": f"(Demo) {pt['name']} elevators to your platforms are unavailable.",
        "informed_entity": [{"stop": s} for s in [pt["station_id"], *stops]]
                           + [{"stop": pt["station_id"], "facility": e["facility_id"]} for e in links]}}


def connection_risks(trip):
    """Connections the rider is now likely to miss, from the latest live times."""
    risks, legs = [], trip["legs"]
    transit = [i for i, l in enumerate(legs) if l["transit"]]
    for a, b in zip(transit, transit[1:]):
        roll_s = sum(legs[k]["minutes"] * 60 for k in range(a + 1, b) if legs[k]["mode"] == "ROLL")
        slack = (_t(legs[b]["start"]) - _t(legs[a]["end"])).total_seconds() - roll_s
        if slack < MIN_CONNECTION_S:
            risks.append({
                "kind": "timing", "station_id": legs[b]["from"]["station_id"] or legs[b]["from"]["stop_id"],
                "station": legs[b]["from"]["name"], "role": "transfer", "lines": [legs[b]["route_id"]],
                "effect": "MISSED_CONNECTION", "blocks": True, "serves_your_line": True,
                "alert_id": f"timing-{legs[b]['trip_id']}",
                "alert": (f"Your {legs[a]['route_name']} now arrives {legs[a]['end'][11:16]}, leaving "
                          f"{max(0, round(slack))} s to reach the {legs[b]['route_name']} "
                          f"leaving {legs[b]['start'][11:16]}.")})
    return risks


def _refresh(trip, now):
    """Update live times of legs not finished yet. Returns problems for trips that disappeared."""
    problems = []
    for i, leg in enumerate(trip["legs"]):
        if not leg["transit"] or _t(leg["end"]) < now:
            continue
        new = otp.refresh_leg(leg)
        if new is None:
            problems.append({"kind": "timing", "station_id": leg["from"]["station_id"] or leg["from"]["stop_id"],
                             "station": leg["from"]["name"], "role": "board", "lines": [leg["route_id"]],
                             "effect": "TRIP_NOT_FOUND", "blocks": True, "serves_your_line": True,
                             "alert_id": f"gone-{leg['trip_id']}",
                             "alert": f"The {leg['route_name']} you planned to take is no longer in the "
                                      "live schedule (it may be cancelled)."})
        else:
            trip["legs"][i] = new
    trip["departs"], trip["arrives"] = trip["legs"][0]["start"], trip["legs"][-1]["end"]
    return problems


def _restart_point(watch, now, current):
    """Where a replan starts: the rider's location if known, else the next leg's start."""
    if current:
        return {"name": "Your location", "lat": current[0], "lon": current[1]}
    trip = watch["trip"]
    if now < _t(trip["departs"]):
        return watch["origin"]
    nxt = next((l for l in trip["legs"] if _t(l["end"]) > now), trip["legs"][-1])
    return {"name": nxt["from"]["name"], "lat": nxt["from"]["lat"], "lon": nxt["from"]["lon"]}


def check_door_watch(conn, watch, mbta_key, simulate=False, now=None, current=None):
    """Re-check the watched door-to-door trip once: live times (missed connections, cancelled
    trips) and alerts. On a NEW problem, replan from where the rider is and switch if better."""
    from agents.door_to_door import plan_door_to_door
    now = now or datetime.now(timezone.utc).astimezone()
    trip = watch["trip"]
    alerts = checker_module.get_live_alerts(mbta_key)
    if simulate:
        alerts = alerts + [demo_door_outage(trip)]
    event = {"time": time.strftime("%H:%M:%S"), "new_problems": [], "resolved": [], "replan": None,
             "switched_to": None, "live_times": True}
    try:
        gone = _refresh(trip, now)
    except otp.OTPUnavailable:
        gone, event["live_times"] = [], False
    check = checker_module.check_door_trip(trip, alerts, watch.get("prefs"))
    current_ = {p["alert_id"]: p for p in check["blocking"] + gone + connection_risks(trip)}
    event["new_problems"] = [p for aid, p in current_.items() if aid not in watch["known_alerts"]]
    event["resolved"] = [aid for aid in watch["known_alerts"] if aid not in current_]
    watch["known_alerts"] = set(current_)

    if event["new_problems"]:
        start = _restart_point(watch, now, current)
        replan = plan_door_to_door(conn, start, watch["dest"], mbta_key, prefs=watch.get("prefs"),
                                   alerts=alerts, log_source="monitor-d2d")
        event["replan"] = replan
        better = replan.get("trip") if replan.get("ok") else None
        if better and better["key"] != trip["key"]:
            watch["trip"] = better
            event["switched_to"] = better
            watch["known_alerts"] = {p["alert_id"] for p in better["check"]["blocking"]}
    watch["history"].append(event)
    return event


def monitor_trip(conn, trip, mbta_key, interval_sec=120, max_checks=10, on_event=print):
    """Keep re-checking the trip every interval_sec seconds."""
    for i in range(max_checks):
        event = check_trip(conn, trip, mbta_key)
        on_event(event)
        if i < max_checks - 1:
            time.sleep(interval_sec)
    return trip["history"]
