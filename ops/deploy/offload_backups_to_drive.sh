#!/usr/bin/env bash
# Mantem o bucket de backup (Cloudflare R2 / S3) abaixo de um teto de tamanho,
# movendo os dumps mais antigos para o Google Drive.
#
# Por que um script, e nao uma regra no Cloudflare: as lifecycle rules do R2 so
# olham a IDADE do objeto (expirar ou ir para Infrequent Access); nao existe
# gatilho por tamanho do bucket nem destino fora do R2. Event Notifications ->
# Worker dispara por objeto, nao por total acumulado, e um Worker subindo dumps
# de centenas de MB ao Drive esbarra nos limites de memoria/CPU dele.
#
# Histerese: dispara acima de OFFLOAD_TRIGGER_GB e move ate ficar abaixo de
# OFFLOAD_TARGET_GB. Sem a folga entre os dois, o bucket encostaria no gatilho
# todo dia e o script moveria um dump por execucao.
#
# O que sai do R2, nesta ordem:
#   1. as cadencias de OFFLOAD_CADENCES, na ordem dada (default: legado monthly weekly);
#   2. dentro de cada uma, do dump mais antigo para o mais novo;
#   3. NUNCA os OFFLOAD_KEEP_LATEST mais recentes de cada cadencia — o restore
#      de emergencia tem que continuar saindo do R2, sem depender do Drive.
#
# Por que daily/ fica de fora no default: o backup_postgres.sh conta com uma
# lifecycle rule expirando daily/ em ~30 dias. Mover um diario para o Drive o
# tornaria eterno (o Drive nao tem lifecycle) por um dado que ia sumir de
# qualquer forma. monthly/ e o que cresce sem limite (retencao infinita), e e
# por isso que vem antes de weekly/.
#
# `legado` sao os dumps soltos na raiz do prefixo, sem subpasta de cadencia:
# tudo o que um backup_postgres.sh anterior a separacao daily/weekly/monthly
# (ago/2026) gravou. Sao dumps completos e nenhuma lifecycle rule por
# subpasta os alcanca, entao vem primeiro. Quando a VPS roda o backup atual,
# a raiz para de receber arquivos e esse balde so encolhe.
#
# Cada dump sai junto com o seu .sha256. O par so e apagado do R2 se os DOIS
# arquivos foram verificados no destino; um .sha256 orfao no R2 nao custa
# nada, um dump sem checksum no Drive e um dump que ninguem consegue validar.
#
# Fluxo (lote unico — sao poucos arquivos grandes, nao milhares de pequenos):
#     rclone copy -> verificacao lendo o conteudo -> so entao apaga do R2
#
# CRIPTOGRAFIA: sao dumps COMPLETOS do banco de producao (CPF, nome de
# paciente, laudos). O script exige que OFFLOAD_RCLONE_REMOTE seja um remote
# `crypt` do rclone, e recusa um `drive` puro a menos que
# OFFLOAD_ALLOW_PLAINTEXT=true. Ver o runbook em ops/deploy/systemd/README.md
# — e guarde a senha do crypt FORA da VPS: perdida a VPS sem a senha, os dumps
# no Drive sao lixo.
#
# RESTORE: restore_postgres.sh le s3:// ou caminho local, nao o Drive. Para
# restaurar um dump movido, baixe antes:
#     rclone copy gdrive-crypt:monthly/prontuai-XXXX.dump /tmp/restore/
#     ./restore_postgres.sh /tmp/restore/prontuai-XXXX.dump
#
# Uso:
#   OFFLOAD_DRY_RUN=true ./ops/deploy/offload_backups_to_drive.sh   # so relata
#   ./ops/deploy/offload_backups_to_drive.sh                        # aplica
#
# Variaveis:
#   OFFLOAD_RCLONE_REMOTE    destino, ex.: gdrive-crypt:  (OBRIGATORIA)
#   OFFLOAD_TRIGGER_GB       dispara acima deste total no bucket (default 3.5)
#   OFFLOAD_TARGET_GB        move ate ficar abaixo deste (default 3)
#   OFFLOAD_CADENCES         cadencias elegiveis, em ordem (default "legado monthly weekly")
#   OFFLOAD_KEEP_LATEST      dumps mais recentes preservados por cadencia (default 2)
#   OFFLOAD_ALLOW_PLAINTEXT  "true" aceita destino sem crypt (default false)
#   OFFLOAD_RCLONE_FLAGS     flags extras do rclone
#   OFFLOAD_WORK_DIR         listas e relatorios (default /home/ec2-user/prontuai-db/offload-tmp)
#   OFFLOAD_DRY_RUN          "true" nao envia e nao apaga (default false)
#   OFFLOAD_SOURCE_ROOT      raiz do bucket como caminho rclone (default: remote
#                            montado a partir de BACKUP_S3_*; util para teste local)
#   BACKUP_S3_BUCKET, BACKUP_S3_PREFIX, BACKUP_S3_ENDPOINT_URL, BACKUP_S3_REGION,
#   BACKUP_S3_ACCESS_KEY_ID, BACKUP_S3_SECRET_ACCESS_KEY
#                            as mesmas do backup_postgres.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

