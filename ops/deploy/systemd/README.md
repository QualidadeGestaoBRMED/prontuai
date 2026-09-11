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
   ops/deploy/lib.sh \
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
`prontuai-archive-drive.timer` antes de seguir aquele runbook.

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

### Por que os jobs nao concorrem

Backup, purga e arquivamento compartilham um **lock com `flock`** (`db_maintenance_lock`, em
`ops/deploy/lib.sh`): quem chega depois **espera**, e o lock e liberado quando o
script termina, inclusive se ele morrer.

- backup: espera ate 1h e, se nao conseguir, **falha** — um backup diario que
  nao acontece precisa aparecer como unit falho no journal.
- purga e arquivamento: esperam ate 30min e, se nao conseguirem, **pulam** com
  aviso — sao semanais, e perder uma execucao nao tem consequencia.

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
ha 10 dias (warning), e exit code diferente de zero (warning).

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
