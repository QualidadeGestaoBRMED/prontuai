#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

require_cmd git rg sed cp mkdir chmod cat

require_file "$BACKEND_DIR/.env"

git -C "$ROOT_DIR" show-ref --verify refs/remotes/origin/v1 >/dev/null \
  || die "origin/v1 not found. Run git fetch origin first."

mkdir -p "$ROOT_DIR/.worktrees"

if [ ! -e "$WORKTREE_DIR" ]; then
  if git -C "$ROOT_DIR" show-ref --verify --quiet "refs/heads/$STAGING_BRANCH"; then
    git -C "$ROOT_DIR" worktree add "$WORKTREE_DIR" "$STAGING_BRANCH"
  else
    git -C "$ROOT_DIR" worktree add "$WORKTREE_DIR" -b "$STAGING_BRANCH" origin/v1
  fi
fi

[ -d "$STAGING_BACKEND_DIR" ] || die "Invalid staging backend dir: $STAGING_BACKEND_DIR"

cp "$BACKEND_DIR/.env" "$STAGING_BACKEND_DIR/.env.stg"

if rg -n '^DATABASE_URL=' "$STAGING_BACKEND_DIR/.env.stg" >/dev/null; then
  sed -i 's|^DATABASE_URL=.*|DATABASE_URL=postgresql://CHANGE_ME_STAGING_USER:CHANGE_ME_STAGING_PASS@prontuai-postgres-staging:5432/prontuai_stg|' "$STAGING_BACKEND_DIR/.env.stg"
else
  printf '\nDATABASE_URL=postgresql://CHANGE_ME_STAGING_USER:CHANGE_ME_STAGING_PASS@prontuai-postgres-staging:5432/prontuai_stg\n' >> "$STAGING_BACKEND_DIR/.env.stg"
fi

if rg -n '^NEXT_PUBLIC_API_URL=' "$STAGING_BACKEND_DIR/.env.stg" >/dev/null; then
  sed -i 's|^NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=http://localhost:8080|' "$STAGING_BACKEND_DIR/.env.stg"
else
  printf '\nNEXT_PUBLIC_API_URL=http://localhost:8080\n' >> "$STAGING_BACKEND_DIR/.env.stg"
fi

if rg -n '^ALLOWED_ORIGINS=' "$STAGING_BACKEND_DIR/.env.stg" >/dev/null; then
  sed -i 's|^ALLOWED_ORIGINS=.*|ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000|' "$STAGING_BACKEND_DIR/.env.stg"
else
  printf '\nALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000\n' >> "$STAGING_BACKEND_DIR/.env.stg"
fi

if rg -n '^DOCUMENT_STORAGE_DIR=' "$STAGING_BACKEND_DIR/.env.stg" >/dev/null; then
  sed -i 's|^DOCUMENT_STORAGE_DIR=.*|DOCUMENT_STORAGE_DIR=/app/uploads-stg|' "$STAGING_BACKEND_DIR/.env.stg"
else
  printf '\nDOCUMENT_STORAGE_DIR=/app/uploads-stg\n' >> "$STAGING_BACKEND_DIR/.env.stg"
fi

chmod 600 "$STAGING_BACKEND_DIR/.env.stg"

mkdir -p \
  "$STAGING_BACKEND_DIR/logs-stg" \
  "$STAGING_BACKEND_DIR/resultados-stg" \
  "$STAGING_BACKEND_DIR/ocr_resultados-stg" \
  "$STAGING_BACKEND_DIR/auditoria_validacao-stg" \
  "$STAGING_BACKEND_DIR/uploads-stg"

cat > "$STAGING_OVERRIDE_FILE" <<'YAML'
services:
  prontuai-backend:
    container_name: prontuai-backend-stg
    ports:
      - "8080:80"
    env_file:
      - .env.stg
    volumes:
      - ./logs-stg:/app/logs
      - ./resultados-stg:/app/resultados
      - ./ocr_resultados-stg:/app/ocr_resultados
      - ./auditoria_validacao-stg:/app/auditoria_validacao
      - ./uploads-stg:/app/uploads-stg
      - ./data:/app/data:ro
    networks:
      - prontuai-staging-net
networks:
  prontuai-staging-net:
    external: true
    name: prontuai-staging-net
YAML

cat > "$STAGING_COMPOSE_FILE" <<YAML
services:
  prontuai-backend:
    build:
      context: $STAGING_BACKEND_DIR
      dockerfile: Dockerfile
    container_name: prontuai-backend-stg
    restart: unless-stopped
    env_file: $STAGING_BACKEND_DIR/.env.stg
    ports:
      - "8080:80"
    volumes:
      - $STAGING_BACKEND_DIR/logs-stg:/app/logs
      - $STAGING_BACKEND_DIR/resultados-stg:/app/resultados
      - $STAGING_BACKEND_DIR/ocr_resultados-stg:/app/ocr_resultados
      - $STAGING_BACKEND_DIR/auditoria_validacao-stg:/app/auditoria_validacao
      - $STAGING_BACKEND_DIR/uploads-stg:/app/uploads-stg
      - $STAGING_BACKEND_DIR/data:/app/data:ro
    networks:
      - prontuai-staging-net
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
networks:
  prontuai-staging-net:
    external: true
    name: prontuai-staging-net
YAML

append_log "===== PREPARE STAGING ====="
append_log "worktree=$WORKTREE_DIR"
append_log "branch=$STAGING_BRANCH"
append_log "env_stg=$STAGING_BACKEND_DIR/.env.stg"
append_log "stg_override=$STAGING_OVERRIDE_FILE"
append_log "stg_compose=$STAGING_COMPOSE_FILE"

log "Preparacao de staging concluida."
log "Worktree: $WORKTREE_DIR"
log "Env stg: $STAGING_BACKEND_DIR/.env.stg"
log "Override: $STAGING_OVERRIDE_FILE"
log "Compose: $STAGING_COMPOSE_FILE"
