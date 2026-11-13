"""Set up and run the OpenTripPlanner server that plans door-to-door trips.

    py -3.12 otp/setup_otp.py all       # download + clip + build + serve (first time, ~5 min)
    py -3.12 otp/setup_otp.py refresh   # new MBTA timetable, rebuild, restart (run weekly)
    py -3.12 otp/setup_otp.py serve | stop | status

Needs Docker. Data (about 400 MB) goes to OTP_DATA_DIR, default ~/transitwise-otp,
kept outside the project folder so OneDrive/git don't sync it.
"""
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

OTP_IMAGE = "opentripplanner/opentripplanner:2.10.0"
OSMIUM_IMAGE = "iboates/osmium:latest"
CONTAINER = "otp-serve"
PORT = 8080
GTFS_URL = "https://cdn.mbta.com/MBTA_GTFS.zip"
OSM_URL = "https://download.geofabrik.de/north-america/us/massachusetts-latest.osm.pbf"
BBOX = "-71.40,42.05,-70.80,42.60"     # MBTA bus and subway area (west,south,east,north)

HERE = Path(__file__).resolve().parent
ROOT = Path(os.getenv("OTP_DATA_DIR", Path.home() / "transitwise-otp"))
DOWNLOAD, DATA = ROOT / "download", ROOT / "data"


def run(cmd, **kw):
    print("$", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=True, **kw)


def docker_path(p):
    return str(p).replace("\\", "/")


def download():
    DOWNLOAD.mkdir(parents=True, exist_ok=True)
    for url, name in ((GTFS_URL, "MBTA_GTFS.zip"), (OSM_URL, "massachusetts-latest.osm.pbf")):
        print("downloading", url, flush=True)
        urllib.request.urlretrieve(url, DOWNLOAD / name)


def download_gtfs():
    DOWNLOAD.mkdir(parents=True, exist_ok=True)
    print("downloading", GTFS_URL, flush=True)
    urllib.request.urlretrieve(GTFS_URL, DOWNLOAD / "MBTA_GTFS.zip")


def clip():
    DATA.mkdir(parents=True, exist_ok=True)
    run(["docker", "run", "--rm", "-v", f"{docker_path(ROOT)}:/w", OSMIUM_IMAGE, "extract",
         "-b", BBOX, "--strategy", "complete_ways", "/w/download/massachusetts-latest.osm.pbf",
         "-o", "/w/data/boston-area.osm.pbf", "--overwrite"],
        env={**os.environ, "MSYS_NO_PATHCONV": "1"})


def build():
    DATA.mkdir(parents=True, exist_ok=True)
    shutil.copy(DOWNLOAD / "MBTA_GTFS.zip", DATA / "mbta-gtfs.zip")
    for name in ("build-config.json", "router-config.json"):
        shutil.copy(HERE / name, DATA / name)
    run(["docker", "run", "--rm", "-e", "JAVA_TOOL_OPTIONS=-Xmx6g",
         "-v", f"{docker_path(DATA)}:/var/opentripplanner", OTP_IMAGE, "--build", "--save"],
        env={**os.environ, "MSYS_NO_PATHCONV": "1"})


def stop():
    subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)


def serve(wait=True):
    stop()
    shutil.copy(HERE / "router-config.json", DATA / "router-config.json")
    run(["docker", "run", "-d", "--name", CONTAINER, "--restart", "unless-stopped",
         "-p", f"{PORT}:8080", "-e", "JAVA_TOOL_OPTIONS=-Xmx5g",
         "-v", f"{docker_path(DATA)}:/var/opentripplanner", OTP_IMAGE, "--load", "--serve"],
        env={**os.environ, "MSYS_NO_PATHCONV": "1"})
    if wait:
        for _ in range(60):
            if status(quiet=True):
                print(f"OTP is ready on http://localhost:{PORT}")
                return
            time.sleep(3)
        sys.exit("OTP did not become ready; see: docker logs otp-serve")


def status(quiet=False):
    import json
    req = urllib.request.Request(
        f"http://localhost:{PORT}/otp/gtfs/v1", method="POST",
        data=json.dumps({"query": "{ feeds { feedId } }"}).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            ok = r.status == 200
    except Exception:
        ok = False
    if not quiet:
        print("OTP running" if ok else "OTP not reachable")
    return ok


STEPS = {
    "download": [download], "clip": [clip], "build": [build], "serve": [serve], "stop": [stop],
    "status": [status], "all": [download, clip, build, serve],
    "refresh": [download_gtfs, build, serve],
}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in STEPS:
        sys.exit(__doc__)
    for step in STEPS[sys.argv[1]]:
        step()
