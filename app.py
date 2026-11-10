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
MBTA_KEY = os.getenv("MBTA_KEY") or os.getenv("MBTA_API_KEY")
missing = [k for k in ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "LLM_API_KEY") if not os.getenv(k)]
if not MBTA_KEY:
    missing.append("MBTA_KEY")
if not any(os.getenv(k) for k in ("SNOWFLAKE_PRIVATE_KEY", "SNOWFLAKE_PRIVATE_KEY_FILE", "SNOWFLAKE_PASSWORD")):
    missing.append("SNOWFLAKE_PRIVATE_KEY_FILE")
if missing:
    status.empty()
    st.error("Missing secrets: " + ", ".join(missing))
    st.stop()

# ---------- load agents ----------
status.info("Loading agents…")
print("app: importing agents", flush=True)
from agents.db import get_connection
from agents.planner import build_graph
from agents.replanner import replanner_agent, LINE_NAMES
from agents.monitor import start_trip, check_trip
from agents.request_parser import parse_request, penalty_for
from agents.retriever import get_model
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


@st.cache_resource
def load_search_model():
    """Load the embedding model at startup, not on the first trip request."""
    print("app: loading search model", flush=True)
    return get_model()


status.info("Connecting to Snowflake…")
conn = get_conn()
status.info("Building the subway map…")
stations, step_free = get_stations()
status.info("Loading the policy search model…")
load_search_model()
status.empty()


def label(name):
    return name if step_free.get(name) else f"{name} (not step-free)"


def show_route(plan, heading):
    st.markdown(f"**{heading}** (about {plan['minutes']} min)")
    if plan.get("legs"):
        for leg in plan["legs"]:
            toward = f" toward {leg['toward']}" if leg.get("toward") else ""
            st.write(f"{LINE_NAMES.get(leg['line'], leg['line'])}{toward}: "
                     f"{leg['from_name']} → {leg['to_name']}")
    else:
        st.write(" → ".join(plan["stations"]))
    if plan["transfers"]:
        st.caption("Change trains at: " + ", ".join(plan["transfers"]))
    if plan.get("passes_through_avoided"):
        st.info("No step-free route avoids " + ", ".join(plan["passes_through_avoided"])
                + " completely. Your train passes through, but you stay on board: no transfer there.")


def plan_trip(origin, dest, source, transfer_penalty=None, avoid_names=None):
    with st.spinner("Planning your route and checking live elevator outages and service changes..."):
        st.session_state.result = replanner_agent(
            conn, origin, dest, MBTA_KEY, log_source=source,
            transfer_penalty=transfer_penalty, avoid_names=avoid_names)
    st.session_state.od = (origin, dest)
    st.session_state.prefs = {"transfer_penalty": transfer_penalty, "avoid_names": avoid_names}
    st.session_state.pop("trip", None)


# ---------- trip input ----------
st.title("♿ TransitWise Boston")
st.caption("Step-free MBTA subway trips, checked against live elevator outages and service changes")

c1, c2 = st.columns(2)
origin = c1.selectbox("From", stations, format_func=label,
                      index=stations.index("Harvard") if "Harvard" in stations else 0)
dest = c2.selectbox("To", stations, format_func=label,
                    index=stations.index("Back Bay") if "Back Bay" in stations else 1)

if st.button("Plan step-free trip", type="primary", use_container_width=True):
    if origin == dest:
        st.warning("Pick two different stations.")
    else:
        st.session_state.pop("parsed", None)
        plan_trip(origin, dest, "app")

st.markdown("**Or describe your trip in your own words**")
nl_text = st.text_input("Trip request", label_visibility="collapsed",
                        placeholder="e.g. I use a wheelchair, Kendall to Back Bay, and I hate changing trains")
if st.button("Understand and plan", use_container_width=True) and nl_text.strip():
    with st.spinner("Understanding your request..."):
        parsed = parse_request(nl_text, stations)
    st.session_state.parsed = parsed
    if parsed["origin"] and parsed["destination"]:
        plan_trip(parsed["origin"], parsed["destination"], "app-nl",
                  transfer_penalty=penalty_for(parsed), avoid_names=parsed["avoid"])
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
        st.success("Your route is clear. No elevator outages or service changes affect this trip.")
        show_route(r["plan"], "Your route")
    else:
        st.error(f"{len(r['problems'])} problem(s) affect your usual route")
        for prob in r["problems"]:
            st.markdown(f"- **{prob['station']}** ({prob['role']}): {prob['alert']}")
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
    watched = (r.get("new_plan") or r.get("original_plan")) if r.get("changed") else r.get("plan")
    if r["ok"] and watched:
        st.divider()
        st.subheader("Trip monitor")
        o, d = st.session_state.od
        if "trip" not in st.session_state:
            st.caption("Watches the route you're taking for new elevator outages and service "
                       "changes while you travel.")
            if st.button("Start monitoring this trip"):
                st.session_state.trip = start_trip(conn, o, d, MBTA_KEY, plan=watched,
                                                   **st.session_state.get("prefs", {}))
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
                    with st.spinner("Re-checking and replanning..."):
                        check_trip(conn, trip, MBTA_KEY, simulate=True)
                st.caption(f"Monitoring {' → '.join(trip['plan']['stations'])}. "
                           f"Checks so far: {len(trip['history'])}")
                for ev in reversed(trip["history"]):
                    if ev["new_problems"]:
                        names_ = ", ".join(x["station"] for x in ev["new_problems"])
                        msg = f"{ev['time']}: new problem at {names_}."
                        if ev.get("switched_to"):
                            msg += " Switched to: " + " → ".join(ev["switched_to"])
                        else:
                            msg += " No better step-free route right now."
                        st.error(msg)
                        if ev["replan"] and ev["replan"].get("explanation"):
                            with st.expander("See updated guidance"):
                                st.markdown(ev["replan"]["explanation"])
                    elif ev["resolved"]:
                        st.success(f"{ev['time']}: an outage on your route was resolved.")
                    else:
                        st.info(f"{ev['time']}: no new problems on your route.")
# py -3.12 -m streamlit run app.py
