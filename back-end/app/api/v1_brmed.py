from fastapi import APIRouter, HTTPException, status, UploadFile, File, Body
from app.services import workflow_service, brmed_service
import logging
import json

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/processar-documento", summary="Processar documento completo com OCR, BRMED e Validação")
async def processar_documento_completo_api(
    arquivo: UploadFile = File(...),
    exames_obrigatorios: str = Body(..., embed=True) # Recebe como string JSON
):
    if not arquivo:
        logger.warning("Arquivo não enviado na requisição de processamento completo.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Arquivo não enviado.")
    
    try:
        # Converte a string JSON de exames_obrigatorios para lista
        exames_obrigatorios_list = json.loads(exames_obrigatorios)
    except json.JSONDecodeError:
        logger.error("Formato inválido para exames_obrigatorios. Esperado JSON array de strings.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Exames obrigatórios devem ser um array JSON válido.")

    try:
        resultado = await workflow_service.processar_documento_completo(arquivo, exames_obrigatorios_list)
        return resultado
    except Exception as e:
        logger.exception(f"Erro inesperado no processamento completo do documento: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro inesperado no processamento do documento.")

@router.post("/consultar-brmed", summary="Consultar exames BRMED por CPF")
async def consultar_brmed_api(cpf: str = Body(..., embed=True)):
    if not cpf:
        logger.warning("CPF não fornecido para consulta BRMED.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CPF é obrigatório.")
    try:
        resultado = await brmed_service.consultar_exames_brmed(cpf)
        if "erro" in resultado:
            logger.error(f"Erro ao consultar BRMED para CPF {cpf}: {resultado['erro']}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=resultado["erro"])
        return resultado
    except Exception as e:
        logger.exception(f"Erro inesperado ao consultar BRMED para CPF {cpf}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro inesperado ao consultar BRMED.")
 