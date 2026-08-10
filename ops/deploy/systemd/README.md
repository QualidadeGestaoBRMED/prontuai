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
cp ops/deploy/backup_postgres.sh ops/deploy/restore_postgres.sh ops/deploy/lib.sh \
  /home/ec2-user/prontuai-db/script/

sudo cp ops/deploy/systemd/prontuai-db-backup.service /etc/systemd/system/
sudo cp ops/deploy/systemd/prontuai-db-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now prontuai-db-backup.timer
```

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
