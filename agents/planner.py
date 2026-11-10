import math
import re
import networkx as nx
from agents.db import query_df

_cache = None

SPEED_KM_PER_MIN = 0.5   # ~30 km/h average train speed
DWELL_MIN = 0.5          # time stopped at each station
TRANSFER_MIN = 5.0       # walking + waiting when changing lines

# Red Line data lists both branches as one chain; these consecutive pairs are fake links
RED_FAKE_LINKS = [{"place-asmnl", "place-nqncy"}, {"place-brntn", "place-shmnl"}]


def _km(a, b):
    """Straight-line distance in km between two (lat, lon) points."""
    lat1, lon1, lat2, lon2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(h))


def _ride_minutes(a, b, coords):
    if a in coords and b in coords:
        return _km(coords[a], coords[b]) / SPEED_KM_PER_MIN + DWELL_MIN
    return 2.0


def _optional(conn, sql):
    """Tables added later (PLATFORMS, FACILITIES) are optional: older databases still work."""
    try:
        return query_df(conn, sql)
    except Exception:
        return None


def build_graph(conn):
    stops = query_df(conn, """
        SELECT rs.ROUTE_ID, rs.STOP_SEQUENCE, rs.STATION_ID, rs.STATION_NAME
        FROM ROUTE_STOPS rs
        JOIN ROUTES r ON r.ROUTE_ID = rs.ROUTE_ID
        WHERE r.ROUTE_TYPE IN (0, 1)
        ORDER BY rs.ROUTE_ID, rs.STOP_SEQUENCE
    """)
    stations = query_df(conn, "SELECT * FROM STATIONS")
    wc_col = [c for c in stations.columns if c.startswith("WHEELCHAIR")][0]
    accessible = dict(zip(stations["STATION_ID"], stations[wc_col].astype(str) == "1"))
    coords = {r.STATION_ID: (float(r.LATITUDE), float(r.LONGITUDE))
              for r in stations.itertuples() if r.LATITUDE is not None}
    names = dict(zip(stops["STATION_ID"], stops["STATION_NAME"]))

    G = nx.Graph()
    lines_at = {}
    seq = {}   # route -> {station: position in direction 0}

    # Ride edges: consecutive stops on the same line
    for route, group in stops.groupby("ROUTE_ID"):
        ids = group["STATION_ID"].tolist()
        seq[route] = {s: i for i, s in enumerate(ids)}
        for s in ids:
            lines_at.setdefault(s, set()).add(route)
        for a, b in zip(ids, ids[1:]):
            if route == "Red" and {a, b} in RED_FAKE_LINKS:
                continue
            G.add_edge((a, route), (b, route), kind="ride",
                       minutes=_ride_minutes(a, b, coords))

    # Red Line branches both start at JFK/UMass
    for branch_start in ["place-nqncy", "place-shmnl"]:
        G.add_edge(("place-jfk", "Red"), (branch_start, "Red"), kind="ride",
                   minutes=_ride_minutes("place-jfk", branch_start, coords))

    # Transfer edges: changing lines inside the same station
    for s, lines in lines_at.items():
        lines = sorted(lines)
        for i in range(len(lines)):
            for j in range(i + 1, len(lines)):
                G.add_edge((s, lines[i]), (s, lines[j]), kind="transfer", minutes=TRANSFER_MIN)

    # Platform data: which platform a rider uses per (station, line, direction)
    platforms, platform_names = {}, {}
    pf = _optional(conn, "SELECT STATION_ID, ROUTE_ID, DIRECTION_ID, STOP_ID, PLATFORM_NAME FROM PLATFORMS")
    for r in (pf.itertuples() if pf is not None else []):
        platforms.setdefault((r.STATION_ID, r.ROUTE_ID, int(r.DIRECTION_ID)), set()).add(r.STOP_ID)
        platform_names[r.STOP_ID] = r.PLATFORM_NAME
    elevators = {}
    fc = _optional(conn, "SELECT FACILITY_ID, STATION_ID, LONG_NAME FROM FACILITIES WHERE TYPE = 'ELEVATOR'")
    for r in (fc.itertuples() if fc is not None else []):
        elevators.setdefault(r.STATION_ID, []).append((str(r.FACILITY_ID), r.LONG_NAME or ""))

    G.graph.update(seq=seq, platforms=platforms, platform_names=platform_names, elevators=elevators)
    return G, names, accessible, lines_at


