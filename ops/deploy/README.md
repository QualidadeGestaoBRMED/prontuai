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

## Staging na VPS sem GitHub Actions

Quando a cota do Actions estoura (ou o workflow esta indisponivel),
`deploy_staging_vps.sh` faz o que o `backend-ghcr-staging-deploy.yml` faz:

```bash
STAGING_HOST=1.2.3.4 ./ops/deploy/deploy_staging_vps.sh
STAGING_HOST=1.2.3.4 ./ops/deploy/deploy_staging_vps.sh --ref staging --skip-tests
```

Duas diferencas em relacao ao workflow, ambas deliberadas:

- **Builda na VPS**, arm64 nativo, em vez de emular aarch64 com QEMU num runner
  amd64. Sem registry no caminho, entao nao precisa de PAT do GHCR.
- **Envia o conteudo de um commit** (`git archive`), nao a arvore de trabalho.
  Nada de `.env`, `__pycache__`, log ou compose local vaza para o servidor — por
  construcao. O script avisa e pede confirmacao se houver alteracao em
  `back-end/` que nao entrara no deploy.

Roda os mesmos testes do CI antes de subir (`--skip-tests` para pular), grava
`.current_backend_image` na VPS e, se o health check falhar, **reverte sozinho**
para a imagem anterior. O `.current_backend_image` nao e sobrescrito por um
deploy que falhou, entao o ponto de rollback continua valido.

Nao faz dump do banco: staging tem Postgres proprio e descartavel. Producao
continua pelo runbook numerado acima, que trata disso.

> O `/health` do backend e estatico — responde 200 sem tocar em banco. Health
> check verde nao substitui olhar o log do container (o script imprime o comando)
> e exercitar um endpoint `/v1/` autenticado. Lembre que `auto_migrate()` roda no
> startup, e voltar a imagem nao desfaz mudanca de schema.

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
./purge_old_records.sh                                 # purga semanal; PURGE_DRY_RUN=true para simular
```

### Cadencia dos dumps e retencao no bucket

O `backup_postgres.sh` escolhe a cadencia pela data e grava em subprefixos
distintos, para que cada faixa tenha sua propria regra de expiracao:

| Prefixo    | Quando        | Escopo           | Retencao sugerida |
|------------|---------------|------------------|-------------------|
| `monthly/` | dia 1 do mes  | completo         | nunca expira      |
| `weekly/`  | domingo       | completo         | 90 dias           |
| `daily/`   | demais dias   | sem `audit_logs` | 30 dias           |

`audit_logs` cresce ~1.150 linhas por dia util (~23 MB/mes) e nao muda depois
de escrita. Mante-la no dump diario custaria reenviar o mesmo dado 365 vezes
por ano. Ficando so no semanal e no mensal, a auditoria continua integralmente
preservada (expostos no maximo 7 dias), enquanto o dado operacional mantem RPO
de 24 h.

As regras de expiracao **nao sao criadas pelo script** — configure no bucket.
No R2, em Settings > Object lifecycle rules, uma regra por prefixo. Via CLI:

```bash
aws s3api put-bucket-lifecycle-configuration --bucket <bucket> \
  --endpoint-url https://<account_id>.r2.cloudflarestorage.com \
  --lifecycle-configuration '{
    "Rules": [
      {"ID":"daily-30d","Status":"Enabled",
       "Filter":{"Prefix":"postgres-backups/prontuai/daily/"},
       "Expiration":{"Days":30}},
      {"ID":"weekly-90d","Status":"Enabled",
       "Filter":{"Prefix":"postgres-backups/prontuai/weekly/"},
       "Expiration":{"Days":90}}
    ]}'
```

`monthly/` fica de fora de proposito: sem regra, nada expira.

> Os anexos do PGR ficam em **bucket separado**, entao estas regras nao
> alcancam dado de outra aplicacao. A **cota do R2 e da conta**, nao do
> bucket: o free tier de 10 GB e somado entre os dois, e foi por isso que a
> pressao apareceu. Ao dimensionar retencao, considere o uso do PGR tambem:
>
> ```bash
> aws s3 ls --summarize --human-readable --recursive s3://<bucket> \
>   --endpoint-url https://<account_id>.r2.cloudflarestorage.com | tail -2
> ```

Para gerar um completo sob demanda (antes de uma migracao, por exemplo):

```bash
BACKUP_CADENCE_OVERRIDE=monthly ./backup_postgres.sh
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
