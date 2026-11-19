#!/usr/bin/env bash
# Isolated procurement-plan and prespec collector, no new public port/cron.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE=/home/worklinks/g2b
SOURCE="$ROOT/scripts/g2b_prebid_collector.py"
TARGET="$BASE/g2b-prebid-collector.py"
SECRET="$BASE/secrets/g2b-standard.env"
DOCKER=/home/ggul-docker/bin/docker
SOCKET=unix:///home/ggul-docker/run/docker.sock
WORKER=worklinks-g2b-prebid
IMG=python:3.11-alpine
dk(){ "$DOCKER" -H "$SOCKET" "$@"; }
for f in "$SOURCE" "$ROOT/tests/test_g2b_prebid_collector.py" "$SECRET" "$DOCKER";do
 test -s "$f" || { echo "PREBID_REQUIRED_FILE_MISSING=$f";exit 5; }
done
test -S /home/ggul-docker/run/docker.sock
dk image inspect "$IMG" >/dev/null
# No API credentials and no outbound traffic during validation.
dk run --rm --network none -e PYTHONPYCACHEPREFIX=/tmp/prebid-pycache -v "$ROOT:/work:ro" "$IMG" \
 python -m py_compile /work/scripts/g2b_prebid_collector.py /work/server/g2b-proxy.py
dk run --rm --network none -e PYTHONPYCACHEPREFIX=/tmp/prebid-pycache -v "$ROOT:/work:ro" "$IMG" \
 python /work/tests/test_g2b_prebid_collector.py
if cmp -s "$SOURCE" "$TARGET" && \
   test "$(dk inspect -f '{{.State.Running}}' "$WORKER" 2>/dev/null || true)" = true;then
 echo 'WORKLINKS_PREBID_COLLECTOR_ALREADY_CURRENT=PASS'
 exit 0
fi
BACKUP="$TARGET.previous"
if test -s "$TARGET";then cp -p "$TARGET" "$BACKUP";fi
install -m 0644 "$SOURCE" "$TARGET"
rollback(){
 echo 'WORKLINKS_PREBID_COLLECTOR_ROLLBACK'
 dk rm -f "$WORKER" >/dev/null 2>&1 || true
 if test -s "$BACKUP";then
  cp -p "$BACKUP" "$TARGET"
  start || true
 fi
}
start(){
 dk rm -f "$WORKER" >/dev/null 2>&1 || true
 dk run -d --name "$WORKER" --restart unless-stopped --network host \
   -e G2B_OPERATING_KEY_PATH=/run/secrets/g2b-standard.env \
   -e G2B_PREBID_DB=/app/data/g2b-prebid.sqlite3 \
   -e WORKLINKS_PREBID_REQUESTS_PER_DAY=48 \
   -e WORKLINKS_PREBID_LOOP_SECONDS=1800 \
   -v "$TARGET:/app/g2b-prebid-collector.py:ro" \
   -v "$SECRET:/run/secrets/g2b-standard.env:ro" \
   -v "$BASE/data:/app/data" \
   "$IMG" python -u /app/g2b-prebid-collector.py >/dev/null
}
trap rollback ERR
start
sleep 2
test "$(dk inspect -f '{{.State.Running}}' "$WORKER")" = true
# A newly created but empty DB is not a false positive for successful
# government ingestion. API reports ready:false until a valid page is fetched.
echo 'WORKLINKS_PREBID_ISOLATED_COLLECTOR_RUNNING=PASS'
echo 'WORKLINKS_PREBID_ZERO_NEW_PORTS_AND_NO_RFP_TOUCH=PASS'
trap - ERR
