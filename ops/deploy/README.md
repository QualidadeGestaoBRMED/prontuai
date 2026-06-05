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
