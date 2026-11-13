# Door-to-door trips

The app's **Door to door** screen plans step-free trips from an address, a place, a station, or the
rider's current location, using rolling, buses, subway, Commuter Rail and ferries. The
**Station to station** screen is unchanged.

## How a trip is planned

| Step | What happens | Code |
|---|---|---|
| 1. Understand | Typed request → start, destination, preferences. "My location" comes from the browser. | `agents/request_parser.py` (`parse_trip_request`) |
| 2. Find the places | Station name, "lat, lon", or an address (OpenStreetMap Nominatim, Boston area only) | `agents/places.py` |
| 3. Suggest | OpenTripPlanner in wheelchair mode, two searches (balanced, less rolling), merged and ranked: rolling counts double, transfers cost 5 min (15 if the rider wants fewer), rolls over the rider's limit cost extra | `agents/otp.py` |
| 4. Check | Every leg against live MBTA alerts: elevators on the platform or stop used (boarding, getting off, changing), suspensions on the stretch ridden, closed/moved/detoured stops where the rider boards or gets off | `agents/checker.py` (`check_door_trip`) |
| 5. Reroute | Follow-up searches that leave out the route at fault (OTP can leave out routes, not stops) | `agents/door_to_door.py` |
| 6. Explain | Claude explanation with policy citations and the same guardrails as station to station | `agents/door_to_door.py` |
| 7. Watch | Live times of each remaining leg, missed connections, cancelled trips, new alerts, replanning from where the rider is | `agents/monitor.py` (`check_door_watch`) |

OpenTripPlanner reads MBTA's timetable (including in-station elevator paths and planned shuttle
buses), MBTA's live trip updates, and OpenStreetMap sidewalks. It does not know about broken
elevators, which is why every trip goes through the Checker.

## Running it

```
py -3.12 otp/setup_otp.py all       # first time: download, clip the map, build, serve (~5 min, Docker)
py -3.12 otp/setup_otp.py refresh   # weekly: new MBTA timetable, rebuild, restart
py -3.12 -m streamlit run app.py
```

Data lives in `OTP_DATA_DIR` (default `~/transitwise-otp`, outside OneDrive). The app finds OTP at
`OTP_URL` (default `http://localhost:8080/otp/gtfs/v1`). "Use my current location" needs
`streamlit-js-eval` and works on localhost or https.

MCP: `plan_door_to_door(origin, destination, depart_at, max_roll_minutes, fewer_transfers)`.

## Tests and evaluation

```
py -3.12 -m pytest tests                      # offline, on recorded OTP answers + alerts
py -3.12 tests/make_otp_fixtures.py           # re-record (needs OTP running)
TW_OTP=1 py -3.12 -m pytest tests             # also hits the live OTP server
py -3.12 otp/sweep_door_to_door.py 300        # random trips with today's live data
```

Sweep on 2026-11-13 (300 random trips, 2–12 km, live alerts): a step-free trip for 100%; 5% of usual
trips hit a live problem (13 elevator outages, 3 suspensions) and all 16 were rerouted; median
58 min, 13 min rolling, 2 transfers; 68% within the 10/20-minute rolling limits; 96% use live
times; 0.27 s median per trip (without the LLM explanation).

## Known limits

- Rolling routes come from OpenStreetMap and may miss broken curb cuts, construction or steep
  sidewalks.
- Alerts are the ones active now. A trip planned for later is checked against today's alerts.
- The map covers the MBTA bus and subway area; far Commuter Rail ends are outside it.
- OTP cannot leave out a single stop, only a whole route, so some reroutes are longer than needed.
- OTP doesn't allow getting off at Revere Beach in wheelchair mode (cause not yet found).
- 480 bus stops have unknown accessibility in MBTA data; OTP's wheelchair mode decides how to treat them.