# As contas de GB passam por awk: em locale pt_BR ele imprime "3,80" e o log
# fica ambiguo com separador de milhar.
export LC_NUMERIC=C

DB_DEPLOY_DIR="${DB_DEPLOY_DIR:-/home/ec2-user/prontuai-db}"
carregar_env_do_banco "$DB_DEPLOY_DIR/.env"

REMOTE="${OFFLOAD_RCLONE_REMOTE:-}"
GATILHO_GB="${OFFLOAD_TRIGGER_GB:-3.5}"
ALVO_GB="${OFFLOAD_TARGET_GB:-3}"
CADENCIAS="${OFFLOAD_CADENCES:-legado monthly weekly}"
MANTER="${OFFLOAD_KEEP_LATEST:-2}"
PERMITIR_SEM_CRYPT="${OFFLOAD_ALLOW_PLAINTEXT:-false}"
WORK="${OFFLOAD_WORK_DIR:-$DB_DEPLOY_DIR/offload-tmp}"
DRY_RUN="${OFFLOAD_DRY_RUN:-false}"
PREFIXO="${BACKUP_S3_PREFIX:-postgres-backups/prontuai}"

# --transfers=2: sao poucos arquivos grandes; mais paralelismo so disputa banda
# da VPS. --drive-stop-on-upload-limit para (sem apagar nada) se a cota diaria
# do Drive estourar. Vale tambem atras de um crypt: flag de backend se aplica a
# todo remote daquele tipo, inclusive o drive embaixo do crypt.
OFFLOAD_RCLONE_FLAGS="${OFFLOAD_RCLONE_FLAGS:---transfers=2 --retries=5 --low-level-retries=20 --drive-stop-on-upload-limit}"
read -r -a RCLONE_FLAGS <<< "$OFFLOAD_RCLONE_FLAGS"

require_cmd rclone awk sort
[ -n "$REMOTE" ] || die "OFFLOAD_RCLONE_REMOTE nao definida (ex.: gdrive-crypt:)."
case "$REMOTE" in *:*) ;; *) die "OFFLOAD_RCLONE_REMOTE precisa ser um remote rclone (nome:caminho), recebi: $REMOTE" ;; esac
awk -v t="$GATILHO_GB" -v a="$ALVO_GB" 'BEGIN { exit !(t+0 > 0 && a+0 > 0 && a+0 < t+0) }' \
  || die "OFFLOAD_TARGET_GB ($ALVO_GB) tem que ser positivo e menor que OFFLOAD_TRIGGER_GB ($GATILHO_GB)."