def _remove_transfers(graph, station, lines_at, only_line=None):
    lines = sorted(lines_at.get(station, []))
    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            if only_line and only_line not in (lines[i], lines[j]):
                continue
            if graph.has_edge((station, lines[i]), (station, lines[j])):
                graph.remove_edge((station, lines[i]), (station, lines[j]))


def _direction(G, line, a, b):
    """0 or 1: MBTA direction of travel when riding `line` from station a to b."""
    order = G.graph["seq"].get(line, {})
    if a in order and b in order:
        return 0 if order[b] > order[a] else 1
    return None


def _platform_sides(long_name):
    """'... Elevator 998 (Oak Grove platform to Alewife platform)' -> ({'oak grove'}, {'alewife'})."""
    m = re.search(r"\(([^()]*?) platforms? to ([^()]*?) platforms?\)", long_name, re.I)
    if not m:
        return None
    split = lambda s: {x.strip().lower() for x in re.split(r",| and ", s) if x.strip()}
    return split(m.group(1)), split(m.group(2))


def _transfer_elevators(G, station, in_stops, out_stops):
    """Elevators that link the arrival platform directly to the departure platform."""
    pn = G.graph["platform_names"]
    arrive = {(pn.get(s) or "").lower() for s in in_stops} - {""}
    depart = {(pn.get(s) or "").lower() for s in out_stops} - {""}
    links = []
    for fid, long_name in G.graph["elevators"].get(station, []):
        sides = _platform_sides(long_name)
        if sides and ((arrive & sides[0] and depart & sides[1]) or (arrive & sides[1] and depart & sides[0])):
            links.append({"facility_id": fid, "name": long_name})
    return links


def _describe(G, nodes, names):
    """Legs, ride edges and platform use for a node path [(station, line), ...]."""
    legs, ride_edges = [], []
    for (a, la), (b, lb) in zip(nodes, nodes[1:]):
        if a == b or la != lb:
            continue                                     # transfer, not a ride
        d = _direction(G, la, a, b)
        ride_edges.append([a, b, la])
        if legs and legs[-1]["line"] == la and legs[-1]["to"] == a and legs[-1]["direction_id"] == d:
            legs[-1]["to"] = b
            legs[-1]["stations"].append(b)
        else:
            legs.append({"line": la, "direction_id": d, "from": a, "to": b, "stations": [a, b]})

    pf, pn = G.graph["platforms"], G.graph["platform_names"]
    use = {}
    for leg in legs:
        out_ = sorted(pf.get((leg["from"], leg["line"], leg["direction_id"]), []))
        in_ = sorted(pf.get((leg["to"], leg["line"], leg["direction_id"]), []))
        use.setdefault(leg["from"], {"in": [], "out": []})["out"] += out_
        use.setdefault(leg["to"], {"in": [], "out": []})["in"] += in_
        toward = sorted({pn.get(s) for s in out_ if pn.get(s)})
        leg["toward"] = " / ".join(toward) if toward else None
        leg["from_name"], leg["to_name"] = names[leg["from"]], names[leg["to"]]
    return legs, ride_edges, use


def planner_agent(conn, origin_name, dest_name, avoid=None, transfer_penalty=None,
                  exclude=None, disruptions=None, blocked_nodes=None):
    """Fastest step-free route.

    avoid:         station IDs where the rider must not change trains (e.g. elevator out);
                   trains may still pass through.
    exclude:       station IDs the rider asked to stay away from entirely. If no route can
                   do that, they are treated like `avoid` and listed in passes_through_avoided.
    disruptions:   from checker.service_disruptions(): suspended segments and closed stops.
    blocked_nodes: (station, line) pairs whose platform can't be used to board, exit or
                   change trains (e.g. the elevator to that platform is out).
    """
    global _cache
    if _cache is None:
        _cache = build_graph(conn)
    G, names, accessible, lines_at = _cache

    lookup = {n.lower(): sid for sid, n in names.items()}
    origin, dest = lookup.get(origin_name.lower()), lookup.get(dest_name.lower())
    if not origin or not dest:
        return {"ok": False, "reason": "Station name not found"}
    if not accessible.get(origin):
        return {"ok": False, "reason": f"{origin_name} is not wheelchair accessible"}
    if not accessible.get(dest):
        return {"ok": False, "reason": f"{dest_name} is not wheelchair accessible"}

    exclude = [s for s in (exclude or []) if s not in (origin, dest)]
    plan = _shortest(G, names, accessible, lines_at, origin, dest, avoid or [], exclude,
                     transfer_penalty, disruptions, set(blocked_nodes or []))
    if not plan["ok"] and exclude:
        # Can't stay away completely: allow riding through, but never changing trains there
        plan = _shortest(G, names, accessible, lines_at, origin, dest, list(avoid or []) + exclude,
                         [], transfer_penalty, disruptions, set(blocked_nodes or []))
        if plan["ok"]:
            plan["passes_through_avoided"] = [names[s] for s in exclude if s in plan["path"]]
    return plan


