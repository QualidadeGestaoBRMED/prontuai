# Backup automatico do Postgres (systemd timer)

Roda `ops/deploy/backup_postgres.sh` uma vez por dia via systemd, sem depender
de crontab do usuario (sobrevive a reboot, tem logs no journal, e retry via
`Persistent=true` caso a VPS esteja desligada no horario agendado).

## Pre-requisitos

- Pasta do banco em `/home/ec2-user/prontuai-db` com `docker-compose.db.yml`
  e `.env` proprio (nao o `.env` do backend); scripts de backup/restore em
  `/home/ec2-user/prontuai-db/script/` (ajuste `EnvironmentFile`/`ExecStart`
  nos units se os caminhos forem outros).
- `.env` do banco (`/home/ec2-user/prontuai-db/.env`) com `POSTGRES_USER`,
  `POSTGRES_DB`, `BACKUP_S3_BUCKET`, `BACKUP_S3_PREFIX`, `BACKUP_S3_ENDPOINT_URL`,
  `BACKUP_S3_REGION`, `BACKUP_S3_SSE`, `BACKUP_S3_ACCESS_KEY_ID`,
  `BACKUP_S3_SECRET_ACCESS_KEY`, `BACKUP_RETENTION_DAYS` (ver `.env.example`).
- `aws` CLI instalado na VPS. Compatível com AWS S3 ou Cloudflare R2 — as
  credenciais de backup são dedicadas (`BACKUP_S3_*`), não a IAM role da
  instância nem as chaves AWS do Textract.
- Usuario do systemd unit (`ec2-user` por padrao) no grupo `docker`.

## Instalar

```bash
# copie os scripts + lib.sh para a pasta dedicada na VPS (uma vez, e de novo
# sempre que editar os scripts — nao ha CI para isso ainda):
mkdir -p /home/ec2-user/prontuai-db/script
cp ops/deploy/backup_postgres.sh ops/deploy/restore_postgres.sh \
   ops/deploy/purge_old_records.sh ops/deploy/archive_documents_to_drive.sh \
   ops/deploy/offload_backups_to_drive.sh ops/deploy/lib.sh \
  /home/ec2-user/prontuai-db/script/

sudo cp ops/deploy/systemd/prontuai-db-backup.service /etc/systemd/system/
sudo cp ops/deploy/systemd/prontuai-db-backup.timer /etc/systemd/system/
sudo cp ops/deploy/systemd/prontuai-db-purge.service /etc/systemd/system/
sudo cp ops/deploy/systemd/prontuai-db-purge.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now prontuai-db-backup.timer
sudo systemctl enable --now prontuai-db-purge.timer
```

O arquivamento no Drive tem um passo a mais (configurar o rclone e rodar o
primeiro lote a mao) e esta em `ops/deploy/arquivamento-drive.md`; nao habilite
`prontuai-archive-drive.timer` antes de seguir aquele runbook. O offload dos
backups para o Drive tambem exige um passo antes (o remote `crypt`); ver a
secao propria abaixo.

## Purga semanal (`prontuai-db-purge.timer`)

Roda domingo 02:00, uma hora antes do backup, removendo dado transitorio que
inflava todo dump diario: `jobs` finalizados (o `result_json` duplica o que ja
esta em `documents.result_payload`), notificacoes **ja lidas** antigas e
refresh tokens expirados. Nao toca em `audit_logs` nem em `documents`.

Simule antes de habilitar — nada e apagado com `PURGE_DRY_RUN`:

```bash
PURGE_DRY_RUN=true /home/ec2-user/prontuai-db/script/purge_old_records.sh
```

Janelas configuraveis por `PURGE_JOBS_DAYS` (default 7) e
`PURGE_NOTIFICATIONS_DAYS` (default 90).

## Arquivamento semanal (`prontuai-archive-drive.timer`)

Roda segunda 04:30 (depois do backup das 03:15) e envia ao Google Drive os
documentos que passaram da janela de **20 dias** *e* que já foram checados por
humano, apagando-os do disco só depois de verificar a cópia por checksum. Quem
não passou pela checagem humana **fica no disco**, por mais velho que seja.

Instalação, configuração do rclone na VPS (a parte que tem armadilha: service
account sem Shared Drive não tem cota, e `rclone.conf` criado com `sudo` vai
para `/root/` e o unit não acha) e o procedimento do primeiro run com o acervo
acumulado: **`ops/deploy/arquivamento-drive.md`**.