case "$MANTER" in ''|*[!0-9]*) die "OFFLOAD_KEEP_LATEST invalido: $MANTER" ;; esac
[ "$MANTER" -ge 1 ] || die "OFFLOAD_KEEP_LATEST tem que ser >= 1: o restore de emergencia sai do R2."
for c in $CADENCIAS; do
  case "$c" in legado|daily|weekly|monthly) ;; *) die "Cadencia invalida em OFFLOAD_CADENCES: $c" ;; esac
done

# ---------------------------------------------------------------------------
# Origem: o bucket do backup, como remote rclone montado por variavel de
# ambiente — sem entrada no rclone.conf e reaproveitando as credenciais
# BACKUP_S3_* que o backup ja usa. Variavel de ambiente, e nao string de
# conexao na linha de comando, para o secret nao aparecer no `ps`.
# ---------------------------------------------------------------------------
if [ -n "${OFFLOAD_SOURCE_ROOT:-}" ]; then
  RAIZ="$OFFLOAD_SOURCE_ROOT"
else
  [ -n "${BACKUP_S3_BUCKET:-}" ] || die "BACKUP_S3_BUCKET nao definido; nao ha bucket para medir."
  case "${BACKUP_S3_ENDPOINT_URL:-}" in
    *r2.cloudflarestorage.com*) PROVEDOR=Cloudflare ;;
    "")                         PROVEDOR=AWS ;;
    *)                          PROVEDOR=Other ;;
  esac
  export RCLONE_CONFIG_PRONTUAIBACKUP_TYPE=s3
  export RCLONE_CONFIG_PRONTUAIBACKUP_PROVIDER="$PROVEDOR"
  export RCLONE_CONFIG_PRONTUAIBACKUP_ACCESS_KEY_ID="${BACKUP_S3_ACCESS_KEY_ID:?BACKUP_S3_ACCESS_KEY_ID is required}"
  export RCLONE_CONFIG_PRONTUAIBACKUP_SECRET_ACCESS_KEY="${BACKUP_S3_SECRET_ACCESS_KEY:?BACKUP_S3_SECRET_ACCESS_KEY is required}"
  export RCLONE_CONFIG_PRONTUAIBACKUP_REGION="${BACKUP_S3_REGION:-auto}"
  # Credencial de bucket unico costuma nao ter permissao de listar/criar
  # buckets; sem isto o rclone tenta checar o bucket e falha com 403.
  export RCLONE_CONFIG_PRONTUAIBACKUP_NO_CHECK_BUCKET=true
  if [ -n "${BACKUP_S3_ENDPOINT_URL:-}" ]; then
    export RCLONE_CONFIG_PRONTUAIBACKUP_ENDPOINT="$BACKUP_S3_ENDPOINT_URL"
  fi
  RAIZ="prontuaibackup:$BACKUP_S3_BUCKET"
fi
BASE="${RAIZ%/}/$PREFIXO"

# ---------------------------------------------------------------------------
# Destino: crypt obrigatorio, e o tipo define como verificar.
#
# Nem o `check` padrao serve aqui. O backup sobe com `aws s3 cp`, que usa
# multipart acima de 8 MB, e objeto multipart nao tem MD5 no S3/R2: o check
# cairia em comparar so tamanho, com um aviso que ninguem le no journal. Os
# dois caminhos abaixo leem o CONTEUDO:
#   crypt -> cryptcheck: le a origem, cifra com o nonce do arquivo remoto e
#            compara com o hash que o Drive guarda;
#   drive -> check --download: baixa os dois lados e compara byte a byte.
# Custa reler os dumps (egress do R2 e gratuito); e a diferenca entre "confio
# que subiu" e "verifiquei que subiu", antes de apagar a unica outra copia.
# ---------------------------------------------------------------------------
NOME_REMOTE="${REMOTE%%:*}"
TIPO_REMOTE="$(rclone listremotes --long 2>/dev/null | awk -v n="$NOME_REMOTE:" '$1 == n { print $2 }')"
[ -n "$TIPO_REMOTE" ] || die "Remote '$NOME_REMOTE' nao existe no rclone.conf de $(id -un).
  Configurou com sudo? O arquivo foi para /root/ e o unit (que roda como ec2-user) nao o ve."
