#!/usr/bin/env bash
# Installs ONLY server123's RFP/Changcom worker, never changes other containers.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE=/home/worklinks/g2b
DOCKER=/home/ggul-docker/bin/docker
SOCKET=unix:///home/ggul-docker/run/docker.sock
IMAGE_HASH="$(sha256sum "$ROOT/server/Dockerfile.worklinks-pipeline" | cut -c1-12)"
IMAGE="worklinks-g2b-pipeline:$IMAGE_HASH"
WORKER=worklinks-g2b-pipeline
SCRIPTS="$BASE/pipeline/scripts"
SNAPSHOTS="$BASE/data/snapshots"
SOURCE="$ROOT/server/worklinks-server123-pipeline.py"
TARGET="$BASE/pipeline/worklinks-server123-pipeline.py"
dk(){ "$DOCKER" -H "$SOCKET" "$@"; }
for item in "$SOURCE" "$ROOT/server/Dockerfile.worklinks-pipeline" \
    "$ROOT/scripts/refresh_worklinks_rfp.py" \
    "$ROOT/scripts/refresh_worklinks_actionable.py" \
    "$ROOT/tests/test_worklinks_server123_pipeline.py" \
    "$DOCKER" "$BASE/data/bids.sqlite3";do
  test -s "$item" || { echo "PIPELINE_REQUIRED_FILE_MISSING"; exit 5; }
done
test -S /home/ggul-docker/run/docker.sock
test "$(dk inspect -f '{{.State.Running}}' worklinks-g2b-api)" = true
test "$(curl -sS -o /dev/null -w '%{http_code}' --max-time 8 \
    'http://127.0.0.1:18192/api/g2b/pipeline-status')" = 200
# Unit test runs on a temporary directory only.
dk run --rm \
    -v "$SOURCE:/app/server/worklinks-server123-pipeline.py:ro" \
    -v "$ROOT/tests/test_worklinks_server123_pipeline.py:/app/tests/test_worklinks_server123_pipeline.py:ro" \
    python:3.11-alpine python /app/tests/test_worklinks_server123_pipeline.py
if ! dk image inspect "$IMAGE" >/dev/null 2>&1;then
  dk build --pull=false -f "$ROOT/server/Dockerfile.worklinks-pipeline" \
      -t "$IMAGE" "$ROOT/server"
fi
dk run --rm "$IMAGE" sh -c 'command -v hwp5txt >/dev/null && python -c "import pypdf; print(\"PIPELINE_PDF_HWP_READY=PASS\")"'
mkdir -p "$SCRIPTS" "$SNAPSHOTS" "$SNAPSHOTS/audits"
# GitHub Pages files are seed-only. An existing 123 snapshot is never overwritten.
for name in changcom-actionable.json rfp-clauses.json rfp-coverage-index.json \
    changcom-bid-review.json sme-cert-snapshot.json direct-production-snapshot.json \
    official-awards-snapshot.json;do
  if test ! -s "$SNAPSHOTS/$name" && test -s "$ROOT/startup-support/$name";then
    cp -p "$ROOT/startup-support/$name" "$SNAPSHOTS/$name"
  fi
done
BACKFILL=audits/changcom-rfp-backfill-60-20261110.json
if test ! -s "$SNAPSHOTS/$BACKFILL" && test -s "$ROOT/startup-support/$BACKFILL";then
  cp -p "$ROOT/startup-support/$BACKFILL" "$SNAPSHOTS/$BACKFILL"
fi
# Initial gzip publication does not touch the source JSON.
dk run --rm -i -v "$SNAPSHOTS:/app/snapshots" python:3.11-alpine python - <<'PY'
import gzip,os,pathlib,shutil
base=pathlib.Path('/app/snapshots')
for name in ('changcom-actionable.json','rfp-clauses.json','rfp-coverage-index.json'):
    src=base/name
    dst=base/(name+'.gz')
    if not src.is_file() or dst.is_file():continue
    temp=base/(name+'.gz.pending')
    with src.open('rb') as data,gzip.open(temp,'wb',compresslevel=6) as out:
        shutil.copyfileobj(data,out,length=1024*1024)
    os.replace(temp,dst)
    print('PIPELINE_SEED_COMPRESSED',name,flush=True)
