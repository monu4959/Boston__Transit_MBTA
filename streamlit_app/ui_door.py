"""Door-to-door screen of the Streamlit app (app.py calls render())."""
import math
from datetime import datetime
from zoneinfo import ZoneInfo

import pydeck as pdk
import streamlit as st

from agents import otp
from agents.door_to_door import ICONS, clock, leg_line, plan_door_to_door
from agents.monitor import check_door_watch, start_door_trip
from agents.places import CURRENT_LOCATION, resolve_place
from agents.replanner import _ids
from agents.request_parser import THRESHOLD, parse_trip_request

try:
    from streamlit_js_eval import get_geolocation
except ImportError:                       # optional: "use my location" needs streamlit-js-eval
    get_geolocation = None

BOSTON = ZoneInfo("America/New_York")
ROLE = {"board": "where you board", "exit": "where you get off", "transfer": "where you change",
        "no service": "no service", "detour": "detour", "roll": "rolling"}


# ---------- inputs ----------

def _here():
    """(lat, lon) from the browser, or None. Browsers only share location on https or localhost."""
    if get_geolocation is None:
        st.caption("Current location needs the streamlit-js-eval package.")
        return None
    loc = get_geolocation()
    if isinstance(loc, dict) and loc.get("coords"):
        c = loc["coords"]
        st.session_state.d2d_here = (c["latitude"], c["longitude"])
        st.caption(f"Location found (accurate to about {round(c.get('accuracy') or 0)} m).")
    elif isinstance(loc, dict) and loc.get("error"):
        st.warning("Location not available: " + str(loc["error"].get("message", "permission denied")))
    else:
        st.caption("Waiting for location permission in your browser…")
    return st.session_state.get("d2d_here")


def _prefs(fewer, max_roll):
    return {"transfer_penalty": 15.0 if fewer else 5.0, "max_roll_min": float(max_roll),
            "max_total_roll_min": max(20.0, 2.0 * max_roll)}


def _run(conn, key, origin_text, dest_text, prefs, avoid, depart_at, here, source):
    o = resolve_place(origin_text, current=here)
    d = resolve_place(dest_text, current=here)
    bad = [p["reason"] for p in (o, d) if not p["ok"]]
    if bad:
        st.session_state.d2d = {"input_error": " ".join(dict.fromkeys(bad))}
        return
    with st.spinner("Planning step-free trips with live bus and train times, then checking "
                    "elevators, stops and service changes..."):
        result = plan_door_to_door(conn, o, d, key, depart_at=depart_at, prefs=prefs,
                                   avoid_ids=_ids(conn, avoid), log_source=source)
    st.session_state.d2d = result
    st.session_state.pop("d2d_watch", None)


# ---------- output ----------

def _rgb(hex_color, fallback=(120, 120, 120)):
    if not hex_color:
        return list(fallback)
    h = hex_color.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def trip_map(trip, origin, dest):
    paths = [{"path": [[lon, lat] for lat, lon in l["geometry"]], "color": _rgb(l["color"]),
              "width": 7 if l["transit"] else 4, "name": l["route_name"] if l["transit"] else "Roll"}
             for l in trip["legs"] if l["geometry"]]
    stops = [{"pos": [l[e]["lon"], l[e]["lat"]], "name": l[e]["name"], "color": [30, 30, 30]}
             for l in trip["legs"] if l["transit"] for e in ("from", "to")]
    ends = [{"pos": [origin["lon"], origin["lat"]], "name": "Start: " + origin["name"], "color": [0, 140, 70]},
            {"pos": [dest["lon"], dest["lat"]], "name": "End: " + dest["name"], "color": [200, 30, 30]}]
    pts = [p for path in paths for p in path["path"]] + [e["pos"] for e in ends]
    lons, lats = [p[0] for p in pts], [p[1] for p in pts]
    span = max(max(lons) - min(lons), (max(lats) - min(lats)) * 1.3, 0.005)
    zoom = max(10, min(16, 9.6 - math.log2(span / 0.35)))
    st.pydeck_chart(pdk.Deck(
        map_style="light",
        initial_view_state=pdk.ViewState(latitude=(min(lats) + max(lats)) / 2,
                                         longitude=(min(lons) + max(lons)) / 2, zoom=zoom),
        layers=[pdk.Layer("PathLayer", [{**p, "width": p["width"] + 4} for p in paths],   # dark outline
                          get_path="path", get_color=[40, 40, 40], get_width="width",
                          width_units=pdk.types.String("pixels"), width_min_pixels=7, cap_rounded=True, joint_rounded=True),
                pdk.Layer("PathLayer", paths, get_path="path", get_color="color",
                          get_width="width", width_units=pdk.types.String("pixels"), width_min_pixels=4, cap_rounded=True,
                          joint_rounded=True, pickable=True),
                pdk.Layer("ScatterplotLayer", stops + ends, get_position="pos", get_fill_color="color",
                          get_radius=6, radius_units=pdk.types.String("pixels"), pickable=True)],
        tooltip={"text": "{name}"}))


