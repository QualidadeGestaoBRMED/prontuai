#!/usr/bin/env bash
# Deploy do backend numa VPS sem passar pelo GitHub Actions.
#
# Serve staging e producao a partir do mesmo caminho de codigo, porque duplicar
# a logica garante que uma correcao chegue so em metade dela. Use os atalhos:
#
#   ./ops/deploy/deploy_staging_vps.sh    (staging, VPS arm64)
#   ./ops/deploy/deploy_prod_vps.sh       (producao, EC2 amd64)
#
# Faz o mesmo que os workflows backend-ghcr-*-deploy.yml, com duas diferencas
# deliberadas:
#
#   - Builda NA VPS, arquitetura nativa, sem registry no caminho: nao precisa de
#     PAT do GHCR nem de emular outra arquitetura com QEMU.
#   - Envia o conteudo de UM COMMIT (git archive), nao a arvore de trabalho.
#     Nada de .env, __pycache__, logs, dump de banco ou compose local vazando
#     para o servidor — por construcao, nao por lista de exclusao que alguem
#     esquece de atualizar.
#
# Producao tem tres travas que staging nao tem, porque o risco e outro:
#   - dump do banco ANTES de subir (auto_migrate() roda no startup, e voltar a
#     imagem nao desfaz mudanca de schema);
#   - confirmacao digitada, nao um "s";
#   - health check tambem na URL publica, cobrindo nginx/TLS/DNS.
#
# Uso:
#   DEPLOY_ENV=prod    DEPLOY_HOST=1.2.3.4 ./ops/deploy/deploy_vps.sh
#   DEPLOY_ENV=staging DEPLOY_HOST=1.2.3.4 ./ops/deploy/deploy_vps.sh --skip-tests
#
# Variaveis (todas com default, menos DEPLOY_HOST):
#   DEPLOY_ENV          staging | prod          (default staging)
#   DEPLOY_HOST         obrigatoria, host/IP da VPS
#   DEPLOY_USER         default ubuntu (staging) / ec2-user (prod)
#   DEPLOY_PORT         default 22
#   DEPLOY_PATH         default /home/ubuntu/prontuai-staging | /home/ec2-user/prontuai
#   DEPLOY_SSH_KEY      opcional, caminho da chave privada
#   PUBLIC_HEALTH_URL   prod: URL publica checada apos o deploy
#   DB_DEPLOY_DIR       prod: pasta do compose do banco (default /home/ec2-user/prontuai-db)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

DEPLOY_ENV="${DEPLOY_ENV:-staging}"
case "$DEPLOY_ENV" in
  staging)
    # Compose e servico saem do que o workflow correspondente envia.
    COMPOSE_SRC="back-end/docker-compose.stg.yml"
    SERVICE="prontuai-backend-stg"
    IMAGE_REPO="prontuai-backend-stg"
    DEPLOY_USER="${DEPLOY_USER:-ubuntu}"
    DEPLOY_PATH="${DEPLOY_PATH:-/home/ubuntu/prontuai-staging}"
    NEEDS_DUMP=0
    ;;
  prod|producao|production)
    DEPLOY_ENV="prod"
    COMPOSE_SRC="back-end/docker-compose.aws.yml"
    SERVICE="prontuai-backend"
    IMAGE_REPO="prontuai-backend"
    DEPLOY_USER="${DEPLOY_USER:-ec2-user}"
    DEPLOY_PATH="${DEPLOY_PATH:-/home/ec2-user/prontuai}"
    NEEDS_DUMP=1
    ;;
  *) echo "DEPLOY_ENV invalida: $DEPLOY_ENV (use staging ou prod)" >&2; exit 1 ;;
esac
DEPLOY_PORT="${DEPLOY_PORT:-22}"
DB_DEPLOY_DIR="${DB_DEPLOY_DIR:-/home/ec2-user/prontuai-db}"
REF="HEAD"
RUN_TESTS=1
ASSUME_YES=0
SKIP_DUMP=0

while [ $# -gt 0 ]; do
  case "$1" in
    --ref)         REF="${2:?--ref exige um valor}"; shift 2 ;;
    --skip-tests)  RUN_TESTS=0; shift ;;
    --yes|-y)      ASSUME_YES=1; shift ;;
    --skip-dump)   SKIP_DUMP=1; shift ;;
    -h|--help)     sed -n '2,42p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
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
[ "$NEEDS_DUMP" -eq 1 ] && TOTAL_STEPS=8
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

