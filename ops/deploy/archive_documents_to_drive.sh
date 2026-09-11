#!/usr/bin/env bash
# Arquiva no Google Drive os documentos que ja passaram da janela de consulta
# E que ja tiveram decisao humana, liberando o disco da VPS.
#
# Duas condicoes, nao uma. O arquivo so sai do disco se:
#   1. tem mais de ARCHIVE_AFTER_DAYS dias (default 20), e
#   2. o documento correspondente no banco ja passou pela checagem humana.
#
# A segunda condicao e o ponto do script. Um documento que ninguem checou
# ainda FICA no disco, por mais velho que seja — ele ainda vai ser aberto na
# tela de revisao, e a tela le o arquivo do disco. Arquivar por idade sozinha
# esvaziaria a fila de checagem por baixo do revisor.
#
# Fluxo, por lote:
#     rclone copy -> rclone check -> so entao apaga os originais
#
# O `check` entre copiar e apagar nao e zelo excessivo: e a diferenca entre
# "confio que subiu" e "verifiquei que subiu". Sao prontuarios; um upload
# truncado que passe despercebido e perda definitiva.
#
# POR QUE NAO ZIPA (a primeira versao deste script zipava por semana/mes):
#
#   a) Disco cheio. Zipar exige espaco livre igual ao tamanho do balde antes
#      de liberar qualquer coisa — exatamente o que nao existe quando o disco
#      estourou, que e o momento em que este script mais precisa rodar.
#   b) O portao de aprovacao quebra o zip por periodo. O zip era nomeado pelo
#      periodo (prontuai-documentos-2026-W32.zip), e havia um guard que so
#      arquivava o periodo quando TODOS os arquivos dele tinham saido da
#      janela, para o nome nao ser gerado duas vezes e o `rclone copy`
#      sobrescrever o zip anterior. Com o portao, um unico documento retido
#      por falta de checagem mantem o periodo aberto para sempre; quando ele
#      finalmente e aprovado, o zip do periodo e regerado com o MESMO nome.
#      Ou nada nunca e arquivado, ou o zip anterior e sobrescrito em silencio.
#      Arquivo por arquivo nao tem nome colidindo e nao tem periodo para
#      fechar: cada documento e enviado assim que fica elegivel.
#
# SOBREPOSICAO COM O drive_service: o backend ja sobe cada documento ao Drive
# no momento da aprovacao (app/services/drive_service.py, chamado no PATCH de
# revisao). Este script NAO assume que aquele upload aconteceu — o de la e
# best-effort, roda em BackgroundTask e so loga em caso de falha. Aqui a copia
# e verificada por checksum antes do delete. Use um prefixo proprio no remote
# (ARCHIVE_RCLONE_REMOTE) se nao quiser os dois no mesmo lugar.
#
# Uso:
#   ARCHIVE_DRY_RUN=true ./ops/deploy/archive_documents_to_drive.sh   # so relata
#   ./ops/deploy/archive_documents_to_drive.sh                        # aplica
#
# Variaveis:
#   ARCHIVE_SOURCE_DIR     pasta dos documentos (default /home/ec2-user/prontuai/data/uploads)
#   ARCHIVE_RCLONE_REMOTE  destino, ex.: gdrive:prontuai/arquivo  (OBRIGATORIA)
#   ARCHIVE_RCLONE_FLAGS   flags extras do rclone
#   ARCHIVE_AFTER_DAYS     idade minima para arquivar (default 20)
#   ARCHIVE_GATE           decidido | aprovado (default decidido)
#   ARCHIVE_ORPHAN_MODE    keep | archive (default keep) — arquivo sem linha no banco
#   ARCHIVE_BATCH          arquivos por lote de copy/check/delete (default 200)
#   ARCHIVE_MAX_FILES      teto de arquivos nesta execucao (default 0 = sem teto)
#   ARCHIVE_WORK_DIR       onde ficam as listas e os relatorios (default <source>/../arquivo-tmp)
#   ARCHIVE_DRY_RUN        "true" nao envia e nao apaga (default false)
#   ARCHIVE_DB_CONTAINER   container do Postgres (default prontuai-db; staging: prontuai-db-stg)
#   DB_DEPLOY_DIR          onde esta o .env do banco (default /home/ec2-user/prontuai-db)
#   POSTGRES_USER, POSTGRES_DB   credenciais/nome do banco
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

