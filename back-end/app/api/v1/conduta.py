"""Conduta sugerida para a tela do médico (Conduta Médica): o objeto Conduta da API de Normalidade e Conduta
Sugerida, calculado para um documento já processado pelo ProntuAI."""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import require_roles
from app.core.database import user_db
from app.models.user import User, UserRole
from app.services.conduta import conduta_sugerida as cs

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Conduta sugerida"])


@router.get("/documents/{document_id}/conduta-sugerida")
async def conduta_do_documento(
    document_id: str,
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.MANAGER])),
) -> dict:
    document = user_db.get_document_by_id(document_id)
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento não encontrado")
    payload = document.result_payload if isinstance(document.result_payload, dict) else {}
    ausentes = [t.get("exame") for t in payload.get("tabela_comparacao") or [] if isinstance(t, dict)
                and t.get("status") == "faltante" and t.get("exame")]
    data = document.uploaded_at.date().isoformat() if getattr(document, "uploaded_at", None) else None
    # Leitura + chamada ao modelo fora do loop (são síncronas).
    return await asyncio.to_thread(cs.sugerir, document.ocr_markdown or "", data, ausentes,
                                   document.exams_ocr or [], document.exams_brnet or [])
