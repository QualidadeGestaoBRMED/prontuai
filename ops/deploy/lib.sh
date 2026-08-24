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
STAGING_BRANCH="${STAGING_BRANCH:-staging}"

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

# Serializa os jobs de manutencao do banco (backup e purga) num lock comum.
#
# Por que nao Conflicts= no unit do systemd: Conflicts e bidirecional e da
# terminacao mutua, nao exclusao mutua — iniciar um PARA o outro. Com
# Persistent=true nos dois timers, um reboot que atrase ambos dispara os dois
# recuperando o horario perdido, e um mata o outro: pg_dump morto no meio = o
# backup do dia perdido. flock faz o segundo ESPERAR em vez de matar o primeiro.
#
# Uso: db_maintenance_lock <segundos_de_espera> <acao_no_timeout: fail|skip>
# O lock e liberado quando o script termina (o fd fecha), inclusive se morrer.
db_maintenance_lock() {
  local espera="${1:-3600}" no_timeout="${2:-fail}"
  local arquivo="${DB_LOCK_FILE:-/tmp/prontuai-db-maintenance.lock}"

  require_cmd flock
  exec 9>"$arquivo" || die "Nao consegui abrir o lock $arquivo"

  if flock -w "$espera" 9; then
    return 0
  fi

  if [ "$no_timeout" = "skip" ]; then
    log "Outro job de manutencao do banco segue rodando apos ${espera}s de espera; pulando esta execucao."
    exit 0
  fi
  die "Outro job de manutencao do banco segue rodando apos ${espera}s de espera (lock: $arquivo)."
}
