
from fastapi import APIRouter, HTTPException, status, Body
from pydantic import BaseModel
from typing import List, Dict, Any
from app.services import faq_service
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

class FAQRequest(BaseModel):
    pergunta: str
    historico: List[Dict[str, str]] = []

@router.post("/faq", summary="Responder perguntas com base em documentos e IA")
async def responder_faq(request: FAQRequest):
    if not request.pergunta:
        logger.warning("Requisição para o FAQ sem o campo 'pergunta'.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O campo 'pergunta' é obrigatório."
        )
    try:
        resultado = faq_service.buscar_e_responder(request.pergunta, request.historico)
        return resultado
    except ConnectionError as e:
        logger.error(f"Erro de conexão no serviço de FAQ: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.exception(f"Erro inesperado ao processar a pergunta do FAQ: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ocorreu um erro inesperado ao processar sua pergunta."
        )
