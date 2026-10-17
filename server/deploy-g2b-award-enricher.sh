#!/usr/bin/env bash
# Deploy ONLY WorkLinks official-award worker; no change to ports, keys or crawler.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE=/home/worklinks/g2b
SOURCE="$ROOT/server/g2b-award-enricher.py"
SNAPSHOT="$ROOT/startup-support/official-awards-snapshot.json"
TEST="$ROOT/tests/test_award_enricher.py"
TARGET="$BASE/g2b-award-enricher.py"
TARGET_SNAPSHOT="$BASE/official-awards-snapshot.json"
DB="$BASE/data/bids.sqlite3"
DOCKER=/home/ggul-docker/bin/docker
SOCKET=unix:///home/ggul-docker/run/docker.sock
IMG=python:3.11-alpine
WORKER=worklinks-g2b-award-enricher
dk(){ "$DOCKER" -H "$SOCKET" "$@"; }
for x in "$SOURCE" "$SNAPSHOT" "$TEST" "$DB" "$DOCKER";do
  test -s "$x" || { echo "AWARD_DEPLOY_MISSING=$(basename "$x")"; exit 5; }
done
test -S /home/ggul-docker/run/docker.sock
test "$(dk inspect -f '{{.State.Running}}' worklinks-g2b-api)" = true
dk image inspect "$IMG" >/dev/null
# The existing API must expose this read-only status route first.
curl -fsS --max-time 8 'http://127.0.0.1:18192/api/g2b/award-cache-status' |
  grep -q '"ok":true' || { echo 'AWARD_API_NOT_DEPLOYED'; exit 8; }
# Unit-test a disposable SQLite database; never touch the production DB in tests.
dk run --rm -v "$SOURCE:/app/g2b-award-enricher.py:ro" \
  "$IMG" python -m py_compile /app/g2b-award-enricher.py
dk run --rm \
  -v "$SOURCE:/app/g2b-award-enricher.py:ro" \
  -v "$TEST:/app/test_award_enricher.py:ro" \
  "$IMG" python /app/test_award_enricher.py
if cmp -s "$SOURCE" "$TARGET" && cmp -s "$SNAPSHOT" "$TARGET_SNAPSHOT" &&
   test "$(dk inspect -f '{{.State.Running}}' "$WORKER" 2>/dev/null || true)" = true;then
  echo 'WORKLINKS_AWARD_ENRICHER_ALREADY_DEPLOYED=PASS'
  exit 0
fi
WAS_EXISTING=0
if dk inspect "$WORKER" >/dev/null 2>&1;then WAS_EXISTING=1;fi
HAS_TARGET=0; HAS_SNAPSHOT=0
if test -s "$TARGET";then HAS_TARGET=1;cp -p "$TARGET" "$TARGET.award-bak";fi
if test -s "$TARGET_SNAPSHOT";then HAS_SNAPSHOT=1;cp -p "$TARGET_SNAPSHOT" "$TARGET_SNAPSHOT.award-bak";fi
start_worker(){
  dk rm -f "$WORKER" >/dev/null 2>&1 || true
  dk run -d --name "$WORKER" --restart unless-stopped --network host \
    -e G2B_DB_PATH=/app/data/bids.sqlite3 \
    -e G2B_AWARD_SEED_PATH=/app/official-awards-snapshot.json \
    -e AWARD_MAX_REQUESTS_PER_CYCLE=2 \
    -e AWARD_INTERVAL_SECONDS=3600 \
    -e AWARD_REQUEST_GAP_SECONDS=15 \
    -v "$TARGET:/app/g2b-award-enricher.py:ro" \
    -v "$TARGET_SNAPSHOT:/app/official-awards-snapshot.json:ro" \
    -v "$BASE/data:/app/data" \
    "$IMG" python -u /app/g2b-award-enricher.py >/dev/null
}
rollback(){
  echo 'WORKLINKS_AWARD_ENRICHER_ROLLBACK=attempt'
  if test "$HAS_TARGET" = 1;then cp -p "$TARGET.award-bak" "$TARGET";else rm -f "$TARGET";fi
  if test "$HAS_SNAPSHOT" = 1;then cp -p "$TARGET_SNAPSHOT.award-bak" "$TARGET_SNAPSHOT";else rm -f "$TARGET_SNAPSHOT";fi
  if test "$WAS_EXISTING" = 1 && test -s "$TARGET" && test -s "$TARGET_SNAPSHOT";then
    start_worker || true
  else
    dk rm -f "$WORKER" >/dev/null 2>&1 || true
  fi
}
trap rollback ERR
install -m 0644 "$SOURCE" "$TARGET"
install -m 0644 "$SNAPSHOT" "$TARGET_SNAPSHOT"
start_worker
# The first official request may be slow; table initialization is immediate.
for i in $(seq 1 18);do
  status="$(curl -fsS --max-time 6 'http://127.0.0.1:18192/api/g2b/award-cache-status' || true)"
  if [[ "$status" == *'"installed":true'* ]];then break;fi
  sleep 2
done
[[ "$status" == *'"installed":true'* ]] || { echo 'AWARD_CACHE_DB_NOT_READY'; exit 9; }
test "$(dk inspect -f '{{.State.Running}}' "$WORKER")" = true
public="$(curl -fsS --max-time 12 'https://api-suaveforge.suaveforge.com:18458/api/g2b/award-cache-status')"
[[ "$public" == *'"installed":true'* ]] || { echo 'AWARD_CACHE_HTTPS_NOT_READY'; exit 10; }
trap - ERR
echo 'WORKLINKS_AWARD_ENRICHER_RUNNING=PASS'
echo 'WORKLINKS_AWARD_CACHE_PUBLIC=PASS'
echo 'WORKLINKS_AWARD_MAX_REQUESTS_PER_CYCLE=2'
echo 'WORKLINKS_AWARD_INTERVAL_SECONDS=3600'
echo 'WORKLINKS_AWARD_NO_NEW_PORTS=PASS'
