#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

require_cmd docker curl
require_file "$BACKEND_DIR/docker-compose.yml"

ROLLBACK_IMAGE="${ROLLBACK_IMAGE:-}"
if [ -z "$ROLLBACK_IMAGE" ]; then
  require_file "$BASELINE_IMAGE_FILE"
  ROLLBACK_IMAGE="$(cat "$BASELINE_IMAGE_FILE")"
fi

ROLLBACK_PIN_FILE="${ROLLBACK_PIN_FILE:-/tmp/prontuai-prod.rollback.yml}"
cat > "$ROLLBACK_PIN_FILE" <<YAML
services:
  prontuai-backend:
    image: $ROLLBACK_IMAGE
YAML

cd "$BACKEND_DIR"
docker compose -f docker-compose.yml -f "$ROLLBACK_PIN_FILE" up -d --no-deps prontuai-backend

curl -fsS http://localhost/health >/dev/null

append_log "===== ROLLBACK ====="
append_log "rollback_image=$ROLLBACK_IMAGE"
append_log "rollback_pin_file=$ROLLBACK_PIN_FILE"
append_log "local_health=ok"

log "Rollback concluido com sucesso."
log "Imagem aplicada: $ROLLBACK_IMAGE"

