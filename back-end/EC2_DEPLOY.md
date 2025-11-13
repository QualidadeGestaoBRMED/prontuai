# Deploy ProntuAI Backend no EC2 com Docker

Guia rápido para deployar o back-end no seu EC2 usando Docker.

## Pré-requisitos no EC2

1. **Docker e Docker Compose instalados**
2. **Porta 8000 liberada no Security Group**
3. **Git instalado** (para clonar o repo)

### Instalar Docker (se necessário)

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y docker.io docker-compose
sudo systemctl enable docker
sudo systemctl start docker

# Adicionar seu usuário ao grupo docker (evita usar sudo)
sudo usermod -aG docker $USER
# Fazer logout/login para aplicar
```

## Deploy Passo a Passo

### 1. Clonar o Repositório

```bash
cd ~
git clone <seu-repo-url> prontuai
cd prontuai/back-end
```

Ou via SCP se preferir:
```bash
# No seu computador local
scp -r back-end/ ubuntu@<ec2-ip>:~/prontuai/
```

### 2. Configurar Variáveis de Ambiente

Criar arquivo `.env` na raiz do `back-end/`:

```bash
nano .env
```

Conteúdo do `.env`:
```env
# OpenAI
OPENAI_API_KEY=sk-...

# BRMED
BRMED_USERNAME=seu_usuario
BRMED_PASSWORD=sua_senha

# Modelos
MODELO_GPT=gpt-4o-mini
MODELO_EMBEDDING=text-embedding-3-large

# FAQ
K_VIZINHOS_FAQ=2
MAX_DISTANCIA_FAQ=1.0

# Workers (ajuste conforme CPU da instância)
WORKERS=4
```

### 3. Build e Start

```bash
# Build da imagem
docker-compose build

# Subir container em background
docker-compose up -d

# Ver logs
docker-compose logs -f
```

### 4. Testar API

```bash
# Health check
curl http://localhost:8000/health

# Ver documentação interativa
curl http://localhost:8000/docs
```

## Expondo a API Publicamente

Você tem 3 opções para expor a porta 8000:

### Opção 1: Acesso Direto pela Porta 8000 (Simples)

**No Security Group do EC2**:
- Adicionar regra Inbound: `Custom TCP | Port 8000 | Source: 0.0.0.0/0`

**Atualizar docker-compose.yml**:
```yaml
ports:
  - "8000:8000"  # Já está assim
```

**Acessar**:
```
http://<ec2-public-ip>:8000/health
http://<ec2-public-ip>:8000/docs
```

**Front-end**:
```typescript
// front-end/.env.local
NEXT_PUBLIC_API_URL=http://<ec2-public-ip>:8000
```

---

### Opção 2: Usar Nginx como Reverse Proxy (Recomendado)

**Vantagens**:
- Roda na porta 80 (padrão HTTP)
- SSL/HTTPS com Let's Encrypt
- Load balancing se escalar
- Logs centralizados

**Instalar Nginx**:
```bash
sudo apt-get install -y nginx
```

**Criar configuração**:
```bash
sudo nano /etc/nginx/sites-available/prontuai
```

Conteúdo:
```nginx
upstream prontuai_backend {
    server localhost:8000;
}

server {
    listen 80;
    server_name <seu-ip-ou-dominio>;

    client_max_body_size 50M;

    location / {
        proxy_pass http://prontuai_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts para processamento longo
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }
}
```

**Ativar e reiniciar**:
```bash
sudo ln -s /etc/nginx/sites-available/prontuai /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default  # Remove site padrão
sudo nginx -t  # Testar configuração
sudo systemctl restart nginx
```

**Security Group**:
- Adicionar regra: `HTTP | Port 80 | Source: 0.0.0.0/0`
- (Opcional) Remover porta 8000 se não precisar acesso direto

**Acessar**:
```
http://<ec2-public-ip>/health
http://<ec2-public-ip>/docs
```

---

### Opção 3: HTTPS com Let's Encrypt (Produção)

**Pré-requisitos**:
- Domínio apontando para o IP do EC2 (ex: `api.prontuai.com.br`)

**Instalar Certbot**:
```bash
sudo apt-get install -y certbot python3-certbot-nginx
```

**Obter certificado SSL**:
```bash
sudo certbot --nginx -d api.prontuai.com.br
```

**Atualizar configuração Nginx** (certbot faz automaticamente):
```nginx
server {
    listen 443 ssl;
    server_name api.prontuai.com.br;

    ssl_certificate /etc/letsencrypt/live/api.prontuai.com.br/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.prontuai.com.br/privkey.pem;

    # ... resto da configuração
}

