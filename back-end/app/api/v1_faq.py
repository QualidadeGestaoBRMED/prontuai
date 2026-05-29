from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import List, Dict
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

class FAQRequest(BaseModel):
    pergunta: str
    historico: List[Dict[str, str]] = []

@router.post("/faq", summary="Responder perguntas com base em documentos e IA")
async def responder_faq(request: FAQRequest):
    _ = request
    logger.info("faq.endpoint.disabled")
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Endpoint de FAQ desativado por segurança.",
    )
