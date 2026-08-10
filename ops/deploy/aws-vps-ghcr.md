# Deploy Backend na VPS AWS Fedora com GHCR

Este fluxo substitui build local/git clone na VPS por imagem publicada no GHCR via GitHub Actions.

## Visao geral

1. GitHub Actions roda testes focados do backend.
2. GitHub Actions constrói `back-end/Dockerfile`.
3. A imagem é publicada em `ghcr.io/<owner>/prontuai-backend`.
4. A VPS recebe `docker-compose.yml`, faz `docker compose pull` e sobe o container.

## Pré-requisitos na VPS Fedora

Instalar Docker e Compose plugin:

```bash
sudo dnf -y install dnf-plugins-core
sudo dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
sudo dnf -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Depois faça logout/login para o grupo `docker` valer.

Criar diretório do deploy:

```bash
sudo mkdir -p /opt/prontuai/back-end
sudo chown -R "$USER":"$USER" /opt/prontuai
```

Criar `/opt/prontuai/back-end/.env` a partir de `back-end/.env.example` e preencher os valores reais:

```bash
nano /opt/prontuai/back-end/.env
chmod 600 /opt/prontuai/back-end/.env
```

Obrigatórios em produção:

- `DATABASE_URL`
- `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` (container `prontuai-db`)
- `OPENAI_API_KEY`
- `JWT_SECRET_KEY`
- `PRONTUAI_SERVICE_TOKEN`
- `PRONTUAI_CLIENT_NAME`
- `USE_PRONTUAI_PATIENTS_EXAMS=true`
- `ALLOWED_ORIGINS`

Para o backup automático (ver seção "Postgres" abaixo, compatível com AWS S3
ou Cloudflare R2): `BACKUP_S3_BUCKET`, `BACKUP_S3_PREFIX`,
`BACKUP_S3_ENDPOINT_URL`, `BACKUP_S3_REGION`, `BACKUP_S3_SSE`,
`BACKUP_S3_ACCESS_KEY_ID`, `BACKUP_S3_SECRET_ACCESS_KEY`,
`BACKUP_RETENTION_DAYS`.

## Postgres na mesma VPS (container `prontuai-db`)

O Postgres vive em **pasta própria na VPS, `/home/ec2-user/prontuai-db`**,
com seu próprio `docker-compose.db.yml` e seu próprio `.env` — nem o compose
nem o `.env` são compartilhados com o backend (`/home/ec2-user/prontuai`).
Os scripts de backup/restore/migração vivem em
`/home/ec2-user/prontuai-db/script/`. De propósito: assim uma manutenção
grande do backend — deploy, rollback, panic-restore, `docker compose down`
do stack, edição do `docker-compose.yml` — nunca arrasta o banco junto, nem
por acidente de estarem na mesma pasta. Os dois compose files só se
conectam pela rede Docker externa `prontuai-db-net` (criada por
`docker-compose.db.yml`, referenciada como `external: true` em
`docker-compose.aws.yml`). A 5432 fica em bind só de loopback (`127.0.0.1`,
nunca `0.0.0.0`) — nunca abra 5432 na security group da instância, isso é
independente do bind local. Acesso de fora da VPS exige túnel SSH (ver seção
"Acesso ao banco" abaixo).

Nenhum workflow de CI toca nesta pasta — nem o `backend-ghcr-deploy.yml` (só
dá `up`/`pull` no serviço `prontuai-backend`, dentro de `docker-compose.yml`)
nem nenhum outro. Tudo aqui é cópia manual, uma única vez (ou de novo,
manualmente, sempre que algum desses arquivos for editado no repo):

```bash
mkdir -p /home/ec2-user/prontuai-db/script
cp back-end/docker-compose.db.yml /home/ec2-user/prontuai-db/
cp ops/deploy/backup_postgres.sh ops/deploy/restore_postgres.sh \
   ops/deploy/60_migrate_neon_to_ec2.sh ops/deploy/lib.sh \
   /home/ec2-user/prontuai-db/script/
