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

# ---------------------------------------------------- acompanhamento visual
# Cores so quando a saida e terminal, para nao poluir log em arquivo/CI.
if [ -t 1 ]; then
  C_DIM=$'\033[2m'; C_OK=$'\033[32m'; C_ERR=$'\033[31m'
  C_STEP=$'\033[1;36m'; C_WARN=$'\033[33m'; C_OFF=$'\033[0m'
else
  C_DIM=""; C_OK=""; C_ERR=""; C_STEP=""; C_WARN=""; C_OFF=""
fi

TOTAL_STEPS=7
STEP_N=0
STEP_NAME="inicializacao"
STEP_START=0

step() {
  STEP_N=$((STEP_N + 1))
  STEP_NAME="$1"
  STEP_START="$(date +%s)"
  printf '\n%s[%d/%d] %s%s\n' "$C_STEP" "$STEP_N" "$TOTAL_STEPS" "$1" "$C_OFF"
}

step_ok() {
  local dur=$(( $(date +%s) - STEP_START ))
  printf '%s      OK%s %s%s\n' "$C_OK" "$C_OFF" "${1:-}" "${C_DIM}${dur}s${C_OFF}"
}

info()  { printf '      %s\n' "$*"; }
warn()  { printf '%s      ! %s%s\n' "$C_WARN" "$*" "$C_OFF"; }
trace() { printf '%s      $ %s%s\n' "$C_DIM" "$*" "$C_OFF"; }

# Erro nao tratado: diz em que passo e em que linha morreu, em vez de sair
# calado com o exit code do ultimo comando.
trap 'rc=$?; printf "\n%s FALHOU no passo %d/%d (%s), linha %d, exit %d %s\n"       "$C_ERR" "$STEP_N" "$TOTAL_STEPS" "$STEP_NAME" "$LINENO" "$rc" "$C_OFF" >&2' ERR

# die() do lib.sh sai com ERROR; aqui acrescentamos o passo, que e o que faltava
# para saber onde parou.
die() {
  printf '\n%s ERRO no passo %d/%d (%s)%s\n' "$C_ERR" "$STEP_N" "$TOTAL_STEPS" "$STEP_NAME" "$C_OFF" >&2
  printf '%s\n' "$*" >&2
  exit 1
}

printf '%s=== Deploy staging (sem GitHub Actions) ===%s\n' "$C_STEP" "$C_OFF"

step "Pre-requisitos locais"
for c in git ssh tar docker; do
  if command -v "$c" >/dev/null 2>&1; then info "$c: ok"; else die "Falta o comando '$c' nesta maquina."; fi
done
[ -n "${STAGING_HOST:-}" ] || die "STAGING_HOST nao definida. Ex.: STAGING_HOST=1.2.3.4 $0"
info "destino: $STAGING_USER@$STAGING_HOST:$STAGING_PORT"
info "caminho: $STAGING_DEPLOY_PATH"
step_ok

SSH_OPTS=(-p "$STAGING_PORT" -o StrictHostKeyChecking=accept-new)
[ -n "${STAGING_SSH_KEY:-}" ] && SSH_OPTS=(-i "$STAGING_SSH_KEY" "${SSH_OPTS[@]}")
TARGET="$STAGING_USER@$STAGING_HOST"

remote() { ssh "${SSH_OPTS[@]}" "$TARGET" "$@"; }

# ---------------------------------------------------------------- 1. o commit
step "Resolvendo o commit a implantar"
SHA="$(git rev-parse "${REF}^{commit}" 2>/dev/null)" || die "Ref invalida: $REF"
SHORT="${SHA:0:7}"
TAG="sha-$SHORT"
info "ref     : $REF"
info "commit  : $SHORT  $(git log -1 --format=%s "$SHA" | cut -c1-58)"
info "imagem  : prontuai-backend-stg:$TAG"

# A arvore de trabalho nao vai para o servidor; so o commit. Duas situacoes bem
# diferentes se escondem em "git status", e tratar as duas igual gera ruido:
#
#   - arquivo VERSIONADO modificado: alguem pode achar que a mudanca subiu.
#     Isso merece parar e confirmar.
#   - arquivo NAO versionado: git archive nunca o enviaria, e neste repo eles sao
#     rotineiramente locais de proposito (compose override, dump, docs). Vira
#     nota, nao pergunta.
# O "|| true" nao e decoracao: head fecha o pipe antes de o git terminar de
# escrever, o git morre com SIGPIPE e o pipefail transforma isso em falha do
# script inteiro. So aparece quando ha muitos arquivos (um venv na pasta, por
# exemplo) — foi exatamente assim que este bug se manifestou.
TRACKED="$(git status --porcelain --untracked-files=no -- back-end | head -20 || true)"
UNTRACKED_N="$(git ls-files --others --exclude-standard -- back-end | wc -l || true)"
UNTRACKED="$(git ls-files --others --exclude-standard -- back-end | head -8 || true)"