PY

if cmp -s "$SOURCE" "$TARGET" &&
   cmp -s "$ROOT/scripts/refresh_worklinks_actionable.py" "$SCRIPTS/refresh_worklinks_actionable.py" &&
   cmp -s "$ROOT/scripts/refresh_worklinks_rfp.py" "$SCRIPTS/refresh_worklinks_rfp.py" &&
   test "$(dk inspect -f '{{.State.Running}}' "$WORKER" 2>/dev/null || true)" = true &&
   test "$(dk inspect -f '{{.Config.Image}}' "$WORKER" 2>/dev/null || true)" = "$IMAGE";then
  echo 'WORKLINKS_SERVER123_PIPELINE_ALREADY_CURRENT=PASS'
  exit 0
fi
mkdir -p "$BASE/pipeline/backup"
for f in "$TARGET" "$SCRIPTS/refresh_worklinks_actionable.py" "$SCRIPTS/refresh_worklinks_rfp.py";do
  test ! -s "$f" || cp -p "$f" "$BASE/pipeline/backup/$(basename "$f")"
done
PREVIOUS="$(dk inspect -f '{{.Config.Image}}' "$WORKER" 2>/dev/null || true)"
start_worker(){
  dk rm -f "$WORKER" >/dev/null 2>&1 || true
  dk run -d --name "$WORKER" --restart unless-stopped --network host \
      -e G2B_PIPELINE_DATA=/app/data \
      -e G2B_PIPELINE_SCRIPTS=/app/scripts \
      -e WORKLINKS_G2B_API=http://127.0.0.1:18192/api/g2b \
      -e G2B_RFP_BATCH=8 \
      -v "$BASE/data:/app/data" \
      -v "$SCRIPTS:/app/scripts:ro" \
      -v "$TARGET:/app/worklinks-server123-pipeline.py:ro" \
      "$1" python -u /app/worklinks-server123-pipeline.py >/dev/null
}
rollback(){
  echo 'PIPELINE_DEPLOY_ROLLBACK_ATTEMPT'
  dk rm -f "$WORKER" >/dev/null 2>&1 || true
  for f in "$TARGET" "$SCRIPTS/refresh_worklinks_actionable.py" "$SCRIPTS/refresh_worklinks_rfp.py";do
    saved="$BASE/pipeline/backup/$(basename "$f")"
    if test -s "$saved";then cp -p "$saved" "$f";else rm -f "$f";fi
  done
  if test -n "$PREVIOUS" && test -s "$TARGET";then start_worker "$PREVIOUS" || true;fi
}
trap rollback ERR
install -m 0644 "$SOURCE" "$TARGET"
install -m 0644 "$ROOT/scripts/refresh_worklinks_actionable.py" "$SCRIPTS/refresh_worklinks_actionable.py"
install -m 0644 "$ROOT/scripts/refresh_worklinks_rfp.py" "$SCRIPTS/refresh_worklinks_rfp.py"
start_worker "$IMAGE"
sleep 4
test "$(dk inspect -f '{{.State.Running}}' "$WORKER")" = true
dk logs --tail 60 "$WORKER" 2>&1 | grep -q 'PIPELINE_SERVER123_STARTED'
for name in changcom-actionable rfp-clauses rfp-coverage-index;do
  code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 \
      "http://127.0.0.1:18192/api/g2b/snapshot?name=$name")"
  test "$code" = 200 || { echo "PIPELINE_LOCAL_SNAPSHOT_UNAVAILABLE=$name"; exit 9; }
done
trap - ERR
echo 'WORKLINKS_SERVER123_PIPELINE_RUNNING=PASS'
echo 'WORKLINKS_SNAPSHOTS_123_READ_ONLY=PASS'
echo 'OTHER_G2B_CONTAINERS_UNCHANGED=PASS'
