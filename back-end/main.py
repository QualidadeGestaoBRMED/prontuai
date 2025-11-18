from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import api_router
from app.core.logging import setup_logging
from app.core.config import settings

setup_logging(settings.LOG_FILE)

app = FastAPI(title="API BR MED - Exames e Validação")

origins = [
    "http://localhost",
    "http://localhost:3000",
    "https://prontuai.grupobrmed.com.br",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

@app.get("/health")
async def health_check():
    """Health check endpoint para Render e monitoramento"""
    return {"status": "healthy", "service": "prontuai-backend"} 