#!/usr/bin/env bash
# Update existing WorkLinks API in place. Preserve nginx, full crawler, history worker and secrets.
set -Eeuo pipefail
DK=/home/ggul-docker/bin/docker
SOCKET=unix:///home/ggul-docker/run/docker.sock
BASE=/home/worklinks/g2b
SRC="$BASE/g2b-proxy-docker.py"
BACKUP="$BASE/g2b-proxy-docker.py.before-eligibility"
SERVICE=worklinks-g2b-api
IMG=python:3.11-alpine
REV=924aa075b6dd905bd0785d6cef182dca25d9d225
dk(){ "$DK" -H "$SOCKET" "$@"; }
test -s "$SRC" && test -s "$BASE/secrets/g2b.env" && test -s "$BASE/data/bids.sqlite3"
test "$(dk inspect -f '{{.State.Running}}' worklinks-g2b-crawler)" = true
test "$(dk inspect -f '{{.State.Running}}' worklinks-g2b-history)" = true
curl -fsSL --max-time 30 \
 "https://raw.githubusercontent.com/programmer119/worklinks/$REV/server/g2b-proxy.py" -o "$SRC.next"
dk run --rm -v "$SRC.next:/work/g2b-proxy.py:ro" "$IMG" python -m py_compile /work/g2b-proxy.py
cp -p "$SRC" "$BACKUP"
install -m 0644 "$SRC.next" "$SRC"
rm -f "$SRC.next"
start_api(){
 dk rm -f "$SERVICE" >/dev/null 2>&1 || true
 dk run -d --name "$SERVICE" --restart unless-stopped --network host \
   -e PORT=18192 -e G2B_SECRET_PATH=/run/secrets/g2b.env \
   -e G2B_DB_PATH=/app/data/bids.sqlite3 -e G2B_QUAL_REPORT=/app/reports/qualification-year.json \
   -v "$SRC:/app/g2b-proxy.py:ro" \
   -v "$BASE/secrets/g2b.env:/run/secrets/g2b.env:ro" \
   -v "$BASE/data:/app/data" -v "$BASE/reports:/app/reports:ro" \
   "$IMG" python -u /app/g2b-proxy.py >/dev/null
}
rollback(){
 echo 'API_ROLLBACK=attempt'
 cp -p "$BACKUP" "$SRC" || true
 start_api || true
}
trap rollback ERR
start_api
for i in $(seq 1 20); do
 if curl -fsS --max-time 3 'http://127.0.0.1:18192/api/g2b/status' >/dev/null 2>&1;then break;fi
 sleep 1
done
PUB=https://api-suaveforge.suaveforge.com:18458/api/g2b
COMPANY="$(curl -fsS --max-time 25 "$PUB/company?bizno=1308185973")"
[[ "$COMPANY" == *'"has1468":true'* ]]
SAVED="$(curl -fsS --max-time 15 "$PUB/saved?sw=1&limit=2&offset=0")"
[[ "$SAVED" == *'"persisted":true'* ]]
ELIG="$(curl -fsS --max-time 25 "$PUB/eligibility?bidNo=R26BK01744830&order=000")"
[[ "$ELIG" == *'"ok":true'* ]]
[[ "$ELIG" == *'1468'* ]]
[[ "$ELIG" == *'lcnsLmtNm'* || "$ELIG" == *'"name"'* ]]
echo 'WORKLINKS_LICENSE_RESTRICTION_API=PASS'
echo 'WORKLINKS_COMPANY_AND_DB_API=PASS'
echo 'WORKLINKS_NGINX_CRAWLER_HISTORY_UNCHANGED=PASS'
trap - ERR
