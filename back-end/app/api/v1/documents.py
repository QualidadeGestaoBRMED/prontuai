"""
Endpoints para gerenciamento de documentos.
"""
from fastapi import APIRouter, HTTPException, status, Depends, Query, Request, BackgroundTasks
from fastapi.responses import FileResponse
from typing import List, Any
from app.core.auth import get_current_user, require_admin
from app.core.database import user_db
from app.models.user import User, UserRole
from app.models.document import (
    Document,
    DocumentUpdate,
    DocumentQueue,
    PaginatedDocumentsResponse,
)
from app.core.logging import set_audit_context
from app.core.config import settings
from app.services import drive_service
import logging
import time
import json
import threading
import mimetypes
import os
import re
from datetime import datetime

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
        if not doc.uploaded_by_user_email:
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


def _status_from_validation(doc: Document) -> str:
    if doc.validation_status == "validated":
        return "approved"
    if doc.validation_status == "rejected":
        return "rejected"
    return "pending_review"


def _in_memory_paged_documents(
    docs: List[Document],
    *,
    page: int,
    page_size: int,
    queue: DocumentQueue | None,
    status_filter: str | None,
    search: str | None,
    sort_by: str,
    sort_dir: str,
) -> dict[str, Any]:
    normalized_search = (search or "").strip().lower()

    filtered = docs
    if normalized_search:
        filtered = [
            d for d in filtered
            if normalized_search in (d.filename or "").lower()
            or normalized_search in (d.cpf or "").lower()
            or normalized_search in (d.uploaded_by_user_email or "").lower()
        ]

    summary_counts = {"approved": 0, "rejected": 0, "pending_review": 0, "total": len(filtered)}
    for doc in filtered:
        summary_counts[_status_from_validation(doc)] += 1

    if queue == DocumentQueue.PENDENTES:
        filtered = [d for d in filtered if d.validation_status != "validated"]
    elif queue == DocumentQueue.CHECAGEM:
        filtered = [
            d for d in filtered
            if d.validation_status in {"validated", "pending"}
            or (d.validation_status == "rejected" and not d.reviewed_by)
        ]

    if status_filter == "approved":
        filtered = [d for d in filtered if d.validation_status == "validated"]
    elif status_filter == "rejected":
        filtered = [d for d in filtered if d.validation_status == "rejected"]
    elif status_filter == "pending_review":
        filtered = [d for d in filtered if d.validation_status in {"pending", None}]

    def _to_ts(value: Any) -> float:
        if not value:
            return 0.0
        try:
            return value.timestamp()
        except Exception:
            return 0.0

    reverse = sort_dir.lower() != "asc"
    if sort_by == "updated_at":
        filtered.sort(key=lambda d: _to_ts(d.updated_at), reverse=reverse)
    elif sort_by == "filename":
        filtered.sort(key=lambda d: (d.filename or "").lower(), reverse=reverse)
    elif sort_by == "cpf":
        filtered.sort(key=lambda d: (d.cpf or "").lower(), reverse=reverse)
    elif sort_by == "status":
        filtered.sort(key=lambda d: (d.validation_status or "").lower(), reverse=reverse)
    else:
        filtered.sort(key=lambda d: _to_ts(d.uploaded_at), reverse=reverse)

    total_items = len(filtered)
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    safe_page = max(1, min(page, total_pages))
    start = (safe_page - 1) * page_size
    end = start + page_size
    items = filtered[start:end]

    return {
        "items": items,
        "page": safe_page,
        "page_size": page_size,
        "total_items": total_items,
        "total_pages": total_pages,
        "has_next": safe_page < total_pages,
        "summary_counts": summary_counts,
    }


