import time
from agents import checker as checker_module
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


def monitor_trip(conn, trip, mbta_key, interval_sec=120, max_checks=10, on_event=print):
    """Keep re-checking the trip every interval_sec seconds."""
    for i in range(max_checks):
        event = check_trip(conn, trip, mbta_key)
        on_event(event)
        if i < max_checks - 1:
            time.sleep(interval_sec)
    return trip["history"]
