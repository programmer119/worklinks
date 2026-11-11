#!/usr/bin/env bash
# Idempotent server123 bootstrap; no changes to existing bid collector or API process.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE=/home/worklinks/g2b
DK=/home/ggul-docker/bin/docker
SOCKET=unix:///home/ggul-docker/run/docker.sock
DOCKERFILE="$ROOT/server/Dockerfile.worklinks-standalone"
SCRIPT="$ROOT/server/worklinks-standalone-jobs.py"
UNIT="$ROOT/tests/test_worklinks_standalone_jobs.py"
CONTAINER=worklinks-standalone
IMAGE="worklinks-standalone:$(sha256sum "$DOCKERFILE" | cut -c1-12)"
TARGET="$BASE/standalone/worklinks-standalone-jobs.py"
dk(){ "$DK" -H "$SOCKET" "$@"; }
for file in "$DOCKERFILE" "$SCRIPT" "$UNIT" "$DK";do
  test -s "$file" || { echo "STANDALONE_MISSING_REQUIRED_SOURCE=$(basename "$file")"; exit 2; }
done
test -S /home/ggul-docker/run/docker.sock
mkdir -p "$BASE/standalone" "$BASE/data/standalone" "$BASE/data/snapshots"
# Always verify the scheduler before touching the persistent container.
dk run --rm \
  -v "$SCRIPT:/app/server/worklinks-standalone-jobs.py:ro" \
  -v "$UNIT:/app/tests/test_worklinks_standalone_jobs.py:ro" \
  python:3.11-alpine python /app/tests/test_worklinks_standalone_jobs.py
if ! dk image inspect "$IMAGE" >/dev/null 2>&1;then
  dk build --pull=false -t "$IMAGE" -f "$DOCKERFILE" "$ROOT/server"
fi
dk run --rm "$IMAGE" sh -c \
  'git --version; node --version; python -c "import requests,bs4,certifi,playwright;print(\"STANDALONE_RUNTIME_DEPS=PASS\")"; test -x /usr/bin/chromium'
if cmp -s "$SCRIPT" "$TARGET" &&
   test "$(dk inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null || true)" = true &&
   test "$(dk inspect -f '{{.Config.Image}}' "$CONTAINER" 2>/dev/null || true)" = "$IMAGE";then
  echo STANDALONE_ALREADY_CURRENT=PASS
  exit 0
fi
if test -s "$TARGET";then cp -p "$TARGET" "$TARGET.rollback";fi
PREVIOUS="$(dk inspect -f '{{.Config.Image}}' "$CONTAINER" 2>/dev/null || true)"
start_container(){
  dk rm -f "$CONTAINER" >/dev/null 2>&1 || true
  dk run -d --name "$CONTAINER" --restart unless-stopped --network host \
    --security-opt no-new-privileges --cap-drop ALL \
    -e WORKLINKS_DATA=/app/data \
    -e WORKLINKS_SNAPSHOT_DIR=/app/snapshots \
    -e WORKLINKS_CHROMIUM_PATH=/usr/bin/chromium \
    -v "$BASE/data/standalone:/app/data" \
    -v "$BASE/data/snapshots:/app/snapshots" \
    -v "$TARGET:/app/worklinks-standalone-jobs.py:ro" \
    "$1" python -u /app/worklinks-standalone-jobs.py >/dev/null
}
rollback(){
  echo STANDALONE_BOOTSTRAP_ROLLBACK
  dk rm -f "$CONTAINER" >/dev/null 2>&1 || true
  if test -s "$TARGET.rollback";then cp -p "$TARGET.rollback" "$TARGET";fi
  if test -n "$PREVIOUS" && test -s "$TARGET";then
    start_container "$PREVIOUS" || true
  fi
}
trap rollback ERR
install -m 0644 "$SCRIPT" "$TARGET"
start_container "$IMAGE"
sleep 5
test "$(dk inspect -f '{{.State.Running}}' "$CONTAINER")" = true
dk logs --tail 25 "$CONTAINER" 2>&1 | grep -q 'WORKLINKS_STANDALONE_START'
trap - ERR
echo WORKLINKS_SERVER123_INDEPENDENT_GIT_POLL_AND_SCHEDULE=PASS
echo WORKLINKS_EXISTING_PROCUREMENT_PIPELINE_UNTOUCHED=PASS