printf '%s=== Deploy %s (sem GitHub Actions) ===%s\n' "$C_STEP" "$(printf %s "$DEPLOY_ENV" | tr a-z A-Z)" "$C_OFF"

step "Pre-requisitos locais"
for c in git ssh tar docker; do
  if command -v "$c" >/dev/null 2>&1; then info "$c: ok"; else die "Falta o comando '$c' nesta maquina."; fi
done
[ -n "${DEPLOY_HOST:-}" ] || die "DEPLOY_HOST nao definida. Ex.: DEPLOY_HOST=1.2.3.4 $0"
info "destino: $DEPLOY_USER@$DEPLOY_HOST:$DEPLOY_PORT"
info "caminho: $DEPLOY_PATH"
info "servico: $SERVICE  (compose: $COMPOSE_SRC)"
step_ok

SSH_OPTS=(-p "$DEPLOY_PORT" -o StrictHostKeyChecking=accept-new)
[ -n "${DEPLOY_SSH_KEY:-}" ] && SSH_OPTS=(-i "$DEPLOY_SSH_KEY" "${SSH_OPTS[@]}")
TARGET="$DEPLOY_USER@$DEPLOY_HOST"

remote() { ssh "${SSH_OPTS[@]}" "$TARGET" "$@"; }

# ---------------------------------------------------------------- 1. o commit
if [ "$DEPLOY_ENV" = "prod" ] && [ "$ASSUME_YES" -ne 1 ]; then
  printf '\n%s Isto vai para PRODUCAO (%s), atendendo usuarios reais.%s\n' "$C_WARN" "$DEPLOY_HOST" "$C_OFF"
  printf 'Digite %sproducao%s para confirmar: ' "$C_WARN" "$C_OFF"
  read -r conf
  [ "$conf" = "producao" ] || die "Nao confirmado (digite exatamente: producao)."
fi

step "Resolvendo o commit a implantar"
SHA="$(git rev-parse "${REF}^{commit}" 2>/dev/null)" || die "Ref invalida: $REF"
SHORT="${SHA:0:7}"
TAG="sha-$SHORT"
info "ref     : $REF"
info "commit  : $SHORT  $(git log -1 --format=%s "$SHA" | cut -c1-58)"
info "imagem  : $IMAGE_REPO:$TAG"

# Confere que o compose do ambiente existe NO COMMIT e declara o servico que
# vamos subir. Sem isto, uma troca de ambiente errada so aparece la na frente,
# no `docker compose up`, depois de o compose errado ja ter sobrescrito o do
# servidor — foi exatamente o que aconteceu ao enviar o compose de staging para
# producao.
git cat-file -e "$SHA:$COMPOSE_SRC" 2>/dev/null \
  || die "$COMPOSE_SRC nao existe no commit $SHORT."
if ! git show "$SHA:$COMPOSE_SRC" | grep -qE "^[[:space:]]+$SERVICE:"; then
  die "Incoerencia de ambiente: $COMPOSE_SRC nao declara o servico '$SERVICE'.
  DEPLOY_ENV=$DEPLOY_ENV espera esse servico; confira se o ambiente esta certo."
fi
info "compose : $COMPOSE_SRC declara '$SERVICE'"

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
trace "ssh -p $DEPLOY_PORT $TARGET true"
SSH_ERR="$(remote true 2>&1)" || die "Nao consegui conectar em $TARGET na porta $DEPLOY_PORT.

  O ssh disse:
$(printf '%s\n' "$SSH_ERR" | sed 's/^/    /')

  Teste na mao com:
    ssh ${DEPLOY_SSH_KEY:+-i $DEPLOY_SSH_KEY }-p $DEPLOY_PORT $TARGET true"
info "ssh: ok"

# Cada pre-requisito e checado em separado, para dizer QUAL falta.
FALTANDO=""
for c in docker curl tar; do
  remote "command -v $c >/dev/null 2>&1" || FALTANDO="$FALTANDO $c"
done
remote "docker compose version >/dev/null 2>&1" || FALTANDO="$FALTANDO docker-compose-plugin"
[ -z "$FALTANDO" ] || die "A VPS nao tem:$FALTANDO"
info "docker, compose, curl, tar: ok"

remote "test -f '$DEPLOY_PATH/.env'" \
  || die "Conectei na VPS, mas falta $DEPLOY_PATH/.env
  Crie a partir de back-end/.env.example antes de implantar."
info ".env presente em $DEPLOY_PATH"

PREV_IMAGE="$(remote "cat '$DEPLOY_PATH/.current_backend_image' 2>/dev/null || true")"
if [ -n "$PREV_IMAGE" ]; then
  info "rollback disponivel: $PREV_IMAGE"
