"""Call the TransitWise MCP server as a client would:  py -3.12 scripts/mcp_client_example.py"""
import asyncio
import sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

server = StdioServerParameters(command=sys.executable, args=[str(Path(__file__).resolve().parents[1] / "mcp_server.py")])


async def main():
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Tools:", [t.name for t in tools.tools])

            result = await session.call_tool(
                "plan_route", {"origin": "Harvard", "destination": "Back Bay"})
            print("\nplan_route:\n", result.content[0].text[:500])

            result = await session.call_tool(
                "check_route", {"origin": "Harvard", "destination": "Back Bay"})
            print("\ncheck_route:\n", result.content[0].text[:500])

            result = await session.call_tool(
                "search_mbta_policy", {"question": "elevator out at Downtown Crossing"})
            print("\nsearch_mbta_policy:\n", result.content[0].text[:500])


asyncio.run(main())