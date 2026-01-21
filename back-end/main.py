from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import api_router
from app.core.logging import setup_logging
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

setup_logging(settings.LOG_FILE)

app = FastAPI(title="API BR MED - Exames e Validação")

@app.on_event("startup")
async def startup_event():
    """Executa tarefas no startup da aplicação"""
    logger.info("🚀 Iniciando aplicação...")

    # Auto-migração do banco de dados
    try:
        from app.core.migrations import auto_migrate
        auto_migrate()
    except Exception as e:
        logger.error(f"Erro durante auto-migração: {e}")
        # Não interromper o startup - a aplicação pode funcionar mesmo sem migração

# Configuração de CORS usando variáveis de ambiente
# Permite configurar origens dinamicamente para diferentes ambientes (dev, staging, prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

@app.get("/")
async def root():
    """Endpoint raiz - Informações da API"""
    return {
        "service": "ProntuAI Backend API",
        "version": "2.0.0",
        "status": "online",
        "docs": "/docs",
        "health": "/health",
        "api_prefix": "/v1"
    }

@app.get("/health")
async def health_check():
    """Endpoint de verificação de saúde para Render e monitoramento"""
    return {"status": "healthy", "service": "prontuai-backend"} 