else
  warn "sem .current_backend_image na VPS: NAO havera rollback automatico"
fi
step_ok

if [ "$NEEDS_DUMP" -eq 1 ]; then
  step "Dump do banco antes de subir"
  if [ "$SKIP_DUMP" -eq 1 ]; then
    warn "dump PULADO (--skip-dump). auto_migrate() roda no startup e voltar a"
    warn "imagem nao desfaz mudanca de schema: voce fica sem rede."
    step_ok "pulado "
  else
    # Reusa o backup_postgres.sh da VPS quando existir: ele ja sabe comprimir,
    # mandar para o bucket e respeitar a retencao — e agora pega o flock, entao
    # nao concorre com a purga semanal.
    if remote "test -x '$DB_DEPLOY_DIR/script/backup_postgres.sh'"; then
      info "usando $DB_DEPLOY_DIR/script/backup_postgres.sh (vai para o bucket)"
      trace "$DB_DEPLOY_DIR/script/backup_postgres.sh"
      remote "cd '$DB_DEPLOY_DIR' && ./script/backup_postgres.sh" \
        || die "O backup falhou. NAO vou implantar sem dump.
  Se o banco estiver indisponivel, resolva isso primeiro; se precisar seguir
  mesmo assim (ciente do risco), use --skip-dump."
    else
      warn "backup_postgres.sh nao encontrado em $DB_DEPLOY_DIR/script/"
      info "caindo para pg_dump local em $DEPLOY_PATH"
      ARQ="pre-deploy-$SHORT-$(date +%Y%m%d-%H%M%S).sql.gz"
      remote "set -a; . '$DB_DEPLOY_DIR/.env' 2>/dev/null || true; set +a; \
              docker exec prontuai-db pg_dump -U \"\${POSTGRES_USER:-prontuai}\" \"\${POSTGRES_DB:-prontuai}\" \
              | gzip > '$DEPLOY_PATH/$ARQ'" \
        || die "pg_dump falhou; nao vou implantar sem dump (ou use --skip-dump)."
      BYTES="$(remote "stat -c %s '$DEPLOY_PATH/$ARQ'")"
      info "dump: $ARQ ($(awk -v b="$BYTES" 'BEGIN{printf "%.1f MB", b/1048576}'))"
      # Um dump de poucos KB e quase sempre erro de credencial ou banco vazio.
      [ "$BYTES" -gt 102400 ] || die "O dump tem $BYTES bytes — pequeno demais para ser um banco de producao.
  Confira POSTGRES_USER/POSTGRES_DB em $DB_DEPLOY_DIR/.env antes de seguir."
    fi
    step_ok
  fi
fi

step "Enviando o commit $SHORT para a VPS"
remote "mkdir -p '$DEPLOY_PATH' '$DEPLOY_PATH/logs' \
        '$DEPLOY_PATH/resultados' '$DEPLOY_PATH/ocr_resultados' \
        '$DEPLOY_PATH/auditoria_validacao' '$DEPLOY_PATH/data/uploads'"
info "diretorios garantidos"

ARQUIVOS="$(git archive --format=tar "$SHA:back-end" | tar -t | wc -l)"
TAMANHO="$(git archive --format=tar "$SHA:back-end" | wc -c | awk '{printf "%.1f MB", $1/1048576}')"
info "pacote: $ARQUIVOS entradas, $TAMANHO (so conteudo versionado)"

# src/ e recriada a cada deploy: arquivo removido no commit nao pode sobrar la.
trace "git archive $SHORT:back-end | ssh ... tar -x -C $DEPLOY_PATH/src"
git archive --format=tar "$SHA:back-end" \
  | remote "rm -rf '$DEPLOY_PATH/src' && mkdir -p '$DEPLOY_PATH/src' \
            && tar -x -C '$DEPLOY_PATH/src'" \
  || die "Falha ao enviar/extrair o pacote na VPS (veja o erro do tar/ssh acima)."

ENVIADOS="$(remote "find '$DEPLOY_PATH/src' -type f | wc -l")"
info "extraidos na VPS: $ENVIADOS arquivos"
[ "$ENVIADOS" -gt 0 ] || die "A pasta src/ ficou vazia na VPS; transferencia nao funcionou."

# O compose tambem sai do commit, nao da arvore local.
git show "$SHA:$COMPOSE_SRC" \
  | remote "cat > '$DEPLOY_PATH/docker-compose.yml'" \
  || die "Falha ao enviar o $COMPOSE_SRC."
