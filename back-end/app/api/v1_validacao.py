from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from app.services import validacao_service
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

class ValidacaoRequest(BaseModel):
    cpf: str
    exames_obrigatorios: list[str]
    exames_enviados: list[str]

@router.post("/validacao", summary="Validar exames enviados vs. obrigatórios")
async def validar_exames(request: ValidacaoRequest):
    if not request.cpf or not request.exames_obrigatorios or not request.exames_enviados:
        logger.warning("Parâmetros obrigatórios ausentes na validação.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CPF, exames obrigatórios e exames enviados são obrigatórios.")
    try:
        resultado = validacao_service.validar_exames(request.cpf, request.exames_obrigatorios, request.exames_enviados)
        return resultado
    except Exception as e:
        logger.exception(f"Erro inesperado na validação: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro inesperado na validação de exames.") 