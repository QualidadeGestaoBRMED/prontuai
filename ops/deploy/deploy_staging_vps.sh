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

# A arvore de trabalho nao vai para o servidor; so o commit. Duas situacoes bem
# diferentes se escondem em "git status", e tratar as duas igual gera ruido:
#
#   - arquivo VERSIONADO modificado: alguem pode achar que a mudanca subiu.
#     Isso merece parar e confirmar.
#   - arquivo NAO versionado: git archive nunca o enviaria, e neste repo eles sao
#     rotineiramente locais de proposito (compose override, dump, docs). Vira
#     nota, nao pergunta.
TRACKED="$(git status --porcelain --untracked-files=no -- back-end | head -20)"
UNTRACKED="$(git ls-files --others --exclude-standard -- back-end | head -10)"

if [ -n "$UNTRACKED" ]; then
  log "Nota: arquivos nao versionados em back-end/ nao entram no deploy (esperado):"
  printf '%s\n' "$UNTRACKED" | sed 's/^/    /'
fi

if [ -n "$TRACKED" ]; then
  log "AVISO: ha alteracoes em arquivos versionados de back-end/ que NAO serao"
  log "       implantadas, porque o deploy usa o commit $SHORT:"
  printf '%s\n' "$TRACKED" | sed 's/^/    /'
  if [ "$ASSUME_YES" -ne 1 ]; then
    printf 'Continuar assim mesmo? [s/N] '
    read -r resposta
    case "$resposta" in [sSyY]) ;; *) die "Abortado. Commite as alteracoes ou use --yes." ;; esac
  fi
fi

# ------------------------------------------------------------------ 2. testes
if [ "$RUN_TESTS" -eq 1 ]; then
  # pytest raramente esta no PATH global. Procura nos lugares plausiveis antes
  # de desistir, e se nao achar da a instrucao em vez de "Missing command".
  PYTEST_CMD=()
  if [ -n "${PYTEST:-}" ]; then
    read -r -a PYTEST_CMD <<< "$PYTEST"
  elif command -v pytest >/dev/null 2>&1; then
    PYTEST_CMD=(pytest)
  elif [ -x "$ROOT_DIR/back-end/.venv/bin/pytest" ]; then
    PYTEST_CMD=("$ROOT_DIR/back-end/.venv/bin/pytest")
  elif [ -x "$ROOT_DIR/.venv/bin/pytest" ]; then
    PYTEST_CMD=("$ROOT_DIR/.venv/bin/pytest")
  elif python3 -c 'import pytest' >/dev/null 2>&1; then
    PYTEST_CMD=(python3 -m pytest)
  else
    die "pytest nao encontrado. Escolha um caminho:

  1) Criar o venv uma vez (o CI faz o equivalente a cada run):
       python3 -m venv back-end/.venv
       back-end/.venv/bin/pip install -r back-end/requirements.txt
     O script encontra back-end/.venv/bin/pytest sozinho nas proximas vezes.

  2) Apontar um pytest existente:
       PYTEST=/caminho/para/pytest $0 ...

  3) Pular os testes, se voce ja os rodou em outro lugar:
       $0 --skip-tests ...
     Sem CI, ninguem mais vai roda-los."
  fi
  log "Rodando os testes que o CI roda antes do deploy (${PYTEST_CMD[*]})"
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
      PYTHONPATH=back-end "${PYTEST_CMD[@]}" back-end/tests/test_auth_security.py -q --noconftest ) \
    || die "test_auth_security falhou; deploy abortado"

  ( cd "$ROOT_DIR" && APP_ENV=test DEV_AUTH_BYPASS=true OPENAI_API_KEY=test-key \
      USE_PRONTUAI_PATIENTS_EXAMS=true \
      DATABASE_URL=postgresql://prontuai:prontuai@127.0.0.1:55432/prontuai_test \
      "${PYTEST_CMD[@]}" back-end/tests/test_brmed.py -q ) \
    || die "test_brmed falhou; deploy abortado"

  docker rm -f "$PG_NAME" >/dev/null 2>&1 || true
  trap - EXIT
  log "Testes passaram"
else
  log "AVISO: testes pulados (--skip-tests). O CI nao vai roda-los por voce."
fi

# ------------------------------------------------------------- 3. transferencia
log "Verificando acesso a VPS"
# Checa a conexao ANTES de qualquer teste remoto. Sem isso, qualquer falha de
# SSH (host errado, chave, firewall) sai como "falta o .env", mandando quem le
# procurar no lugar errado.
remote true >/dev/null 2>&1 \
  || die "Nao consegui conectar em $TARGET na porta $STAGING_PORT.
  Verifique STAGING_HOST/STAGING_USER/STAGING_PORT e a chave (STAGING_SSH_KEY).
  Teste com: ssh ${STAGING_SSH_KEY:+-i $STAGING_SSH_KEY }-p $STAGING_PORT $TARGET true"

remote "test -f '$STAGING_DEPLOY_PATH/.env'" \
  || die "Conectei na VPS, mas falta $STAGING_DEPLOY_PATH/.env. Crie a partir de back-end/.env.example antes."

# O build e o health check rodam la; falhar aqui e melhor que falhar no meio.
remote "command -v docker >/dev/null && docker compose version >/dev/null 2>&1 && command -v curl >/dev/null && command -v tar >/dev/null" \
  || die "A VPS precisa de docker (com o plugin compose), curl e tar."

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
