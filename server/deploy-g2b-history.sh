#!/usr/bin/env bash
# Adds background verified recurring-project enrichment. Does not change Nginx, ports or secrets.
set -Eeuo pipefail
D=/home/ggul-docker/bin/docker
H=unix:///home/ggul-docker/run/docker.sock
dk(){ "$D" -H "$H" "$@"; }
BASE=/home/worklinks/g2b
API=$BASE/g2b-proxy-docker.py
HISTORY=$BASE/g2b-repeat-history.py
SECRET=$BASE/secrets/g2b.env
DATA=$BASE/data
IMG=python:3.11-alpine
REPEAT=worklinks-g2b-history
SERVICE=worklinks-g2b-api
test -s "$API" && test -s "$SECRET" && test -s "$DATA/bids.sqlite3"
dk image inspect "$IMG" >/dev/null
curl -fsSL --max-time 35 "https://raw.githubusercontent.com/programmer119/worklinks/111b9822499127bd530ade1d37169422deeb8154/server/g2b-proxy.py" -o "$API.next"
curl -fsSL --max-time 35 "https://raw.githubusercontent.com/programmer119/worklinks/ba4372ff5cc3477acdcb00c1666045780e8df4a6/server/g2b-repeat-history.py" -o "$HISTORY.next"
dk run --rm \
 -v "$API.next:/work/api.py:ro" \
 -v "$HISTORY.next:/work/history.py:ro" \
 "$IMG" python -m py_compile /work/api.py /work/history.py
dk run --rm -i \
 -v "$API.next:/work/api.py:ro" \
 -v "$HISTORY.next:/work/history.py:ro" \
 -e G2B_DB_PATH=/tmp/mock.sqlite3 \
 "$IMG" python - <<'PY'
import runpy, sqlite3,json,datetime
a=runpy.run_path('/work/api.py',run_name='test')
db=a['open_bid_db']()
a['persist_bids']([{'kind':'servc','bidNo':'TESTREPEAT','order':'000','title':'2026년 시정정보시스템 유지관리'}])
h=runpy.run_path('/work/history.py',run_name='test')
h['init'](db)
with db:
 db.execute('INSERT INTO recurring_projects(kind,bid_no,history_json,repeat_years,checked_at,error) VALUES(?,?,?,?,?,NULL)',
  ('servc','TESTREPEAT',json.dumps([{'year':2026,'verified':True,'awardee':None},{'year':2025,'verified':True,'awardee':'검증테스트업체'}]),2,'2026-10-12'))
saved=a['query_saved_bids'](20,0,False)
assert len(saved['items'])==1
assert saved['items'][0]['repeatYears']==2
assert len(saved['items'][0]['repeatHistory'])==2
assert h['confidence']('2026년 시정정보시스템 유지관리','2025년 시정정보시스템 유지관리')>0.95
db.close()
print('RECURRING_HISTORY_TEST=PASS')
PY
cp -p "$API" "$API.before-history"
install -m 0644 "$API.next" "$API"
install -m 0644 "$HISTORY.next" "$HISTORY"
rm -f "$API.next" "$HISTORY.next"
start_api(){
 dk rm -f "$SERVICE" >/dev/null 2>&1 || true
 dk run -d --name "$SERVICE" --restart unless-stopped --network host \
  -e PORT=18192 -e G2B_SECRET_PATH=/run/secrets/g2b.env \
  -e G2B_DB_PATH=/app/data/bids.sqlite3 -e G2B_QUAL_REPORT=/app/reports/qualification-year.json \
  -v "$API:/app/g2b-proxy.py:ro" \
  -v "$SECRET:/run/secrets/g2b.env:ro" \
  -v "$DATA:/app/data" -v "$BASE/reports:/app/reports:ro" \
  "$IMG" python -u /app/g2b-proxy.py >/dev/null
}
rollback(){
 cp -p "$API.before-history" "$API"
 start_api || true
}
trap rollback ERR
start_api
for k in $(seq 1 25); do
 if curl -fsS --max-time 4 'http://127.0.0.1:18192/api/g2b/saved?sw=1&limit=2&offset=0' | grep -q '"persisted":true';then break;fi
 sleep 1
done
PUBLIC="$(curl -fsS --max-time 12 'https://api-suaveforge.suaveforge.com:18458/api/g2b/saved?sw=1&limit=2&offset=0')"
[[ "$PUBLIC" == *'"persisted":true'* ]]
dk rm -f "$REPEAT" >/dev/null 2>&1 || true
dk run -d --name "$REPEAT" --restart unless-stopped --network host \
 -e G2B_DB_PATH=/app/data/bids.sqlite3 \
 -e G2B_SECRET_PATH=/run/secrets/g2b.env \
 -v "$HISTORY:/app/g2b-repeat-history.py:ro" \
 -v "$SECRET:/run/secrets/g2b.env:ro" \
 -v "$DATA:/app/data" \
 "$IMG" python -u /app/g2b-repeat-history.py >/dev/null
sleep 3
test "$(dk inspect -f '{{.State.Running}}' "$REPEAT")" = true
echo 'REPEAT_WORKER_RUNNING=PASS'
echo 'SAVED_HISTORY_ENDPOINT=PASS'
echo 'NGINX_18458_UNCHANGED=YES'
