# Dockerfile para deploy em produção (EC2, Render, etc)
FROM python:3.11-slim

WORKDIR /app

# Instalar dependências do sistema para Playwright, Docling e Nginx
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
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements e instalar dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn

# Instalar navegador Chromium do Playwright
RUN playwright install chromium && \
    playwright install-deps chromium

# Copiar código da aplicação
COPY . .

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
