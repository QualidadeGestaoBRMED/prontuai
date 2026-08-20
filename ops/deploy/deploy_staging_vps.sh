#!/usr/bin/env bash
# Deploy do backend na VPS de staging sem passar pelo GitHub Actions.
#
# Faz o mesmo que o workflow backend-ghcr-staging-deploy.yml, com duas
# diferencas deliberadas:
#
#   - Builda NA VPS, nativo arm64 (Graviton), em vez de emular aarch64 com QEMU
#     num runner amd64. Sem registry no caminho: nao precisa de PAT do GHCR.
#   - Envia o conteudo de UM COMMIT (git archive), nao a arvore de trabalho.
#     Nada de .env, __pycache__, logs, dump de banco ou compose local vazando
#     para o servidor — por construcao, nao por lista de exclusao que alguem
#     esquece de atualizar.
#
# Nao faz dump do banco: staging tem Postgres proprio e descartavel. Para
# producao use o runbook numerado (00_precheck -> 40_go_live), que trata disso.
#
# Uso:
#   STAGING_HOST=1.2.3.4 ./ops/deploy/deploy_staging_vps.sh
#   STAGING_HOST=1.2.3.4 ./ops/deploy/deploy_staging_vps.sh --ref staging --skip-tests
#
# Variaveis (todas com default, menos STAGING_HOST):
#   STAGING_HOST         obrigatoria, host/IP da VPS de staging
#   STAGING_USER         default ubuntu
#   STAGING_PORT         default 22
#   STAGING_DEPLOY_PATH  default /home/ubuntu/prontuai-staging
#   STAGING_SSH_KEY      opcional, caminho da chave privada
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

STAGING_USER="${STAGING_USER:-ubuntu}"
STAGING_PORT="${STAGING_PORT:-22}"
STAGING_DEPLOY_PATH="${STAGING_DEPLOY_PATH:-/home/ubuntu/prontuai-staging}"
REF="HEAD"
RUN_TESTS=1
ASSUME_YES=0

while [ $# -gt 0 ]; do
  case "$1" in
    --ref)         REF="${2:?--ref exige um valor}"; shift 2 ;;
    --skip-tests)  RUN_TESTS=0; shift ;;
    --yes|-y)      ASSUME_YES=1; shift ;;
    -h|--help)     sed -n '2,28p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)             die "Argumento desconhecido: $1 (use --help)" ;;
  esac
done

require_cmd git ssh tar docker
[ -n "${STAGING_HOST:-}" ] || die "STAGING_HOST nao definida. Ex.: STAGING_HOST=1.2.3.4 $0"

SSH_OPTS=(-p "$STAGING_PORT" -o StrictHostKeyChecking=accept-new)
[ -n "${STAGING_SSH_KEY:-}" ] && SSH_OPTS=(-i "$STAGING_SSH_KEY" "${SSH_OPTS[@]}")
TARGET="$STAGING_USER@$STAGING_HOST"

remote() { ssh "${SSH_OPTS[@]}" "$TARGET" "$@"; }

# ---------------------------------------------------------------- 1. o commit
SHA="$(git rev-parse "${REF}^{commit}")" || die "Ref invalida: $REF"
SHORT="${SHA:0:7}"
TAG="sha-$SHORT"
log "Commit a implantar: $SHORT ($(git log -1 --format=%s "$SHA" | cut -c1-60))"

# A arvore suja nao vai para o servidor. Avisa alto, porque a diferenca entre
# "testei local" e "esta rodando na VPS" nasce exatamente aqui.
DIRTY="$(git status --porcelain -- back-end | head -20)"
if [ -n "$DIRTY" ]; then
  log "AVISO: ha alteracoes em back-end/ que NAO serao implantadas (o deploy usa o commit $SHORT):"
  printf '%s\n' "$DIRTY" | sed 's/^/    /'
  if [ "$ASSUME_YES" -ne 1 ]; then
    printf 'Continuar assim mesmo? [s/N] '
    read -r resposta
    case "$resposta" in [sSyY]) ;; *) die "Abortado. Commite as alteracoes ou use --yes." ;; esac
  fi
fi

# ------------------------------------------------------------------ 2. testes
if [ "$RUN_TESTS" -eq 1 ]; then
  require_cmd pytest
  log "Rodando os testes que o CI roda antes do deploy"
  PG_NAME="prontuai-pg-deploytest-$$"
  docker run -d --rm --name "$PG_NAME" \
    -e POSTGRES_USER=prontuai -e POSTGRES_PASSWORD=prontuai -e POSTGRES_DB=prontuai_test \
    -p 55432:5432 postgres:16-alpine >/dev/null
  trap 'docker rm -f "$PG_NAME" >/dev/null 2>&1 || true' EXIT
  for _ in $(seq 1 30); do
    docker exec "$PG_NAME" pg_isready -U prontuai -d prontuai_test >/dev/null 2>&1 && break
    sleep 1
  done

  ( cd "$ROOT_DIR" && APP_ENV=test OPENAI_API_KEY=test-key \
      PYTHONPATH=back-end pytest back-end/tests/test_auth_security.py -q --noconftest ) \
    || die "test_auth_security falhou; deploy abortado"

  ( cd "$ROOT_DIR" && APP_ENV=test DEV_AUTH_BYPASS=true OPENAI_API_KEY=test-key \
      USE_PRONTUAI_PATIENTS_EXAMS=true \
      DATABASE_URL=postgresql://prontuai:prontuai@127.0.0.1:55432/prontuai_test \
      pytest back-end/tests/test_brmed.py -q ) \
    || die "test_brmed falhou; deploy abortado"

  docker rm -f "$PG_NAME" >/dev/null 2>&1 || true
  trap - EXIT
  log "Testes passaram"
