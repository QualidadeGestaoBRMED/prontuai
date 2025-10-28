from fastapi import APIRouter, UploadFile, File, HTTPException, status
from app.services import ocr_service
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/ocr", summary="Processar documento via OCR e extrair exames/CPF")
async def processar_ocr(arquivo: UploadFile = File(...)):
    if not arquivo:
        logger.warning("Arquivo não enviado na requisição OCR.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Arquivo não enviado.")
    try:
        resultado = await ocr_service.ocr_pipeline(arquivo)
        if "erro" in resultado:
            logger.error(f"Erro no OCR: {resultado['erro']}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=resultado["erro"])
        return resultado
    except Exception as e:
        logger.exception(f"Erro inesperado no OCR: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro inesperado no processamento do OCR.") 