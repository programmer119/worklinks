#!/usr/bin/env bash
# Self-managed 123 Git source poll, tests, scoped deployments and B123 sync.
set -Eeuo pipefail
BASE=/home/worklinks/g2b
ROOT="$BASE/selfdeploy/worklinks"
STATE="$BASE/data/selfdeploy"
DK=/home/ggul-docker/bin/docker
SOCKET=unix:///home/ggul-docker/run/docker.sock
mkdir -p "$STATE" "$BASE/selfdeploy"
dk(){ "$DK" -H "$SOCKET" "$@"; }
log(){ printf '%s WORKLINKS_SELFDEPLOY %s\n' "$(date -u +%FT%TZ)" "$*"; }
read_stamp(){ test -s "$1" && cat "$1" || echo 0; }
run_py(){ dk run --rm -v "$ROOT:/work:ro" python:3.11-alpine python "/work/$1"; }
update_repo(){
 if test ! -d "$ROOT/.git";then
  test ! -e "$ROOT" || test -z "$(ls -A "$ROOT")" || return 1
  git clone --depth 2 --single-branch --branch main \
    https://github.com/programmer119/worklinks.git "$ROOT"
 else
  git -C "$ROOT" fetch --depth 2 origin main
  git -C "$ROOT" reset --hard FETCH_HEAD
 fi
}
deploy_changed(){
 local sha="$1" approved
 test "$sha" != "$(read_stamp "$STATE/last-deployed-sha")" || return 0
 approved="$(python3 - "$BASE/data/standalone/standalone-jobs-state.json" <<'PY'
import json,sys
try:
 d=json.load(open(sys.argv[1]))
 print(d.get('checkedHead') if (d.get('lastQa') or {}).get('ok') else '')
except (OSError,ValueError):print('')
PY
)"
 if test "$approved" != "$sha";then
  log "AWAITING_LOCAL_CI_SHA $sha"
  return 0
 fi
 for item in deploy-g2b-api-only deploy-g2b-award-enricher \
  deploy-g2b-crawler-only deploy-g2b-eligibility-worker-only \
  deploy-worklinks-server123-pipeline deploy-worklinks-standalone;do
  bash -n "$ROOT/server/$item.sh" || return 1
 done
 run_py tests/test_bid_evidence.py || return 1
 run_py tests/test_g2b_eligibility_worker.py || return 1
 run_py tests/test_worklinks_standalone_jobs.py || return 1
 for item in deploy-g2b-api-only deploy-g2b-award-enricher \
  deploy-g2b-crawler-only deploy-g2b-eligibility-worker-only \
  deploy-worklinks-server123-pipeline deploy-worklinks-standalone;do
  bash "$ROOT/server/$item.sh" || return 1
 done
 printf '%s\n' "$sha" > "$STATE/last-deployed-sha.tmp"
 mv "$STATE/last-deployed-sha.tmp" "$STATE/last-deployed-sha"
 log "CODE_DEPLOYED_SHA $sha"
}
sync_standard_daily(){
 local now last
 now="$(date +%s)"
 last="$(read_stamp "$STATE/b123-last-success-epoch")"
 if test $((now-last)) -lt 86400;then return 0;fi
 last="$(read_stamp "$STATE/b123-last-attempt-epoch")"
 if test $((now-last)) -lt 21600;then return 0;fi
 printf '%s\n' "$now" > "$STATE/b123-last-attempt-epoch"
 log B123_SCHEDULED_START
 test -s "$BASE/secrets/g2b-standard.env" || { log B123_CREDENTIAL_FILE_MISSING;return 1; }
 run_py tests/test_g2b_standard_worker.py || { log B123_OFFLINE_TEST_FAILED;return 1; }
 log B123_OFFLINE_TEST_COMPLETE
 dk run --rm --network host \
   -e G2B_STANDARD_DB=/app/data/g2b-standard.sqlite3 \
   -e WORKLINKS_RFP_LEDGER_DB=/app/data/rfp-request-ledger.sqlite3 \
   -e G2B_STANDARD_KEY_PATH=/run/secrets/g2b-standard.env \
   -v "$ROOT/server/g2b-standard-worker.py:/app/g2b-standard-worker.py:ro" \
   -v "$ROOT/scripts/rfp_call_ledger.py:/app/rfp_call_ledger.py:ro" \
   -v "$BASE/secrets/g2b-standard.env:/run/secrets/g2b-standard.env:ro" \
   -v "$BASE/data:/app/data" \
   python:3.11-alpine python -u /app/g2b-standard-worker.py \
     --days 5 --max-requests 145 || { log B123_COLLECTOR_FAILED;return 1; }
 log B123_COLLECTOR_COMPLETE
 dk run --rm -v "$BASE/data:/app/data" python:3.11-alpine python -c '
import sqlite3
db=sqlite3.connect("file:/app/data/g2b-standard.sqlite3?mode=ro",uri=True)
assert db.execute("PRAGMA quick_check").fetchone()[0]=="ok"
services=set(x[0] for x in db.execute("SELECT DISTINCT service FROM std_windows"))
assert {"B1","B2","B3"}.issubset(services)
assert all(db.execute("SELECT COUNT(*) FROM "+t).fetchone()[0]>0
 for t in ("std_notices","std_awards","std_contracts"))
print("B123_DAILY_123_COMPLETE=PASS")' || { log B123_DB_INTEGRITY_FAILED;return 1; }
 printf '%s\n' "$now" > "$STATE/b123-last-success-epoch"
 log B123_DAILY_SYNC_COMPLETE
}
exec 9>"$STATE/check.lock"
log START
while true;do
 if flock -n 9;then
  if update_repo;then
   sha="$(git -C "$ROOT" rev-parse HEAD)"
   deploy_changed "$sha" || log CODE_DEPLOY_FAILED
   sync_standard_daily || log B123_SYNC_FAILED
  else log GIT_FETCH_FAILED
  fi
  flock -u 9
 else log LOCK_BUSY
 fi
 if test -s "$STATE/last-deployed-sha";then sleep 1800;else sleep 300;fi
done