O primeiro run não deve ir pelo systemd — são dezenas de GB, e o
`TimeoutStartSec` mata no meio. Rode a mão num `tmux`, com `ARCHIVE_DRY_RUN=true`
antes.

Simule antes de habilitar — nada é enviado nem apagado com dry-run:

```bash
ARCHIVE_DRY_RUN=true /home/ec2-user/prontuai-db/script/archive_documents_to_drive.sh
```

Ele compartilha o mesmo `flock` do backup e da purga (ver abaixo) e, como a
purga, **pula** a execução se o backup ainda estiver rodando.

## Teto do bucket de backup (`prontuai-offload-backups.timer`)

Roda todo dia as 05:00 e mantem o bucket de backup abaixo de um teto, movendo
os dumps mais antigos para o Google Drive: acima de `OFFLOAD_TRIGGER_GB`
(default 3.5) move ate ficar abaixo de `OFFLOAD_TARGET_GB` (default 3). O teto
e de 4 GB, e o gatilho fica abaixo dele para um dump novo nao furar o teto
entre duas execucoes. Abaixo do gatilho a execucao e so um `rclone size`.

O R2 nao faz isso sozinho: lifecycle rule olha idade, nao tamanho, e nao tem
destino fora do R2.

O que sai, nesta ordem: os dumps soltos na raiz do prefixo (`legado`, gravados
por um `backup_postgres.sh` anterior a ago/2026, sem subpasta de cadencia),
depois `monthly/` e `weekly/` (`OFFLOAD_CADENCES`), do
mais antigo para o mais novo, **nunca** os 2 mais recentes de cada cadencia
(`OFFLOAD_KEEP_LATEST`), para o restore de emergencia continuar saindo do R2.
`daily/` fica de fora no default porque a lifecycle rule ja o expira. Cada dump
sai com o seu `.sha256`, e o par so e apagado do R2 depois de verificado no
destino lendo o conteudo (`cryptcheck`), nao so pelo tamanho.

### Remote `crypt` (obrigatorio)

Sao dumps completos do banco de producao, e o script recusa destino sem
criptografia (a nao ser com `OFFLOAD_ALLOW_PLAINTEXT=true`). Sobre o remote
`gdrive` do arquivamento (`ops/deploy/arquivamento-drive.md`), **sem sudo**:

```bash
# Gere as duas senhas e guarde-as NO COFRE DE SENHAS, fora da VPS. Sem elas,
# perdida a VPS, os dumps no Drive sao ilegiveis — inclusive para nos.
SENHA="$(openssl rand -base64 32)"; SAL="$(openssl rand -base64 32)"
rclone config create gdrive-crypt crypt \
  remote gdrive:prontuai/backups-postgres-v2 \
  filename_encryption off directory_name_encryption false suffix none \
  password "$SENHA" password2 "$SAL" --obscure
rclone listremotes --long          # gdrive-crypt: crypt
```

So o CONTEUDO e cifrado; o nome fica legivel no Drive
(`prontuai-AAAAMMDD-HHMMSS.dump`), para dar para achar um dump pela data sem
abrir a VPS. O nome nao carrega dado nenhum alem do instante do backup. Essas
tres opcoes nao podem ser trocadas num remote que ja tem arquivos — os nomes
antigos param de ser decifrados —, entao mudar de ideia depois exige copiar
tudo para uma pasta nova (foi o que gerou o sufixo `-v2`).

Depois, no `.env` do banco: `OFFLOAD_RCLONE_REMOTE=gdrive-crypt:`. A origem
(R2) nao precisa de entrada no `rclone.conf`: o script monta o remote a partir
das mesmas `BACKUP_S3_*` do backup.

### Instalar

```bash
OFFLOAD_DRY_RUN=true /home/ec2-user/prontuai-db/script/offload_backups_to_drive.sh

sudo cp ops/deploy/systemd/prontuai-offload-backups.service /etc/systemd/system/
sudo cp ops/deploy/systemd/prontuai-offload-backups.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now prontuai-offload-backups.timer
```

### Restaurar um dump que foi para o Drive

`restore_postgres.sh` le `s3://` ou caminho local, nao o Drive. Baixe antes (o
`crypt` decifra no caminho):

```bash
rclone lsf gdrive-crypt:monthly/
rclone copy gdrive-crypt:monthly/prontuai-AAAAMMDD-HHMMSS.dump /tmp/restore/
rclone copy gdrive-crypt:monthly/prontuai-AAAAMMDD-HHMMSS.dump.sha256 /tmp/restore/
cd /tmp/restore && [ "$(sha256sum prontuai-*.dump | cut -d' ' -f1)" = "$(cat prontuai-*.dump.sha256)" ] && echo OK
/home/ec2-user/prontuai-db/script/restore_postgres.sh /tmp/restore/prontuai-AAAAMMDD-HHMMSS.dump
```

