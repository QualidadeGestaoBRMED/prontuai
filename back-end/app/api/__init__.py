from fastapi import APIRouter
from app.api import v1_ocr, v1_brmed, v1_validacao, v1_faq
from app.api.v1 import auth, users

api_router = APIRouter()
api_router.include_router(v1_ocr.router, prefix="/v1")
api_router.include_router(v1_brmed.router, prefix="/v1")
api_router.include_router(v1_validacao.router, prefix="/v1")
api_router.include_router(v1_faq.router, prefix="/v1")
api_router.include_router(auth.router, prefix="/v1")
api_router.include_router(users.router, prefix="/v1") 