if [ -n "$UNTRACKED" ]; then
  info "nao versionados em back-end/ (nao entram no deploy, esperado): $UNTRACKED_N arquivo(s)"
  printf '%s\n' "$UNTRACKED" | sed 's/^/        /'
  [ "$UNTRACKED_N" -gt 8 ] && printf '        ... e %d outros\n' "$((UNTRACKED_N - 8))"
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
step_ok

# ------------------------------------------------------------------ 2. testes
step "Testes (os mesmos do CI)"
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

  1) Criar o venv uma vez (o CI faz o equivalente a cada run). Os caminhos sao
     absolutos de proposito: rodar o comando relativo de dentro de back-end/
     cria back-end/back-end/.venv, que o script nao encontra.
       python3 -m venv '$ROOT_DIR/back-end/.venv'
       '$ROOT_DIR/back-end/.venv/bin/pip' install -r '$ROOT_DIR/back-end/requirements.txt'
     Depois disso o script acha o pytest sozinho.

  2) Apontar um pytest existente:
       PYTEST=/caminho/para/pytest $0 ...

  3) Pular os testes, se voce ja os rodou em outro lugar:
       $0 --skip-tests ...
     Sem CI, ninguem mais vai roda-los."
  fi
  info "runner: ${PYTEST_CMD[*]}"
  info "subindo Postgres 16 temporario para os testes"
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
    || die "test_auth_security falhou. A saida do pytest esta acima; deploy abortado
  antes de tocar na VPS."

  ( cd "$ROOT_DIR" && APP_ENV=test DEV_AUTH_BYPASS=true OPENAI_API_KEY=test-key \
      USE_PRONTUAI_PATIENTS_EXAMS=true \
      DATABASE_URL=postgresql://prontuai:prontuai@127.0.0.1:55432/prontuai_test \
      "${PYTEST_CMD[@]}" back-end/tests/test_brmed.py -q ) \
    || die "test_brmed falhou. A saida do pytest esta acima; deploy abortado
  antes de tocar na VPS."

  docker rm -f "$PG_NAME" >/dev/null 2>&1 || true
  trap - EXIT
  step_ok "2 suites "
else
  warn "testes pulados (--skip-tests). Sem CI, ninguem mais vai roda-los."
  step_ok "pulado "
fi

# ------------------------------------------------------------- 3. transferencia
step "Conexao e pre-requisitos na VPS"
# Checa a conexao ANTES de qualquer teste remoto: qualquer falha de SSH sairia
# como "falta o .env" e mandaria quem le procurar no lugar errado. E o erro do
# ssh e MOSTRADO — engoli-lo era o pior silenciador do script.
trace "ssh -p $STAGING_PORT $TARGET true"
SSH_ERR="$(remote true 2>&1)" || die "Nao consegui conectar em $TARGET na porta $STAGING_PORT.

  O ssh disse:
$(printf '%s\n' "$SSH_ERR" | sed 's/^/    /')

  Teste na mao com:
    ssh ${STAGING_SSH_KEY:+-i $STAGING_SSH_KEY }-p $STAGING_PORT $TARGET true"
info "ssh: ok"

# Cada pre-requisito e checado em separado, para dizer QUAL falta.
FALTANDO=""
for c in docker curl tar; do
  remote "command -v $c >/dev/null 2>&1" || FALTANDO="$FALTANDO $c"
done
remote "docker compose version >/dev/null 2>&1" || FALTANDO="$FALTANDO docker-compose-plugin"
[ -z "$FALTANDO" ] || die "A VPS nao tem:$FALTANDO"
info "docker, compose, curl, tar: ok"

remote "test -f '$STAGING_DEPLOY_PATH/.env'" \
  || die "Conectei na VPS, mas falta $STAGING_DEPLOY_PATH/.env
  Crie a partir de back-end/.env.example antes de implantar."
info ".env presente em $STAGING_DEPLOY_PATH"

PREV_IMAGE="$(remote "cat '$STAGING_DEPLOY_PATH/.current_backend_image' 2>/dev/null || true")"
if [ -n "$PREV_IMAGE" ]; then
  info "rollback disponivel: $PREV_IMAGE"
else
  warn "sem .current_backend_image na VPS: NAO havera rollback automatico"
fi
step_ok

step "Enviando o commit $SHORT para a VPS"
remote "mkdir -p '$STAGING_DEPLOY_PATH' '$STAGING_DEPLOY_PATH/logs' \
        '$STAGING_DEPLOY_PATH/resultados' '$STAGING_DEPLOY_PATH/ocr_resultados' \
        '$STAGING_DEPLOY_PATH/auditoria_validacao' '$STAGING_DEPLOY_PATH/data/uploads'"