SRC="${ARCHIVE_SOURCE_DIR:-/home/ec2-user/prontuai/data/uploads}"
REMOTE="${ARCHIVE_RCLONE_REMOTE:-}"
DIAS="${ARCHIVE_AFTER_DAYS:-20}"
GATE="${ARCHIVE_GATE:-decidido}"
ORPHAN_MODE="${ARCHIVE_ORPHAN_MODE:-keep}"
LOTE="${ARCHIVE_BATCH:-200}"
# Teto de arquivos por execucao. 0 = sem teto.
#
# Existe para ensaio graduado: numa base de dezenas de GB, a primeira execucao
# real nao deveria ser "tudo". Com ARCHIVE_MAX_FILES=20 da para arquivar 20,
# abrir um documento arquivado na tela e confirmar que o 410 chega com a
# mensagem certa, e so entao soltar o resto. Sem isso, o unico jeito de testar
# o caminho completo em producao e apostar nos 21 GB de uma vez.
MAX_FILES="${ARCHIVE_MAX_FILES:-0}"
WORK="${ARCHIVE_WORK_DIR:-$(dirname "$SRC")/arquivo-tmp}"
DRY_RUN="${ARCHIVE_DRY_RUN:-false}"
DB_DEPLOY_DIR="${DB_DEPLOY_DIR:-/home/ec2-user/prontuai-db}"
# Container do Postgres consultado pelo portao e onde archived_at e gravado.
#
# Configuravel porque o banco de staging se chama `prontuai-db-stg` (ver
# back-end/docker-compose.stg.yml): com o nome fixo, o script se recusaria a
# rodar em staging. E num host onde os dois containers existam lado a lado, o
# nome fixo faria um teste "de staging" consultar e marcar o banco de PRODUCAO
# sem erro nenhum — por isso o banco em uso aparece no inicio do log.
DB_CONTAINER="${ARCHIVE_DB_CONTAINER:-prontuai-db}"

# --transfers=4: o gargalo aqui e latencia por arquivo, nao banda — sao muitos
# PDFs pequenos, nao um zip de GB. --drive-stop-on-upload-limit para o script
# (sem apagar nada) quando a cota diaria do Drive estoura, em vez de insistir.
ARCHIVE_RCLONE_FLAGS="${ARCHIVE_RCLONE_FLAGS:---transfers=4 --retries=5 --low-level-retries=20 --drive-stop-on-upload-limit}"
read -r -a RCLONE_FLAGS <<< "$ARCHIVE_RCLONE_FLAGS"

require_cmd rclone find docker stat awk
[ -n "$REMOTE" ] || die "ARCHIVE_RCLONE_REMOTE nao definida (ex.: gdrive:prontuai/arquivo)."
[ -d "$SRC" ] || die "Pasta de origem nao existe: $SRC"
case "$GATE" in
  aprovado|decidido) ;;
  *) die "ARCHIVE_GATE invalido: $GATE (use aprovado ou decidido)" ;;
esac
case "$ORPHAN_MODE" in
  keep|archive) ;;
  *) die "ARCHIVE_ORPHAN_MODE invalido: $ORPHAN_MODE (use keep ou archive)" ;;
esac

track_job "arquivamento-drive"
# Ler 30 GB do disco concorrendo com o pg_dump so faz os dois demorarem mais.
# Espera e, se o backup nao terminar, PULA: o arquivamento e semanal e perder
# uma execucao nao tem consequencia, ao contrario de perder um backup.
db_maintenance_lock "${DB_LOCK_WAIT:-1800}" skip

if [ -z "${POSTGRES_USER:-}" ] && [ -f "$DB_DEPLOY_DIR/.env" ]; then
  set -a
  . "$DB_DEPLOY_DIR/.env"
  set +a
fi
POSTGRES_USER="${POSTGRES_USER:?POSTGRES_USER is required (defina no ambiente ou em $DB_DEPLOY_DIR/.env)}"
POSTGRES_DB="${POSTGRES_DB:-prontuai}"

