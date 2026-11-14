"""Evaluate door-to-door planning on random trips with today's live data.

    py -3.12 otp/sweep_door_to_door.py [N=200] [seed=7]

Start and end points are random spots 50-300 m from random MBTA bus/subway stops, 2-12 km apart.
Runs the full agent (OTP + Checker + reroute), without the LLM explanation and without logging.
"""
import csv
import io
import math
import os
import random
import statistics
import sys
import time
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
import conftest  # noqa: E402  (offline station graph, no Snowflake)
from agents import checker, otp, planner  # noqa: E402
from agents.door_to_door import plan_door_to_door  # noqa: E402
from pipeline.load_alerts import clean_mbta_key  # noqa: E402

GTFS = Path(os.getenv("OTP_DATA_DIR", Path.home() / "transitwise-otp")) / "download" / "MBTA_GTFS.zip"


class NoLog:
    def cursor(self):
        raise RuntimeError("sweep: no logging")


def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def random_points(n, seed):
    z = zipfile.ZipFile(GTFS)
    stops = [(float(s["stop_lat"]), float(s["stop_lon"]))
             for s in csv.DictReader(io.TextIOWrapper(z.open("stops.txt"), "utf-8-sig"))
             if s["location_type"] == "0" and s["stop_lat"] and s["vehicle_type"] in ("0", "1", "3")]
    stops = [s for s in stops if 42.20 <= s[0] <= 42.48 and -71.25 <= s[1] <= -70.95]
    rng = random.Random(seed)

    def jitter(p):
        d, ang = rng.uniform(0.05, 0.3), rng.uniform(0, 2 * math.pi)
        return (p[0] + d / 111 * math.cos(ang), p[1] + d / (111 * math.cos(math.radians(p[0]))) * math.sin(ang))
    pairs = []
    while len(pairs) < n:
        a, b = jitter(rng.choice(stops)), jitter(rng.choice(stops))
        if 2 <= km(a, b) <= 12:
            pairs.append((a, b))
    return pairs


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    planner.query_df = conftest.fake_query_df
    planner._cache = planner.build_graph(NoLog())
    alerts = checker.get_live_alerts(clean_mbta_key(os.getenv("MBTA_KEY") or os.getenv("MBTA_API_KEY")))
    rows, kinds, times = [], Counter(), []
    for i, (a, b) in enumerate(random_points(n, seed)):
        t0 = time.perf_counter()
        r = plan_door_to_door(NoLog(), {"name": f"A{i}", "lat": a[0], "lon": a[1]},
                              {"name": f"B{i}", "lat": b[0], "lon": b[1]}, None,
                              alerts=alerts, explain=False, log_source="sweep")
        times.append(time.perf_counter() - t0)
        kinds.update(p["kind"] + ":" + p["effect"] for p in r.get("problems", []))
        t = r.get("trip")
        rows.append({"ok": r["ok"], "changed": r.get("changed"), "trip": bool(t),
                     "minutes": t and t["minutes"], "rolling": t and t["rolling_minutes"],
                     "longest": t and t["longest_roll"], "transfers": t and t["transfers"],
                     "within": t and otp.within_limits(t), "live": t and t["live"],
                     "modes": t and "+".join(sorted({l["mode"] for l in t["legs"] if l["transit"]}))})
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{n}", flush=True)
    trips = [x for x in rows if x["trip"]]
    pct = lambda k: f"{100 * k / len(rows):.0f}%"
    med = lambda k: statistics.median(x[k] for x in trips)
    times.sort()
    print(f"\ntrips: {len(rows)} | found a step-free trip: {len(trips)} ({pct(len(trips))})")
    print(f"usual trip blocked by a live problem: {sum(bool(x['changed']) for x in rows)} "
          f"({pct(sum(bool(x['changed']) for x in rows))}), rerouted: "
          f"{sum(bool(x['changed']) and x['trip'] for x in rows)}")
    print(f"median trip {med('minutes')} min | median rolling {med('rolling')} min | "
          f"median longest roll {med('longest')} min | median transfers {med('transfers')}")
    print(f"within 10-min/20-min rolling limits: {sum(bool(x['within']) for x in trips)}/{len(trips)} | "
          f"uses live times: {sum(bool(x['live']) for x in trips)}/{len(trips)}")
    print("modes:", Counter(x["modes"] for x in trips).most_common(6))
    print("problems on usual trips:", kinds.most_common(8))
    print(f"time per trip: median {times[len(times) // 2]:.2f} s, 95th pct {times[int(len(times) * .95)]:.2f} s")


if __name__ == "__main__":
    main()
