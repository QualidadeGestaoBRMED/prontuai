#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

require_cmd docker

STAGING_CONTAINER="${STAGING_CONTAINER:-prontuai-backend-stg}"
PROD_CONTAINER="${PROD_CONTAINER:-prontuai-backend}"

STAGING_IMAGE="$(docker inspect "$STAGING_CONTAINER" --format '{{.Image}}')"
if [ -z "$STAGING_IMAGE" ]; then
  die "Could not resolve image from $STAGING_CONTAINER"
fi

if [ ! -f "$BASELINE_IMAGE_FILE" ]; then
  docker inspect "$PROD_CONTAINER" --format '{{.Image}}' > "$BASELINE_IMAGE_FILE"
fi

cat > "$PROD_PIN_FILE" <<YAML
services:
  prontuai-backend:
    image: $STAGING_IMAGE
YAML

append_log "===== PIN PROD IMAGE ====="
append_log "prod_pin_file=$PROD_PIN_FILE"
append_log "staging_image=$STAGING_IMAGE"
append_log "baseline_image_file=$BASELINE_IMAGE_FILE"

log "Pin file gerado: $PROD_PIN_FILE"
log "Staging image: $STAGING_IMAGE"