docker inspect "$DB_CONTAINER" >/dev/null 2>&1 \
  || die "Container $DB_CONTAINER nao encontrado. O arquivamento so roda com o banco no ar:
  sem o banco nao ha como saber o que ja passou pela checagem humana, e apagar
  por idade sozinha removeria documentos da fila de revisao."

mkdir -p "$WORK"

# $WORK nao pode ficar DENTRO de $SRC: o `find` da secao 1 varre $SRC inteiro,
# entao as proprias listas entrariam na lista de candidatos e seriam enviadas
# ao Drive e apagadas como se fossem documentos.
SRC_ABS="$(cd "$SRC" && pwd -P)"
WORK_ABS="$(cd "$WORK" && pwd -P)"
case "$WORK_ABS/" in
  "$SRC_ABS"/*) die "ARCHIVE_WORK_DIR ($WORK_ABS) esta dentro de ARCHIVE_SOURCE_DIR ($SRC_ABS).
  As listas de trabalho seriam varridas como se fossem documentos. Use uma pasta irma." ;;
esac

# Todas as listas ficam em $WORK, e nao em /tmp, e NAO sao removidas no fim:
# depois de um run que falhou no meio, elas sao o post-mortem — dizem o que o
# script achou, o que liberou e o que estava no lote em andamento. Sao poucos
# MB de texto, reescritos a cada execucao.
#
# Sem `trap ... EXIT` de limpeza, de proposito: `track_job` (lib.sh) instala o
# proprio trap EXIT para reportar a metrica do job, e um segundo `trap ... EXIT`
# aqui SUBSTITUIRIA aquele — o job nunca reportaria sucesso, e o alerta
# prontuai-job-arquivamento-atrasado (noDataState: Alerting) ficaria disparado
# para sempre sem que nada estivesse errado.
CANDIDATOS="$WORK/.lista-candidatos.tmp"   # caminho relativo dos arquivos com idade > DIAS
LIBERADOS="$WORK/.lista-liberados.tmp"     # basename liberado pelo portao
CONHECIDOS="$WORK/.lista-conhecidos.tmp"   # basename com qualquer linha em documents
LOTE_LISTA="$WORK/.lista-lote.tmp"
ENVIAR="$WORK/lista-enviar.txt"
RETIDOS="$WORK/relatorio-retidos.txt"
ORFAOS="$WORK/relatorio-orfaos.txt"

log "Origem:  $SRC"
log "Banco:   $DB_CONTAINER (db=$POSTGRES_DB)"
log "Destino: $REMOTE"
log "Janela:  $DIAS dias | portao: $GATE | orfaos: $ORPHAN_MODE${DRY_RUN:+ | DRY_RUN=$DRY_RUN}"

# ---------------------------------------------------------------------------
# 1. Candidatos por idade.
#
# %P (e nao %p) grava o caminho RELATIVO a $SRC: e o formato que o
# --files-from do rclone espera, e o que faz a arvore no Drive espelhar a
# arvore local em vez de reproduzir /home/ec2-user/... dentro do destino.
# ---------------------------------------------------------------------------
find "$SRC" -type f -mtime +"$DIAS" -printf '%P\n' | sort > "$CANDIDATOS"
TOTAL_DISCO="$(find "$SRC" -type f -printf '.' | wc -c)"
TOTAL_CAND="$(wc -l < "$CANDIDATOS")"
log "Disco: $TOTAL_DISCO arquivo(s); $TOTAL_CAND fora da janela de $DIAS dias."
if [ "$TOTAL_CAND" -eq 0 ]; then
  log "Nada fora da janela. Nada a fazer."
  exit 0
fi

# ---------------------------------------------------------------------------
# 2. Quem o banco libera.
#
# O casamento e por BASENAME, e nao pelo caminho: documents.file_path guarda o
# caminho de DENTRO do container (/app/data/uploads/x.pdf, ver o volume
# ./data/uploads:/app/data/uploads no compose), que nunca vai bater com o
# caminho do host. O basename e igual nos dois lados.
#
# GROUP BY + bool_and, e nao um WHERE por linha, por causa do caso em que dois
# registros de documents apontam para o MESMO basename. Hoje isso nao deveria
# acontecer: as duas chamadas de upload passam prefixo unico (uuid4 no
# sincrono, v1_brmed.py:156; job_id no assincrono, :617). Mas
# _store_upload_bytes/_store_upload_file ainda aceitam prefix=None na
# assinatura, e registros antigos podem preceder o prefixo — e nesse caso um
# WHERE liberaria o arquivo se QUALQUER uma das linhas estivesse decidida.
# bool_and exige que TODAS estejam: basta uma linha esperando checagem para o
# arquivo ficar. O delete e irreversivel; a consulta mais conservadora custa
# nada.
#
# COALESCE no validation_status porque bool_and IGNORA entradas NULL: sem ele,
# uma linha com status NULL (registro antigo, pre-migracao) seria desprezada e
# o arquivo poderia ser liberado pelas outras linhas.
#
# reviewed_by e o unico sinal confiavel de checagem humana.
# validation_status='validated' NAO serve: v1_brmed.py marca 'validated'
# sozinho quando a IA nao acha exame faltante, antes de qualquer humano ver o
# documento — e a fila de CHECAGEM do produto (api/v1/documents.py) trata
# justamente esses como pendentes. As duas decisoes humanas gravam o revisor:
# na aprovacao o back preenche reviewed_by com o e-mail de quem aprovou
# (api/v1/documents.py); na rejeicao o front envia reviewed_by com o e-mail da
# sessao (front-end/app/checagem/page.tsx). Ja a rejeicao AUTOMATICA da IA
# (v1_brmed.py) nao tem revisor — e por isso fica no disco, aguardando checagem.
case "$GATE" in
  # Default. Sai do disco tudo que um humano DECIDIU, aprovando ou rejeitando.
  # Pendente, validated-so-pela-IA e rejected-so-pela-IA ficam: nenhum humano
  # olhou ainda, e a tela de checagem precisa do arquivo.
  decidido)
    COND="COALESCE(reviewed_by,'') <> ''" ;;
  # Mais conservador: sai somente o que um humano APROVOU; rejeitado por
  # humano fica. Use se o rejeitado precisar continuar reabrivel.
  aprovado)
    COND="COALESCE(validation_status,'') = 'validated' AND COALESCE(reviewed_by,'') <> ''" ;;
esac

psql_run() {
  docker exec -i "$DB_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -tA "$@"
}

psql_run -c "
  SELECT regexp_replace(file_path, '^.*/', '')
  FROM documents
  WHERE COALESCE(file_path,'') <> ''
  GROUP BY 1
  HAVING bool_and($COND);