def _leaves_in(trip):
    first = next((l for l in trip["legs"] if l["transit"]), None)
    if not first:
        return ""
    mins = round((datetime.fromisoformat(first["start"]) - datetime.now(BOSTON)).total_seconds() / 60)
    return f" · first ride leaves in {mins} min" if mins >= 0 else ""


def show_trip(trip, heading):
    st.markdown(f"**{heading}**: leave {clock(trip['departs'])}, arrive {clock(trip['arrives'])} "
                f"({trip['minutes']} min, {round(trip['rolling_minutes'])} min rolling, "
                f"{trip['transfers']} transfer{'s' if trip['transfers'] != 1 else ''}){_leaves_in(trip)}")
    for leg in trip["legs"]:
        st.write(f"{ICONS.get(leg['mode'], '•')} {leg_line(leg)}")
    if trip.get("uses_avoided"):
        st.info("No step-free trip avoids the stations you asked to skip; this one still stops there.")


def _issue(p):
    note = f" ({p['note']})" if p.get("note") else ""
    return f"- **{p['station']}** ({ROLE.get(p['role'], p['role'])}): {p['alert']}{note}"


def _summary(t):
    rides = " → ".join(l["route_name"] for l in t["legs"] if l["transit"]) or "roll only"
    return f"{clock(t['departs'])}–{clock(t['arrives'])}: {rides} ({round(t['rolling_minutes'])} min rolling)"


def show_result(conn, key, r):
    st.divider()
    if r.get("input_error"):
        st.error(r["input_error"])
        return
    st.caption(f"From **{r['origin']['name']}** to **{r['dest']['name']}**"
               + (f", leaving {clock(r['depart_at'])}" if r.get("depart_at") else ""))
    if not r["ok"]:
        st.error(r["reason"])
        return
    trip = r["trip"]
    if not r["changed"]:
        st.success("Your trip is clear. No elevator outages, stop changes or service problems affect it.")
    else:
        st.error(f"{len(r['problems'])} problem(s) on the usual trip")
        st.markdown("\n".join(_issue(p) for p in r["problems"]))
        with st.expander("Usual trip (has the problems above)"):
            show_trip(r["usual"], "Usual trip")
        if trip:
            st.success("Step-free alternative found")
        else:
            st.warning("No step-free bus or train trip avoids these problems right now.")
    if trip:
        show_trip(trip, "Recommended trip" if r["changed"] else "Your trip")
        trip_map(trip, r["origin"], r["dest"])
        if r.get("warnings"):
            with st.expander(f"Good to know ({len(r['warnings'])})"):
                st.markdown("\n".join(_issue(p) for p in r["warnings"]))
        if r.get("alternatives"):
            with st.expander("Other step-free options"):
                for t in r["alternatives"]:
                    st.write(_summary(t))
    if r["changed"]:
        st.subheader("What to do")
        st.markdown(r["explanation"])
        if r.get("sources"):
            st.caption("Sources: " + ", ".join(r["sources"]))
    if r.get("guardrails"):
        st.caption("Safety checks applied: " + ", ".join(r["guardrails"]))
    st.caption("Times come from MBTA live predictions where marked live, otherwise the timetable. "
               "Rolling routes use OpenStreetMap and may miss broken curb cuts or construction.")
    if trip:
        _monitor(conn, key, r)


