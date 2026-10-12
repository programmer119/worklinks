#!/usr/bin/env bash
# WorkLinks G2B: deploy full-page automatic collector on existing server123.
# Reuses existing HTTPS Nginx 18458 -> API 18192. Never edits Nginx, firewall or secret.
set -Eeuo pipefail
DOCKER=/home/ggul-docker/bin/docker
SOCKET=unix:///home/ggul-docker/run/docker.sock
BASE=/home/worklinks/g2b
SECRET="$BASE/secrets/g2b.env"
API=worklinks-g2b-api
CRAWLER=worklinks-g2b-crawler
API_SOURCE="$BASE/g2b-proxy-docker.py"
CRAWLER_SOURCE="$BASE/g2b-full-crawler.py"
API_REV=111b9822499127bd530ade1d37169422deeb8154
CRAWLER_REV=54ad9fae04603d93caaf882e028f5b4aef708731
IMG=python:3.11-alpine
dk(){ "$DOCKER" -H "$SOCKET" "$@"; }

for p in "$DOCKER" "$SECRET" "$API_SOURCE"; do test -e "$p" || { echo "MISSING $p"; exit 5; }; done
install -d -m 0755 "$BASE/data" "$BASE/reports"
test -s "$BASE/data/bids.sqlite3"
curl -fsSL --max-time 35 \
 "https://raw.githubusercontent.com/programmer119/worklinks/$API_REV/server/g2b-proxy.py" \
 -o "$API_SOURCE.next"
curl -fsSL --max-time 35 \
 "https://raw.githubusercontent.com/programmer119/worklinks/$CRAWLER_REV/server/g2b-full-crawler.py" \
 -o "$CRAWLER_SOURCE.next"
dk image inspect "$IMG" >/dev/null
dk run --rm \
 -v "$API_SOURCE.next:/app/g2b-proxy.py:ro" \
 -v "$CRAWLER_SOURCE.next:/app/g2b-full-crawler.py:ro" \
 "$IMG" python -m py_compile /app/g2b-proxy.py /app/g2b-full-crawler.py

# Test migration/duplicate handling in a disposable container, not production DB.
dk run --rm -i \
  -v "$API_SOURCE.next:/app/g2b-proxy.py:ro" \
  -v "$CRAWLER_SOURCE.next:/app/g2b-full-crawler.py:ro" \
  -e G2B_DB_PATH=/tmp/g2b-test.sqlite3 "$IMG" python - <<'PY'
import runpy
p=runpy.run_path('/app/g2b-proxy.py',run_name='test')
a={'kind':'servc','bidNo':'TEST123456','order':'000','title':'데이터 인공지능 플랫폼 개발'}
b={'kind':'thng','bidNo':'TEST654321','order':'000','title':'청소 용역'}
assert p['persist_bids']([a,b])['storedTotal']==2
assert p['persist_bids']([a,b])['storedTotal']==2
assert p['query_saved_bids'](20,0,True)['totalCount']==1
c=runpy.run_path('/app/g2b-full-crawler.py',run_name='test')
db=c['connect']()
assert c['save'](db,[a,b])==2
assert db.execute('SELECT COUNT(*) FROM bid_notices').fetchone()[0]==2
assert db.execute('SELECT COUNT(*) FROM bid_notices WHERE sw_candidate=1').fetchone()[0]==1
db.close()
print('FULL_CRAWLER_SQLITE_MIGRATION_AND_DEDUP=PASS')
PY

cp -p "$API_SOURCE" "$API_SOURCE.previous"
install -m 0644 "$API_SOURCE.next" "$API_SOURCE"
install -m 0644 "$CRAWLER_SOURCE.next" "$CRAWLER_SOURCE"
rm -f "$API_SOURCE.next" "$CRAWLER_SOURCE.next"

start_api(){
 dk rm -f "$API" >/dev/null 2>&1 || true
 dk run -d --name "$API" --restart unless-stopped --network host \
   -e PORT=18192 -e G2B_SECRET_PATH=/run/secrets/g2b.env \
   -e G2B_DB_PATH=/app/data/bids.sqlite3 \
   -e G2B_QUAL_REPORT=/app/reports/qualification-year.json \
   -v "$API_SOURCE:/app/g2b-proxy.py:ro" \
   -v "$SECRET:/run/secrets/g2b.env:ro" \
   -v "$BASE/data:/app/data" \
   -v "$BASE/reports:/app/reports:ro" \
   "$IMG" python -u /app/g2b-proxy.py >/dev/null
}
rollback(){
 echo 'API_ROLLBACK=attempt'
 cp -p "$API_SOURCE.previous" "$API_SOURCE" || true
 start_api || true
}
trap rollback ERR
start_api
ready=0
for n in $(seq 1 25); do
 if curl -fsS --max-time 4 'http://127.0.0.1:18192/api/g2b/saved?sw=1&limit=1&offset=0' | grep -q '"persisted":true'; then ready=1;break;fi
 sleep 1
done
test "$ready" = 1
PUBLIC="$(curl -fsS --max-time 18 'https://api-suaveforge.suaveforge.com:18458/api/g2b/saved?sw=1&limit=1&offset=0')"
[[ "$PUBLIC" == *'"persisted":true'* ]]
echo 'PUBLIC_SAVED_SW_FILTER=PASS'

# Collector uses a dedicated container; no new public port. Crash/reboot auto-restart.
dk rm -f "$CRAWLER" >/dev/null 2>&1 || true
dk run -d --name "$CRAWLER" --restart unless-stopped --network host \
  -e G2B_SECRET_PATH=/run/secrets/g2b.env \
  -e G2B_DB_PATH=/app/data/bids.sqlite3 \
  -e G2B_BACKFILL_DAYS=14 -e G2B_REFRESH_DAYS=3 -e G2B_INTERVAL_SECONDS=3600 \
  -v "$CRAWLER_SOURCE:/app/g2b-full-crawler.py:ro" \
  -v "$SECRET:/run/secrets/g2b.env:ro" \
  -v "$BASE/data:/app/data" \
  "$IMG" python -u /app/g2b-full-crawler.py >/dev/null

sleep 3
state="$(curl -fsS --max-time 8 'https://api-suaveforge.suaveforge.com:18458/api/g2b/crawl-status')"
[[ "$state" == *'"installed":true'* ]]
[[ "$state" == *'"state":"running"'* || "$state" == *'"state":"completed"'* ]]
dk inspect -f '{{.State.Running}}' "$CRAWLER" | grep -q true
trap - ERR
echo 'WORKLINKS_FULL_CRAWLER_ACTIVE=PASS'
echo 'RESTART_POLICY=unless-stopped'
echo 'BACKFILL_DAYS=14;REFRESH_DAYS=3;INTERVAL_SECONDS=3600'
echo 'HTTPS_NGINX=unchanged;PORTS=unchanged;KEY=unchanged'
