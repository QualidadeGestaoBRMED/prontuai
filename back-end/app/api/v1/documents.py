"""
Endpoints para gerenciamento de documentos.
"""
from fastapi import APIRouter, HTTPException, status, Depends, Query, Request, BackgroundTasks
from fastapi.responses import FileResponse
from typing import List
from app.core.auth import get_current_user, require_admin
from app.core.database import user_db
from app.models.user import User, UserRole
from app.models.document import Document
from app.models.document import DocumentUpdate
from app.core.logging import set_audit_context
from app.core.config import settings
from app.services import drive_service
import logging
import time
import json
import threading
import mimetypes
import os

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documentos"])

_DOCS_CACHE: dict[str, dict] = {}
_DOCS_CACHE_MAX_SECONDS = 60
_DOCS_STALE_MAX_SECONDS = 300
_DOCS_CACHE_LOCK = threading.Lock()

def _compact_result_payload(payload: dict | None) -> dict | None:
    if not isinstance(payload, dict):
        return payload
    # Faz uma cópia rasa para não alterar o payload salvo em memória
    compact = dict(payload)
    ocr_result = compact.get("ocr_result")
    if isinstance(ocr_result, dict):
        ocr_result = dict(ocr_result)
        # Remover texto completo do OCR para reduzir payload
        if "text" in ocr_result:
            ocr_result["text"] = None
        compact["ocr_result"] = ocr_result
    return compact

def _get_cache_entry(cache_key: str) -> dict | None:
    with _DOCS_CACHE_LOCK:
        return _DOCS_CACHE.get(cache_key)

def _set_cache_entry(cache_key: str, documents: List[Document]) -> None:
    with _DOCS_CACHE_LOCK:
        _DOCS_CACHE[cache_key] = {
            "cached_at": time.monotonic(),
            "documents": documents,
            "refreshing": False,
        }

def _set_cache_refreshing(cache_key: str, refreshing: bool) -> None:
    with _DOCS_CACHE_LOCK:
        entry = _DOCS_CACHE.get(cache_key)
        if entry is not None:
            entry["refreshing"] = refreshing

def _load_documents(
    role: UserRole,
    clinic_id: str | None,
    compact: bool,
    user_id: str | None = None,
) -> List[Document]:
    if role in [UserRole.CHECKER, UserRole.ADMIN]:
        documents = user_db.get_all_documents(use_compact_payload=compact)
        logger.debug(f"[DOCUMENTS] {role.value} listou {len(documents)} documentos (todas clínicas)")
    else:
        if not clinic_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuário SENDER deve estar associado a uma clínica",
            )
        documents = user_db.get_documents_by_clinic(clinic_id, use_compact_payload=compact)
        if user_id:
            documents = [doc for doc in documents if doc.uploaded_by_user_id == user_id]
            logger.debug(
                "[DOCUMENTS] SENDER listou %d documentos (clinic_id: %s, user_id: %s)",
                len(documents),
                clinic_id,
                user_id,
            )
        else:
            logger.debug(
                "[DOCUMENTS] SENDER listou %d documentos (clinic_id: %s)",
                len(documents),
                clinic_id,
            )

    uploader_ids = list({doc.uploaded_by_user_id for doc in documents if doc.uploaded_by_user_id})
    uploader_map = {}
    if uploader_ids:
        try:
            uploaders = user_db.get_users_by_ids(uploader_ids)
            uploader_map = {u.id: u.email for u in uploaders}
        except Exception:
            uploader_map = {}

    for doc in documents:
        doc.uploaded_by_user_email = uploader_map.get(doc.uploaded_by_user_id)
        if compact:
            doc.ocr_markdown = None
            doc.result_payload = _compact_result_payload(doc.result_payload)

    return documents

