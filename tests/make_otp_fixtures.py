"""Record real OpenTripPlanner answers for the offline door-to-door tests.

    py -3.12 tests/make_otp_fixtures.py      (needs the OTP server: otp/setup_otp.py serve)

For each place pair it saves both search profiles with no routes left out, and with each route of
the best option left out (alone and all together), which is what the Replanner's follow-up
searches ask for. Also saves the live MBTA alerts at the same moment.
"""
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))
from agents import otp  # noqa: E402
from agents.checker import get_live_alerts  # noqa: E402
from pipeline.load_alerts import clean_mbta_key  # noqa: E402

PLACES = {
    "Harvard Yard": (42.3744, -71.1169),
    "Mass General Hospital": (42.3632, -71.0686),
    "Fields Corner": (42.3000, -71.0617),
    "Boston Medical Center": (42.3350, -71.0726),
    "Back Bay station": (42.3473, -71.0757),
    "Harvard station": (42.3734, -71.1189),
    "Wonderland station": (42.4135, -70.9916),
    "Revere Beach": (42.4087, -70.9926),
    "Downtown Crossing": (42.3555, -71.0603),
    "Union Square, Somerville": (42.3796, -71.0937),
    "Boston Convention Center": (42.3456, -71.0442),
}
PAIRS = [("Harvard Yard", "Mass General Hospital"), ("Fields Corner", "Boston Medical Center"),
         ("Back Bay station", "Harvard station"), ("Wonderland station", "Back Bay station"),
         ("Revere Beach", "Downtown Crossing"), ("Union Square, Somerville", "Boston Convention Center")]


def place(name):
    lat, lon = PLACES[name]
    return {"name": name, "lat": lat, "lon": lon}


def key(o, d, profile, excluded):
    return f"{o}|{d}|{profile}|{','.join(sorted(excluded))}"


def main():
    answers = {}
    for o, d in PAIRS:
        base = otp.plan_options(place(o), place(d))
        routes = sorted({l["route_id"] for l in base["options"][0]["legs"] if l["transit"]}) if base["ok"] else []
        exclusions = [()] + [(r,) for r in routes] + ([tuple(routes)] if len(routes) > 1 else [])
        for excl in exclusions:
            for prof in otp.PROFILES:
                its, errs = otp.query_itineraries(place(o), place(d), None, prof, excl)
                answers[key(o, d, prof["name"], excl)] = {"itineraries": its, "errors": errs}
        print(o, "->", d, "routes:", routes, "searches:", len(exclusions) * len(otp.PROFILES))
    alerts = get_live_alerts(clean_mbta_key(os.getenv("MBTA_KEY") or os.getenv("MBTA_API_KEY")))
    out = {"recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "places": PLACES, "answers": answers, "alerts": alerts}
    path = os.path.join(ROOT, "tests", "fixtures", "otp_trips.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"wrote {path}: {len(answers)} searches, {len(alerts)} alerts")


if __name__ == "__main__":
    main()
