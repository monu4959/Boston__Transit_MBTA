#!/usr/bin/env bash
# Start OpenTripPlanner in the background (restarting it if it stops), then the website.
# The website is up right away; trips work once OTP has loaded its graph (about a minute).
set -u
DATA="$OTP_DATA_DIR/data"

(
  if [ ! -f "$DATA/graph.obj" ]; then
    echo "No routing graph in the image: building it now (about 10 minutes)"
    python otp/setup_otp.py graph || echo "graph build failed"
  fi
  while true; do
    java "-Xmx${OTP_HEAP:-6g}" -jar "$OTP_JAR" --load --serve "$DATA"
    echo "OpenTripPlanner stopped; restarting in 10 s"
    sleep 10
  done
) &

exec python -m uvicorn web.server:app --host 0.0.0.0 --port 7860
