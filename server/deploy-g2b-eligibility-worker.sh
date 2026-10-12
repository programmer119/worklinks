#!/usr/bin/env bash
# WorkLinks qualifications: activate permanent notice-level industry evidence.
# Existing nginx:18458, API:18192, 14-day crawler, and annual history worker stay intact.
set -Eeuo pipefail
DOCKER=/home/ggul-docker/bin/docker
SOCKET=unix:///home/ggul-docker/run/docker.sock
DK(){ "$DOCKER" -H "$SOCKET" "$@"; }
BASE=/home/worklinks/g2b
IMG=python:3.11-alpine
API=worklinks-g2b-api
ENRICH=worklinks-g2b-eligibility
SOURCE="$BASE/g2b-proxy-docker.py"
WORKER="$BASE/g2b-eligibility-worker.py"
API_REV=5660985bd37c9d85015c0f52586d68a81da6cc0d
WORKER_REV=2d1dbfb0cff0038de18378f5d2bb4cdf349781c3
test -s "$SOURCE" && test -s "$BASE/data/bids.sqlite3"
test -s "$BASE/secrets/g2b.env"
test "$(DK inspect -f '{{.State.Running}}' worklinks-g2b-crawler)" = true
test "$(DK inspect -f '{{.State.Running}}' worklinks-g2b-history)" = true
curl -fsSL --max-time 30 \
 "https://raw.githubusercontent.com/programmer119/worklinks/$API_REV/server/g2b-proxy.py" -o "$SOURCE.new"
curl -fsSL --max-time 30 \
 "https://raw.githubusercontent.com/programmer119/worklinks/$WORKER_REV/server/g2b-eligibility-worker.py" -o "$WORKER.new"
DK run --rm -v "$SOURCE.new:/work/g2b-proxy.py:ro" -v "$WORKER.new:/work/g2b-eligibility-worker.py:ro" \
 "$IMG" python -m py_compile /work/g2b-proxy.py /work/g2b-eligibility-worker.py
# Run a persistent SQLite cache regression without touching the production DB.
DK run --rm -i -e G2B_DB_PATH=/tmp/bid-test.sqlite3 \
 -v "$SOURCE.new:/work/api.py:ro" "$IMG" python - <<'PY'
import json,runpy,sqlite3,datetime
a=runpy.run_path('/work/api.py',run_name='integration_test')
x={'kind':'servc','bidNo':'R26BK99999999','order':'000','title':'정보시스템 유지관리'}
a['persist_bids']([x])
db=a['open_bid_db']()
with db:
 db.execute('INSERT OR REPLACE INTO bid_license_cache(bid_no,bid_ord,payload,checked_at) VALUES(?,?,?,?)',
 ('R26BK99999999','000',json.dumps({'ok':True,'complete':True,'requirements':[{'group':'1','codes':['1468']}]},ensure_ascii=False),
 datetime.datetime.now(datetime.timezone.utc).isoformat()))
db.close()
z=a['query_saved_bids'](5,0,True)
assert z['items'][0]['bidEligibility']['requirements'][0]['codes']==['1468']
assert z['eligibilityChecked']==1
print('SQLITE_NOTICE_ELIGIBILITY_JOIN=PASS')
PY

cp -p "$SOURCE" "$SOURCE.before-qualification-worker"
install -m 0644 "$SOURCE.new" "$SOURCE"
install -m 0644 "$WORKER.new" "$WORKER"
rm -f "$SOURCE.new" "$WORKER.new"
start_api(){
 DK rm -f "$API" >/dev/null 2>&1 || true
 DK run -d --name "$API" --restart unless-stopped --network host \
  -e PORT=18192 -e G2B_SECRET_PATH=/run/secrets/g2b.env \
  -e G2B_DB_PATH=/app/data/bids.sqlite3 \
  -e G2B_QUAL_REPORT=/app/reports/qualification-year.json \
  -v "$SOURCE:/app/g2b-proxy.py:ro" \
  -v "$BASE/secrets/g2b.env:/run/secrets/g2b.env:ro" \
  -v "$BASE/data:/app/data" -v "$BASE/reports:/app/reports:ro" \
  "$IMG" python -u /app/g2b-proxy.py >/dev/null
}
rollback(){
 echo 'QUALIFICATION_API_ROLLBACK=attempt'
 cp -p "$SOURCE.before-qualification-worker" "$SOURCE" || true
 start_api || true
}
trap rollback ERR
start_api
for i in $(seq 1 25); do
 if curl -fsS --max-time 4 'http://127.0.0.1:18192/api/g2b/status' >/dev/null 2>&1;then break;fi
 sleep 1
done
BASE_URL='https://api-suaveforge.suaveforge.com:18458/api/g2b'
SAVED="$(curl -fsS --max-time 20 "$BASE_URL/saved?sw=1&limit=1&offset=0")"
[[ "$SAVED" == *'"eligibilityChecked":'* ]]
[[ "$SAVED" == *'"persisted":true'* ]]
BID="$(curl -fsS --max-time 20 "$BASE_URL/eligibility?bidNo=R26BK01744830&order=000")"
[[ "$BID" == *'"ok":true'* ]]
REG="$(curl -fsS --max-time 20 "$BASE_URL/company?bizno=1308185973")"
[[ "$REG" == *'"has1468":true'* ]]
DK rm -f "$ENRICH" >/dev/null 2>&1 || true
DK run -d --name "$ENRICH" --restart unless-stopped --network host \
 -e G2B_DB_PATH=/app/data/bids.sqlite3 \
 -e G2B_LOCAL_API=http://127.0.0.1:18192/api/g2b \
 -e G2B_QUAL_BATCH=200 -e G2B_QUAL_POLL=180 \
 -v "$WORKER:/app/g2b-eligibility-worker.py:ro" \
 -v "$BASE/data:/app/data" \
 "$IMG" python -u /app/g2b-eligibility-worker.py >/dev/null
sleep 3
test "$(DK inspect -f '{{.State.Running}}' "$ENRICH")" = true
trap - ERR
echo 'QUALIFICATIONS_API_SQLITE=PASS'
echo 'QUALIFICATIONS_BACKFILL_WORKER_RUNNING=PASS'
echo 'G2B_FULL_CRAWLER_HISTORY_WORKER_PRESERVED=PASS'
echo 'NGINX_PORTS_TLS_UNCHANGED=PASS'
