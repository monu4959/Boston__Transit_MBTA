import os
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

from agents.db import get_connection
from agents.planner import planner_agent
from agents.checker import checker_agent, get_live_alerts
from agents.retriever import search_policies

mcp = FastMCP("transitwise")
MBTA_KEY = os.getenv("MBTA_KEY")
_conn = None


def conn():
    global _conn
    if _conn is None:
        _conn = get_connection()
    return _conn


@mcp.tool()
def plan_route(origin: str, destination: str, avoid: list[str] | None = None) -> dict:
    """Find a step-free MBTA subway route between two stations.
    Optionally avoid station IDs such as 'place-dwnxg' (Downtown Crossing)."""
    if not origin.strip() or not destination.strip():
        return {"ok": False, "reason": "Origin and destination are required."}
    return planner_agent(conn(), origin.strip(), destination.strip(), avoid=(avoid or [])[:10])


@mcp.tool()
def check_route(origin: str, destination: str) -> dict:
    """Plan a route and check it against live MBTA elevator and escalator outages.
    Returns whether the trip is safe and any blocking problems."""
    if not origin.strip() or not destination.strip():
        return {"ok": False, "reason": "Origin and destination are required."}
    plan = planner_agent(conn(), origin.strip(), destination.strip())
    if not plan["ok"]:
        return plan
    try:
        return {"route": plan["stations"], "check": checker_agent(plan, MBTA_KEY)}
    except Exception:
        return {"route": plan["stations"],
                "error": "Live outage data unavailable. Check mbta.com/alerts/access."}


@mcp.tool()
def get_accessibility_alerts(limit: int = 20) -> list[dict]:
    """List current MBTA elevator and escalator outage alerts (max 50)."""
    limit = max(1, min(limit, 50))
    alerts = get_live_alerts(MBTA_KEY)[:limit]
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