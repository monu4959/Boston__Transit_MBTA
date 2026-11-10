# TransitWise Boston: Data Model

TransitWise stores its data in **Snowflake**, in the database `TRANSITWISE_DB`, organized into three layers:

| Schema | Purpose |
|---|---|
| `RAW` | Data loaded from the MBTA V3 API |
| `CLEAN` | SQL views built from RAW data |
| `RAG` | MBTA policy documents, split into passages with vector embeddings |

![TransitWise ER diagram](TransitWise_ER_Diagram.png)

## ER diagram (as code)

```mermaid
erDiagram
    RAW_ROUTES ||--o{ RAW_ROUTE_STOPS : "serves"
    RAW_STATIONS ||--o{ RAW_ROUTE_STOPS : "on line"
    RAW_STATIONS ||--o{ RAW_FACILITIES : "has"
    RAW_STATIONS ||--o{ RAW_PLATFORMS : "has"
    RAW_ROUTES ||--o{ RAW_PLATFORMS : "stops at"
    RAW_FACILITIES }o--o{ RAW_ALERTS_HISTORY : "affected by"
    RAW_STATIONS }o--o{ RAW_ALERTS_HISTORY : "affected by"
    RAW_ROUTES }o--o{ RAW_ALERTS_HISTORY : "affected by"
    RAW_STATIONS ||--o{ CLEAN_CURRENT_ELEVATOR_OUTAGES : "summarized in"

    RAW_ROUTES {
        string ROUTE_ID PK
        string LONG_NAME
        int ROUTE_TYPE
    }
    RAW_STATIONS {
        string STATION_ID PK
        string NAME
        float LATITUDE
        float LONGITUDE
        int WHEELCHAIR_BOARDING
    }
    RAW_ROUTE_STOPS {
        string ROUTE_ID PK,FK
        int STOP_SEQUENCE PK
        string STATION_ID FK
    }
    RAW_FACILITIES {
        string FACILITY_ID PK
        string TYPE
        string LONG_NAME
        string STATION_ID FK
    }
    RAW_PLATFORMS {
        string STATION_ID FK
        string ROUTE_ID PK,FK
        int DIRECTION_ID PK
        string STOP_ID PK
        string PLATFORM_NAME
    }
    RAW_ALERTS_HISTORY {
        string ID PK
        timestamp LOADED_AT PK
        string EFFECT
        string FACILITY_IDS
        string STATION_IDS
        string ROUTE_IDS
    }
    CLEAN_CURRENT_ELEVATOR_OUTAGES {
        string STATION_ID FK
        string STATION
        string ELEVATOR
        string HEADER
    }
    RAG_POLICY_CHUNKS {
        string SOURCE PK
        int CHUNK_NO PK
        string CHUNK
        vector EMBEDDING
    }
```

## Tables

### RAW layer

**`ROUTES`**: subway, light rail, and commuter rail lines
| Key | Column | Type |
|---|---|---|
| PK | ROUTE_ID | string |
| | LONG_NAME | string |
| | ROUTE_TYPE | int |

**`STATIONS`**: 257 stations; the hub table
| Key | Column | Type |
|---|---|---|
| PK | STATION_ID | string |
| | NAME | string |
| | LATITUDE | float |
| | LONGITUDE | float |
| | WHEELCHAIR_BOARDING | int |

**`ROUTE_STOPS`**: stations on each line, in order
| Key | Column | Type |
|---|---|---|
| PK, FK → ROUTES | ROUTE_ID | string |
| PK | STOP_SEQUENCE | int |
| FK → STATIONS | STATION_ID | string |

**`FACILITIES`**: elevators, escalators, and boarding lifts
| Key | Column | Type |
|---|---|---|
| PK | FACILITY_ID | string |
| | TYPE | string |
| | LONG_NAME | string |
| FK → STATIONS | STATION_ID | string |

