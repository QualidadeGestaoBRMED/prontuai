# Dockerfile para deploy em produção (EC2, Render, etc)
FROM python:3.11-slim

# Argumentos de build para controlar source do código
ARG USE_GIT_CLONE=false
ARG GIT_REPO=https://github.com/QualidadeGestaoBRMED/prontuai.git
ARG GIT_BRANCH=v1

WORKDIR /app

# Instalar dependências do sistema para Playwright, Nginx e Git
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    nginx \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copiar ou clonar código baseado no build argument
RUN if [ "$USE_GIT_CLONE" = "true" ]; then \
        echo "🔄 Clonando código do GitHub (branch: $GIT_BRANCH)..." && \
        git clone --depth 1 --branch $GIT_BRANCH $GIT_REPO /tmp/repo && \
        cp -r /tmp/repo/back-end/* /app/ && \
        rm -rf /tmp/repo && \
        echo "✅ Código clonado com sucesso!"; \
    else \
        echo "📦 Usando código do contexto local..."; \
    fi

# Se não usou git clone, copiar do contexto local
COPY requirements.txt* ./
RUN if [ "$USE_GIT_CLONE" = "false" ]; then \
        echo "📁 Copiando código local..."; \
    fi

# Instalar dependências Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn

# Instalar navegador Chromium do Playwright
RUN playwright install chromium && \
    playwright install-deps chromium

# Copiar código local se não usou git clone (depois das deps para aproveitar cache)
RUN if [ "$USE_GIT_CLONE" = "false" ]; then \
        echo "Copiando restante dos arquivos..."; \
    fi
COPY --chown=root:root . .

# Criar diretórios necessários
RUN mkdir -p logs resultados ocr_resultados auditoria_validacao

# Copiar configuração do nginx
COPY nginx.conf /etc/nginx/nginx.conf

# Tornar o script de entrypoint executável
RUN chmod +x /app/entrypoint.sh

# Expor portas (80 para nginx, 8000 para FastAPI interno)
EXPOSE 80

# Health check via nginx
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost/health || exit 1

# Comando de inicialização usando entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]