info "diretorios garantidos"

ARQUIVOS="$(git archive --format=tar "$SHA:back-end" | tar -t | wc -l)"
TAMANHO="$(git archive --format=tar "$SHA:back-end" | wc -c | awk '{printf "%.1f MB", $1/1048576}')"
info "pacote: $ARQUIVOS entradas, $TAMANHO (so conteudo versionado)"

# src/ e recriada a cada deploy: arquivo removido no commit nao pode sobrar la.
trace "git archive $SHORT:back-end | ssh ... tar -x -C $STAGING_DEPLOY_PATH/src"
git archive --format=tar "$SHA:back-end" \
  | remote "rm -rf '$STAGING_DEPLOY_PATH/src' && mkdir -p '$STAGING_DEPLOY_PATH/src' \
            && tar -x -C '$STAGING_DEPLOY_PATH/src'" \
  || die "Falha ao enviar/extrair o pacote na VPS (veja o erro do tar/ssh acima)."

ENVIADOS="$(remote "find '$STAGING_DEPLOY_PATH/src' -type f | wc -l")"
info "extraidos na VPS: $ENVIADOS arquivos"
[ "$ENVIADOS" -gt 0 ] || die "A pasta src/ ficou vazia na VPS; transferencia nao funcionou."

# O compose tambem sai do commit, nao da arvore local.
git show "$SHA:back-end/docker-compose.stg.yml" \
  | remote "cat > '$STAGING_DEPLOY_PATH/docker-compose.yml'" \
  || die "Falha ao enviar o docker-compose.stg.yml."
info "docker-compose.yml atualizado a partir do commit"
step_ok

# ----------------------------------------------------------- 4. build e subida
step "Build na VPS (arm64 nativo) e subida"
info "o build imprime abaixo; a primeira vez costuma levar alguns minutos"
remote "DEPLOY_PATH='$STAGING_DEPLOY_PATH' TAG='$TAG' PREV_IMAGE='$PREV_IMAGE' bash -s" <<'REMOTE'
set -euo pipefail
cd "$DEPLOY_PATH"

echo ">> build de prontuai-backend-stg:$TAG"
docker build -t "prontuai-backend-stg:$TAG" ./src

set -a; . ./.env; set +a
export BACKEND_IMAGE="prontuai-backend-stg:$TAG"

echo ">> subindo o container com BACKEND_IMAGE=$BACKEND_IMAGE"
docker compose -f docker-compose.yml up -d --remove-orphans prontuai-backend-stg

PORT="${BACKEND_HTTP_PORT:-8080}"
echo ">> health check em http://127.0.0.1:${PORT}/health (ate 60s)"
for i in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    echo ""
    printf '%s\n' "$BACKEND_IMAGE" > .current_backend_image
    docker image prune -f >/dev/null 2>&1 || true
    echo "DEPLOY_OK $BACKEND_IMAGE (health em ${i} tentativa(s))"
    exit 0
  fi
  # Progresso visivel em vez de 60s de silencio.
  printf '   tentativa %02d/30\r' "$i"
  sleep 2
done
echo ""

echo "!! health check FALHOU depois de 30 tentativas (60s)" >&2
echo "!! estado do container:" >&2
docker compose -f docker-compose.yml ps >&2 || true
echo "!! ultimas 80 linhas do log:" >&2
docker compose -f docker-compose.yml logs --tail=80 prontuai-backend-stg >&2 || true

if [ -n "${PREV_IMAGE:-}" ]; then
  echo "!! revertendo para $PREV_IMAGE" >&2
  export BACKEND_IMAGE="$PREV_IMAGE"
  docker compose -f docker-compose.yml up -d prontuai-backend-stg >&2 || true
  for i in $(seq 1 20); do
    if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
      echo "ROLLBACK_OK $PREV_IMAGE (staging voltou a versao anterior)" >&2
      echo "   .current_backend_image NAO foi alterado: o ponto de rollback segue valido" >&2
      exit 1
    fi
    printf '   rollback %02d/20\r' "$i" >&2
    sleep 2
  done
  echo "" >&2
  echo "!! ROLLBACK FALHOU: staging esta fora do ar, intervencao manual necessaria" >&2
else
  echo "!! sem imagem anterior registrada: nao ha rollback automatico" >&2
fi
exit 1
REMOTE

step_ok
step "Registro"
append_log "staging_vps_deploy=ok sha=$SHORT image=prontuai-backend-stg:$TAG"
step_ok
printf '\n%s=== Deploy concluido: prontuai-backend-stg:%s ===%s\n' "$C_OK" "$TAG" "$C_OFF"
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
