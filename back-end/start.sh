#!/bin/bash
# Script de inicialização para Render
# Não é necessário executar manualmente - usado pelo render.yaml

set -e

echo "🚀 Iniciando ProntuAI Backend..."

# Verificar se os artefatos críticos existem
if [ ! -f "data/exam_similarity_index.faiss" ] || [ ! -f "data/exam_similarity_data.json" ] || [ ! -f "data/exam_similarity_index.faiss.hmac" ] || [ ! -f "data/exam_similarity_data.json.hmac" ]; then
    echo "❌ Artefatos de similaridade de exames não encontrados (index + json + hmac)."
    echo "❌ Gere artefatos assinados previamente no pipeline de build."
    exit 1
fi

echo "✅ Artefatos validados"

# Criar diretórios de output se não existirem
mkdir -p logs resultados ocr_resultados auditoria_validacao

echo "✅ Diretórios criados"

# Iniciar servidor com Gunicorn
echo "🌐 Iniciando servidor FastAPI..."
exec gunicorn main:app \
    --workers 2 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:${PORT:-8000} \
    --timeout 300 \
    --graceful-timeout 300 \
    --keep-alive 5 \
    --worker-tmp-dir /dev/shm \
    --access-logfile - \
    --error-logfile - \
    --log-level info