info "docker-compose.yml atualizado a partir do commit"
step_ok

# ----------------------------------------------------------- 4. build e subida
step "Build na VPS (arquitetura nativa) e subida"
info "o build imprime abaixo; a primeira vez costuma levar alguns minutos"
remote "DEPLOY_PATH='$DEPLOY_PATH' TAG='$TAG' PREV_IMAGE='$PREV_IMAGE' \
        SERVICE='$SERVICE' IMAGE_REPO='$IMAGE_REPO' bash -s" <<'REMOTE'
set -euo pipefail
cd "$DEPLOY_PATH"

echo ">> build de $IMAGE_REPO:$TAG"
docker build -t "$IMAGE_REPO:$TAG" ./src

set -a; . ./.env; set +a
export BACKEND_IMAGE="$IMAGE_REPO:$TAG"

echo ">> subindo o container com BACKEND_IMAGE=$BACKEND_IMAGE"
docker compose -f docker-compose.yml up -d --remove-orphans $SERVICE

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
docker compose -f docker-compose.yml logs --tail=80 $SERVICE >&2 || true

if [ -n "${PREV_IMAGE:-}" ]; then
  echo "!! revertendo para $PREV_IMAGE" >&2
  export BACKEND_IMAGE="$PREV_IMAGE"
  docker compose -f docker-compose.yml up -d $SERVICE >&2 || true
  for i in $(seq 1 20); do
    if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
      echo "ROLLBACK_OK $PREV_IMAGE (voltou a versao anterior)" >&2
      echo "   .current_backend_image NAO foi alterado: o ponto de rollback segue valido" >&2
      exit 1
    fi
    printf '   rollback %02d/20\r' "$i" >&2
    sleep 2
  done
  echo "" >&2
  echo "!! ROLLBACK FALHOU: o servico esta fora do ar, intervencao manual necessaria" >&2
else
  echo "!! sem imagem anterior registrada: nao ha rollback automatico" >&2
fi
exit 1
REMOTE

step_ok

if [ "$DEPLOY_ENV" = "prod" ]; then
  step "Health check publico (nginx/TLS/DNS)"
  URL="${PUBLIC_HEALTH_URL:-}"
  if [ -z "$URL" ]; then
    warn "PUBLIC_HEALTH_URL nao definida; conferindo so o health interno"
    warn "defina para cobrir nginx, certificado e DNS — o caminho que o usuario usa"
    step_ok "sem URL "
  else
    info "GET $URL"
    OK=0
    for i in $(seq 1 10); do
      if curl -fsS --max-time 10 "$URL" >/dev/null 2>&1; then OK=1; break; fi
      printf '      tentativa %02d/10\r' "$i"; sleep 3
    done
    printf '\n'
    if [ "$OK" -eq 1 ]; then
      step_ok
    else
      # O container respondeu no localhost, entao a aplicacao subiu; o que
      # falhou esta na borda. Nao reverto por isso, mas nao deixo passar calado.
      warn "a URL publica nao respondeu, embora o health interno tenha passado."
      warn "a aplicacao subiu; o problema esta na borda (nginx, certificado, DNS)."
      warn "para reverter: DEPLOY_ENV=prod DEPLOY_HOST=$DEPLOY_HOST, e na VPS:"
      warn "  cd $DEPLOY_PATH && export BACKEND_IMAGE=\$(cat .current_backend_image) && docker compose up -d $SERVICE"
      die "Health check publico falhou em $URL"
    fi
  fi
fi

step "Registro"
append_log "vps_deploy=ok env=$DEPLOY_ENV sha=$SHORT image=$IMAGE_REPO:$TAG"
step_ok
printf '\n%s=== Deploy concluido: %s:%s ===%s\n' "$C_OK" "$TAG" "$C_OFF"
cat <<FIM

Proximos passos de verificacao (o /health e estatico, nao prova muita coisa):

  ssh ${DEPLOY_SSH_KEY:+-i $DEPLOY_SSH_KEY }-p $DEPLOY_PORT $TARGET \\
    'docker logs prontuai-backend-stg 2>&1 | grep -iE "erro|falha|Traceback|migra|setup_telemetry" | tail -20'

Procure por falha de auto_migrate e exercite um endpoint /v1/ autenticado.

Rollback manual, se precisar:

  ssh -p $DEPLOY_PORT $TARGET \\
    'cd $DEPLOY_PATH && export BACKEND_IMAGE=\$(cat .current_backend_image) \\
     && docker compose up -d prontuai-backend-stg'
FIM
