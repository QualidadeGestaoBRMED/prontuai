#!/usr/bin/env bash
# Purga registros transitorios do Postgres de producao (container prontuai-db).
#
# Motivacao: cada MB que fica no banco custa ~365 MB/ano de backup, porque o
# dump diario reenvia tudo de novo. Tabelas de dado transitorio (jobs,
# notificacoes lidas, tokens expirados) dominavam o crescimento sem valor
# correspondente — `jobs` sozinha tinha 53 MB para 5.021 linhas, guardando em
# `result_json` o mesmo resultado que ja esta persistido em `documents`.
#
# NAO toca em `audit_logs` nem em `documents`: a auditoria e usada para
# analise e o conteudo dos documentos tem valor de prontuario. Para tirar
# `audit_logs` do peso diario, ver o backup_postgres.sh (exclui do dump
# diario e mantem no semanal completo).
#
# Uso (na VPS):
#   ./purge_old_records.sh            # aplica
#   PURGE_DRY_RUN=true ./purge_old_records.sh   # so mostra o que apagaria
#
# Variaveis:
#   POSTGRES_USER, POSTGRES_DB          - credenciais/nome do banco
#   PURGE_JOBS_DAYS                     - jobs finalizados mais antigos que isso (default: 7)
#   PURGE_NOTIFICATIONS_DAYS            - notificacoes JA LIDAS mais antigas que isso (default: 90)
#   PURGE_DRY_RUN                       - "true" para so contar, sem apagar (default: false)
#   PURGE_VACUUM                        - "true" para rodar VACUUM ANALYZE ao final (default: true)
#   DB_DEPLOY_DIR                       - onde esta o .env do banco (default: /home/ec2-user/prontuai-db)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

require_cmd docker

# Nao concorre com o dump: um DELETE grande durante o pg_dump so gera trabalho
# extra de MVCC, e o dump ja nao enxergaria as linhas removidas. Espera ate
# 30min; se o backup ainda estiver rodando, PULA — a purga e semanal e perder
# uma execucao nao tem consequencia, ao contrario de perder um backup.
db_maintenance_lock "${DB_LOCK_WAIT:-1800}" skip

DB_DEPLOY_DIR="${DB_DEPLOY_DIR:-/home/ec2-user/prontuai-db}"
if [ -z "${POSTGRES_USER:-}" ] && [ -f "$DB_DEPLOY_DIR/.env" ]; then
  set -a
  . "$DB_DEPLOY_DIR/.env"
  set +a
fi

POSTGRES_USER="${POSTGRES_USER:?POSTGRES_USER is required (defina no ambiente ou em $DB_DEPLOY_DIR/.env)}"
POSTGRES_DB="${POSTGRES_DB:-prontuai}"
PURGE_JOBS_DAYS="${PURGE_JOBS_DAYS:-7}"
PURGE_NOTIFICATIONS_DAYS="${PURGE_NOTIFICATIONS_DAYS:-90}"
PURGE_DRY_RUN="${PURGE_DRY_RUN:-false}"
PURGE_VACUUM="${PURGE_VACUUM:-true}"

docker inspect prontuai-db >/dev/null 2>&1 \
  || die "Container prontuai-db nao encontrado. A purga so roda com o banco no ar."

psql_run() {
  docker exec -i prontuai-db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 "$@"
}

psql_scalar() {
  psql_run -tAc "$1" | tr -d '[:space:]'
}

db_size() {
  psql_scalar "SELECT pg_size_pretty(pg_database_size('$POSTGRES_DB'));"
}

# Jobs finalizados: o resultado ja foi persistido em documents.result_payload,
# entao result_json vira duplicata. Jobs ainda em andamento nunca sao tocados,
# independentemente da idade — um job travado precisa continuar visivel.
JOBS_WHERE="status IN ('completed','failed','cancelled','error')
            AND COALESCE(completed_at, updated_at) < now() - interval '$PURGE_JOBS_DAYS days'"

# Somente notificacoes ja lidas. Nao lida permanece, por mais antiga que seja.
NOTIFICATIONS_WHERE="read = true
                     AND created_at < now() - interval '$PURGE_NOTIFICATIONS_DAYS days'"

# Somente EXPIRADOS. Linhas revogadas precisam sobreviver ate a expiracao:
# sao elas que permitem a _handle_refresh_reuse (api/v1/auth.py) detectar reuso
# de refresh token e revogar a familia inteira. Apagando-as, um token roubado
# cairia em "sessao nao encontrada" e a deteccao de roubo silenciaria. Mesmo
# criterio do housekeeping da aplicacao (purge_expired_refresh_sessions).
TOKENS_WHERE="expires_at < now()"

log "Banco antes da purga: $(db_size)"

purge_table() {
  local tabela="$1" condicao="$2" descricao="$3"
  local n
  n="$(psql_scalar "SELECT count(*) FROM $tabela WHERE $condicao;")"

  if [ "$n" = "0" ]; then
    log "$tabela: nada a remover ($descricao)"
    return
  fi

  if [ "$PURGE_DRY_RUN" = "true" ]; then
    log "[dry-run] $tabela: removeria $n linhas ($descricao)"
    return
  fi

  psql_run -c "DELETE FROM $tabela WHERE $condicao;" >/dev/null \
    || die "DELETE em $tabela falhou"
  log "$tabela: $n linhas removidas ($descricao)"
  append_log "purge tabela=$tabela linhas=$n"
}

purge_table "jobs"           "$JOBS_WHERE"          "finalizados ha mais de ${PURGE_JOBS_DAYS}d"
purge_table "notifications"  "$NOTIFICATIONS_WHERE" "lidas ha mais de ${PURGE_NOTIFICATIONS_DAYS}d"
purge_table "refresh_tokens" "$TOKENS_WHERE"        "expirados"

if [ "$PURGE_DRY_RUN" = "true" ]; then
  log "dry-run: nada foi alterado."
  exit 0
fi

# VACUUM ANALYZE (nao FULL): devolve as paginas para reuso e atualiza as
# estatisticas sem travar a tabela. O dump ja encolhe imediatamente apos o
# DELETE — o pg_dump le so linhas vivas —, entao VACUUM FULL nao e necessario
# para o objetivo de backup e exigiria lock exclusivo.
if [ "$PURGE_VACUUM" = "true" ]; then
  log "Rodando VACUUM ANALYZE"
  psql_run -c "VACUUM ANALYZE jobs, notifications, refresh_tokens;" >/dev/null \
    || log "AVISO: VACUUM falhou (a purga em si foi aplicada)"
fi

log "Banco depois da purga: $(db_size)"
append_log "purge_ok"