def _refresh_cache_async(
    cache_key: str,
    role: UserRole,
    clinic_id: str | None,
    compact: bool,
    user_id: str | None,
) -> None:
    def _runner() -> None:
        try:
            documents = _load_documents(role, clinic_id, compact, user_id=user_id)
            _set_cache_entry(cache_key, documents)
            logger.debug("[DOCUMENTS] Cache refresh concluído key=%s rows=%d", cache_key, len(documents))
        except Exception as exc:
            logger.warning("[DOCUMENTS] Cache refresh falhou key=%s erro=%s", cache_key, exc)
        finally:
            _set_cache_refreshing(cache_key, False)

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()

def warm_documents_cache() -> None:
    try:
        documents = _load_documents(UserRole.ADMIN, None, True)
        _set_cache_entry("ADMIN:all:True", documents)
        logger.debug("[DOCUMENTS] Cache warmup concluído key=ADMIN:all:True rows=%d", len(documents))
    except Exception as exc:
        logger.warning("[DOCUMENTS] Cache warmup falhou: %s", exc)

@router.get("", response_model=List[Document])
async def list_documents(
    request: Request,
    current_user: User = Depends(get_current_user),
    compact: bool = Query(True, description="Remove campos pesados do payload para melhorar performance"),
    cache_seconds: int = Query(5, ge=0, le=_DOCS_CACHE_MAX_SECONDS, description="Cache em memória para aliviar latência do DB"),
    stale_seconds: int = Query(30, ge=0, le=_DOCS_STALE_MAX_SECONDS, description="Permite retornar cache expirado enquanto atualiza em background")
):
    """
    Lista documentos processados.

    - SENDER: retorna apenas documentos da própria clínica
    - CHECKER/ADMIN: retorna documentos de todas as clínicas
    """
    try:
        client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")
        user_agent = request.headers.get("user-agent") or "unknown"
        referer = request.headers.get("referer") or "unknown"
        logger.debug(
            "[DOCUMENTS] request user=%s ip=%s ua=%s referer=%s",
            current_user.email,
            client_ip,
            user_agent,
            referer,
        )
        if current_user.role == UserRole.SENDER:
            cache_key = f"{current_user.role.value}:{current_user.clinic_id or 'all'}:{current_user.id}:{compact}"
        else:
            cache_key = f"{current_user.role.value}:{current_user.clinic_id or 'all'}:{compact}"
        now = time.monotonic()
        if cache_seconds > 0:
            cached = _get_cache_entry(cache_key)
            if cached:
                cached_at = cached["cached_at"]
                cached_docs = cached["documents"]
                age = now - cached_at
                if age <= cache_seconds:
                    logger.debug("[DOCUMENTS] Cache hit (fresh %.0fs) key=%s rows=%d", age, cache_key, len(cached_docs))
                    return cached_docs
                if stale_seconds > 0 and age <= stale_seconds:
                    if not cached.get("refreshing"):
                        _set_cache_refreshing(cache_key, True)
                        _refresh_cache_async(
                            cache_key,
                            current_user.role,
                            current_user.clinic_id,
                            compact,
                            current_user.id if current_user.role == UserRole.SENDER else None,
                        )
                    logger.debug("[DOCUMENTS] Cache hit (stale %.0fs) key=%s rows=%d", age, cache_key, len(cached_docs))
                    return cached_docs

        start_time = time.perf_counter()
        documents = _load_documents(
            current_user.role,
            current_user.clinic_id,
            compact,
            user_id=current_user.id if current_user.role == UserRole.SENDER else None,
        )

        if cache_seconds > 0:
            _set_cache_entry(cache_key, documents)

        elapsed = time.perf_counter() - start_time
        try:
            payload_size = len(json.dumps([doc.dict() for doc in documents], default=str).encode("utf-8"))
            logger.debug(f"[DOCUMENTS] Listagem concluída em {elapsed:.2f}s | payload ~{payload_size / 1024:.1f} KB | compact={compact}")
        except Exception:
            logger.debug(f"[DOCUMENTS] Listagem concluída em {elapsed:.2f}s | compact={compact}")

        return documents
    except Exception as e:
        logger.exception(f"Erro ao listar documentos: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao listar documentos: {str(e)}"
        )


