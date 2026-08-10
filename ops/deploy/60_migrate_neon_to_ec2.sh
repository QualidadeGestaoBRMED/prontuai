#!/usr/bin/env bash
# Cutover do banco: Neon -> Postgres local (container prontuai-db) na mesma
# VPS. Janela de manutencao curta: o backend fica fora do ar durante o dump
# do Neon + restore local, para garantir que nenhuma escrita fique para
# tras (dump so comeca depois do backend parar).
#
# Banco e backend vivem em pastas SEPARADAS na VPS (de proposito, ver
# docker-compose.db.yml): este script opera nas duas.
#
# Pre-requisitos:
#   - DB_DEPLOY_DIR (default /home/ec2-user/prontuai-db) com
#     docker-compose.db.yml e .env proprio (POSTGRES_USER/PASSWORD/DB).
#   - BACKEND_DEPLOY_DIR (default /home/ec2-user/prontuai) com
#     docker-compose.yml e .env proprio (DATABASE_URL, JWT_SECRET_KEY etc.).
#   - NEON_DATABASE_URL exportado no ambiente (a URL antiga do Neon), ex.:
#       export NEON_DATABASE_URL='postgresql://user:pass@ep-xxx.neon.tech/dbname?sslmode=require'
#   - Aviso previo enviado (esse script para o backend).
#
# Uso (rode de qualquer diretorio, os caminhos sao absolutos):
#   NEON_DATABASE_URL=... ./60_migrate_neon_to_ec2.sh
#   # ou, se as pastas de deploy tiverem outro caminho:
#   NEON_DATABASE_URL=... DB_DEPLOY_DIR=/outro/caminho BACKEND_DEPLOY_DIR=/outro/caminho ./60_migrate_neon_to_ec2.sh
#
# Rollback automatico: se o health check pos-cutover falhar, o script
# restaura o .env anterior (apontando pro Neon) e reinicia o backend.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

require_cmd docker curl

DB_DEPLOY_DIR="${DB_DEPLOY_DIR:-/home/ec2-user/prontuai-db}"
BACKEND_DEPLOY_DIR="${BACKEND_DEPLOY_DIR:-/home/ec2-user/prontuai}"

require_file "$DB_DEPLOY_DIR/.env"
require_file "$DB_DEPLOY_DIR/docker-compose.db.yml"
require_file "$BACKEND_DEPLOY_DIR/.env"
require_file "$BACKEND_DEPLOY_DIR/docker-compose.yml"

NEON_DATABASE_URL="${NEON_DATABASE_URL:?Exporte NEON_DATABASE_URL com a connection string do Neon}"
DUMP_DIR="${DUMP_DIR:-$DB_DEPLOY_DIR/backups}"
mkdir -p "$DUMP_DIR"
TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"
DUMP_PATH="$DUMP_DIR/neon-final-${TIMESTAMP}.dump"

# POSTGRES_USER/PASSWORD/DB vivem no .env do banco, nao no .env do backend
# (pastas separadas, ver docker-compose.db.yml).
set -a
. "$DB_DEPLOY_DIR/.env"
set +a
POSTGRES_USER="${POSTGRES_USER:?POSTGRES_USER ausente no .env do banco ($DB_DEPLOY_DIR/.env)}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD ausente no .env do banco ($DB_DEPLOY_DIR/.env)}"
POSTGRES_DB="${POSTGRES_DB:-prontuai}"

TABLES_TO_CHECK=(users clinics documents)

count_local() {
  local table="$1"
  docker exec prontuai-db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT count(*) FROM $table;" 2>/dev/null || echo "erro"
}

count_neon() {
  local table="$1"
  docker run --rm postgres:17-alpine psql "$NEON_DATABASE_URL" -tAc "SELECT count(*) FROM $table;" 2>/dev/null || echo "erro"
}

log "== Passo 1/6: subindo prontuai-db via docker-compose.db.yml (se ainda nao estiver) =="
(cd "$DB_DEPLOY_DIR" && docker compose -f docker-compose.db.yml up -d)
for i in $(seq 1 30); do
  status="$(docker inspect --format '{{.State.Health.Status}}' prontuai-db 2>/dev/null || echo starting)"
  [ "$status" = "healthy" ] && break
  sleep 2
done
[ "$status" = "healthy" ] || die "prontuai-db nao ficou healthy a tempo"
log "prontuai-db healthy."

echo
log "Isso vai PARAR o backend de producao agora para congelar escritas no Neon."
if [ "${AUTO_CONFIRM:-0}" != "1" ]; then
  read -r -p "Confirma inicio da janela de manutencao? (digite 'sim'): " CONFIRM
  [ "$CONFIRM" = "sim" ] || die "Cancelado pelo operador."
