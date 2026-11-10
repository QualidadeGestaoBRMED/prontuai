#!/usr/bin/env bash
# Falha se o ambiente de PRODUÇÃO puder ligar as ferramentas só de staging
# (`back-end/app/staging`, STC-981). Em produção, usar pedido antigo liberaria
# documento sem expedição aberta.
#
# O código dessas ferramentas pode estar na v1: elas só agem com as duas chaves
# de `app.staging.ativo()` — APP_ENV=staging e FERRAMENTAS_DE_STAGING=true. O que
# se confere aqui é que produção não tem nenhuma das duas:
#
#   conferir_producao_sem_ferramentas_de_staging.sh            compose de produção da árvore (CI)
#   conferir_producao_sem_ferramentas_de_staging.sh <commit>   compose de produção do commit (deploy direto)
#   conferir_producao_sem_ferramentas_de_staging.sh --config   linhas de APP_ENV/FERRAMENTAS_DE_STAGING
#                                                              de `docker compose config` na stdin,
#                                                              seguidas de CONFERENCIA_OK
#
# O modo --config é o que vale de verdade: é o ambiente final do container, com o
# .env do servidor e o compose juntos. Os outros pegam o erro antes, no repositório.
# Ele falha FECHADO: sem a linha CONFERENCIA_OK (o `config` não rodou, o ssh caiu),
# não há o que conferir e o deploy para. O servidor a produz assim:
#
#   set -o pipefail; cd "$DEPLOY_PATH" && BACKEND_IMAGE=conferencia docker compose -f docker-compose.yml config \
#     | { grep -Ei 'FERRAMENTAS_DE_STAGING|APP_ENV' || true; } && echo CONFERENCIA_OK
set -euo pipefail

raiz="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel 2>/dev/null \
  || cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
compose='back-end/docker-compose.aws.yml'

# Linha de variável no compose (lista "- X=..." ou mapa "X: ...") e no
# `docker compose config` (mapa). APP_ENV é comparado sem caixa, como em config.py.
chave='^[[:space:]-]*FERRAMENTAS_DE_STAGING[[:space:]]*[:=]'
ambiente='^[[:space:]-]*APP_ENV[[:space:]]*[:=][[:space:]]*"?staging"?[[:space:]]*$'

conferir() {
  local texto="$1" origem="$2"
  local achados
  achados="$(printf '%s\n' "$texto" | grep -Ei -e "$chave" -e "$ambiente" | sed 's/^[[:space:]-]*//' | cut -d'=' -f1 | cut -d':' -f1 | sort -u || true)"
  if [ -n "$achados" ]; then
    echo "Producao com chave de ferramentas de staging em $origem: $achados" >&2
    echo "Nao pode subir: ver back-end/app/staging/__init__.py (STC-981)." >&2
    exit 1
  fi
}

case "${1:-}" in
  --config)
    entrada="$(cat)"
    if ! printf '%s\n' "$entrada" | grep -qx 'CONFERENCIA_OK'; then
      echo "A conferencia do ambiente de producao nao rodou no servidor (sem CONFERENCIA_OK)." >&2
      exit 1
    fi
    conferir "$(printf '%s\n' "$entrada" | grep -vx 'CONFERENCIA_OK' || true)" "docker compose config"
    ;;
  "")
    conferir "$(cat "$raiz/$compose")" "$compose"
    ;;
  *)
    conferir "$(git -C "$raiz" show "$1:$compose")" "$compose ($1)"
    ;;
esac
echo "Producao sem chave de ferramentas de staging."