**`PLATFORMS`**: which platform a rider uses at each station, per line and direction
| Key | Column | Type |
|---|---|---|
| FK → STATIONS | STATION_ID | string |
| PK, FK → ROUTES | ROUTE_ID | string |
| PK | DIRECTION_ID | int (0 or 1) |
| PK | STOP_ID | string (platform, e.g. `70078`) |
| | PLATFORM_NAME | string (e.g. `Alewife`) |

Elevator alerts list the platform stop IDs an elevator serves, so the Checker matches them
against the rider's platforms instead of blocking every rider at the station.

**`ALERTS_HISTORY`**: append-only alert snapshots from the pipeline
| Key | Column | Type |
|---|---|---|
| PK | ID | string |
| PK | LOADED_AT | timestamp |
| | EFFECT | string |
| | FACILITY_IDS | comma-separated list |
| | STATION_IDS | comma-separated list |
| | ROUTE_IDS | comma-separated list |

### CLEAN layer

**`CURRENT_ELEVATOR_OUTAGES`** (view): elevators out of service in the latest snapshot
| Key | Column | Type |
|---|---|---|
| FK → STATIONS | STATION_ID | string |
| | STATION | string |
| | ELEVATOR | string |
| | HEADER | string |

### RAG layer

**`POLICY_CHUNKS`**: MBTA policy passages, searched by meaning
| Key | Column | Type |
|---|---|---|
| PK | SOURCE | string |
| PK | CHUNK_NO | int |
| | CHUNK | text |
| | EMBEDDING | VECTOR(FLOAT, 384) |

## Relationships

| From | To | Type |
|---|---|---|
| ROUTES | ROUTE_STOPS | One-to-many |
| STATIONS | ROUTE_STOPS | One-to-many |
| STATIONS | FACILITIES | One-to-many |
| STATIONS, ROUTES | PLATFORMS | One-to-many |
| ROUTES, STATIONS, FACILITIES | ALERTS_HISTORY | Many-to-many, through ID lists |
| ALERTS_HISTORY + STATIONS | CURRENT_ELEVATOR_OUTAGES | Feed the view |

`POLICY_CHUNKS` has no key relationships. It is searched by vector similarity.

## How the tables are created

| Table | Created by | Load pattern |
|---|---|---|
| Database and schemas | `sql/01_setup.sql` | One time |
| ROUTES, STATIONS, ROUTE_STOPS, PLATFORMS, FACILITIES | `pipeline/build_db.py` (MBTA API → pandas → `write_pandas`) | Refreshed by overwrite |
| ALERTS_HISTORY | `pipeline/load_alerts.py` on GitHub Actions | Appended every 30 minutes |
| CURRENT_ELEVATOR_OUTAGES | `sql/02_clean_views.sql` | Recomputed on every query |
| POLICY_CHUNKS | `pipeline/build_db.py` (`policy_docs/*.pdf` → page chrome removed → MiniLM embeddings) | Rebuilt on every run |

## Notes

- Only key columns are shown; some tables have additional columns.
- Keys are logical. Snowflake records but does not enforce them; the code joins on these keys.
- `ALERTS_HISTORY` repeats an alert in every snapshot while it is active, so its key is `ID` + `LOADED_AT`.
- ID list columns are split with `SPLIT_TO_TABLE` in the CLEAN view. `STATION_IDS` also includes platform and entrance IDs; only `place-` IDs match `STATIONS`.
- Alert snapshots before 2026-10-23 have empty ID columns.
- The Checker agent reads live alerts from the MBTA API (elevators, escalators, suspensions, shuttles
  and closures). The CLEAN view is used for analysis and reporting.
- Live status never comes from `POLICY_CHUNKS`: the saved snapshots of live-status pages were moved
  to `policy_docs/archive/` and are not indexed.

## Tests

`tests/` runs the agents offline on a snapshot of the real network and of real MBTA alerts
(`tests/fixtures/`, made by `py -3.12 tests/make_fixtures.py`):

```
py -3.12 -m pytest tests            # offline: no Snowflake, MBTA or LLM calls
TW_LIVE=1 py -3.12 -m pytest tests  # also runs the LLM parser tests
```