### Por que os jobs nao concorrem

Backup, purga, arquivamento e offload compartilham um **lock com `flock`** (`db_maintenance_lock`, em
`ops/deploy/lib.sh`): quem chega depois **espera**, e o lock e liberado quando o
script termina, inclusive se ele morrer.

- backup: espera ate 1h e, se nao conseguir, **falha** — um backup diario que
  nao acontece precisa aparecer como unit falho no journal.
- purga, arquivamento e offload: esperam ate 30min e, se nao conseguirem,
  **pulam** com aviso — perder uma execucao nao tem consequencia (o offload
  tem folga entre o gatilho e o teto justamente para isso).

Ajustaveis por `DB_LOCK_WAIT`; o arquivo de lock, por `DB_LOCK_FILE`.

Isso **substituiu** um `Conflicts=prontuai-db-backup.service` que existia no
unit da purga. `Conflicts` e bidirecional e da terminacao mutua, nao exclusao
mutua: iniciar um **para** o outro. Com `Persistent=true` nos dois timers, um
reboot que atrase ambos dispara as duas recuperacoes de horario, e uma mataria a
outra — `pg_dump` morto no meio significa o backup do dia perdido. O `flock`
tambem cobre execucao manual dos scripts, que o unit nao alcancaria.

## Monitorar os jobs

Os scripts reportam o proprio resultado para o coletor OTel na saida, via
`track_job` (ver `ops/deploy/lib.sh`). Basta acrescentar ao `.env` do banco
(`/home/ec2-user/prontuai-db/.env`), que os units ja carregam via
`EnvironmentFile`:

```
JOBS_OTLP_ENDPOINT=https://brmed-otel-collector.duckdns.org
JOBS_OTLP_TOKEN='<mesmo token do coletor>'
```

Sem essas variaveis os scripts rodam normalmente e so registram no log que nao
reportaram — telemetria nunca derruba a tarefa que observa.

### Por que o alerta e sobre idade, e nao sobre erro

Tres metricas sao emitidas, e a que importa e `job_last_success_timestamp_seconds`,
escrita **so em sucesso**. O alerta compara a IDADE dela
(`time() - metrica > limite`), o que pega o que exit code nao pega: timer que
nunca disparou, script travado, maquina desligada. Um job que simplesmente
para de rodar e invisivel para alerta baseado em falha — foi assim que o
collector do postgres_exporter ficou 18 dias quebrado com `pg_up` em 1.

Os alertas correspondentes estao em `otel/grafana/provisioning/alerting/alerts.yml`:
backup sem sucesso ha 26h (critical), purga ha 9 dias (warning), arquivamento
ha 10 dias (warning), offload dos backups ha 3 dias (warning), e exit code
diferente de zero (warning). O offload sai com codigo 1 quando algum dump nao
passou na verificacao ou quando nao ha elegiveis suficientes para voltar abaixo
do gatilho — nos dois casos o bucket segue crescendo e alguem precisa olhar.

`noDataState: Alerting` nos dois primeiros e proposital: se o job nunca
reportou, a serie nem existe, e "sem dado" e exatamente o alarme desejado.

### Para um script novo

```bash
source "$SCRIPT_DIR/lib.sh"
track_job "nome-do-job"      # instala o trap; nada mais e preciso
```

O atributo se chama `task`, nao `job`: o exporter Prometheus do coletor ja cria
um label `job` a partir do `service.name`, e um atributo homonimo faz a metrica
ser descartada em silencio (HTTP 200, `partialSuccess` vazio, so o log do
coletor acusa).

## Verificar

```bash
systemctl list-timers prontuai-db-backup.timer
sudo systemctl start prontuai-db-backup.service   # roda uma vez agora, fora do horario
journalctl -u prontuai-db-backup.service -n 50 --no-pager
```

## Retencao no bucket

O script cuida da retencao local (`BACKUP_RETENTION_DAYS`), mas o bucket
tambem deve ter uma lifecycle rule configurada (painel do R2/console AWS) para
expirar objetos antigos no prefixo de backup — o script nao apaga nada remoto.
Sugestao: expirar objetos com mais de `BACKUP_RETENTION_DAYS` dias, e manter
versionamento do bucket ligado como rede de seguranca contra delete acidental
(R2 suporta versionamento de bucket).
