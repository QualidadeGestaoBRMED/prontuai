#!/bin/bash
# Script de inicialização para Render
# Não é necessário executar manualmente - usado pelo render.yaml

set -e

echo "🚀 Iniciando ProntuAI Backend..."

# Verificar se os índices FAISS existem
if [ ! -f "data/faq_index.faiss" ]; then
    echo "⚠️  Índice FAQ não encontrado. Gerando..."
    python scripts/generate_faq_index.py
fi

if [ ! -f "data/exam_similarity_index.faiss" ]; then
    echo "⚠️  Índice de similaridade de exames não encontrado. Gerando..."
    python scripts/generate_exam_similarity_index.py
fi

echo "✅ Índices FAISS verificados"

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
    --access-logfile - \
    --error-logfile - \
    --log-level info
