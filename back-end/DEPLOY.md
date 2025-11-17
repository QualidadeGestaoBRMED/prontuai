# Deploy na AWS EC2

## ⚡ Build Otimizado para Textract

Se você usa `USE_TEXTRACT=true` no `.env`, pode usar o Dockerfile otimizado que **NÃO instala PyTorch/Docling**, economizando ~3.5GB de espaço:

```bash
# Build com requirements mínimo (sem PyTorch)
docker build -f Dockerfile.textract -t prontuai-backend .

# Ou com docker-compose usando o Dockerfile alternativo
docker-compose -f docker-compose.textract.yml up -d --build
```

**Comparação de tamanho:**
- Dockerfile padrão (com Docling): ~5GB
- Dockerfile.textract (apenas Textract): ~1.5GB

---

## Opção 1: Usando Docker Compose (RECOMENDADO)

Esta é a forma mais simples, pois todas as variáveis de ambiente são carregadas automaticamente do `.env`:

```bash
# 1. Clone o repositório
git clone <seu-repo>
cd back-end

# 2. Configure o .env (copie do .env.example e preencha)
cp .env.example .env
nano .env  # ou vim, vi, etc.

# 3. Build e start com docker-compose
docker-compose up -d --build

# 4. Verificar logs
docker-compose logs -f

# 5. Verificar health
curl http://localhost/health
```

Para parar:
```bash
docker-compose down
```

Para rebuild após mudanças:
```bash
docker-compose up -d --build
```

## Opção 2: Docker Run com --env-file

Se preferir não usar docker-compose:

```bash
# Build da imagem
docker build -t prontuai-backend .

# Rodar com --env-file
docker run -d \
  --name prontuai-backend \
  -p 80:80 \
  --env-file .env \
  --restart unless-stopped \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/resultados:/app/resultados \
  -v $(pwd)/ocr_resultados:/app/ocr_resultados \
  -v $(pwd)/auditoria_validacao:/app/auditoria_validacao \
  -v $(pwd)/data:/app/data:ro \
  prontuai-backend

# Ver logs
docker logs -f prontuai-backend
```

## Opção 3: Docker Run com variáveis inline

Menos recomendado, mas funciona:

```bash
docker run -d \
  --name prontuai-backend \
  -p 80:80 \
  -e OPENAI_API_KEY="sua_key" \
  -e BRMED_USERNAME="user" \
  -e BRMED_PASSWORD="pass" \
  -e WORKERS=4 \
  prontuai-backend
```

## Portas

- **Porta 80**: Nginx (HTTP) - esta é a porta que você expõe
- **Porta 8000**: FastAPI (interna) - roda apenas dentro do container

## Configuração da EC2

### Security Group
Libere a porta 80 (HTTP) no Security Group da instância:
- Type: HTTP
- Port: 80
- Source: 0.0.0.0/0 (ou seu IP específico)

### Instalar Docker na EC2 (Amazon Linux 2/Ubuntu)

Amazon Linux 2:
```bash
sudo yum update -y
sudo yum install -y docker
sudo service docker start
sudo usermod -a -G docker ec2-user
```

Ubuntu:
```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -a -G docker ubuntu
```

Depois faça logout e login novamente para aplicar as permissões do grupo docker.

## Acessando a aplicação

Após o deploy:
- API: `http://<IP-da-EC2>/`
- Docs: `http://<IP-da-EC2>/docs`
- Health: `http://<IP-da-EC2>/health`

## Monitoramento

Ver logs do nginx:
```bash
docker exec -it prontuai-backend tail -f /var/log/nginx/access.log
docker exec -it prontuai-backend tail -f /var/log/nginx/error.log
```

Ver logs da aplicação:
```bash
docker-compose logs -f
# ou
docker logs -f prontuai-backend
```

Ver status do container:
```bash
docker ps
docker stats prontuai-backend
```

## Troubleshooting

Container não inicia:
```bash
docker logs prontuai-backend
```

Rebuild forçado:
```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

Limpar volumes órfãos:
```bash
docker system prune -a
```
