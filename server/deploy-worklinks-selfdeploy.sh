#!/usr/bin/env bash
# Bootstrap 123-owned source deployer after main data worker is healthy.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE=/home/worklinks/g2b
DK=/home/ggul-docker/bin/docker
SOCKET=unix:///home/ggul-docker/run/docker.sock
SCRIPT="$ROOT/server/worklinks-selfdeploy-loop.sh"
DOCKERFILE="$ROOT/server/Dockerfile.worklinks-selfdeploy"
CONTAINER=worklinks-selfdeploy
IMAGE="worklinks-selfdeploy:$(sha256sum "$DOCKERFILE" | cut -c1-12)"
TARGET="$BASE/selfdeploy/worklinks-selfdeploy-loop.sh"
dk(){ "$DK" -H "$SOCKET" "$@"; }
test -s "$SCRIPT" && test -s "$DOCKERFILE"
bash -n "$SCRIPT"
test -S /home/ggul-docker/run/docker.sock
test "$(dk inspect -f '{{.State.Running}}' worklinks-standalone)" = true || {
  echo "SELFDEPLOY_REQUIRES_INDEPENDENT_SOURCE_QA_CONTAINER"; exit 8;
}
mkdir -p "$BASE/selfdeploy" "$BASE/data/selfdeploy"
if ! dk image inspect "$IMAGE" >/dev/null 2>&1;then
  dk build --pull=false -t "$IMAGE" -f "$DOCKERFILE" "$ROOT/server"
fi
dk run --rm "$IMAGE" sh -c 'git --version && python3 --version && command -v flock'
if cmp -s "$SCRIPT" "$TARGET" &&
   test "$(dk inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null || true)" = true &&
   test "$(dk inspect -f '{{.Config.Image}}' "$CONTAINER" 2>/dev/null || true)" = "$IMAGE";then
   echo WORKLINKS_SELFDEPLOY_ALREADY_CURRENT=PASS;exit 0
fi
if test -s "$TARGET";then cp -p "$TARGET" "$TARGET.rollback";fi
PREVIOUS="$(dk inspect -f '{{.Config.Image}}' "$CONTAINER" 2>/dev/null || true)"
start_selfdeploy(){
  dk rm -f "$CONTAINER" >/dev/null 2>&1 || true
  dk run -d --name "$CONTAINER" --restart unless-stopped --network host \
      --security-opt no-new-privileges \
      -v "$BASE:$BASE" \
      -v /home/ggul-docker/bin/docker:/home/ggul-docker/bin/docker:ro \
      -v /home/ggul-docker/run/docker.sock:/home/ggul-docker/run/docker.sock \
      -v "$TARGET:/app/worklinks-selfdeploy-loop.sh:ro" \
      "$1" bash /app/worklinks-selfdeploy-loop.sh >/dev/null
}
rollback(){
  echo WORKLINKS_SELFDEPLOY_ROLLBACK_ATTEMPT
  dk rm -f "$CONTAINER" >/dev/null 2>&1 || true
  if test -s "$TARGET.rollback";then cp -p "$TARGET.rollback" "$TARGET";fi
  if test -n "$PREVIOUS" && test -s "$TARGET";then start_selfdeploy "$PREVIOUS" || true;fi
}
trap rollback ERR
install -m 0644 "$SCRIPT" "$TARGET"
start_selfdeploy "$IMAGE"
sleep 5
test "$(dk inspect -f '{{.State.Running}}' "$CONTAINER")" = true
dk logs --tail 30 "$CONTAINER" 2>&1 | grep -q WORKLINKS_SELFDEPLOY
trap - ERR
echo WORKLINKS_SERVER123_SELFDEPLOY_DAEMON=PASS
