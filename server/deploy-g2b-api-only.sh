#!/usr/bin/env bash
# Safely update ONLY the existing WorkLinks G2B API container on server123.
# No Nginx/Caddy, firewall, public port, credentials, crawler or history changes.
set -Eeuo pipefail
BASE=/home/worklinks/g2b
API=worklinks-g2b-api
TARGET="$BASE/g2b-proxy-docker.py"
DOCKER=/home/ggul-docker/bin/docker
SOCKET=unix:///home/ggul-docker/run/docker.sock
IMG=python:3.11-alpine
SECRET="$BASE/secrets/g2b.env"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/server/g2b-proxy.py"
dk(){ "$DOCKER" -H "$SOCKET" "$@"; }
for file in "$DOCKER" "$TARGET" "$SRC" "$SECRET" "$BASE/data/bids.sqlite3"; do
  test -s "$file" || { echo "PREFLIGHT_MISSING=$file"; exit 5; }
done
dk image inspect "$IMG" >/dev/null
test "$(dk inspect -f '{{.State.Running}}' "$API")" = true
test "$(dk inspect -f '{{.HostConfig.NetworkMode}}' "$API")" = host
# The API runs against the existing DB and read-only secrets; validate in a
# disposable container BEFORE changing the production service.
NEXT="$TARGET.next"
cp -p "$SRC" "$NEXT"
trap 'rm -f "$NEXT"' EXIT
dk run --rm -v "$NEXT:/app/api.py:ro" "$IMG" python -m py_compile /app/api.py
dk run --rm -v "$NEXT:/app/api.py:ro" -v "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/tests/test_direct_production.py:/app/test_direct_production.py:ro" "$IMG" python /app/test_direct_production.py
dk run --rm -v "$NEXT:/app/api.py:ro" -v "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/tests/test_bid_evidence.py:/app/test_bid_evidence.py:ro" "$IMG" python /app/test_bid_evidence.py
dk run --rm -v "$NEXT:/app/api.py:ro" -v "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/tests/test_contract_evidence.py:/app/test_contract_evidence.py:ro" "$IMG" python /app/test_contract_evidence.py
dk run --rm -e WORKLINKS_STATE_DB=/tmp/worklinks-state-test.sqlite3 -v "$NEXT:/app/g2b-proxy.py:ro" -v "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/tests/test_worklinks_user_state.py:/app/test_worklinks_user_state.py:ro" "$IMG" python /app/test_worklinks_user_state.py
dk run --rm -i -v "$NEXT:/app/api.py:ro" -e G2B_DB_PATH=/tmp/test.sqlite3 "$IMG" python - <<'PY'
import datetime,json,runpy
p=runpy.run_path('/app/api.py',run_name='preflight_test')
rows=[{'kind':'servc','bidNo':'R26BK12345678','order':'0','title':'공공정보시스템 개발'}]
assert p['persist_bids'](rows)['storedTotal']==1
db=p['open_bid_db']()
with db:
 db.execute("INSERT INTO bid_license_cache(bid_no,bid_ord,payload,checked_at) VALUES(?,?,?,?)",
  ('R26BK12345678','000',json.dumps({'ok':True,'complete':True,'requirements':[{'codes':['1468']}]}),
   datetime.datetime.now(datetime.timezone.utc).isoformat()))
db.close()
result=p['query_saved_bids'](20,0,True)
assert result['eligibilityChecked']==1
assert result['eligibilityLinked']==1
assert result['items'][0]['bidEligibility']['requirements'][0]['codes']==['1468']
print('WORKLINKS_API_PREFLIGHT=PASS')
PY
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="$TARGET.backup-$STAMP"
cp -p "$TARGET" "$BACKUP"
start_api(){
 dk rm -f "$API" >/dev/null 2>&1 || true
 dk run -d --name "$API" --restart unless-stopped --network host \
  -e PORT=18192 -e G2B_SECRET_PATH=/run/secrets/g2b.env \
  -e G2B_DB_PATH=/app/data/bids.sqlite3 \
  -e G2B_QUAL_REPORT=/app/reports/qualification-year.json \
  -v "$TARGET:/app/g2b-proxy.py:ro" \
  -v "$SECRET:/run/secrets/g2b.env:ro" \
  -v "$BASE/data:/app/data" \
  -v "$BASE/reports:/app/reports:ro" \
  "$IMG" python -u /app/g2b-proxy.py >/dev/null
}
rollback(){
 echo 'API_DEPLOY_FAILED_ROLLING_BACK'
 cp -p "$BACKUP" "$TARGET"
 start_api || true
}
trap rollback ERR
install -m 0644 "$NEXT" "$TARGET"
start_api
ready=0
for n in $(seq 1 25);do
 if curl -fsS --max-time 4 'http://127.0.0.1:18192/api/g2b/saved?sw=1&limit=1&offset=0' |
   grep -q '"eligibilityLinked"';then ready=1;break;fi
 sleep 1
done
test "$ready" = 1
# Route-existence smoke without consuming upstream quota. Invalid requests to
# deployed endpoints must be 400, not an absent-route 404.
for path in 'contract-notice?bidNo=BAD&bizno=1' 'bid-change-price?bidNo=BAD&order=0';do
  code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:18192/api/g2b/$path")"
  test "$code" = 400 || { echo "MISSING_NEW_G2B_ROUTE=$path status=$code"; exit 9; }
done
echo 'WORKLINKS_CONTRACT_AND_CHANGE_API_ROUTES=PASS'
PUBLIC="$(curl -fsS --max-time 20 'https://api-suaveforge.suaveforge.com:18458/api/g2b/saved?sw=1&limit=1&offset=0')"
[[ "$PUBLIC" == *'"eligibilityLinked"'* ]]
test "$(dk inspect -f '{{.State.Running}}' "$API")" = true
trap - ERR
echo 'WORKLINKS_G2B_API_DEPLOY=PASS'
echo 'HTTPS_NGINX=unchanged;PORTS=unchanged;SECRETS=unchanged'
echo 'CRAWLER_AND_HISTORY_WORKERS=unchanged'
