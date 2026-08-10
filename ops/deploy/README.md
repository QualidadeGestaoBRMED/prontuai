# Deploy Runbook Automation (Backend)

Automacao das fases do runbook para reduzir passos manuais.
Os scripts assumem o backend em Docker e geram artefatos em `/tmp`.

## Ordem de execucao

```bash
./ops/deploy/00_precheck.sh
./ops/deploy/10_prepare_staging.sh
./ops/deploy/20_up_staging.sh
# validar funcionalmente em localhost:8080
./ops/deploy/30_pin_prod_image.sh
./ops/deploy/40_go_live.sh
```

## Rollback

```bash
./ops/deploy/50_rollback.sh
```

## Banco de dados (Postgres self-hosted na VPS)

O Postgres roda numa **pasta propria na VPS**, `/home/ec2-user/prontuai-db`
(com `docker-compose.db.yml` + `.env` proprio + `pgdata/`), **separada** da
pasta do backend (`/home/ec2-user/prontuai`) e da pasta de scripts
(`/home/ec2-user/prontuai-db/script/`), de proposito: nada neste README
(deploy, rollback, panic-restore do backend) toca no banco. Ele so sobe/desce
com um comando explicito `docker compose -f docker-compose.db.yml ...`
rodado de dentro de `/home/ec2-user/prontuai-db`. Ver `ops/deploy/aws-vps-ghcr.md`
para o provisionamento inicial e a copia manual desses arquivos (nao ha CI
para essa pasta ainda).

Migracao unica de Neon para o container `prontuai-db` (mesma VPS do backend).
Os caminhos das duas pastas de deploy tem default certo para a VPS atual;
so precisam ser passados se voce usar outros caminhos:

```bash
NEON_DATABASE_URL='postgresql://...' /home/ec2-user/prontuai-db/script/60_migrate_neon_to_ec2.sh
```

Causa uma janela de manutencao curta (para o backend antes de dumpar o Neon,
para garantir consistencia). Reverte automaticamente se as contagens pos-restore
nao baterem ou se o health check pos-cutover falhar.

Backup diario continuo e restore/drill (rodados de dentro de
`/home/ec2-user/prontuai-db/script/`):

```bash
./backup_postgres.sh                                   # roda manual/via systemd, ver systemd/README.md
./restore_postgres.sh s3://bucket/prefixo/arquivo.dump # drill seguro (banco descartavel)
```

## Variaveis uteis

- `WORKTREE_DIR` (default: `.worktrees/prontuai-stg`)
- `STAGING_BRANCH` (default: `staging`)
- `STAGING_PROJECT` (default: `prontuai_stg`)
- `STAGING_OVERRIDE_FILE` (default: `/tmp/prontuai-stg.override.yml`)
- `STAGING_COMPOSE_FILE` (default: `/tmp/prontuai-stg.compose.yml`)
- `PROD_PIN_FILE` (default: `/tmp/prontuai-prod.pin.yml`)
- `BASELINE_IMAGE_FILE` (default: `/tmp/prontuai-baseline.image`)
- `LOG_FILE` (default: `/tmp/prontuai-release-YYYYMMDD.log`)
- `CHECK_PUBLIC_HEALTH` (default: `1`)
- `PUBLIC_HEALTH_URL` (default: `https://api.prontuai.grupobrmed.com.br/health`)

## Observacoes

- Fluxo esperado de branches: `dev -> staging -> v1`.
- `dev` e branches de trabalho podem seguir seu padrao normal de commits como `chore`, `fix` e `feat`; isso nao deve ser usado no nome da branch `staging`.
- `10_prepare_staging.sh` gera `.env.stg` com `DATABASE_URL` placeholder de seguranca.
- `10_prepare_staging.sh` tambem gera um compose dedicado de staging sem bind na porta 80.
- Antes de subir staging, ajuste `DATABASE_URL` da `.env.stg` para o banco de homologacao.
- `40_go_live.sh` causa downtime breve (stop/start do container produtivo).
