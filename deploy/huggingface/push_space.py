"""Publish the website to a Hugging Face Space (Docker), which then builds and runs it.

    hf auth login                                    # once, with a token that can write
    py -3.12 deploy/huggingface/push_space.py USER/transitwise
    py -3.12 deploy/huggingface/push_space.py USER/transitwise --set-mbta-key   # also store MBTA_KEY from .env as a Space secret
    py -3.12 deploy/huggingface/push_space.py USER/transitwise --refresh        # rebuild with this week's timetable

Only the code the website needs is uploaded (no .env, keys, notebooks or PDFs). The Space's
build downloads the MBTA timetable and OpenStreetMap data and builds the routing graph.
"""
import argparse
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
INCLUDE = ["agents", "web", "pipeline/load_alerts.py", "otp/setup_otp.py", "otp/build-config.json",
           "otp/router-config.json", "otp/extra_pathways.csv", "tests/conftest.py",
           "tests/fixtures/network.json", "tests/fixtures/alerts.json", "tests/fixtures/otp_trips.json"]
SPACE_FILES = ["Dockerfile", "start.sh", "requirements.txt", "README.md"]


def stage(dest):
    for rel in INCLUDE:
        src = ROOT / rel
        if src.is_dir():
            shutil.copytree(src, dest / rel, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dest / rel)
    for name in SPACE_FILES:
        shutil.copy(HERE / name, dest / name)
    # Any change to this file makes the Space rebuild the graph with fresh data
    (dest / "BUILD_DATE").write_text(datetime.now(timezone.utc).isoformat() + "\n")
    leaked = [p for p in dest.rglob("*") if p.name == ".env" or p.suffix in (".p8", ".pem")]
    if leaked:
        sys.exit(f"refusing to upload secrets: {leaked}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("space", help="USER/NAME of the Space")
    ap.add_argument("--set-mbta-key", action="store_true", help="store MBTA_KEY from .env as a Space secret")
    ap.add_argument("--refresh", action="store_true", help="only bump BUILD_DATE, so the Space rebuilds with fresh data")
    args = ap.parse_args()

    api = HfApi(token=os.getenv("HF_TOKEN") or None)
    if args.refresh:
        api.upload_file(path_or_fileobj=(datetime.now(timezone.utc).isoformat() + "\n").encode(),
                        path_in_repo="BUILD_DATE", repo_id=args.space, repo_type="space",
                        commit_message="Weekly rebuild with the new MBTA timetable")
        print("rebuild started:", f"https://huggingface.co/spaces/{args.space}")
        return

    api.create_repo(args.space, repo_type="space", space_sdk="docker", exist_ok=True)
    if args.set_mbta_key:
        from dotenv import dotenv_values
        sys.path.insert(0, str(ROOT))
        from pipeline.load_alerts import clean_mbta_key
        key = clean_mbta_key(dotenv_values(ROOT / ".env").get("MBTA_KEY") or "")
        if not key:
            sys.exit("no valid MBTA_KEY in .env")
        api.add_space_secret(args.space, "MBTA_KEY", key)
        print("MBTA_KEY stored as a Space secret")

    with tempfile.TemporaryDirectory() as tmp:
        stage(Path(tmp))
        api.upload_folder(folder_path=tmp, repo_id=args.space, repo_type="space",
                          commit_message="Deploy TransitWise website",
                          delete_patterns=["agents/**", "web/**", "otp/**", "pipeline/**", "tests/**"])
    print("uploaded; the Space is building:", f"https://huggingface.co/spaces/{args.space}")
    print("site link once it's running:", f"https://{args.space.replace('/', '-').lower()}.hf.space")


if __name__ == "__main__":
    main()
