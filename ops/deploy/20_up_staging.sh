#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

require_cmd docker curl
require_file "$STAGING_COMPOSE_FILE"
require_file "$STAGING_BACKEND_DIR/.env.stg"

cd "$STAGING_BACKEND_DIR"
docker compose -p "$STAGING_PROJECT" \
  -f "$STAGING_COMPOSE_FILE" \
  up -d --build prontuai-backend

for i in $(seq 1 30); do
  if curl -fsS http://localhost:8080/health >/dev/null 2>&1; then
    append_log "staging_health=ok after ${i} attempts"
    log "Staging healthy em http://localhost:8080/health"
    exit 0
  fi
  sleep 2
done

append_log "staging_health=failed"
die "Staging nao ficou saudavel em localhost:8080 dentro do tempo esperado."
