#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

require_cmd docker curl
require_file "$PROD_PIN_FILE"
require_file "$BACKEND_DIR/docker-compose.yml"

PUBLIC_HEALTH_URL="${PUBLIC_HEALTH_URL:-https://api.prontuai.cloud/health}"
CHECK_PUBLIC_HEALTH="${CHECK_PUBLIC_HEALTH:-1}"

cd "$BACKEND_DIR"
docker compose stop prontuai-backend
docker compose -f docker-compose.yml -f "$PROD_PIN_FILE" up -d --no-deps prontuai-backend

curl -fsS http://localhost/health >/dev/null
if [ "$CHECK_PUBLIC_HEALTH" = "1" ]; then
  curl -fsS "$PUBLIC_HEALTH_URL" >/dev/null
fi

append_log "===== GO LIVE ====="
append_log "pin_file=$PROD_PIN_FILE"
append_log "local_health=ok"
if [ "$CHECK_PUBLIC_HEALTH" = "1" ]; then
  append_log "public_health=ok"
fi

log "Go-live concluido com sucesso."

