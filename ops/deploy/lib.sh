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

# Reporta o resultado de um job para o coletor OTel, via OTLP/HTTP.
#
# Emite tres metricas, e a que importa e a primeira:
#
#   job_last_success_timestamp_seconds  — so em sucesso. O alerta e sobre a
#       IDADE dela (`time() - metrica > limite`), nao sobre erro. Isso pega o
#       caso que exit code nao pega: timer que nunca disparou, script que
#       travou, maquina desligada. Um job que simplesmente para de rodar e
#       invisivel para alerta baseado em falha.
#   job_last_run_timestamp_seconds      — sempre, para distinguir "rodou e
#       falhou" de "nao rodou".
#   job_last_exit_code                  — 0 em sucesso.
#
# O atributo se chama "task", nao "job": o exporter Prometheus do coletor ja
# cria um label `job` a partir do service.name, e um atributo homonimo faz a
# metrica ser DESCARTADA com "duplicate label names in constant and variable
# labels" — com HTTP 200 e partialSuccess vazio na resposta. So o log do
# coletor denuncia.
#
# Nao falha o job se o envio nao der certo: telemetria nunca deve derrubar a
# tarefa que ela observa.
#
# Uso: report_job_result <nome-do-job> <exit_code> [duracao_segundos]
# Requer JOBS_OTLP_ENDPOINT e JOBS_OTLP_TOKEN no ambiente (ver .env do deploy).
report_job_result() {
  local nome="$1" codigo="${2:-0}" duracao="${3:-0}"
  local endpoint="${JOBS_OTLP_ENDPOINT:-}" token="${JOBS_OTLP_TOKEN:-}"

  if [ -z "$endpoint" ]; then
    log "JOBS_OTLP_ENDPOINT nao definido; resultado do job nao reportado."
    return 0
  fi
  command -v curl >/dev/null 2>&1 || { log "curl ausente; job nao reportado."; return 0; }

  local agora_ns agora_s
  agora_s="$(date +%s)"
  agora_ns="${agora_s}000000000"

  # Gauge com o instante do ultimo sucesso: so escreve quando deu certo, para a
  # metrica "envelhecer" enquanto o job estiver quebrado.
  local metricas=""
  if [ "$codigo" -eq 0 ]; then
    metricas="$(_otlp_gauge job_last_success_timestamp_seconds "$nome" "$agora_s" "$agora_ns"),"
  fi
  metricas="${metricas}$(_otlp_gauge job_last_run_timestamp_seconds "$nome" "$agora_s" "$agora_ns"),"
  metricas="${metricas}$(_otlp_gauge job_last_exit_code "$nome" "$codigo" "$agora_ns"),"
  metricas="${metricas}$(_otlp_gauge job_duration_seconds "$nome" "$duracao" "$agora_ns")"

  local payload
  payload="$(printf '{"resourceMetrics":[{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":"%s"}}]},"scopeMetrics":[{"metrics":[%s]}]}]}' \
    "${JOBS_SERVICE_NAME:-prontuai-jobs}" "$metricas")"

  if curl -fsS --max-time 10 -o /dev/null \
       -X POST "${endpoint%/}/v1/metrics" \
       -H "Content-Type: application/json" \
       ${token:+-H "Authorization: Bearer $token"} \
       --data "$payload"; then
    log "Resultado do job '$nome' reportado (exit=$codigo, ${duracao}s)."
  else
    log "AVISO: falha ao reportar o job '$nome'; a tarefa em si nao foi afetada."
  fi
  return 0
}

_otlp_gauge() {
  printf '{"name":"%s","gauge":{"dataPoints":[{"asDouble":%s,"timeUnixNano":"%s","attributes":[{"key":"task","value":{"stringValue":"%s"}}]}]}}' \
    "$1" "$3" "$4" "$2"
}

# Instala o report automatico na saida do script, com duracao medida.
# Uso: no inicio do script, apos o source do lib.sh: track_job <nome>
track_job() {
  JOB_NOME="$1"
  JOB_INICIO="$(date +%s)"
  trap 'report_job_result "$JOB_NOME" "$?" "$(( $(date +%s) - JOB_INICIO ))"' EXIT
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