# Redirect HTTP -> HTTPS
server {
    listen 80;
    server_name api.prontuai.com.br;
    return 301 https://$server_name$request_uri;
}
```

**Security Group**:
- Adicionar regra: `HTTPS | Port 443 | Source: 0.0.0.0/0`

**Acessar**:
```
https://api.prontuai.com.br/health
https://api.prontuai.com.br/docs
```

**Front-end**:
```typescript
// front-end/.env.local
NEXT_PUBLIC_API_URL=https://api.prontuai.com.br
```

## Comandos Úteis

### Gerenciar Container

```bash
# Ver status
docker-compose ps

# Ver logs em tempo real
docker-compose logs -f

# Reiniciar
docker-compose restart

# Parar
docker-compose stop

# Parar e remover
docker-compose down

# Rebuild após mudanças no código
docker-compose build --no-cache
docker-compose up -d
```

### Atualizar Código

```bash
# Pull do repositório
git pull origin main

# Rebuild e restart
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Monitoramento

```bash
# Uso de recursos do container
docker stats prontuai-backend

# Inspecionar container
docker inspect prontuai-backend

# Executar comando dentro do container
docker exec -it prontuai-backend bash
```

## Atualizar CORS no Backend

Edite `main.py` para incluir o IP/domínio do front-end:

```python
origins = [
    "http://localhost:3000",
    "http://<ec2-public-ip>",  # Adicionar
    "https://seu-frontend.vercel.app",  # Ou domínio do front
]
```

Rebuild após mudança:
```bash
docker-compose build --no-cache
docker-compose up -d
```

## Estrutura Final

```
~/prontuai/back-end/
├── docker-compose.yml
├── Dockerfile
├── .env                  # Suas credenciais (não commitar!)
├── app/
├── data/
├── logs/                 # Persistido via volume
├── resultados/           # Persistido via volume
├── ocr_resultados/       # Persistido via volume
└── auditoria_validacao/  # Persistido via volume
```

## Troubleshooting

### Container não inicia

```bash
# Ver logs de erro
docker-compose logs

# Verificar arquivo .env
cat .env
```

### Erro de memória

Ajustar workers no `.env`:
```env
WORKERS=2  # Reduzir para instâncias pequenas
```

### Playwright não funciona

```bash
# Entrar no container
docker exec -it prontuai-backend bash

# Reinstalar Playwright
playwright install chromium
```

### Porta 8000 já em uso

```bash
# Ver o que está usando a porta
sudo lsof -i :8000

# Matar processo
sudo kill -9 <PID>
```

## Recomendações de Instância EC2

| Tipo | vCPU | RAM | Preço/mês | Recomendação |
|------|------|-----|-----------|--------------|
| t3.small | 2 | 2 GB | ~$15 | Desenvolvimento |
| t3.medium | 2 | 4 GB | ~$30 | Produção (básico) |
| t3.large | 2 | 8 GB | ~$60 | Produção (recomendado) |
| c5.xlarge | 4 | 8 GB | ~$122 | Alta performance |

**Para Playwright + Docling OCR**: Mínimo t3.medium (4 GB RAM)

---

**Deploy realizado em**: 2025-01-XX
**Última atualização**: 2025-01-XX
