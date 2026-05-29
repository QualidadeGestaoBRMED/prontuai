#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

require_cmd git docker curl rg

append_log "===== PRECHECK START ====="
append_log "root=$ROOT_DIR"

BASELINE_IMAGE="$(docker inspect prontuai-backend --format '{{.Image}}')"
printf '%s\n' "$BASELINE_IMAGE" > "$BASELINE_IMAGE_FILE"

{
  echo "===== PRONTUAI RELEASE EVIDENCE $(date -Iseconds) ====="
  echo "[git-branch]"
  git -C "$ROOT_DIR" branch -vv
  echo
  echo "[docker-ps]"
  docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
  echo
  echo "[health-localhost]"
  curl -fsS http://localhost/health
  echo
  echo "[backend-image]"
  echo "$BASELINE_IMAGE"
  echo
  echo "[baseline-image-metadata]"
  docker image inspect back-end-prontuai-backend --format 'ID={{.Id}} Created={{.Created}}'
  echo
  echo "[baseline-image-present]"
  docker image ls | rg "${BASELINE_IMAGE#sha256:}" || true
  echo "===== END ====="
} | tee -a "$LOG_FILE"

append_log "baseline_image=$BASELINE_IMAGE"
append_log "baseline_image_file=$BASELINE_IMAGE_FILE"
append_log "===== PRECHECK END ====="

log "Precheck concluido."
log "Evidence: $LOG_FILE"
log "Baseline image: $BASELINE_IMAGE"

