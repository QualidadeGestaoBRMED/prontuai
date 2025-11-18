from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import api_router
from app.core.logging import setup_logging
from app.core.config import settings

setup_logging(settings.LOG_FILE)

app = FastAPI(title="API BR MED - Exames e Validação")

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

@app.get("/health")
async def health_check():
    """Health check endpoint para Render e monitoramento"""
    return {"status": "healthy", "service": "prontuai-backend"} 