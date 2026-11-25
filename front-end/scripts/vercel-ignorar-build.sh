#!/bin/sh
# Ignored Build Step da Vercel (vercel.json → ignoreCommand), para os dois projetos do front.
# Sai 0 = pula o build (não gasta minuto); sai 1 = builda.
#
# Builda só no branch de produção de cada projeto (VERCEL_ENV=production: `staging` no prontuai-staging, `v1` no
# prontuai) e só quando o push mexeu em front-end/. Branch de PR e push só de back-end não buildam.

[ "$VERCEL_ENV" = "production" ] || { echo "Pulando: $VERCEL_GIT_COMMIT_REF não é o branch de produção do projeto."; exit 0; }

BASE="${VERCEL_GIT_PREVIOUS_SHA:-HEAD^}"
# A Vercel clona raso: se o commit anterior ficou fora do clone, builda por garantia.
git cat-file -e "$BASE^{commit}" 2>/dev/null || { echo "Commit base $BASE fora do clone: buildando."; exit 1; }

if git diff --quiet "$BASE" HEAD -- .; then
  echo "Pulando: nenhuma mudança em front-end/ desde $BASE."
  exit 0
fi
echo "Buildando: front-end/ mudou desde $BASE."
exit 1