def _shortest(G, names, accessible, lines_at, origin, dest, avoid, exclude,
              transfer_penalty, disruptions, blocked):
    graph = G.copy()

    # No transfers at inaccessible stations (trains can still pass through)
    for s in lines_at:
        if not accessible.get(s):
            _remove_transfers(graph, s, lines_at)

    # Avoided stations can't be used to transfer, but trains pass through
    for s in avoid:
        if s not in (origin, dest):
            _remove_transfers(graph, s, lines_at)

    # Excluded stations are left out completely
    for s in exclude:
        graph.remove_nodes_from([(s, line) for line in lines_at.get(s, [])])

    # Live service changes: no trains on suspended segments, no stopping at closed stops
    for seg in (disruptions or {}).get("segments", []):
        for a, b, data in list(graph.edges(data=True)):
            if data.get("kind") == "ride" and a[1] == seg["route"] and \
                    (seg["stations"] is None or (a[0] in seg["stations"] and b[0] in seg["stations"])):
                graph.remove_edge(a, b)
    for c in (disruptions or {}).get("closed", []):
        for line in ([c["route"]] if c["route"] else lines_at.get(c["station"], [])):
            blocked.add((c["station"], line))

    # Blocked platforms: no boarding, exiting or changing trains there
    for s, line in blocked:
        _remove_transfers(graph, s, lines_at, only_line=line)

    # Virtual start/end nodes so the rider can board/exit on any open line there
    start_lines = [l for l in lines_at[origin] if (origin, l) not in blocked and graph.has_node((origin, l))]
    end_lines = [l for l in lines_at[dest] if (dest, l) not in blocked and graph.has_node((dest, l))]
    if not start_lines:
        return {"ok": False, "reason": f"No step-free way to board at {names[origin]} right now"}
    if not end_lines:
        return {"ok": False, "reason": f"No step-free way to exit at {names[dest]} right now"}
    for line in start_lines:
        graph.add_edge("START", (origin, line), minutes=0)
    for line in end_lines:
        graph.add_edge((dest, line), "END", minutes=0)

    if transfer_penalty is not None:
        for _, _, data in graph.edges(data=True):
            if data.get("kind") == "transfer":
                data["minutes"] = transfer_penalty
    try:
        nodes = nx.shortest_path(graph, "START", "END", weight="minutes")  # Dijkstra
    except nx.NetworkXNoPath:
        return {"ok": False, "reason": "No step-free route found avoiding those stations"}

    nodes = nodes[1:-1]  # drop START and END
    minutes = sum(G[a][b]["minutes"] for a, b in zip(nodes, nodes[1:]))

    path, station_lines = [], {}
    for s, line in nodes:
        if not path or path[-1] != s:
            path.append(s)
        station_lines.setdefault(s, []).append(line)

    transfer_ids = [nodes[i][0] for i in range(1, len(nodes)) if nodes[i][0] == nodes[i - 1][0]]
    legs, ride_edges, platform_use = _describe(G, nodes, names)
    transfer_elevators = {s: _transfer_elevators(G, s, platform_use.get(s, {}).get("in", []),
                                                 platform_use.get(s, {}).get("out", []))
                          for s in transfer_ids}

    return {
        "ok": True,
        "path": path,
        "stations": [names[s] for s in path],
        "transfers": [names[s] for s in transfer_ids],
        "transfer_ids": transfer_ids,
        "minutes": round(minutes),
        "station_lines": station_lines,
        "legs": legs,
        "ride_edges": ride_edges,
        "platform_use": platform_use,
        "transfer_elevators": transfer_elevators,
    }