fi

log "== Passo 2/6: parando prontuai-backend (inicio da janela de manutencao) =="
(cd "$BACKEND_DEPLOY_DIR" && docker compose -f docker-compose.yml stop prontuai-backend)
append_log "cutover: backend parado em $(date -Iseconds)"

log "== Passo 3/6: dump final do Neon -> $DUMP_PATH =="
docker run --rm -v "$DUMP_DIR:/backup" postgres:17-alpine \
  pg_dump "$NEON_DATABASE_URL" -Fc -f "/backup/$(basename "$DUMP_PATH")" \
  || die "pg_dump do Neon falhou (backend ainda parado — restart manual se for abortar)"
[ -s "$DUMP_PATH" ] || die "Dump do Neon veio vazio"

log "Contagens no Neon (pos-freeze, referencia para validar o restore):"
declare -A NEON_COUNTS
for t in "${TABLES_TO_CHECK[@]}"; do
  NEON_COUNTS[$t]="$(count_neon "$t")"
  printf '  neon.%-10s %s\n' "$t" "${NEON_COUNTS[$t]}"
done

log "== Passo 4/6: restaurando dump em prontuai-db/$POSTGRES_DB =="
cat "$DUMP_PATH" | docker exec -i prontuai-db pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --clean --if-exists --no-owner --no-privileges \
  || die "pg_restore falhou — backend continua parado, banco local pode estar inconsistente. Nao prossiga sem investigar."

log "Contagens locais pos-restore:"
MISMATCH=0
for t in "${TABLES_TO_CHECK[@]}"; do
  LOCAL_COUNT="$(count_local "$t")"
  printf '  local.%-10s %s (neon: %s)\n' "$t" "$LOCAL_COUNT" "${NEON_COUNTS[$t]}"
  [ "$LOCAL_COUNT" = "${NEON_COUNTS[$t]}" ] || MISMATCH=1
done

if [ "$MISMATCH" = "1" ]; then
  log "!!! Contagens nao batem. NAO trocando DATABASE_URL. Reiniciando backend contra o Neon (rollback automatico) !!!"
  (cd "$BACKEND_DEPLOY_DIR" && docker compose -f docker-compose.yml up -d --remove-orphans prontuai-backend)
  die "Cutover abortado por divergencia de dados. Investigue o dump/restore antes de tentar de novo."
fi

log "== Passo 5/6: trocando DATABASE_URL para o Postgres local =="
BACKEND_ENV="$BACKEND_DEPLOY_DIR/.env"
cp "$BACKEND_ENV" "$BACKEND_ENV.bak.${TIMESTAMP}"
NEW_DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@prontuai-db:5432/${POSTGRES_DB}"
if grep -q '^DATABASE_URL=' "$BACKEND_ENV"; then
  sed -i "s#^DATABASE_URL=.*#DATABASE_URL=${NEW_DATABASE_URL}#" "$BACKEND_ENV"
else
  echo "DATABASE_URL=${NEW_DATABASE_URL}" >> "$BACKEND_ENV"
fi

log "== Passo 6/6: subindo prontuai-backend contra o banco local =="
(cd "$BACKEND_DEPLOY_DIR" && docker compose -f docker-compose.yml up -d --remove-orphans prontuai-backend)

HEALTHY=0
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:${BACKEND_HTTP_PORT:-8080}/health >/dev/null 2>&1; then
    HEALTHY=1
    break
  fi
  sleep 2
done

if [ "$HEALTHY" != "1" ]; then
  log "!!! Health check falhou pos-cutover. Restaurando .env anterior (Neon) e reiniciando backend !!!"
  cp "$BACKEND_ENV.bak.${TIMESTAMP}" "$BACKEND_ENV"
  (cd "$BACKEND_DEPLOY_DIR" && docker compose -f docker-compose.yml up -d --remove-orphans prontuai-backend)
  die "Cutover revertido automaticamente. Banco local ficou restaurado em $POSTGRES_DB para investigacao, mas producao voltou a apontar pro Neon."
fi

append_log "cutover_ok dump=$DUMP_PATH mismatch=$MISMATCH"
log "Cutover concluido. Backend rodando contra o Postgres local."
log "IMPORTANTE: mantenha o projeto Neon pausado (nao deletado) por pelo menos alguns dias como fallback."
log "Backup do dump final do Neon: $DUMP_PATH (copie tambem para o bucket de backups)."
