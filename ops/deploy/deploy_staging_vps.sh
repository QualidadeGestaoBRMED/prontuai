#!/usr/bin/env bash
# Atalho: deploy na VPS de staging. Toda a logica esta em deploy_vps.sh, que
# atende os dois ambientes — duplicar o script garantiria que uma correcao
# chegasse so em metade dele.
#
#   DEPLOY_HOST=1.2.3.4 ./ops/deploy/deploy_staging_vps.sh [--ref X] [--skip-tests]
set -euo pipefail
exec env DEPLOY_ENV=staging "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/deploy_vps.sh" "$@"