if [ "$TIPO_REMOTE" = "crypt" ]; then
  VERIFICAR=(cryptcheck)
elif [ "$PERMITIR_SEM_CRYPT" = "true" ]; then
  log "AVISO: destino '$NOME_REMOTE' e do tipo '$TIPO_REMOTE', SEM criptografia (OFFLOAD_ALLOW_PLAINTEXT=true)."
  VERIFICAR=(check --download)
else
  die "Destino '$NOME_REMOTE' e do tipo '$TIPO_REMOTE', nao 'crypt'. Sao dumps completos do banco de
  producao; crie um remote crypt sobre o Drive (ver ops/deploy/systemd/README.md) ou, ciente do
  risco, rode com OFFLOAD_ALLOW_PLAINTEXT=true."
fi

track_job "offload-backups-drive"
# Nao toca no banco, mas nao deve mover nada enquanto o backup do dia ainda
# esta subindo: espera e, se nao der, PULA — roda de novo amanha.
db_maintenance_lock "${DB_LOCK_WAIT:-1800}" skip

mkdir -p "$WORK"
CANDIDATOS="$WORK/.lista-candidatos.tmp"   # bytes<TAB>dump<TAB>sha256 (caminhos relativos a BASE)
ENVIAR="$WORK/lista-enviar.txt"
PARES="$WORK/.lista-pares.tmp"
MATCH="$WORK/.lista-match.tmp"
DIFFER="$WORK/.lista-differ.tmp"
MISSING="$WORK/.lista-missing.tmp"
APAGAR="$WORK/.lista-apagar.tmp"
FALHAS="$WORK/relatorio-nao-verificados.txt"

# GB decimal (10^9), nao GiB: e a unidade em que o Cloudflare cobra e exibe
# o uso, e o lado conservador — 3.5 GB disparam antes de 3.5 GiB.
gb_para_bytes() { awk -v g="$1" 'BEGIN { printf "%.0f", g * 1000000000 }'; }
bytes_para_gb() { awk -v b="$1" 'BEGIN { printf "%.2f", b / 1000000000 }'; }

medir_bucket() {
  local saida
  saida="$(rclone size "${RCLONE_FLAGS[@]}" --json "$RAIZ")" || return 1
  printf '%s' "$saida" | sed -n 's/.*"bytes":\([0-9]*\).*/\1/p'
}

GATILHO="$(gb_para_bytes "$GATILHO_GB")"
ALVO="$(gb_para_bytes "$ALVO_GB")"

log "Origem:  $BASE"
log "Destino: $REMOTE (tipo $TIPO_REMOTE)"
log "Gatilho: ${GATILHO_GB} GB | alvo: ${ALVO_GB} GB | cadencias: $CADENCIAS | preserva: $MANTER por cadencia$([ "$DRY_RUN" = "true" ] && echo " | DRY_RUN")"

# Mede o bucket INTEIRO, nao so o prefixo do backup: o teto e do bucket.
TOTAL="$(medir_bucket)" || die "Nao consegui medir o bucket ($RAIZ). Credenciais/endpoint?"
[ -n "$TOTAL" ] || die "rclone size nao devolveu o total em bytes."
log "Bucket: $(bytes_para_gb "$TOTAL") GB."

if [ "$TOTAL" -le "$GATILHO" ]; then
  log "Abaixo do gatilho. Nada a fazer."
  exit 0
fi
PRECISA=$(( TOTAL - ALVO ))
log "Acima do gatilho: liberar ao menos $(bytes_para_gb "$PRECISA") GB."