```

Antes do primeiro `up`, prepare um volume dedicado para o dado do banco
(dado de saúde: CPF, laudos — mantenha separado do volume raiz e
criptografado):

```bash
# Confirme que a criptografia default de EBS está habilitada na conta/região
# antes de criar o volume (Console -> EC2 -> Configurações da conta).
# Anexe/monte o volume dedicado no path abaixo antes de subir o container:
sudo mkdir -p /home/ec2-user/prontuai-db/pgdata
# (montar o EBS dedicado em /home/ec2-user/prontuai-db/pgdata, via /etc/fstab)
sudo chown -R 999:999 /home/ec2-user/prontuai-db/pgdata   # uid/gid do postgres na imagem alpine
```

Crie `/home/ec2-user/prontuai-db/.env` (próprio, não é o `.env` do backend)
com `POSTGRES_USER`, uma `POSTGRES_PASSWORD` forte (32+ caracteres),
`POSTGRES_DB` e os `BACKUP_S3_*` (ver `back-end/.env.example`). Depois:

```bash
cd /home/ec2-user/prontuai-db
docker compose -f docker-compose.db.yml up -d
```

No `.env` do backend (`/home/ec2-user/prontuai/.env`), aponte `DATABASE_URL`
para o nome do serviço, não para localhost — usando o **mesmo**
usuário/senha/banco que você colocou no `.env` do banco (os dois arquivos
não se leem automaticamente, o valor precisa estar escrito nos dois):

```
DATABASE_URL=postgresql://<POSTGRES_USER>:<POSTGRES_PASSWORD>@prontuai-db:5432/<POSTGRES_DB>
```

Como a rede `prontuai-db-net` é criada pelo `docker-compose.db.yml`, ele
precisa subir **antes** da primeira vez que o backend sobe apontando pro
banco local (senão o `docker compose up` do backend falha por rede externa
inexistente).

### Acesso ao banco (só via túnel SSH)

Enquanto o setup estiver em teste, o único jeito de conectar num cliente
(psql, DBeaver, pgAdmin) a partir da sua máquina é via túnel SSH — não existe
(nem deve existir) caminho público até a porta 5432:

```bash
ssh -L 5433:127.0.0.1:5432 usuario@ec2-host -N
# noutro terminal / no seu cliente de banco:
psql "postgresql://<POSTGRES_USER>:<POSTGRES_PASSWORD>@localhost:5433/<POSTGRES_DB>"
```

Isso funciona porque a 5432 do container está mapeada em `127.0.0.1:5432` no
host (`DB_BIND_ADDRESS`/`DB_HOST_PORT` em `docker-compose.db.yml`) — o túnel
SSH só repassa uma porta local sua até essa porta de loopback da VPS; sem
chave SSH válida não há como alcançar o Postgres de jeito nenhum, nem de
dentro da própria rede da AWS. Quando parar de precisar desse acesso direto,
remova o bloco `ports:` do `docker-compose.db.yml` — o backend continua
funcionando normalmente porque ele fala com `prontuai-db:5432` pela rede
Docker interna, não pela porta do host.

Backup automático diário (systemd timer) e restore/drill: ver
`ops/deploy/systemd/README.md` e os scripts já copiados para
`/home/ec2-user/prontuai-db/script/` (`backup_postgres.sh`,
`restore_postgres.sh`). Migração inicial do Neon para este Postgres:
`/home/ec2-user/prontuai-db/script/60_migrate_neon_to_ec2.sh` (ver
`ops/deploy/README.md`).

## Secrets/vars no GitHub

Em `Settings -> Secrets and variables -> Actions`:

Secrets obrigatórios:

- `AWS_VPS_HOST`: IP ou DNS da VPS.
- `AWS_VPS_USER`: usuário SSH com acesso ao Docker.
- `AWS_VPS_SSH_KEY`: chave privada SSH.

Secrets opcionais:

- `AWS_VPS_PORT`: porta SSH. Default: `22`.
- `GHCR_DEPLOY_USERNAME`: usuário GitHub para `docker login` na VPS.
- `GHCR_DEPLOY_TOKEN`: PAT com permissão `read:packages`, necessário se o pacote GHCR for privado.

Variable opcional:

- `AWS_VPS_DEPLOY_PATH`: diretório remoto. Default: `/home/ec2-user/prontuai`.

## GHCR

O workflow publica:

- `ghcr.io/<owner>/prontuai-backend:<commit-sha>`
- `ghcr.io/<owner>/prontuai-backend:staging`
- `ghcr.io/<owner>/prontuai-backend:v1`
- `ghcr.io/<owner>/prontuai-backend:latest`

Se o pacote estiver privado, configure `GHCR_DEPLOY_USERNAME` e `GHCR_DEPLOY_TOKEN`.
Se estiver público, esses secrets podem ficar vazios.

## Deploy

Fluxo esperado de branches:

- `dev` para desenvolvimento diario
- `staging` para homologacao
- `v1` para producao

O deploy automático roda em:

- push na branch `v1`
- push na branch `staging`
- execução manual em `Actions -> Backend GHCR Deploy -> Run workflow`
- execução manual em `Actions -> Backend GHCR Staging Deploy -> Run workflow`

O deploy de produção usa secrets/vars `AWS_VPS_*` e `GHCR_DEPLOY_*`.
O deploy de staging usa secrets/vars `AWS_STAGING_VPS_*` e `GHCR_STAGING_DEPLOY_*`.

Secrets obrigatórios para staging:

- `AWS_STAGING_VPS_HOST`
- `AWS_STAGING_VPS_USER`
- `AWS_STAGING_VPS_SSH_KEY`

Secrets opcionais para staging:

- `GHCR_STAGING_DEPLOY_USERNAME`
- `GHCR_STAGING_DEPLOY_TOKEN`

Variables opcionais para staging:

- `AWS_STAGING_VPS_PORT`
- `AWS_STAGING_VPS_DEPLOY_PATH`

O push em outras branches nao faz deploy automatico. Producao so acontece em `v1`; staging so acontece em `staging`; ambos tambem podem ser executados manualmente.

## Nginx no host para api.prontuai.grupobrmed.com.br

O compose AWS publica o backend apenas em loopback da VPS por padrão:

- `BACKEND_BIND_ADDRESS=127.0.0.1`
- `BACKEND_HTTP_PORT=8080`

Use o arquivo `ops/deploy/nginx/api.prontuai.grupobrmed.com.br.conf` como base do Nginx do host:

```bash
sudo cp ops/deploy/nginx/api.prontuai.grupobrmed.com.br.conf /etc/nginx/conf.d/api.prontuai.grupobrmed.com.br.conf
sudo nginx -t
sudo systemctl reload nginx
```

Depois aponte o DNS `api.prontuai.grupobrmed.com.br` para o IP da VPS e emita o certificado:

```bash
sudo certbot --nginx -d api.prontuai.grupobrmed.com.br
```

## Verificação na VPS

```bash
cd /home/ec2-user/prontuai
docker compose ps
docker compose logs -f prontuai-backend
curl -fsS http://127.0.0.1:8080/health
```

Se usar porta customizada:

```bash
BACKEND_HTTP_PORT=8080 curl -fsS http://127.0.0.1:8080/health
```

## Rollback

Use uma tag de commit anterior:

```bash
cd /home/ec2-user/prontuai
export BACKEND_IMAGE=ghcr.io/<owner>/prontuai-backend:<commit-sha-anterior>
docker compose -f docker-compose.yml pull prontuai-backend
docker compose -f docker-compose.yml up -d --remove-orphans prontuai-backend
curl -fsS http://127.0.0.1:8080/health
```
