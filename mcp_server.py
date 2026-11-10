import os
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

from agents.db import get_connection
from agents.planner import planner_agent
from agents.checker import checker_agent, get_live_alerts, access_alerts, service_disruptions
from agents.retriever import search_policies

mcp = FastMCP("transitwise")
MBTA_KEY = os.getenv("MBTA_KEY") or os.getenv("MBTA_API_KEY")
_conn = None


def conn():
    global _conn
    if _conn is None:
        _conn = get_connection()
    return _conn


@mcp.tool()
def plan_route(origin: str, destination: str, avoid: list[str] | None = None) -> dict:
    """Find a step-free MBTA subway route between two stations (ignores live alerts).
    Optionally stay away from station IDs such as 'place-dwnxg' (Downtown Crossing);
    if that's impossible, the route may pass through them (listed in passes_through_avoided)."""
    if not origin.strip() or not destination.strip():
        return {"ok": False, "reason": "Origin and destination are required."}
    return planner_agent(conn(), origin.strip(), destination.strip(), exclude=(avoid or [])[:10])


@mcp.tool()
def check_route(origin: str, destination: str) -> dict:
    """Plan a route and check it against live MBTA elevator/escalator outages and service
    changes (suspensions, shuttles, closures). Returns whether the trip is safe, any blocking
    problems, and a route that avoids suspended segments and closed stops."""
    if not origin.strip() or not destination.strip():
        return {"ok": False, "reason": "Origin and destination are required."}
    plan = planner_agent(conn(), origin.strip(), destination.strip())
    if not plan["ok"]:
        return plan
    try:
        alerts = get_live_alerts(MBTA_KEY)
    except Exception:
        return {"route": plan["stations"],
                "error": "Live outage data unavailable. Check mbta.com/alerts/access."}
    result = {"route": plan["stations"], "check": checker_agent(plan, MBTA_KEY, alerts=alerts)}
    live = planner_agent(conn(), origin.strip(), destination.strip(),
                         disruptions=service_disruptions(alerts))
    if live["ok"] and live["path"] != plan["path"]:
        result["route_with_service_changes"] = live["stations"]
    return result


@mcp.tool()
def get_accessibility_alerts(limit: int = 20) -> list[dict]:
    """List current MBTA elevator and escalator outage alerts (max 50)."""
    limit = max(1, min(limit, 50))
    alerts = access_alerts(get_live_alerts(MBTA_KEY))[:limit]
    return [{"effect": a["attributes"]["effect"], "header": a["attributes"]["header"]}
            for a in alerts]


@mcp.tool()
def search_mbta_policy(question: str, k: int = 4) -> list[dict]:
    """Search official MBTA accessibility policy documents (max 10 results).
    Returns the most relevant passages with their source files."""
    if not question.strip():
        return []
    k = max(1, min(k, 10))
    return search_policies(conn(), question.strip()[:500], k=k)


if __name__ == "__main__":
    # Load the embedding model before serving: loading it lazily inside a tool call
    # (which runs in a worker thread) hangs the server on Windows.
    from agents.retriever import get_model
    get_model()
    mcp.run()
    #py -3.12 mcp_server.py