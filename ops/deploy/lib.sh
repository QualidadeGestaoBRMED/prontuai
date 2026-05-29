#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$ROOT_DIR/back-end"
WORKTREE_DIR="${WORKTREE_DIR:-$ROOT_DIR/.worktrees/prontuai-stg}"
STAGING_BACKEND_DIR="$WORKTREE_DIR/back-end"
LOG_FILE="${LOG_FILE:-/tmp/prontuai-release-$(date +%Y%m%d).log}"
STAGING_OVERRIDE_FILE="${STAGING_OVERRIDE_FILE:-/tmp/prontuai-stg.override.yml}"
STAGING_COMPOSE_FILE="${STAGING_COMPOSE_FILE:-/tmp/prontuai-stg.compose.yml}"
PROD_PIN_FILE="${PROD_PIN_FILE:-/tmp/prontuai-prod.pin.yml}"
BASELINE_IMAGE_FILE="${BASELINE_IMAGE_FILE:-/tmp/prontuai-baseline.image}"
STAGING_PROJECT="${STAGING_PROJECT:-prontuai_stg}"
STAGING_BRANCH="${STAGING_BRANCH:-feat_runbook_staging_$(date +%Y%m%d)}"

log() {
  printf '[%s] %s\n' "$(date -Iseconds)" "$*"
}

append_log() {
  mkdir -p "$(dirname "$LOG_FILE")"
  printf '[%s] %s\n' "$(date -Iseconds)" "$*" >> "$LOG_FILE"
}

die() {
  log "ERROR: $*"
  exit 1
}

require_cmd() {
  local cmd
  for cmd in "$@"; do
    command -v "$cmd" >/dev/null 2>&1 || die "Missing command: $cmd"
  done
}

require_file() {
  local file="$1"
  [ -f "$file" ] || die "File not found: $file"
}
