import os
import streamlit as st
from dotenv import load_dotenv

st.set_page_config(page_title="TransitWise Boston", page_icon="♿", layout="centered")
load_dotenv()

status = st.empty()
status.info("Starting up…")
print("app: starting", flush=True)

# ---------- optional password gate ----------
APP_PASSWORD = os.getenv("APP_PASSWORD")
if APP_PASSWORD and not st.session_state.get("authed"):
    status.empty()
    entered = st.text_input("App password", type="password")
    if entered == APP_PASSWORD:
        st.session_state.authed = True
        st.rerun()
    st.stop()

# ---------- secrets check ----------
missing = [k for k in ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "MBTA_KEY", "LLM_API_KEY") if not os.getenv(k)]
if not any(os.getenv(k) for k in ("SNOWFLAKE_PRIVATE_KEY", "SNOWFLAKE_PRIVATE_KEY_FILE", "SNOWFLAKE_PASSWORD")):
    missing.append("SNOWFLAKE_PRIVATE_KEY_FILE")
if missing:
    status.empty()
    st.error("Missing secrets: " + ", ".join(missing))
    st.stop()

MBTA_KEY = os.getenv("MBTA_KEY")

# ---------- load agents ----------
status.info("Loading agents…")
print("app: importing agents", flush=True)
from agents.db import get_connection
from agents.planner import build_graph
from agents.replanner import replanner_agent
from agents.monitor import start_trip, check_trip
from agents.request_parser import parse_request, penalty_for
print("app: agents imported", flush=True)


@st.cache_resource
def get_conn():
    print("app: connecting to Snowflake", flush=True)
    c = get_connection()
    print("app: connected", flush=True)
    return c


@st.cache_resource
def get_stations():
    print("app: building graph", flush=True)
    G, names, accessible, lines_at = build_graph(get_conn())
    step_free = {names[s]: accessible.get(s, False) for s in names}
    print("app: graph ready", flush=True)
    return sorted(step_free), step_free


status.info("Connecting to Snowflake…")
conn = get_conn()
status.info("Building the subway map…")
stations, step_free = get_stations()
status.empty()


def label(name):
    return name if step_free.get(name) else f"{name} (not step-free)"


def show_route(plan, heading):
    st.markdown(f"**{heading}** (about {plan['minutes']} min)")
    st.write(" → ".join(plan["stations"]))
    if plan["transfers"]:
        st.caption("Change trains at: " + ", ".join(plan["transfers"]))


# ---------- trip input ----------
st.title("♿ TransitWise Boston")
st.caption("Step-free MBTA subway trips, checked against live elevator outages")

c1, c2 = st.columns(2)
origin = c1.selectbox("From", stations, format_func=label,
                      index=stations.index("Harvard") if "Harvard" in stations else 0)
dest = c2.selectbox("To", stations, format_func=label,
                    index=stations.index("Back Bay") if "Back Bay" in stations else 1)

if st.button("Plan step-free trip", type="primary", use_container_width=True):
    if origin == dest:
        st.warning("Pick two different stations.")
    else:
        with st.spinner("Planning your route and checking live elevator outages..."):
            st.session_state.result = replanner_agent(conn, origin, dest, MBTA_KEY, log_source="app")
            st.session_state.od = (origin, dest)
            st.session_state.pop("trip", None)
            st.markdown("**Or describe your trip in your own words**")
nl_text = st.text_input("Trip request", label_visibility="collapsed",
                        placeholder="e.g. I use a wheelchair, Kendall to Back Bay, and I hate changing trains")
if st.button("Understand and plan", use_container_width=True) and nl_text.strip():
    with st.spinner("Understanding your request..."):
        parsed = parse_request(nl_text, stations)
    st.session_state.parsed = parsed
    if parsed["origin"] and parsed["destination"]:
        with st.spinner("Planning your route and checking live elevator outages..."):
            st.session_state.result = replanner_agent(
                conn, parsed["origin"], parsed["destination"], MBTA_KEY, log_source="app-nl",
                transfer_penalty=penalty_for(parsed), avoid_names=parsed["avoid"])
            st.session_state.od = (parsed["origin"], parsed["destination"])
            st.session_state.pop("trip", None)
        st.rerun()

p = st.session_state.get("parsed")
if p:
    if not (p["origin"] and p["destination"]):
        st.warning("I couldn't match both stations. Try official station names, or use the dropdowns.")
    pref = "fewer transfers" if p["fewer_transfers"] >= 0.6 else "fastest route"
    st.caption(f"Understood: {p['origin']} → {p['destination']}, preference: {pref}"
               + (f", wants to avoid {', '.join(p['avoid'])}" if p["avoid"] else "")
               + f" ({p['seconds']} s)")

# ---------- results ----------
r = st.session_state.get("result")
if r:
    st.divider()
    if not r["ok"]:
        st.error(r["reason"])
    elif not r["changed"]:
        st.success("Your route is clear. No elevator outages affect this trip.")
        show_route(r["plan"], "Your route")
    else:
        st.error(f"{len(r['problems'])} elevator problem(s) affect your usual route")
        for p in r["problems"]:
            st.markdown(f"- **{p['station']}** ({p['role']}): {p['alert']}")
        show_route(r["original_plan"], "Usual route")
        if r["new_plan"]:
            st.success("Step-free alternative found")
            show_route(r["new_plan"], "Recommended route")
        else:
            st.warning("No fully step-free train route right now.")
        st.subheader("What to do")
        st.markdown(r["explanation"])
        if r["sources"]:
            st.caption("Sources: " + ", ".join(r["sources"]))
        if r.get("guardrails"):
            st.caption("Safety checks applied: " + ", ".join(r["guardrails"]))

    # ---------- monitor ----------
    if r["ok"]:
        st.divider()
        st.subheader("Trip monitor")
        o, d = st.session_state.od
        if "trip" not in st.session_state:
            st.caption("Watches your trip for new elevator outages while you travel.")
            if st.button("Start monitoring this trip"):
                st.session_state.trip = start_trip(conn, o, d, MBTA_KEY)
                st.rerun()
        else:
            trip = st.session_state.trip
            if not trip["ok"]:
                st.error(trip["reason"])
            else:
                b1, b2 = st.columns(2)
                if b1.button("Check again now", use_container_width=True):
                    with st.spinner("Checking live outages..."):
                        check_trip(conn, trip, MBTA_KEY)
                if b2.button("Simulate a new outage (demo)", use_container_width=True):
                    trip["known_alerts"] = set()
                    with st.spinner("Re-checking and replanning..."):
                        check_trip(conn, trip, MBTA_KEY)
                st.caption(f"Monitoring {o} → {d}. Checks so far: {len(trip['history'])}")
                for ev in reversed(trip["history"]):
                    if ev["new_problems"]:
                        names_ = ", ".join(p["station"] for p in ev["new_problems"])
                        st.error(f"{ev['time']}: new outage at {names_}. Trip replanned.")
                        if ev["replan"] and ev["replan"].get("explanation"):
                            with st.expander("See updated guidance"):
                                st.markdown(ev["replan"]["explanation"])
                    elif ev["resolved"]:
                        st.success(f"{ev['time']}: an outage on your route was resolved.")
                    else:
                        st.info(f"{ev['time']}: no new problems on your route.")
                        #py -3.12 -m streamlit run app.py