# ---------------------------------------------------------------------------
# 1. Candidatos, por cadencia e do mais antigo para o mais novo.
#
# A ordem vem do NOME (prontuai-AAAAMMDD-HHMMSS.dump, em UTC), e nao do mtime
# do objeto: o nome e o instante do dump; o mtime e o do upload, que muda se
# alguem copiar o objeto de novo.
# ---------------------------------------------------------------------------
: > "$CANDIDATOS"
for c in $CADENCIAS; do
  # legado = raiz do prefixo. --files-only sem -R lista so o nivel da pasta,
  # entao as subpastas de cadencia nao entram aqui.
  if [ "$c" = "legado" ]; then dir="$BASE"; rel=""; else dir="$BASE/$c"; rel="$c/"; fi
  # Prefixo inexistente (ainda nao houve um weekly, p.ex.) lista vazio no S3,
  # mas da erro em outros backends; com pipefail, o erro derrubaria o script
  # calado. O acesso ao bucket ja foi provado pelo `rclone size` acima, entao
  # falha aqui e tratada como pasta vazia, com aviso.
  if ! listagem="$(rclone lsf "${RCLONE_FLAGS[@]}" --files-only --format "sp" --separator $'\t' "$dir" 2>/dev/null)"; then
    log "AVISO: nao consegui listar $dir; tratando como vazia."
    listagem=""
  fi
  printf '%s\n' "$listagem" | sed '/^$/d' \
  | awk -F'\t' -v rel="$rel" -v manter="$MANTER" '
      { tam[$2] = $1 }
      $2 ~ /^prontuai-[0-9]{8}-[0-9]{6}\.dump$/ { dumps[++n] = $2 }
      END {
        # lsf ja lista em ordem, mas nao por contrato: ordena aqui.
        for (i = 2; i <= n; i++) {
          v = dumps[i]
          for (j = i - 1; j >= 1 && dumps[j] > v; j--) dumps[j + 1] = dumps[j]
          dumps[j + 1] = v
        }
        for (i = 1; i <= n - manter; i++) {
          d = dumps[i]; s = d ".sha256"
          bytes = tam[d] + ((s in tam) ? tam[s] : 0)
          printf "%d\t%s%s\t%s\n", bytes, rel, d, ((s in tam) ? rel s : "")
        }
      }' >> "$CANDIDATOS"
done

# ---------------------------------------------------------------------------
# 2. Pega candidatos em ordem ate cobrir o que precisa liberar.
# ---------------------------------------------------------------------------
: > "$ENVIAR"; : > "$PARES"
LIBERA=0; N_DUMPS=0
while IFS=$'\t' read -r bytes dump sha || [ -n "${bytes:-}" ]; do
  [ "$LIBERA" -lt "$PRECISA" ] || break
  printf '%s\n' "$dump" >> "$ENVIAR"
  [ -n "$sha" ] && printf '%s\n' "$sha" >> "$ENVIAR"
  printf '%s\t%s\n' "$dump" "$sha" >> "$PARES"
  LIBERA=$(( LIBERA + bytes )); N_DUMPS=$(( N_DUMPS + 1 ))
done < "$CANDIDATOS"

log "-----------------------------------------------------------------"
log "Elegiveis : $(wc -l < "$CANDIDATOS") dump(s) fora dos $MANTER mais recentes de cada cadencia"
log "A mover   : $N_DUMPS dump(s), $(bytes_para_gb "$LIBERA") GB"
log "Lista     : $ENVIAR"
log "-----------------------------------------------------------------"

INSUFICIENTE=0
if [ "$LIBERA" -lt "$PRECISA" ]; then
  INSUFICIENTE=1
  log "AVISO: os elegiveis nao bastam para chegar a ${ALVO_GB} GB. Opcoes: incluir daily em"
  log "  OFFLOAD_CADENCES, baixar OFFLOAD_KEEP_LATEST, ou revisar o que mais ocupa o bucket."
fi

if [ "$N_DUMPS" -eq 0 ]; then
  log "Nenhum dump elegivel. Nada foi enviado nem apagado."
  exit 1   # acima do gatilho e sem saida: o alerta do job tem que disparar
fi