@router.get("/{document_id}", response_model=Document)
async def get_document(document_id: str, current_user: User = Depends(get_current_user)):
    """
    Obtém detalhes de um documento específico.

    - SENDER: apenas se o documento pertencer à sua clínica
    - CHECKER/ADMIN: qualquer documento
    """
    try:
        document = user_db.get_document_by_id(document_id)

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Documento não encontrado"
            )

        # Verificar permissão
        if current_user.role == UserRole.SENDER:
            if not current_user.clinic_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Usuário SENDER deve estar associado a uma clínica"
                )
            if document.clinic_id != current_user.clinic_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Você não tem permissão para acessar este documento"
                )

        logger.debug(f"[DOCUMENTS] {current_user.email} acessou documento {document_id}")
        return document

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao obter documento {document_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao obter documento: {str(e)}"
        )


@router.get("/{document_id}/view")
async def view_document(document_id: str, current_user: User = Depends(get_current_user)):
    """
    Retorna o arquivo original do documento para visualização.

    - SENDER: apenas documentos próprios
    - CHECKER/ADMIN: qualquer documento
    """
    try:
        document = user_db.get_document_by_id(document_id)

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Documento não encontrado"
            )

        if current_user.role == UserRole.SENDER:
            if document.uploaded_by_user_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Você não tem permissão para acessar este documento"
                )

        file_path = getattr(document, "file_path", None)
        if not file_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Arquivo do documento não disponível"
            )

        abs_path = os.path.abspath(file_path)
        base_dir = os.path.abspath(settings.DOCUMENT_STORAGE_DIR)
        if not abs_path.startswith(base_dir + os.sep):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Caminho do documento inválido"
            )

        if not os.path.exists(abs_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Arquivo do documento não encontrado"
            )

        media_type, _ = mimetypes.guess_type(document.filename)
        response = FileResponse(
            abs_path,
            media_type=media_type or "application/octet-stream",
            filename=document.filename,
        )
        response.headers["Content-Disposition"] = f'inline; filename="{document.filename}"'
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao visualizar documento {document_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao visualizar documento: {str(e)}"
        )


@router.patch("/{document_id}", response_model=Document)
async def update_document(
    document_id: str,
    payload: DocumentUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """
    Atualiza status de validação e dados do documento.

    - SENDER: apenas documentos da própria clínica
    - CHECKER/ADMIN: qualquer documento
    """
    try:
        document = user_db.get_document_by_id(document_id)
        if not document:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento não encontrado")

        # Verificar permissão
        if current_user.role == UserRole.SENDER:
            if not current_user.clinic_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuário SENDER deve estar associado a uma clínica")
            if document.clinic_id != current_user.clinic_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Você não tem permissão para atualizar este documento")

        updated = user_db.update_document(
            document_id=document_id,
            validation_status=payload.validation_status,
            exams_found=payload.exams_found,
            exams_ocr=payload.exams_ocr,
            exams_brnet=payload.exams_brnet,
            ocr_markdown=payload.ocr_markdown,
            run_id=payload.run_id,
            result_payload=payload.result_payload,
        )
        should_upload = (
            payload.validation_status == "validated"
            and isinstance(payload.result_payload, dict)
            and payload.result_payload.get("reviewed_by")
        )
        if should_upload and background_tasks is not None:
            logger.info(
                "[DRIVE] Agendando upload doc_id=%s reviewer=%s",
                document_id,
                payload.result_payload.get("reviewed_by") if isinstance(payload.result_payload, dict) else None,
            )
            background_tasks.add_task(drive_service.upload_document_to_drive, updated)
        try:
            set_audit_context(
                {
                    "action": "documents.update",
                    "resource": "documents",
                    "resource_id": document_id,
                    "metadata": {
                        "before_status": document.validation_status,
                        "after_status": payload.validation_status,
                    },
                }
            )
        except Exception as audit_error:
            logger.warning(f"Falha ao preparar auditoria do documento {document_id}: {audit_error}")
        return updated
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao atualizar documento {document_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao atualizar documento: {str(e)}"
        )