def _monitor(conn, key, r):
    st.divider()
    st.subheader("Trip monitor")
    if "d2d_watch" not in st.session_state:
        st.caption("Watches your trip for new elevator outages, stop changes, delays that would make "
                   "you miss a connection, and cancelled trips.")
        if st.button("Start monitoring this trip"):
            st.session_state.d2d_watch = start_door_trip(r)
            st.rerun()
        return
    watch = st.session_state.d2d_watch
    if not watch["ok"]:
        st.error(watch["reason"])
        return
    here = st.session_state.get("d2d_here") if st.session_state.get("d2d_use_loc") else None
    b1, b2 = st.columns(2)
    if b1.button("Check again now", use_container_width=True):
        with st.spinner("Checking live times and alerts..."):
            check_door_watch(conn, watch, key, current=here)
    if b2.button("Simulate a new outage (demo)", use_container_width=True):
        with st.spinner("Re-checking and replanning..."):
            check_door_watch(conn, watch, key, simulate=True, current=here)
    st.caption(f"Watching: {_summary(watch['trip'])}. Checks so far: {len(watch['history'])}")
    for ev in reversed(watch["history"]):
        if ev["new_problems"]:
            where = ", ".join(p["station"] for p in ev["new_problems"])
            msg = f"{ev['time']}: new problem at {where}."
            msg += (" Switched to: " + _summary(ev["switched_to"])) if ev["switched_to"] \
                else " No better step-free trip right now."
            st.error(msg)
            with st.expander("Details"):
                st.markdown("\n".join(_issue(p) for p in ev["new_problems"]))
                if ev["replan"] and ev["replan"].get("explanation") and ev["replan"].get("changed"):
                    st.markdown(ev["replan"]["explanation"])
        elif ev["resolved"]:
            st.success(f"{ev['time']}: a problem on your trip was resolved.")
        else:
            st.info(f"{ev['time']}: no new problems. "
                    + ("Live times updated." if ev["live_times"] else "Live times unavailable."))


# ---------- screen ----------

def render(conn, key, stations):
    if not otp.is_available():
        st.error("The door-to-door trip planner isn't running. Start it with "
                 "`py -3.12 otp/setup_otp.py serve` (needs Docker), or switch to Station to station.")
        return
    use_loc = st.checkbox("Start from my current location", key="d2d_use_loc")
    here = _here() if use_loc else None
    c1, c2 = st.columns(2)
    origin_text = c1.text_input("From", placeholder="Address, place or station", disabled=use_loc,
                                key="d2d_from")
    dest_text = c2.text_input("To", placeholder="Address, place or station", key="d2d_to")
    with st.expander("Options"):
        fewer = st.checkbox("Fewer transfers matter more than speed", key="d2d_fewer")
        max_roll = st.slider("Longest roll at one time (minutes)", 3, 20, 10, key="d2d_roll")
        later = st.radio("Leave", ["Now", "Later"], horizontal=True, key="d2d_when") == "Later"
        depart_at = None
        if later:
            d1, d2 = st.columns(2)
            day = d1.date_input("Date", key="d2d_day")
            at = d2.time_input("Time", key="d2d_time")
            depart_at = datetime.combine(day, at, tzinfo=BOSTON).isoformat()
        avoid = st.multiselect("Stay away from these stations", stations, key="d2d_avoid")
    if st.button("Plan door-to-door trip", type="primary", use_container_width=True):
        start = CURRENT_LOCATION if use_loc else origin_text
        _run(conn, key, start, dest_text, _prefs(fewer, max_roll), avoid, depart_at, here, "app-d2d")

    st.markdown("**Or describe your trip in your own words**")
    nl = st.text_input("Trip request", label_visibility="collapsed", key="d2d_nl",
                       placeholder="e.g. from my location to Boston Children's Hospital, short rolls please")
    if st.button("Understand and plan", use_container_width=True, key="d2d_nl_go") and nl.strip():
        with st.spinner("Understanding your request..."):
            p = parse_trip_request(nl, stations)
        st.session_state.d2d_parsed = p
        if p["origin"] and p["destination"]:
            roll = p["max_roll_minutes"] or max_roll
            _run(conn, key, p["origin"], p["destination"], _prefs(p["fewer_transfers"] >= THRESHOLD, roll),
                 p["avoid"], depart_at, here, "app-d2d-nl")
        else:
            st.session_state.d2d = {"input_error": "I couldn't tell where you're starting and going. "
                                                   "Try \"from <place> to <place>\"."}
    p = st.session_state.get("d2d_parsed")
    if p:
        start = "your location" if p["origin"] == CURRENT_LOCATION else p["origin"]
        end = "your location" if p["destination"] == CURRENT_LOCATION else p["destination"]
        st.caption(f"Understood: {start} → {end}"
                   + (", fewer transfers" if p["fewer_transfers"] >= THRESHOLD else "")
                   + (f", rolls up to {round(p['max_roll_minutes'])} min" if p["max_roll_minutes"] else "")
                   + (f", avoid {', '.join(p['avoid'])}" if p["avoid"] else "") + f" ({p['seconds']} s)")
    r = st.session_state.get("d2d")
    if r:
        show_result(conn, key, r)
