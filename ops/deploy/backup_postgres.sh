#!/usr/bin/env bash
# Backup diario do Postgres de producao (container prontuai-db) para um bucket
# S3-compativel (AWS S3 ou Cloudflare R2 — mesma API, so muda endpoint/creds).
#
# Uso (na VPS, a partir de /home/ec2-user/prontuai-db/script/, apos o
# container prontuai-db estar no ar):
#   ./backup_postgres.sh
#
# Variaveis (lidas do ambiente; normalmente vem do .env do banco, em
# /home/ec2-user/prontuai-db/.env, via EnvironmentFile no systemd unit, ver
# ops/deploy/systemd/):
#   POSTGRES_USER, POSTGRES_DB          - credenciais/nome do banco
#   BACKUP_S3_BUCKET                    - bucket destino. Se vazio/nao definido, o backup
#                                          fica SO local (sem copia externa) e o script avisa
#                                          em vez de falhar — util antes de configurar o R2/S3.
#   BACKUP_S3_PREFIX                    - prefixo dentro do bucket (default: postgres-backups/prontuai)
#   BACKUP_S3_ENDPOINT_URL              - endpoint S3-compativel (vazio = AWS S3 padrao;
#                                          para R2: https://<account_id>.r2.cloudflarestorage.com)
#   BACKUP_S3_REGION                    - default: auto (funciona pro R2; use us-east-1 etc para AWS S3)
#   BACKUP_S3_SSE                       - default: vazio. Use "AES256" no AWS S3; deixe vazio no
#                                          R2 (ja criptografa em repouso por padrao e pode nao aceitar o header)
#   BACKUP_S3_ACCESS_KEY_ID/SECRET      - credenciais dedicadas do bucket de backup. NAO reutilize
#                                          AWS_ACCESS_KEY_ID/SECRET do Textract (escopo/provedor diferentes)
#   BACKUP_RETENTION_DAYS                - retencao local (default: 35). Configure lifecycle rule
#                                          no bucket separadamente para expirar objetos antigos la.
#   BACKUP_LOCAL_DIR                     - onde ficam os dumps antes do upload (default: /home/ec2-user/prontuai-db/backups)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

require_cmd docker sha256sum

# Via systemd, POSTGRES_USER/etc chegam pelo EnvironmentFile. Rodando na mao,
# carrega do .env do banco automaticamente se ainda nao estiver no ambiente.
DB_DEPLOY_DIR="${DB_DEPLOY_DIR:-/home/ec2-user/prontuai-db}"
if [ -z "${POSTGRES_USER:-}" ] && [ -f "$DB_DEPLOY_DIR/.env" ]; then
  set -a
  . "$DB_DEPLOY_DIR/.env"
  set +a
fi

POSTGRES_USER="${POSTGRES_USER:?POSTGRES_USER is required (defina no ambiente ou em $DB_DEPLOY_DIR/.env)}"
POSTGRES_DB="${POSTGRES_DB:-prontuai}"
BACKUP_S3_BUCKET="${BACKUP_S3_BUCKET:-}"
BACKUP_S3_PREFIX="${BACKUP_S3_PREFIX:-postgres-backups/prontuai}"
BACKUP_S3_ENDPOINT_URL="${BACKUP_S3_ENDPOINT_URL:-}"
BACKUP_S3_REGION="${BACKUP_S3_REGION:-auto}"
BACKUP_S3_SSE="${BACKUP_S3_SSE:-}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-35}"
BACKUP_LOCAL_DIR="${BACKUP_LOCAL_DIR:-/home/ec2-user/prontuai-db/backups}"

S3_ENDPOINT_ARGS=()
[ -n "$BACKUP_S3_ENDPOINT_URL" ] && S3_ENDPOINT_ARGS+=(--endpoint-url "$BACKUP_S3_ENDPOINT_URL")
S3_SSE_ARGS=()
[ -n "$BACKUP_S3_SSE" ] && S3_SSE_ARGS+=(--sse "$BACKUP_S3_SSE")