@router.get("/paged", response_model=PaginatedDocumentsResponse)
async def list_documents_paged(
    current_user: User = Depends(get_current_user),
    queue: DocumentQueue | None = Query(None, description="Fila para otimizar a consulta"),
    compact: bool = Query(True, description="Remove campos pesados do payload para melhorar performance"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, max_length=120),
    status_filter: str | None = Query(None, pattern="^(approved|rejected|pending_review)$"),
    sort_by: str = Query("uploaded_at", pattern="^(uploaded_at|updated_at|filename|cpf|status)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
):
    """
    Lista documentos com paginação e filtros server-side.
    """
    try:
        role = current_user.role
        user_id = current_user.id if role == UserRole.SENDER else None
        clinic_id = current_user.clinic_id

        if hasattr(user_db, "list_documents_paged"):
            payload = user_db.list_documents_paged(
                role=role,
                clinic_id=clinic_id,
                user_id=user_id,
                queue=queue.value if queue else None,
                page=page,
                page_size=page_size,
                use_compact_payload=compact,
                search=search,
                status_filter=status_filter,
                sort_by=sort_by,
                sort_dir=sort_dir,
            )
        else:
            docs = _load_documents(
                role,
                clinic_id,
                compact,
                user_id=user_id,
            )
            payload = _in_memory_paged_documents(
                docs,
                page=page,
                page_size=page_size,
                queue=queue,
                status_filter=status_filter,
                search=search,
                sort_by=sort_by,
                sort_dir=sort_dir,
            )

        items = payload.get("items", [])
        if role == UserRole.SENDER and current_user.email:
            for doc in items:
                if doc.uploaded_by_user_id == current_user.id and not doc.uploaded_by_user_email:
                    doc.uploaded_by_user_email = current_user.email

        return PaginatedDocumentsResponse(
            items=items,
            page=int(payload.get("page", page)),
            page_size=int(payload.get("page_size", page_size)),
            total_items=int(payload.get("total_items", 0)),
            total_pages=int(payload.get("total_pages", 1)),
            has_next=bool(payload.get("has_next", False)),
            summary_counts=payload.get("summary_counts") or {},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Erro ao listar documentos paginados: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar documentos paginados."
        ) from exc

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

        if current_user.role == UserRole.SENDER and current_user.email:
            for doc in documents:
                if doc.uploaded_by_user_id == current_user.id:
                    doc.uploaded_by_user_email = current_user.email

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

        base_dir = os.path.abspath(settings.DOCUMENT_STORAGE_DIR)
        base_dir_prefix = base_dir + os.sep
        candidate_paths: list[str] = []
        file_path = getattr(document, "file_path", None)

        def add_candidate(path: str | None) -> None:
            if not path:
                return
            if path not in candidate_paths:
                candidate_paths.append(path)

        def safe_filename(filename: str | None) -> str:
            base = os.path.basename(filename or "documento")
            safe = re.sub(r"[^A-Za-z0-9._-]", "_", base)
            return safe or "documento"

        add_candidate(file_path)
        # Se vier path relativo, resolve dentro do diretório de uploads
        if file_path and not os.path.isabs(file_path):
            add_candidate(os.path.join(base_dir, file_path))
        # Fallback para paths absolutos antigos: tenta basename no diretório atual
        if file_path:
            add_candidate(os.path.join(base_dir, os.path.basename(file_path)))

        # Fallback final para registros antigos sem file_path persistido:
        # arquivos salvos pelo upload usam "<prefixo>_<nome_sanitizado>".
        original_safe_name = safe_filename(document.filename)
        add_candidate(os.path.join(base_dir, original_safe_name))
        try:
            for entry in os.scandir(base_dir):
                if not entry.is_file():
                    continue
                if entry.name == original_safe_name or entry.name.endswith(f"_{original_safe_name}"):
                    add_candidate(entry.path)
        except FileNotFoundError:
            pass

        resolved_path: str | None = None
        for candidate in candidate_paths:
            abs_candidate = os.path.abspath(candidate)
            if not abs_candidate.startswith(base_dir_prefix):
                continue
            if os.path.exists(abs_candidate):
                resolved_path = abs_candidate
                break

        if not resolved_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Arquivo do documento não encontrado"
            )

        # Se o path salvo estava fora do padrão atual, atualiza para evitar novos 404
        try:
            if os.path.abspath(file_path) != resolved_path:
                user_db.update_document(document_id=document_id, file_path=resolved_path)
        except Exception as update_error:
            logger.warning(f"Falha ao atualizar file_path do documento {document_id}: {update_error}")

        media_type, _ = mimetypes.guess_type(document.filename)
        response = FileResponse(
            resolved_path,
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

        approval_reason = payload.approval_reason
        rejection_reason = payload.rejection_reason
        payload_result = payload.result_payload if isinstance(payload.result_payload, dict) else None
        existing_result = document.result_payload if isinstance(document.result_payload, dict) else None
        reviewed_by = None
        reviewed_at = None
        if payload_result is not None:
            if approval_reason is None:
                approval_reason = payload_result.get("approvalReason")
            if rejection_reason is None:
                rejection_reason = payload_result.get("rejectionReason")
            reviewed_by = payload_result.get("reviewed_by") or payload_result.get("reviewedBy")
            reviewed_at = payload_result.get("reviewed_at") or payload_result.get("reviewedAt")

        existing_reviewed_by = None
        existing_reviewed_at = None
        if existing_result is not None:
            existing_reviewed_by = existing_result.get("reviewed_by") or existing_result.get("reviewedBy")
            existing_reviewed_at = existing_result.get("reviewed_at") or existing_result.get("reviewedAt")

        if not reviewed_by:
            reviewed_by = existing_reviewed_by
        if not reviewed_at:
            reviewed_at = existing_reviewed_at

        is_human_reviewer = current_user.role in [UserRole.ADMIN, UserRole.CHECKER]
        effective_status = payload.validation_status or document.validation_status

        if effective_status == "validated" and is_human_reviewer and not reviewed_by:
            reviewed_by = current_user.email
            reviewed_at = reviewed_at or datetime.utcnow().isoformat()
            merged_payload = dict(payload_result) if payload_result is not None else dict(existing_result or {})
            merged_payload["reviewed_by"] = reviewed_by
            merged_payload["reviewed_at"] = reviewed_at
            payload.result_payload = merged_payload
            payload_result = merged_payload
        reviewed_at_dt = None
        if reviewed_at:
            try:
                reviewed_at_dt = datetime.fromisoformat(str(reviewed_at).replace("Z", "+00:00"))
            except Exception:
                reviewed_at_dt = None

        try:
            updated = user_db.update_document(
                document_id=document_id,
                validation_status=payload.validation_status,
                exams_found=payload.exams_found,
                exams_ocr=payload.exams_ocr,
                exams_brnet=payload.exams_brnet,
                ocr_markdown=payload.ocr_markdown,
                run_id=payload.run_id,
                result_payload=payload.result_payload,
                reviewed_by=reviewed_by,
                reviewed_at=reviewed_at_dt,
                approval_reason=approval_reason,
                rejection_reason=rejection_reason,
            )
        except TypeError:
            # Compatibilidade com implementações antigas do backend de persistência.
            updated = user_db.update_document(
                document_id=document_id,
                validation_status=payload.validation_status,
                exams_found=payload.exams_found,
                exams_ocr=payload.exams_ocr,
                exams_brnet=payload.exams_brnet,
                ocr_markdown=payload.ocr_markdown,
                run_id=payload.run_id,
                result_payload=payload.result_payload,
                approval_reason=approval_reason,
                rejection_reason=rejection_reason,
            )
        payload_reviewed_by = None
        if isinstance(payload_result, dict):
            payload_reviewed_by = payload_result.get("reviewed_by") or payload_result.get("reviewedBy")
        should_upload = (
            effective_status == "validated"
            and is_human_reviewer
            and (payload.validation_status == "validated" or payload_reviewed_by or reviewed_by)
        )
        if should_upload and background_tasks is not None:
            logger.info(
                "[DRIVE] Agendando upload doc_id=%s reviewer=%s",
                document_id,
                payload_reviewed_by or reviewed_by,
            )
            background_tasks.add_task(drive_service.upload_document_to_drive, updated)
        elif payload.validation_status == "validated":
            logger.warning(
                "[DRIVE] Upload não agendado doc_id=%s reviewed_by=%s role=%s",
                document_id,
                payload_reviewed_by or reviewed_by,
                current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
            )
        try:
            set_audit_context(
                {
                    "action": "documents.update",
                    "resource": "documents",
                    "resource_id": document_id,
                        "metadata": {
                            "before_status": document.validation_status,
                            "after_status": effective_status,
                        "approval_reason": approval_reason,
                        "rejection_reason": rejection_reason,
                        "validation_message": (
                            payload.result_payload.get("validation_result", {}).get("analysis")
                            if isinstance(payload.result_payload, dict)
                            else None
                        ),
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
