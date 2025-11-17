#!/bin/bash
set -e

echo "Iniciando serviços..."

# Criar diretórios de log do nginx se não existirem
mkdir -p /var/log/nginx

# Iniciar nginx em background
echo "Iniciando Nginx..."
nginx -g "daemon off;" &
NGINX_PID=$!

# Aguardar nginx iniciar
sleep 2

# Iniciar aplicação FastAPI com gunicorn
echo "Iniciando FastAPI com Gunicorn..."
exec gunicorn main:app \
    --workers ${WORKERS:-4} \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 127.0.0.1:8000 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - &
GUNICORN_PID=$!

echo "Serviços iniciados - Nginx (PID: $NGINX_PID) e Gunicorn (PID: $GUNICORN_PID)"

# Função para lidar com sinais de término
cleanup() {
    echo "Encerrando serviços..."
    kill -TERM $GUNICORN_PID 2>/dev/null || true
    kill -TERM $NGINX_PID 2>/dev/null || true
    wait $GUNICORN_PID 2>/dev/null || true
    wait $NGINX_PID 2>/dev/null || true
    echo "Serviços encerrados"
    exit 0
}

trap cleanup SIGTERM SIGINT

# Aguardar os processos
wait -n

# Se um dos processos morreu, encerrar o outro
cleanup
