#!/usr/bin/env bash
# Deploy ONLY the WorkLinks G2B crawler when its source differs from production.
# No proxy/API, routes, ports, credentials, or DB schema changes.
set -Eeuo pipefail
BASE=/home/worklinks/g2b
TARGET="$BASE/g2b-full-crawler.py"
SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/server/g2b-full-crawler.py"
DOCKER=/home/ggul-docker/bin/docker
SOCKET=unix:///home/ggul-docker/run/docker.sock
IMG=python:3.11-alpine
SECRET="$BASE/secrets/g2b.env"
DB="$BASE/data/bids.sqlite3"
CRAWLER=worklinks-g2b-crawler
dk(){ "$DOCKER" -H "$SOCKET" "$@"; }
for f in "$SOURCE" "$TARGET" "$DOCKER" "$SECRET" "$DB";do
 test -s "$f" || { echo "CRAWLER_DEPLOY_MISSING=$f";exit 5; }
done
test -S /home/ggul-docker/run/docker.sock
dk image inspect "$IMG" >/dev/null
test "$(dk inspect -f '{{.State.Running}}' "$CRAWLER")" = true
test "$(dk inspect -f '{{.HostConfig.NetworkMode}}' "$CRAWLER")" = host
# An explicitly authorized key rotation requires a new bind mount even if code is identical.
if cmp -s "$SOURCE" "$TARGET" && test "${G2B_FORCE_RECREATE:-0}" != "1";then
 echo 'WORKLINKS_G2B_CRAWLER_SOURCE_CURRENT=PASS'
 exit 0
fi
# Read-only new-source validation before touching production.
dk run --rm -v "$SOURCE:/app/crawler.py:ro" "$IMG" python -m py_compile /app/crawler.py
dk run --rm -i -v "$SOURCE:/app/crawler.py:ro" "$IMG" python - <<'PY'
import runpy
m=runpy.run_path('/app/crawler.py',run_name='preflight')
sample={'bidNtceNo':'R26BK12345678','bidNtceOrd':'000','cntrctCnclsMthdNm':'제한경쟁',
 'sucsfbidMthdCd':'낙010001','sucsfbidMthdNm':'협상에 의한 계약','sucsfbidLwltRate':'87.745'}
r=m['compact'](sample,'servc')
assert r['contract']=='제한경쟁'
assert r['awardMethodCode']=='낙010001'
assert r['awardMethod']=='협상에 의한 계약'
assert r['awardFloorRate']=='87.745'
print('WORKLINKS_CRAWLER_FOUR_STRUCTURED_FIELDS=PASS')
PY
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="$TARGET.backup-$STAMP"
cp -p "$TARGET" "$BACKUP"
start_crawler(){
 dk rm -f "$CRAWLER" >/dev/null 2>&1 || true
 dk run -d --name "$CRAWLER" --restart unless-stopped --network host \
  -e G2B_SECRET_PATH=/run/secrets/g2b.env \
  -e G2B_DB_PATH=/app/data/bids.sqlite3 \
  -e WORKLINKS_RFP_LEDGER_DB=/app/data/rfp-request-ledger.sqlite3 \
  -e G2B_BACKFILL_DAYS=14 -e G2B_REFRESH_DAYS=3 -e G2B_INTERVAL_SECONDS=3600 \
  -v "$TARGET:/app/g2b-full-crawler.py:ro" \
  -v "$BASE/pipeline/scripts/rfp_call_ledger.py:/app/rfp_call_ledger.py:ro" \
  -v "$SECRET:/run/secrets/g2b.env:ro" \
  -v "$BASE/data:/app/data" \
  "$IMG" python -u /app/g2b-full-crawler.py >/dev/null
}
rollback(){
 echo 'WORKLINKS_CRAWLER_DEPLOY_FAILED_ROLLING_BACK'
 cp -p "$BACKUP" "$TARGET" || true
 start_crawler || true
}
trap rollback ERR
install -m 0644 "$SOURCE" "$TARGET"
start_crawler
sleep 5
test "$(dk inspect -f '{{.State.Running}}' "$CRAWLER")" = true
curl -fsS --max-time 8 'http://127.0.0.1:18192/api/g2b/crawl-status' |grep -q '"installed":true'
trap - ERR
echo 'WORKLINKS_G2B_CRAWLER_UPDATED=PASS'
echo 'OTHER_SERVICES_AND_API=unchanged'
