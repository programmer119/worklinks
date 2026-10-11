#!/usr/bin/env bash
# WorkLinks G2B SQLite persistence activation on server123.
# Reuses existing Nginx HTTPS:18458 -> existing API localhost:18192.
# Leaves existing TLS, ports, database migrations, and other projects untouched.
set -Eeuo pipefail

DOCKER=/home/ggul-docker/bin/docker
SOCKET=unix:///home/ggul-docker/run/docker.sock
DIR=/home/worklinks/g2b
SERVICE=worklinks-g2b-api
SOURCE="$DIR/g2b-proxy-docker.py"
BACKUP="$DIR/g2b-proxy-docker.py.before-sqlite"
DATA="$DIR/data"
KEYFILE="$DIR/secrets/g2b.env"
COMMIT=6367c38c845ba71a31dbf1a1f09f6054a46a5693

test -x "$DOCKER" || { echo 'ERROR: missing Docker CLI'; exit 1; }
test -s "$SOURCE" || { echo 'ERROR: existing WorkLinks API file not found'; exit 1; }
test -s "$KEYFILE" || { echo 'ERROR: existing service key not found'; exit 1; }
install -d -m 0755 "$DATA"

curl -fsSL --max-time 30 \
  "https://raw.githubusercontent.com/programmer119/worklinks/$COMMIT/server/g2b-proxy.py" \
  -o "$SOURCE.new"
"$DOCKER" -H "$SOCKET" run --rm \
  -v "$SOURCE.new:/app/g2b-proxy.py:ro" \
  python:3.11-alpine python -m py_compile /app/g2b-proxy.py

cp -p "$SOURCE" "$BACKUP"
install -m 0644 "$SOURCE.new" "$SOURCE"
rm -f "$SOURCE.new"

start() {
  "$DOCKER" -H "$SOCKET" rm -f "$SERVICE" >/dev/null 2>&1 || true
  "$DOCKER" -H "$SOCKET" run -d --name "$SERVICE" --restart unless-stopped --network host \
    -e PORT=18192 \
    -e G2B_SECRET_PATH=/run/secrets/g2b.env \
    -e G2B_DB_PATH=/app/data/bids.sqlite3 \
    -v "$SOURCE:/app/g2b-proxy.py:ro" \
    -v "$KEYFILE:/run/secrets/g2b.env:ro" \
    -v "$DATA:/app/data" \
    python:3.11-alpine python -u /app/g2b-proxy.py >/dev/null
}
rollback(){
  echo 'RESTART_FAILED: restoring previous WorkLinks API'
  cp -p "$BACKUP" "$SOURCE"
  start || true
}
trap rollback ERR
start
for i in $(seq 1 20); do
  if curl -fsS --max-time 4 'http://127.0.0.1:18192/api/g2b/status' >/dev/null 2>&1; then break; fi
  sleep 1
done
SAVED="$(curl -fsS --max-time 8 'http://127.0.0.1:18192/api/g2b/saved?limit=1&offset=0')"
[[ "$SAVED" == *'"persisted":true'* ]] || { echo 'ERROR: saved endpoint not working'; exit 2; }
FROM="$(TZ=Asia/Seoul date -d '6 days ago' +%Y%m%d)"
TO="$(TZ=Asia/Seoul date +%Y%m%d)"
TEST="$(curl -fsS --max-time 25 "http://127.0.0.1:18192/api/g2b/bids?kind=servc&from=$FROM&to=$TO&page=1&rows=10")"
[[ "$TEST" == *'"persisted":true'* ]] || { echo 'ERROR: API read not persisted'; exit 3; }
PUBLIC="$(curl -fsS --max-time 15 'https://api-suaveforge.suaveforge.com:18458/api/g2b/saved?limit=1&offset=0')"
[[ "$PUBLIC" == *'"persisted":true'* ]] || { echo 'ERROR: public HTTPS saved endpoint'; exit 4; }
trap - ERR
echo 'WORKLINKS_SQLITE_PERSISTENCE=PASS'
echo 'PORTS: HTTPS Nginx 18458 unchanged, API 18192 unchanged.'
echo "SQLITE_DB=$DATA/bids.sqlite3"
