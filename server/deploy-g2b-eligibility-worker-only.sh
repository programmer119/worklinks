#!/usr/bin/env bash
# Replace ONLY the independent WorkLinks G2B qualification worker.
# Do not restart or modify API, crawler, history, awards, Nginx, ports or keys.
set -Eeuo pipefail
DK=/home/ggul-docker/bin/docker
SOCKET=unix:///home/ggul-docker/run/docker.sock
BASE=/home/worklinks/g2b
SOURCE="$GITHUB_WORKSPACE/worklinks/server/g2b-eligibility-worker.py"
TARGET="$BASE/g2b-eligibility-worker.py"
BACKUP="$BASE/g2b-eligibility-worker.py.pre-backfill-fix"
WORKER=worklinks-g2b-eligibility
IMG=python:3.11-alpine
dk(){ "$DK" -H "$SOCKET" "$@"; }
test -s "$SOURCE" && test -s "$BASE/data/bids.sqlite3"
test -x "$DK" && test -S /home/ggul-docker/run/docker.sock
[[ "$(curl -fsS --max-time 8 'http://127.0.0.1:18192/api/g2b/status')" == *'"ok":true'* ]]
if cmp -s "$SOURCE" "$TARGET" && [[ "$(dk inspect -f '{{.State.Running}}' "$WORKER" 2>/dev/null || true)" == true ]]; then
 echo 'WORKLINKS_ELIGIBILITY_WORKER_ALREADY_CURRENT=PASS'
 exit 0
fi
dk run --rm -v "$SOURCE:/tmp/g2b-eligibility-worker.py:ro" "$IMG" \
 python -c 'import ast;ast.parse(open("/tmp/g2b-eligibility-worker.py").read());print("ELIGIBILITY_WORKER_SYNTAX=PASS")'
test -f "$TARGET" && cp -p "$TARGET" "$BACKUP" || true
restore(){
 echo 'WORKLINKS_ELIGIBILITY_WORKER_ROLLBACK=attempt'
 if test -s "$BACKUP";then cp -p "$BACKUP" "$TARGET";fi
 dk rm -f "$WORKER" >/dev/null 2>&1 || true
 if test -s "$TARGET";then start_worker || true;fi
}
start_worker(){
 dk run -d --name "$WORKER" --restart unless-stopped --network host \
  -e G2B_DB_PATH=/app/data/bids.sqlite3 \
  -e G2B_LOCAL_API=http://127.0.0.1:18192/api/g2b \
  -e G2B_QUAL_BATCH=200 -e G2B_QUAL_POLL=180 \
  -v "$TARGET:/app/g2b-eligibility-worker.py:ro" \
  -v "$BASE/data:/app/data" \
  "$IMG" python -u /app/g2b-eligibility-worker.py >/dev/null
}
trap restore ERR
install -m 0644 "$SOURCE" "$TARGET"
dk rm -f "$WORKER" >/dev/null 2>&1 || true
start_worker
sleep 5
test "$(dk inspect -f '{{.State.Running}}' "$WORKER")" = true
test "$(curl -sS -o /dev/null -w '%{http_code}' --max-time 8 'http://127.0.0.1:18192/api/g2b/status')" = 200
# Do not assert that every upstream query succeeds immediately. Quota failures
# are retriable and must never change bidder eligibility decisions.
echo 'WORKLINKS_WHOLE_CORPUS_ELIGIBILITY_WORKER=DEPLOYED'
echo 'WORKLINKS_API_CRAWLER_HISTORY_AWARDS_NGINX_UNTOUCHED=PASS'
trap - ERR