# Credenciais dedicadas ao backup, sem depender de instance role (nao existe
# no R2) nem reaproveitar as chaves AWS do Textract (provedor/escopo diferentes).
awscli() {
  AWS_ACCESS_KEY_ID="${BACKUP_S3_ACCESS_KEY_ID:?BACKUP_S3_ACCESS_KEY_ID is required}" \
  AWS_SECRET_ACCESS_KEY="${BACKUP_S3_SECRET_ACCESS_KEY:?BACKUP_S3_SECRET_ACCESS_KEY is required}" \
  AWS_DEFAULT_REGION="$BACKUP_S3_REGION" \
  aws "${S3_ENDPOINT_ARGS[@]}" "$@"
}

mkdir -p "$BACKUP_LOCAL_DIR"

TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"
DUMP_NAME="prontuai-${TIMESTAMP}.dump"
DUMP_PATH="$BACKUP_LOCAL_DIR/$DUMP_NAME"
CHECKSUM_PATH="$DUMP_PATH.sha256"

log "Iniciando backup do Postgres (db=$POSTGRES_DB) -> $DUMP_PATH"

if ! docker inspect prontuai-db >/dev/null 2>&1; then
  die "Container prontuai-db nao encontrado. O backup so roda com o banco no ar."
fi

# pg_dump em formato custom (-Fc): ja comprimido, restauravel com pg_restore
# e permite restaurar tabelas/objetos individualmente se preciso.
docker exec prontuai-db pg_dump -U "$POSTGRES_USER" -Fc -d "$POSTGRES_DB" > "$DUMP_PATH" \
  || die "pg_dump falhou"

if [ ! -s "$DUMP_PATH" ]; then
  rm -f "$DUMP_PATH"
  die "Dump gerado esta vazio, abortando upload"
fi

sha256sum "$DUMP_PATH" | awk '{print $1}' > "$CHECKSUM_PATH"

if [ -z "$BACKUP_S3_BUCKET" ]; then
  log "AVISO: BACKUP_S3_BUCKET nao configurado — backup fica SOMENTE local em $DUMP_PATH, sem copia externa."
  log "Configure BACKUP_S3_* (R2/S3) assim que possivel: um dump so local nao sobrevive a perda do disco/instancia."
  DEST_DESC="$DUMP_PATH (somente local)"
else
  require_cmd aws
  S3_URI="s3://$BACKUP_S3_BUCKET/$BACKUP_S3_PREFIX/$DUMP_NAME"

  log "Enviando dump para $S3_URI"
  awscli s3 cp "$DUMP_PATH" "$S3_URI" "${S3_SSE_ARGS[@]}" --only-show-errors \
    || die "Upload do dump falhou"
  awscli s3 cp "$CHECKSUM_PATH" "$S3_URI.sha256" "${S3_SSE_ARGS[@]}" --only-show-errors \
    || die "Upload do checksum falhou"

  # Confirma que o objeto existe no bucket antes de contar o backup como valido.
  awscli s3api head-object --bucket "$BACKUP_S3_BUCKET" --key "$BACKUP_S3_PREFIX/$DUMP_NAME" >/dev/null \
    || die "head-object nao confirmou o upload; backup considerado FALHO"

  log "Upload confirmado."
  DEST_DESC="$S3_URI"
fi

# Retencao local: mantem apenas os ultimos N dias em disco (o bucket e a
# copia de longo prazo; configure lifecycle rule la para expirar objetos
# antigos, o script nao apaga nada remoto).
find "$BACKUP_LOCAL_DIR" -maxdepth 1 -name 'prontuai-*.dump*' -mtime "+$BACKUP_RETENTION_DAYS" -delete

append_log "backup_ok dump=$DUMP_NAME dest=$DEST_DESC"
log "Backup concluido: $DUMP_NAME -> $DEST_DESC"
