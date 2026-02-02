from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from app.api import api_router
from app.core.logging import (
    setup_logging,
    set_request_context,
    clear_context,
    get_user_context,
    get_request_id,
    get_audit_context,
    was_audit_logged,
    mark_audit_logged,
)
from app.core.auth import decode_token
from app.core.config import settings
from app.core.database import user_db
from app.models.audit_log import AuditLogCreate
from app.core.telemetry import setup_telemetry
import logging
import os
import time
import asyncio
from uuid import uuid4

logger = logging.getLogger(__name__)

setup_logging(settings.LOG_FILE)

if os.getenv("SENTRY_DSN"):
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=os.getenv("SENTRY_DSN"),
            integrations=[FastApiIntegration()],
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
        )
        logger.info("Sentry inicializado")
    except Exception as e:
        logger.warning(f"Falha ao inicializar Sentry: {e}")

app = FastAPI(title="API BR MED - Exames e Validação")
setup_telemetry(app=app, engine=getattr(user_db, "engine", None))

@app.middleware("http")
async def cors_preflight_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        origin = request.headers.get("origin")
        response = Response(status_code=200)
        if origin and origin in settings.ALLOWED_ORIGINS:
            response.headers["access-control-allow-origin"] = origin
            response.headers["access-control-allow-credentials"] = "true"
            response.headers["access-control-allow-methods"] = "DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT"
            req_headers = request.headers.get("access-control-request-headers")
            if req_headers:
                response.headers["access-control-allow-headers"] = req_headers
            response.headers["vary"] = "Origin"
        return response
    return await call_next(request)

@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid4())
    set_request_context(request_id)
    start_time = time.perf_counter()
    response = None
    error = None
    try:
        response = await call_next(request)
    except Exception as exc:
        error = exc
    finally:
        if response is not None:
            response.headers["x-request-id"] = request_id
    elapsed_ms = (time.perf_counter() - start_time) * 1000
    status_code = response.status_code if response is not None else 500
    if error is not None:
        logger.exception(
            "request.error",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": round(elapsed_ms, 2),
                "ip": request.client.host if request.client else None,
                "user_agent": request.headers.get("user-agent"),
            },
        )
        clear_context()
        raise error
    if os.getenv("REQUEST_LOGGING", "true").lower() == "true":
        logger.info(
            "request.completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": round(elapsed_ms, 2),
                "ip": request.client.host if request.client else None,
                "user_agent": request.headers.get("user-agent"),
            },
        )
    audit_enabled = os.getenv("AUDIT_LOG_ENABLED", "true").lower() == "true"
    audit_all = os.getenv("AUDIT_LOG_ALL_REQUESTS", "false").lower() == "true"
    if audit_enabled and not was_audit_logged() and (audit_all or request.method not in {"GET", "HEAD", "OPTIONS"}):
        try:
            path_parts = request.url.path.split("/")
            default_resource = path_parts[2] if len(path_parts) > 2 else None
            default_resource_id = path_parts[3] if len(path_parts) > 3 else None
            user_context = get_user_context()
            if not user_context.get("user_email"):
                auth_header = request.headers.get("authorization")
                if auth_header and auth_header.lower().startswith("bearer "):
                    token = auth_header.split(" ", 1)[1].strip()
                    if token:
                        try:
                            token_data = decode_token(token)
                            user_context = {
                                "user_id": None,
                                "user_email": token_data.email,
                                "user_role": token_data.role.value,
                                "clinic_id": token_data.clinic_id,
                            }
                        except Exception:
                            pass
            audit_context = get_audit_context()
            user_db.create_audit_log(
                AuditLogCreate(
                    user_id=user_context.get("user_id"),
                    user_email=user_context.get("user_email"),
                    user_role=user_context.get("user_role"),
                    action=audit_context.get("action") or f"{request.method.lower()}:{request.url.path}",
                    resource=audit_context.get("resource") or default_resource,
                    resource_id=audit_context.get("resource_id") or default_resource_id,
                    method=request.method,
                    path=request.url.path,
                    status_code=status_code,
                    ip=request.client.host if request.client else None,
                    user_agent=request.headers.get("user-agent"),
                    request_id=get_request_id(),
                    metadata=audit_context.get("metadata"),
                )
            )
            logger.info(
                "audit.created",
                extra={
                    "action": audit_context.get("action") or f"{request.method.lower()}:{request.url.path}",
                    "resource": audit_context.get("resource") or default_resource,
                    "resource_id": audit_context.get("resource_id") or default_resource_id,
                    "status_code": status_code,
                    "request_id": get_request_id(),
                },
            )
            mark_audit_logged(True)
        except Exception as audit_error:
            logger.warning(f"Falha ao registrar audit log: {audit_error}")
    clear_context()
    return response

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

    # Warmup de cache de documentos (não bloqueia o startup)
    try:
        from app.api.v1 import documents as documents_api
        import threading
        threading.Thread(target=documents_api.warm_documents_cache, daemon=True).start()
    except Exception as e:
        logger.warning(f"Warmup de cache de documentos falhou: {e}")

    # Watchdog de jobs para encerrar processamentos travados
    try:
        from app.core.job_watchdog import job_watchdog_loop
        asyncio.create_task(job_watchdog_loop())
    except Exception as e:
        logger.warning(f"Job watchdog falhou ao iniciar: {e}")

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
