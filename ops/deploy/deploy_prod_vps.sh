#!/usr/bin/env bash
# Atalho: deploy na EC2 de producao. Toda a logica esta em deploy_vps.sh.
#
# Diferente de staging, aqui o script faz dump do banco antes de subir, exige
# confirmacao digitada e checa a URL publica no fim.
#
#   DEPLOY_HOST=1.2.3.4 PUBLIC_HEALTH_URL=https://api.exemplo.com/health \
#     ./ops/deploy/deploy_prod_vps.sh
set -euo pipefail
exec env DEPLOY_ENV=prod "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/deploy_vps.sh" "$@"