else
  log "AVISO: testes pulados (--skip-tests). O CI nao vai roda-los por voce."
fi

# ------------------------------------------------------------- 3. transferencia
log "Verificando a VPS e o .env"
remote "test -f '$STAGING_DEPLOY_PATH/.env'" \
  || die "Falta $STAGING_DEPLOY_PATH/.env na VPS. Crie a partir de back-end/.env.example antes."

PREV_IMAGE="$(remote "cat '$STAGING_DEPLOY_PATH/.current_backend_image' 2>/dev/null || true")"
[ -n "$PREV_IMAGE" ] && log "Imagem atual (ponto de rollback): $PREV_IMAGE" \
                     || log "Sem .current_backend_image na VPS: nao havera rollback automatico"

log "Enviando o conteudo do commit $SHORT"
remote "mkdir -p '$STAGING_DEPLOY_PATH' '$STAGING_DEPLOY_PATH/logs' \
        '$STAGING_DEPLOY_PATH/resultados' '$STAGING_DEPLOY_PATH/ocr_resultados' \
        '$STAGING_DEPLOY_PATH/auditoria_validacao' '$STAGING_DEPLOY_PATH/data/uploads'"

# src/ e recriada a cada deploy: arquivo removido no commit nao pode sobrar la.
git archive --format=tar "$SHA:back-end" \
  | remote "rm -rf '$STAGING_DEPLOY_PATH/src' && mkdir -p '$STAGING_DEPLOY_PATH/src' \
            && tar -x -C '$STAGING_DEPLOY_PATH/src'"

# O compose tambem sai do commit, nao da arvore local.
git show "$SHA:back-end/docker-compose.stg.yml" \
  | remote "cat > '$STAGING_DEPLOY_PATH/docker-compose.yml'"

# ----------------------------------------------------------- 4. build e subida
log "Buildando na VPS (arm64 nativo) e subindo"
remote "DEPLOY_PATH='$STAGING_DEPLOY_PATH' TAG='$TAG' PREV_IMAGE='$PREV_IMAGE' bash -s" <<'REMOTE'
set -euo pipefail
cd "$DEPLOY_PATH"

docker build -t "prontuai-backend-stg:$TAG" ./src

set -a; . ./.env; set +a
export BACKEND_IMAGE="prontuai-backend-stg:$TAG"

docker compose -f docker-compose.yml up -d --remove-orphans prontuai-backend-stg

PORT="${BACKEND_HTTP_PORT:-8080}"
for i in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    printf '%s\n' "$BACKEND_IMAGE" > .current_backend_image
    docker image prune -f >/dev/null 2>&1 || true
    echo "DEPLOY_OK $BACKEND_IMAGE"
    exit 0
  fi
  sleep 2
done

echo "Health check falhou apos o deploy." >&2
docker compose -f docker-compose.yml logs --tail=80 prontuai-backend-stg >&2 || true

if [ -n "${PREV_IMAGE:-}" ]; then
  echo "Revertendo para $PREV_IMAGE" >&2
  export BACKEND_IMAGE="$PREV_IMAGE"
  docker compose -f docker-compose.yml up -d prontuai-backend-stg >&2 || true
  for i in $(seq 1 20); do
    if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
      echo "ROLLBACK_OK $PREV_IMAGE" >&2; exit 1
    fi
    sleep 2
  done
  echo "ROLLBACK_FALHOU: staging esta fora do ar, intervencao manual necessaria" >&2
fi
exit 1
REMOTE

# ------------------------------------------------------------------- 5. fecho
append_log "staging_vps_deploy=ok sha=$SHORT image=prontuai-backend-stg:$TAG"
log "Deploy concluido: prontuai-backend-stg:$TAG"
cat <<FIM

Proximos passos de verificacao (o /health e estatico, nao prova muita coisa):

  ssh ${STAGING_SSH_KEY:+-i $STAGING_SSH_KEY }-p $STAGING_PORT $TARGET \\
    'docker logs prontuai-backend-stg 2>&1 | grep -iE "erro|falha|Traceback|migra|setup_telemetry" | tail -20'

Procure por falha de auto_migrate e exercite um endpoint /v1/ autenticado.

Rollback manual, se precisar:

  ssh -p $STAGING_PORT $TARGET \\
    'cd $STAGING_DEPLOY_PATH && export BACKEND_IMAGE=\$(cat .current_backend_image) \\
     && docker compose up -d prontuai-backend-stg'
FIM
