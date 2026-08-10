#!/usr/bin/env bash
# Restaura um dump do Postgres (gerado por backup_postgres.sh) no container
# prontuai-db. Por padrao SEMPRE restaura num banco descartavel de teste
# (<db>_restore_drill), nunca no banco de producao, para que o restore possa
# ser exercitado com seguranca (drill trimestral recomendado).
#
# Uso (na VPS, a partir de /home/ec2-user/prontuai-db/script/):
#   ./restore_postgres.sh s3://bucket/prefixo/prontuai-XXXX.dump
#   ./restore_postgres.sh /caminho/local/prontuai-XXXX.dump
#
# Para restaurar de fato em cima da producao (cenario de disaster recovery),
# use explicitamente:
#   RESTORE_INTO_PROD=1 ./restore_postgres.sh <dump> --into-prod
# O script vai pedir uma confirmacao explicita antes de sobrescrever.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

require_cmd docker

SOURCE="${1:?Uso: restore_postgres.sh <s3://bucket/key.dump ou caminho local> [--into-prod]}"
INTO_PROD=0
if [ "${2:-}" = "--into-prod" ]; then
  INTO_PROD=1
fi

# Rodando manualmente (fora do systemd), POSTGRES_USER/etc nao vem de
# EnvironmentFile — carrega do .env do banco automaticamente se ainda nao
# estiver no ambiente.
DB_DEPLOY_DIR="${DB_DEPLOY_DIR:-/home/ec2-user/prontuai-db}"
if [ -z "${POSTGRES_USER:-}" ] && [ -f "$DB_DEPLOY_DIR/.env" ]; then
  set -a
  . "$DB_DEPLOY_DIR/.env"
  set +a
fi

POSTGRES_USER="${POSTGRES_USER:?POSTGRES_USER is required (defina no ambiente ou em $DB_DEPLOY_DIR/.env)}"
POSTGRES_DB="${POSTGRES_DB:-prontuai}"
RESTORE_WORK_DIR="${RESTORE_WORK_DIR:-/home/ec2-user/prontuai-db/backups/restore-tmp}"
mkdir -p "$RESTORE_WORK_DIR"

if ! docker inspect prontuai-db >/dev/null 2>&1; then
  die "Container prontuai-db nao encontrado."
fi

if [[ "$SOURCE" == s3://* ]]; then
  require_cmd aws
  # Mesmas variaveis do backup_postgres.sh (bucket S3-compativel: AWS S3 ou R2).
  BACKUP_S3_ENDPOINT_URL="${BACKUP_S3_ENDPOINT_URL:-}"
  BACKUP_S3_REGION="${BACKUP_S3_REGION:-auto}"
  S3_ENDPOINT_ARGS=()
  [ -n "$BACKUP_S3_ENDPOINT_URL" ] && S3_ENDPOINT_ARGS+=(--endpoint-url "$BACKUP_S3_ENDPOINT_URL")
  awscli() {
    AWS_ACCESS_KEY_ID="${BACKUP_S3_ACCESS_KEY_ID:?BACKUP_S3_ACCESS_KEY_ID is required}" \
    AWS_SECRET_ACCESS_KEY="${BACKUP_S3_SECRET_ACCESS_KEY:?BACKUP_S3_SECRET_ACCESS_KEY is required}" \
    AWS_DEFAULT_REGION="$BACKUP_S3_REGION" \
    aws "${S3_ENDPOINT_ARGS[@]}" "$@"
  }
  DUMP_PATH="$RESTORE_WORK_DIR/$(basename "$SOURCE")"
  log "Baixando $SOURCE"
  awscli s3 cp "$SOURCE" "$DUMP_PATH" --only-show-errors || die "Falha ao baixar dump"
  if awscli s3 cp "$SOURCE.sha256" "$DUMP_PATH.sha256" --only-show-errors 2>/dev/null; then
    log "Verificando checksum"
    EXPECTED="$(cat "$DUMP_PATH.sha256")"
    ACTUAL="$(sha256sum "$DUMP_PATH" | awk '{print $1}')"
    [ "$EXPECTED" = "$ACTUAL" ] || die "Checksum nao confere (esperado=$EXPECTED atual=$ACTUAL)"
    log "Checksum OK"
  else
    log "AVISO: checksum .sha256 nao encontrado no S3, seguindo sem verificar integridade"
  fi
else
  require_file "$SOURCE"
  DUMP_PATH="$SOURCE"
fi

if [ "$INTO_PROD" = "1" ]; then
  [ "${RESTORE_INTO_PROD:-0}" = "1" ] || die "Passe RESTORE_INTO_PROD=1 alem de --into-prod para confirmar a intencao."
  TARGET_DB="$POSTGRES_DB"
  echo
  echo "!!! ATENCAO: isso vai SOBRESCREVER o banco de producao '$POSTGRES_DB' !!!"
  read -r -p "Digite exatamente 'restaurar producao' para confirmar: " CONFIRM
  [ "$CONFIRM" = "restaurar producao" ] || die "Confirmacao nao bateu, abortando."
else
  TARGET_DB="${POSTGRES_DB}_restore_drill"
  log "Restaurando em banco descartavel de teste: $TARGET_DB (producao nao e tocada)"
  docker exec prontuai-db psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 \
    -c "DROP DATABASE IF EXISTS \"$TARGET_DB\";" \
    -c "CREATE DATABASE \"$TARGET_DB\" OWNER \"$POSTGRES_USER\";" \
    || die "Falha ao (re)criar banco de teste $TARGET_DB"
fi

log "Restaurando $DUMP_PATH em $TARGET_DB"
cat "$DUMP_PATH" | docker exec -i prontuai-db pg_restore -U "$POSTGRES_USER" -d "$TARGET_DB" \
  --clean --if-exists --no-owner --no-privileges \
  || die "pg_restore falhou (ou terminou com warnings — revise a saida acima)"

log "Restore concluido. Contagens de sanidade:"
for TABLE in users clinics documents; do
  COUNT="$(docker exec prontuai-db psql -U "$POSTGRES_USER" -d "$TARGET_DB" -tAc "SELECT count(*) FROM $TABLE;" 2>/dev/null || echo "erro")"
  printf '  %-12s %s\n' "$TABLE" "$COUNT"
done

if [ "$INTO_PROD" != "1" ]; then
  log "Drill concluido em '$TARGET_DB'. Para remover: docker exec prontuai-db psql -U $POSTGRES_USER -d postgres -c 'DROP DATABASE \"$TARGET_DB\";'"
fi

append_log "restore done target_db=$TARGET_DB source=$SOURCE into_prod=$INTO_PROD"
