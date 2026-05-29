#!/usr/bin/env bash
# Botão de pânico: derruba o staging e restaura o prod ao baseline salvo.
# Use quando suspeitar que o staging quebrou alguma coisa.
#
# Pré-requisito: 00_precheck.sh foi executado antes do teste, gerando
# /tmp/prontuai-baseline.image (o script aborta se não encontrar).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

require_cmd docker curl

log "== Passo 1/4: derrubando staging =="
if docker ps -a --format '{{.Names}}' | grep -q '^prontuai-backend-stg$'; then
  docker stop prontuai-backend-stg >/dev/null 2>&1 || true
  docker rm prontuai-backend-stg >/dev/null 2>&1 || true
  log "Staging derrubado."
else
  log "Staging já não estava rodando."
fi

log "== Passo 2/4: verificando estado do prod =="
PROD_HEALTH="$(curl -fsS --max-time 5 http://localhost/health || echo '')"
log "Resposta /health do prod: ${PROD_HEALTH:-<sem resposta>}"

if echo "$PROD_HEALTH" | grep -q 'staging_marker'; then
  log "DETECTADO: container de prod está rodando imagem de staging!"
  RESTORE_PROD=1
elif [ -z "$PROD_HEALTH" ]; then
  log "Prod não respondeu — vou tentar restaurar imagem baseline."
  RESTORE_PROD=1
else
  log "Prod respondeu normalmente. Sem necessidade de restaurar imagem."
  RESTORE_PROD=0
fi

if [ "$RESTORE_PROD" = "1" ]; then
  log "== Passo 3/4: restaurando imagem baseline do prod =="
  require_file "$BASELINE_IMAGE_FILE"
  ROLLBACK_IMAGE="$(cat "$BASELINE_IMAGE_FILE")"
  log "Imagem baseline: $ROLLBACK_IMAGE"

  ROLLBACK_PIN_FILE="/tmp/prontuai-prod.panic-rollback.yml"
  cat > "$ROLLBACK_PIN_FILE" <<YAML
services:
  prontuai-backend:
    image: $ROLLBACK_IMAGE
YAML

  cd "$BACKEND_DIR"
  docker compose -f docker-compose.yml -f "$ROLLBACK_PIN_FILE" up -d --no-deps prontuai-backend
  sleep 3
  curl -fsS http://localhost/health >/dev/null
  append_log "panic_rollback=ok image=$ROLLBACK_IMAGE"
  log "Prod restaurado para baseline."
else
  log "== Passo 3/4: pulado (prod estava OK) =="
fi

log "== Passo 4/4: relatório final =="
echo "  - container prod:"
docker ps --filter 'name=prontuai-backend' --format '    {{.Names}} | {{.Image}} | {{.Status}}'
echo "  - /health local:    $(curl -fsS --max-time 5 http://localhost/health 2>&1 || echo '<erro>')"
echo "  - /health público:  $(curl -fsS --max-time 5 https://api.prontuai.cloud/health 2>&1 || echo '<erro>')"
echo
log "Se ainda houver dúvida sobre dados (DB/Drive), veja Cenário D no CONTEXTO.md."
