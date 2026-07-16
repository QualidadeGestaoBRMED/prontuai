from fastapi import APIRouter, UploadFile, File, HTTPException, status, Depends
from app.services import ocr_service
from app.core.auth import require_sender
from app.models.user import User
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/ocr", summary="Processar documento via OCR e extrair identificação e exames")
async def processar_ocr(
    arquivo: UploadFile = File(...),
    current_user: User = Depends(require_sender)  # Apenas SENDER ou ADMIN
):
    if not arquivo:
        logger.warning("Arquivo não enviado na requisição OCR.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Arquivo não enviado.")
    try:
        logger.info(f"Usuário {current_user.email} ({current_user.role.value}) processando OCR para {arquivo.filename}")
        resultado = await ocr_service.ocr_pipeline(arquivo)
        if "erro" in resultado:
            logger.error(f"Erro no OCR: {resultado['erro']}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=resultado["erro"])
        return resultado
    except Exception as e:
        logger.exception(f"Erro inesperado no OCR: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro inesperado no processamento do OCR.")
