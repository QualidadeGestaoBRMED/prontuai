#!/usr/bin/env bash
# Falha se o código tiver a função de pedidos guardados, que é só para testes em
# staging (STC-981). Em produção, usar pedido antigo liberaria documento sem
# expedição aberta.
#
#   bloquear_codigo_de_staging.sh          olha a árvore de trabalho (CI)
#   bloquear_codigo_de_staging.sh <commit> olha o commit (deploy direto)
#
# Não roda na staging: o deploy dela usa outro workflow, e o deploy direto só
# chama este script com DEPLOY_ENV=prod.
set -euo pipefail

raiz="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
padrao='pedidos_guardados|pedidos-guardados|PedidosGuardados|PEDIDOS_GUARDADOS'
pastas=(back-end/app back-end/main.py back-end/migrations front-end/app front-end/components front-end/lib)

if [ "$#" -ge 1 ]; then
  achados="$(git -C "$raiz" grep -lE "$padrao" "$1" -- "${pastas[@]}" || true)"
else
  achados="$(cd "$raiz" && grep -rlE "$padrao" "${pastas[@]}" 2>/dev/null || true)"
fi

if [ -n "$achados" ]; then
  echo "Codigo exclusivo de staging encontrado. Nao pode ir para producao (STC-981):" >&2
  echo "$achados" >&2
  exit 1
fi
echo "Sem codigo exclusivo de staging."