" | sed '/^$/d' | sort -u > "$LIBERADOS" || die "Consulta ao banco falhou; nada foi apagado."

psql_run -c "
  SELECT DISTINCT regexp_replace(file_path, '^.*/', '')
  FROM documents
  WHERE COALESCE(file_path,'') <> '';
" | sed '/^$/d' | sort -u > "$CONHECIDOS" || die "Consulta ao banco falhou; nada foi apagado."

log "Banco: $(wc -l < "$CONHECIDOS") arquivo(s) referenciados, $(wc -l < "$LIBERADOS") liberado(s) pelo portao '$GATE'."

# ---------------------------------------------------------------------------
# 3. Classifica cada candidato: enviar, retido ou orfao.
#
# Os tres baldes sao exaustivos, e o do meio e o default seguro: na duvida o
# arquivo FICA. So vai para a lista de envio o que o banco liberou.
#
# awk com hash, e nao `grep` por arquivo: com dezenas de milhares de arquivos
# e outras tantas linhas liberadas, um grep por candidato e quadratico e leva
# minutos. Aqui e uma passada em cada lista.
# ---------------------------------------------------------------------------
: > "$ENVIAR"; : > "$RETIDOS"; : > "$ORFAOS"
awk -v lib="$LIBERADOS" -v con="$CONHECIDOS" \
    -v f_env="$ENVIAR" -v f_ret="$RETIDOS" -v f_orf="$ORFAOS" '
  BEGIN {
    while ((getline l < lib) > 0) if (l != "") L[l] = 1
    while ((getline c < con) > 0) if (c != "") C[c] = 1
  }
  {
    base = $0; sub(/^.*\//, "", base)
    if      (base in L) print >> f_env
    else if (base in C) print >> f_ret
    else                print >> f_orf
  }
' "$CANDIDATOS"

mb() {
  # Soma o tamanho das entradas de uma lista, em MB. Lista vazia -> 0.
  [ -s "$1" ] || { echo 0; return; }
  ( cd "$SRC" && du -cb --files0-from=<(tr '\n' '\0' < "$1") 2>/dev/null | tail -1 | cut -f1 ) \
    | awk '{printf "%d", $1/1048576}'
}

# Orfao e o balde que merece olho humano antes de virar rotina: arquivo no
# disco sem nenhuma linha em documents e ou registro antigo com file_path
# NULL, ou sobra de upload que morreu no meio. O default e nao tocar.
if [ "$ORPHAN_MODE" = "archive" ] && [ -s "$ORFAOS" ]; then
  log "AVISO: ARCHIVE_ORPHAN_MODE=archive — $(wc -l < "$ORFAOS") orfao(s) tambem serao enviados e apagados."
  cat "$ORFAOS" >> "$ENVIAR"
  sort -u -o "$ENVIAR" "$ENVIAR"
fi

if [ "$MAX_FILES" -gt 0 ] && [ "$(wc -l < "$ENVIAR")" -gt "$MAX_FILES" ]; then
  ELEGIVEIS_TOTAL="$(wc -l < "$ENVIAR")"
  head -n "$MAX_FILES" "$ENVIAR" > "$ENVIAR.limitado"
  mv "$ENVIAR.limitado" "$ENVIAR"
  log "ARCHIVE_MAX_FILES=$MAX_FILES: $ELEGIVEIS_TOTAL elegiveis, tratando os $MAX_FILES primeiros nesta execucao."
  log "Rode de novo (sem o teto, ou com outro) para continuar de onde parou."
fi

log "-----------------------------------------------------------------"
log "A enviar e apagar : $(wc -l < "$ENVIAR") arquivo(s), $(mb "$ENVIAR") MB"
log "Retidos no disco  : $(wc -l < "$RETIDOS") arquivo(s), $(mb "$RETIDOS") MB  (sem checagem humana)"
log "Orfaos            : $(wc -l < "$ORFAOS") arquivo(s), $(mb "$ORFAOS") MB  (sem linha em documents)"
log "-----------------------------------------------------------------"
log "Listas: $ENVIAR | $RETIDOS | $ORFAOS"

if [ -s "$ORFAOS" ] && [ "$ORPHAN_MODE" = "keep" ]; then
  log "Orfaos preservados. Revise $ORFAOS e, se forem descartaveis, rode com ARCHIVE_ORPHAN_MODE=archive."
fi

if [ ! -s "$ENVIAR" ]; then
  log "Nenhum arquivo liberado pelo portao. Nada foi enviado nem apagado."
  exit 0
fi

if [ "$DRY_RUN" = "true" ]; then
  log "DRY_RUN: nada foi enviado nem apagado."
  exit 0
fi

# ---------------------------------------------------------------------------
# 4. Lote por lote: copy -> check -> apaga SO o que a verificacao aprovou.
#
# Em lotes, e nao tudo de uma vez, para o disco comecar a ser liberado nos
# primeiros minutos. Com 30 GB numa unica passada, uma falha de rede no fim do
# upload nao libera um byte; em lotes, o que ja foi verificado ja saiu do
# disco e o proximo run continua de onde parou.
#
# A verificacao NAO derruba o lote inteiro quando um arquivo divergir. O
# `rclone check --match` escreve a lista do que casou por checksum, e so essa
# lista e apagada; o que divergiu fica no disco e entra na contagem de falhas.
# A alternativa — abortar o run no primeiro arquivo divergente — significa que
# um unico arquivo com problema bloquearia a liberacao dos outros 30 GB,
# exatamente quando o disco esta cheio. Divergencia nao deveria ser comum
# (upload truncado, arquivo alterado durante o run), mas quando acontecer o
# certo e isolar o arquivo, nao desistir do lote.
# ---------------------------------------------------------------------------
CUTOFF=$(( $(date +%s) - DIAS * 86400 ))
TOTAL_ENVIAR="$(wc -l < "$ENVIAR")"
ENVIADOS=0; APAGADOS=0; PULADOS=0; DIVERGENTES=0; NO_LOTE=0; PARAR=0
MATCH="$WORK/.lista-match.tmp"
DIFFER="$WORK/.lista-differ.tmp"
MISSING="$WORK/.lista-missing.tmp"
FALHAS="$WORK/relatorio-nao-verificados.txt"
: > "$FALHAS"

processa_lote() {
  local n rc rel caminho m
  n="$(wc -l < "$LOTE_LISTA")"
  [ "$n" -gt 0 ] || return 0

  log "Lote de $n arquivo(s): enviando..."
  set +e
  rclone copy "${RCLONE_FLAGS[@]}" --files-from "$LOTE_LISTA" "$SRC" "$REMOTE"
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    # Nao aborta: a verificacao logo abaixo e a autoridade sobre o que pode ser
    # apagado. Um copy que falhou parcialmente ainda deixou arquivos bons no
    # destino, e esses podem sair do disco.
    log "AVISO: rclone copy saiu com codigo $rc; a verificacao decide o que pode ser apagado."
    # 7 = erro fatal, o que inclui a cota diaria do Drive estourada via
    # --drive-stop-on-upload-limit. Insistir com os lotes seguintes so gera
    # erro; verifica e apaga o que ja subiu, e para depois deste lote.
    if [ "$rc" -eq 7 ]; then
      log "Erro fatal do rclone (possivel cota diaria do Drive). Parando apos este lote."
      PARAR=1
    fi
  fi

  # --one-way: basta que o que enviamos exista igual no destino; o que mais
  # houver la nao interessa.
  log "Lote: verificando checksum no destino..."
  : > "$MATCH"; : > "$DIFFER"; : > "$MISSING"
  set +e
  rclone check "${RCLONE_FLAGS[@]}" --files-from "$LOTE_LISTA" "$SRC" "$REMOTE" --one-way \
    --match "$MATCH" --differ "$DIFFER" --missing-on-dst "$MISSING"
  set -e

  local ok nao_ok
  ok="$(wc -l < "$MATCH")"
  nao_ok=$(( n - ok ))
  if [ "$nao_ok" -gt 0 ]; then
    log "AVISO: $nao_ok de $n arquivo(s) NAO verificados; ficam no disco."
    cat "$DIFFER" "$MISSING" >> "$FALHAS" 2>/dev/null || true
    DIVERGENTES=$(( DIVERGENTES + nao_ok ))
  fi
  ENVIADOS=$(( ENVIADOS + ok ))

  if [ "$ok" -eq 0 ]; then
    log "Lote: nada verificado, nada a apagar."
    : > "$LOTE_LISTA"
    NO_LOTE=0
    return 0
  fi

  # Marca archived_at ANTES do rm, e nao depois.
  #
  # E o que permite o endpoint de visualizacao responder 410 "arquivado, peca a
  # recuperacao" em vez de um 404 indistinguivel de arquivo perdido por bug
  # (api/v1/documents.py). A ordem importa: se marcar e o rm falhar, o arquivo
  # segue no disco e continua sendo servido normalmente — o endpoint resolve o
  # arquivo primeiro e so olha archived_at quando nao acha nada. O inverso
  # (apagar e falhar ao marcar) deixaria o usuario com erro generico.
  #
  # A lista vai por \copy em tabela temporaria em vez de ser interpolada num
  # IN (...): sao centenas de nomes por lote, e nome de arquivo nao deve entrar
  # em SQL por concatenacao.
  if ! {
        printf 'CREATE TEMP TABLE _arquivados (base text);\n'
        printf '\\copy _arquivados (base) FROM STDIN\n'
        sed 's#.*/##' "$MATCH"
        printf '\\.\n'
        printf 'UPDATE documents SET archived_at = now()
                WHERE regexp_replace(file_path, %s, %s) IN (SELECT base FROM _arquivados)
                  AND archived_at IS NULL;\n' "'^.*/'" "''"
      } | docker exec -i "$DB_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -q; then
    # Nao apaga sem ter marcado: o arquivo ficaria inacessivel com erro
    # generico. A copia no Drive ja existe e o proximo run re-verifica rapido e
    # tenta marcar de novo, entao pular o delete e seguro e idempotente.
    log "AVISO: falha ao marcar archived_at deste lote; os $ok arquivo(s) NAO serao apagados."
    cat "$MATCH" >> "$FALHAS"
    DIVERGENTES=$(( DIVERGENTES + ok ))
    : > "$LOTE_LISTA"
    NO_LOTE=0
    return 0
  fi

  # Segunda camada, depois do check e imediatamente antes do rm: recheca o
  # mtime. Se o arquivo foi reescrito na janela entre o check e o rm, o que
  # verificamos no Drive nao e mais o que esta no disco — e o conteudo novo
  # nunca passou por checagem humana. mtime mais novo que o corte de idade =
  # deixa quieto. Custa um stat por arquivo.
  while IFS= read -r rel; do
    caminho="$SRC/$rel"
    m="$(stat -c %Y "$caminho" 2>/dev/null)" || { PULADOS=$(( PULADOS + 1 )); continue; }
    if [ "$m" -gt "$CUTOFF" ]; then
      log "Pulado (modificado depois da listagem): $rel"
      printf '%s\n' "$rel" >> "$FALHAS"
      PULADOS=$(( PULADOS + 1 ))
      continue
    fi
    rm -f -- "$caminho" && APAGADOS=$(( APAGADOS + 1 ))
  done < "$MATCH"

  log "Progresso: $APAGADOS/$TOTAL_ENVIAR apagados, $(df -Pm "$SRC" | awk 'NR==2 {print $4}') MB livres em $SRC."
  : > "$LOTE_LISTA"
  NO_LOTE=0
}

: > "$LOTE_LISTA"
while IFS= read -r rel || [ -n "$rel" ]; do
  printf '%s\n' "$rel" >> "$LOTE_LISTA"
  NO_LOTE=$(( NO_LOTE + 1 ))
  if [ "$NO_LOTE" -ge "$LOTE" ]; then
    processa_lote
    if [ "$PARAR" -eq 1 ]; then break; fi
  fi
done < "$ENVIAR"
# Resto do ultimo lote (parcial). Nao roda se o rclone pediu parada: esses
# arquivos ficam para o proximo run.
if [ "$PARAR" -eq 0 ]; then processa_lote; fi

RETIDOS_N="$(wc -l < "$RETIDOS")"
ORFAOS_N="$(wc -l < "$ORFAOS")"
append_log "arquivamento-drive enviados=$ENVIADOS apagados=$APAGADOS pulados=$PULADOS divergentes=$DIVERGENTES retidos=$RETIDOS_N"
log "-----------------------------------------------------------------"
log "Concluido: $APAGADOS arquivo(s) arquivados e removidos do disco."
log "Permanecem: $RETIDOS_N sem checagem humana, $ORFAOS_N orfao(s), $(( DIVERGENTES + PULADOS )) nao verificado(s)."
log "Livre agora em $SRC: $(df -Pm "$SRC" | awk 'NR==2 {print $4}') MB"

# Sai diferente de zero se algo ficou para tras por falha de verificacao, para
# o alerta de job disparar (ver track_job / lib.sh) — mas so DEPOIS de ter
# liberado tudo o que era seguro liberar. Falha de verificacao precisa ser
# vista; ela nao pode custar o alivio de disco que o resto do lote daria.
if [ "$(( DIVERGENTES + PULADOS ))" -gt 0 ]; then
  log "ATENCAO: $(( DIVERGENTES + PULADOS )) arquivo(s) nao verificados. Lista: $FALHAS"
  exit 1
fi
if [ "$PARAR" -eq 1 ]; then
  log "Execucao interrompida pelo rclone antes do fim da lista. Rode de novo para continuar."
  exit 1
fi
