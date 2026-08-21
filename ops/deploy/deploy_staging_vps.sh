#!/usr/bin/env bash
# Atalho: deploy na VPS de staging. Toda a logica esta em deploy_vps.sh, que
# atende os dois ambientes — duplicar o script garantiria que uma correcao
# chegasse so em metade dele.
#
#   DEPLOY_HOST=1.2.3.4 ./ops/deploy/deploy_staging_vps.sh [--ref X] [--skip-tests]
set -euo pipefail

# Compatibilidade: este script nasceu usando STAGING_*, antes de o nucleo passar
# a atender producao tambem. Os nomes antigos continuam valendo para nao quebrar
# comando salvo nem memoria muscular.
[ -n "${STAGING_HOST:-}"    ] && export DEPLOY_HOST="${DEPLOY_HOST:-$STAGING_HOST}"
[ -n "${STAGING_USER:-}"    ] && export DEPLOY_USER="${DEPLOY_USER:-$STAGING_USER}"
[ -n "${STAGING_PORT:-}"    ] && export DEPLOY_PORT="${DEPLOY_PORT:-$STAGING_PORT}"
[ -n "${STAGING_SSH_KEY:-}" ] && export DEPLOY_SSH_KEY="${DEPLOY_SSH_KEY:-$STAGING_SSH_KEY}"
[ -n "${STAGING_DEPLOY_PATH:-}" ] && export DEPLOY_PATH="${DEPLOY_PATH:-$STAGING_DEPLOY_PATH}"

exec env DEPLOY_ENV=staging "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/deploy_vps.sh" "$@"
