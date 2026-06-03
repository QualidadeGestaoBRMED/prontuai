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
- `OPENAI_API_KEY`
- `JWT_SECRET_KEY`
- `PRONTUAI_SERVICE_TOKEN`
- `PRONTUAI_CLIENT_NAME`
- `USE_PRONTUAI_PATIENTS_EXAMS=true`
- `ALLOWED_ORIGINS`

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
- `ghcr.io/<owner>/prontuai-backend:latest`

Se o pacote estiver privado, configure `GHCR_DEPLOY_USERNAME` e `GHCR_DEPLOY_TOKEN`.
Se estiver público, esses secrets podem ficar vazios.

## Deploy

O deploy automático roda em:

- push na branch `v1`
- execução manual em `Actions -> Backend GHCR Deploy -> Run workflow`

O push em `main` roda os testes, mas o build/push/deploy automático só acontece para `v1` ou execução manual.

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