if [ "$DRY_RUN" = "true" ]; then
  sed 's/^/  /' "$ENVIAR"
  log "DRY_RUN: nada foi enviado nem apagado."
  exit 0
fi

# ---------------------------------------------------------------------------
# 3. copy -> verificacao -> apaga do R2 SO os pares verificados.
#
# --files-from com caminhos relativos a BASE faz o Drive espelhar a arvore
# do bucket (monthly/..., weekly/...), entao o caminho de restore e obvio.
# ---------------------------------------------------------------------------
log "Enviando..."
set +e
rclone copy "${RCLONE_FLAGS[@]}" --files-from "$ENVIAR" "$BASE" "$REMOTE"
rc=$?
set -e
# Nao aborta: a verificacao e a autoridade sobre o que pode ser apagado, e o
# que subiu inteiro antes de uma falha parcial pode sair do R2.
[ "$rc" -eq 0 ] || log "AVISO: rclone copy saiu com codigo $rc; a verificacao decide o que pode ser apagado."

log "Verificando conteudo no destino (${VERIFICAR[*]})..."
: > "$MATCH"; : > "$DIFFER"; : > "$MISSING"
set +e
rclone "${VERIFICAR[@]}" "${RCLONE_FLAGS[@]}" --files-from "$ENVIAR" "$BASE" "$REMOTE" --one-way \
  --match "$MATCH" --differ "$DIFFER" --missing-on-dst "$MISSING"
set -e

# Par completo ou nada.
awk -F'\t' -v match_f="$MATCH" '
  BEGIN { while ((getline l < match_f) > 0) ok[l] = 1 }
  ($1 in ok) && ($2 == "" || ($2 in ok)) { print $1; if ($2 != "") print $2 }
' "$PARES" > "$APAGAR"

N_APAGAR_DUMPS="$(grep -c '\.dump$' "$APAGAR" || true)"
NAO_VERIFICADOS=$(( N_DUMPS - N_APAGAR_DUMPS ))
: > "$FALHAS"
if [ "$NAO_VERIFICADOS" -gt 0 ]; then
  cat "$DIFFER" "$MISSING" > "$FALHAS" 2>/dev/null || true
  log "AVISO: $NAO_VERIFICADOS dump(s) NAO verificados; ficam no R2. Lista: $FALHAS"
fi

if [ -s "$APAGAR" ]; then
  log "Apagando do R2 $N_APAGAR_DUMPS dump(s) verificados no destino..."
  rclone delete "${RCLONE_FLAGS[@]}" --files-from "$APAGAR" "$BASE" \
    || die "rclone delete falhou. As copias no Drive estao verificadas; rode de novo para concluir."
else
  log "Nada verificado, nada apagado."
fi

DEPOIS="$(medir_bucket || echo "")"
append_log "offload-backups-drive movidos=$N_APAGAR_DUMPS nao_verificados=$NAO_VERIFICADOS bucket_antes=$TOTAL bucket_depois=${DEPOIS:-?}"
log "-----------------------------------------------------------------"
log "Concluido: $N_APAGAR_DUMPS dump(s) movidos para $REMOTE."
[ -n "$DEPOIS" ] && log "Bucket: $(bytes_para_gb "$TOTAL") GB -> $(bytes_para_gb "$DEPOIS") GB."

# Sai diferente de zero quando algo ficou pendente, para o alerta do job
# disparar — mas so depois de ter liberado o que era seguro liberar.
if [ "$NAO_VERIFICADOS" -gt 0 ] || [ "$rc" -ne 0 ]; then
  exit 1
fi
if [ -n "$DEPOIS" ] && [ "$DEPOIS" -gt "$GATILHO" ]; then
  log "ATENCAO: o bucket segue acima do gatilho (${GATILHO_GB} GB)."
  exit 1
fi
[ "$INSUFICIENTE" -eq 0 ] || log "AVISO: abaixo do gatilho, mas nao do alvo (${ALVO_GB} GB)."
