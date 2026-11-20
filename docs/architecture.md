# TransitWise Boston: Architecture

## System architecture

```mermaid
flowchart TD
    API[MBTA V3 API<br/>alerts, routes, stops, facilities]
    RT[MBTA GTFS-Realtime<br/>trip updates, vehicle positions]
    GTFS[MBTA GTFS + OpenStreetMap]
    DOCS[MBTA policy PDFs<br/>accessibility, shuttles, The RIDE]
    PIPE[Alert pipeline<br/>pipeline/load_alerts.py, GitHub Actions every 30 min]
    BUILD[Database build<br/>pipeline/build_db.py: reference tables, policy chunks + embeddings]
    SF[(Snowflake<br/>RAW, CLEAN, RAG, LOGS)]
    OTP[OpenTripPlanner 2.10<br/>wheelchair routing, otp/setup_otp.py]
    WEB[Website<br/>web/server.py + web/static]
    PLACES[Places<br/>agents/places.py]
    PARSE[Request parser<br/>agents/request_parser.py]
    D2D[Door-to-door Replanner<br/>agents/door_to_door.py]
    CHECK[Checker<br/>agents/checker.py]
    RET[Policy search<br/>agents/retriever.py]
    LLM[Claude API + guardrails<br/>agents/llm.py, agents/replanner.py]
    MON[Monitor<br/>agents/monitor.py]
    MCP[MCP server<br/>mcp_server.py]

    API --> PIPE --> SF
    API --> BUILD
    DOCS --> BUILD --> SF
    GTFS --> OTP
    RT -. live times .-> OTP
    WEB --> PLACES
    WEB --> PARSE
    WEB --> D2D
    WEB --> MON
    D2D --> OTP
    D2D --> CHECK
    API -. live alerts .-> CHECK
    D2D --> RET --> LLM
    SF --> RET
    D2D -. trip log .-> SF
    MON --> OTP
    MON --> CHECK
    MCP --> D2D
    MCP --> CHECK
    MCP --> RET
```

The station-to-station planner (`agents/planner.py`, a NetworkX graph built from the Snowflake
tables) came first. It still backs the MCP `plan_route` and `check_route` tools and the older
Streamlit app in `streamlit_app/`; the website plans door to door with OpenTripPlanner.

## Data architecture

| Layer | Components |
|---|---|
| Sources | MBTA V3 API; MBTA GTFS and GTFS-Realtime; OpenStreetMap; MBTA policy PDFs in `policy_docs/` |
| Ingestion | `pipeline/load_alerts.py` (GitHub Actions, every 30 minutes); `pipeline/build_db.py` for reference tables and policy chunks; `otp/setup_otp.py` for the routing graph |
| Storage | Snowflake `TRANSITWISE_DB`: `RAW` (as loaded), `CLEAN` (SQL views), `RAG` (policy chunks with embeddings), `LOGS` (one row per planned trip) |
| Consumption | Website, Door-to-door Replanner, Checker, Monitor, policy search; MCP tools |

The data model is in [docs/README.md](README.md).
