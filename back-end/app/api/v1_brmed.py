from fastapi import APIRouter, HTTPException, status, UploadFile, File, Body, Depends, Request
from fastapi.responses import StreamingResponse
from app.services import workflow_service, brmed_service
from app.core.job_manager import job_manager
from app.core.auth import create_upload_token, require_sender, require_upload_sender, get_current_user
from app.models.user import User, UserRole
from app.core.database import user_db
from app.core.logging import set_audit_context
from app.models.audit_log import AuditLogCreate
from app.core.config import settings
from pydantic import BaseModel
import logging
import json
import asyncio
import tempfile
import shutil
import os
import re
import time
import hashlib
import threading
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timedelta

router = APIRouter()
logger = logging.getLogger(__name__)

_UPLOAD_DEDUP_LOCK = asyncio.Lock()
_RECENT_UPLOADS: dict[str, tuple[float, str | None]] = {}


class ConsultarBrmedRequest(BaseModel):
    cpf: str | None = None
    passaporte: str | None = None
    cnpj: str | None = None


class UploadTokenResponse(BaseModel):
    upload_token: str
    expires_in_seconds: int = 600
    token_type: str = "Bearer"

def _purge_recent_uploads(now: float, window_seconds: int) -> None:
    if window_seconds <= 0:
        _RECENT_UPLOADS.clear()
        return
    expired = [key for key, (ts, _) in _RECENT_UPLOADS.items() if now - ts > window_seconds]
    for key in expired:
        _RECENT_UPLOADS.pop(key, None)

def _safe_filename(filename: str) -> str:
    base = os.path.basename(filename or "documento")
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    return safe or "documento"

def _store_upload_bytes(content: bytes, original_name: str, prefix: str | None) -> str:
    storage_dir = Path(settings.DOCUMENT_STORAGE_DIR)
    storage_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_filename(original_name)
    if prefix:
        safe_name = f"{prefix}_{safe_name}"
    dest_path = storage_dir / safe_name
    with open(dest_path, "wb") as f:
        f.write(content)
    return str(dest_path)

def _store_upload_file(file_path: str, original_name: str, prefix: str | None) -> str:
    storage_dir = Path(settings.DOCUMENT_STORAGE_DIR)
    storage_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_filename(original_name)
    if prefix:
        safe_name = f"{prefix}_{safe_name}"
    dest_path = storage_dir / safe_name
    shutil.copyfile(file_path, dest_path)
    return str(dest_path)


def _get_clinic_cnpj(clinic_id: str | None) -> str | None:
    if not clinic_id:
        return None
    try:
        clinic = user_db.get_clinic_by_id(clinic_id)
        cnpj = getattr(clinic, "cnpj", None) if clinic else None
        if not cnpj:
            return None
        digits = re.sub(r"\D", "", cnpj)
        return digits if len(digits) == 14 else None
    except Exception as exc:
        logger.warning(f"[CLINIC] Falha ao obter CNPJ da clínica {clinic_id}: {exc}")
        return None


@router.post("/upload-token", response_model=UploadTokenResponse, summary="Gerar token curto para upload direto")
async def create_direct_upload_token(current_user: User = Depends(require_sender)):
    """
    Emite token curto e limitado ao endpoint de upload direto.

    O front chama este endpoint via proxy (requisição pequena) e usa o token
    apenas para enviar o arquivo diretamente ao backend, sem passar pela Vercel.
    """
    return UploadTokenResponse(upload_token=create_upload_token(current_user))


def _run_background_job_in_thread(**kwargs) -> None:
    """
    Executa o processamento assíncrono em thread dedicada.

    Isso evita bloquear o worker HTTP (e o polling de /v1/jobs) quando o
    processamento do documento leva vários minutos.
    """
    job_id = kwargs.get("job_id", "unknown")
    try:
        asyncio.run(process_document_background(**kwargs))
    except Exception as exc:
        logger.exception("[JOB %s] Falha inesperada no worker thread: %s", job_id, exc)
        if isinstance(job_id, str) and job_id:
            try:
                asyncio.run(job_manager.fail_job(job_id, f"Falha interna no worker thread: {exc}"))
            except Exception:
                logger.exception("[JOB %s] Não foi possível marcar job como failed após exceção do thread worker", job_id)

@router.post("/processar-documento", summary="Processar documento completo com OCR, BRMED e Validação")
async def processar_documento_completo_api(
    arquivo: UploadFile = File(...),
    exames_obrigatorios: str = Body(..., embed=True), # Recebe como string JSON
    current_user: User = Depends(require_sender) # Requer autenticação SENDER
):
    if not arquivo:
        logger.warning("Arquivo não enviado na requisição de processamento completo.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Arquivo não enviado.")

# Log de entrada da requisição
    file_size = "desconhecido"
    stored_path = None
    content_hash = None
    try:
        content = await arquivo.read()
        file_size = f"{len(content) / 1024 / 1024:.2f}MB"
        if content:
            content_hash = hashlib.sha256(content).hexdigest()
        try:
            stored_path = _store_upload_bytes(content, arquivo.filename, str(uuid4()))
        except Exception as store_error:
            logger.warning(f"[REQUEST] Falha ao salvar arquivo para visualização: {store_error}")
        await arquivo.seek(0)  # Volta ao início para o workflow poder ler
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[REQUEST] Falha ao ler arquivo enviado: %s", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Falha ao ler arquivo enviado.") from exc

    logger.info(
        "[REQUEST] Documento recebido uploader_id=%s email=%s role=%s clinic_id=%s file=%s size=%s",
        current_user.id,
        current_user.email,
        current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
        current_user.clinic_id,
        arquivo.filename,
        file_size,
    )

    try:
        # Converte a string JSON de exames_obrigatorios para lista
        exames_obrigatorios_list = json.loads(exames_obrigatorios)
        logger.info(f"[REQUEST] Exames obrigatórios fornecidos: {len(exames_obrigatorios_list)}")
    except json.JSONDecodeError:
        logger.error("Formato inválido para exames_obrigatorios. Esperado JSON array de strings.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Exames obrigatórios devem ser um array JSON válido.")

    try:
        clinic_cnpj = _get_clinic_cnpj(current_user.clinic_id)
        resultado = await workflow_service.processar_documento_completo(
            arquivo,
            exames_obrigatorios_list,
            clinic_cnpj=clinic_cnpj,
        )
        logger.info(f"[REQUEST] Processamento concluído com sucesso para: {arquivo.filename}")

        # Salvar documento no banco de dados
        if current_user.clinic_id:
            try:
                # Extrair informações do resultado
                cpf = (
                    resultado.get('cpf_processado')
                    or resultado.get('cpf')
                    or resultado.get("identificador_consulta")
                )
                exams_ocr = resultado.get('exames_ocr', []) or resultado.get('ocr_result', {}).get('exames_extraidos', [])
                exams_brnet = resultado.get('exames_brnet', []) or resultado.get('brmed_result', {}).get('exames_obrigatorios', [])
                exams_found = exams_ocr
                ocr_markdown = resultado.get('ocr_result', {}).get('text', '')
                validation_status = 'validated' if not resultado.get('validation_result', {}).get('exames_faltantes') and resultado.get('status') == 'success' else 'pending'
                if resultado.get('status') == 'error':
                    validation_status = 'rejected'

                # Criar documento no banco
                clinic_id = current_user.clinic_id
                if not clinic_id:
                    clinics = user_db.get_all_clinics()
                    clinic_id = clinics[0].id if clinics else None
                if not clinic_id:
                    try:
                        clinic = user_db.create_clinic(name="Clinica Dev")
                        clinic_id = clinic.id
                        logger.info("[DB] Clinica criada automaticamente para salvar documento (sync)")
                    except Exception as clinic_error:
                        logger.error(f"[DB] Falha ao criar clinica automaticamente (sync): {clinic_error}")
                if not clinic_id:
                    raise ValueError("clinic_id não encontrado para salvar documento")

                confidence_score = resultado.get("confidence_score")
                confidence_details = resultado.get("confidence_details", {})
                document = user_db.create_document(
                    clinic_id=clinic_id,
                    uploaded_by_user_id=current_user.id,
                    filename=arquivo.filename,
                    file_path=stored_path,
                    content_hash=content_hash,
                    uploaded_by_user_email=current_user.email,
                    cpf=cpf,
                    exams_found=exams_found,
                    exams_ocr=exams_ocr,
                    exams_brnet=exams_brnet,
                    validation_status=validation_status,
                    ocr_markdown=ocr_markdown,
                    run_id=resultado.get("run_id"),
                    result_payload=resultado,
                    confidence_score=confidence_score,
                    quality_score=confidence_details.get("quality_score"),
                    mandatory_coverage=confidence_details.get("mandatory_coverage")
                )

                logger.info(f"[DB] Documento salvo com ID: {document.id}")
                resultado['document_id'] = document.id
                try:
                    set_audit_context(
                        {
                            "action": "documents.processed",
                            "resource": "documents",
                            "resource_id": document.id,
                            "metadata": {
                                "document_id": document.id,
                                "cpf": cpf,
                                "filename": arquivo.filename,
                                "run_id": resultado.get("run_id"),
                                "validation_status": validation_status,
                                "async": False,
                            },
                        }
                    )
                except Exception:
                    pass
            except Exception as db_error:
                logger.error(f"[DB] Erro ao salvar documento: {db_error}")
                # Não interromper o fluxo se falhar ao salvar no banco

        return resultado
    except Exception as e:
        logger.exception(f"Erro inesperado no processamento completo do documento: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro inesperado no processamento do documento.")

@router.post("/processar-documento-stream", summary="Processar documento com feedback em tempo real (SSE)")
async def processar_documento_stream_api(
    request: Request,
    arquivo: UploadFile = File(...),
    exames_obrigatorios: str = Body(..., embed=True),
    current_user: User = Depends(require_sender),
):
    """Endpoint com Server-Sent Events para feedback de progresso em tempo real."""

    if not arquivo:
        logger.warning("Arquivo não enviado na requisição de processamento stream.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Arquivo não enviado.")

    # Log de entrada e leitura do arquivo (evita leitura duplicada)
    file_size = "desconhecido"
    content = b""
    try:
        content = await arquivo.read()
        file_size = f"{len(content) / 1024 / 1024:.2f}MB"
        await arquivo.seek(0)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[REQUEST-STREAM] Falha ao ler arquivo enviado: %s", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Falha ao ler arquivo enviado.") from exc

    logger.info(
        "[REQUEST-STREAM] Documento recebido uploader_id=%s email=%s clinic_id=%s file=%s size=%s",
        current_user.id,
        current_user.email,
        current_user.clinic_id,
        arquivo.filename,
        file_size,
    )

    dedup_window = int(os.getenv("UPLOAD_DEDUP_WINDOW_SECONDS", "0"))
    if dedup_window > 0 and content:
        fingerprint = hashlib.sha256(content).hexdigest()
        client_ip = "unknown"
        if request is not None:
            client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")
        dedup_key = f"stream:{client_ip}:{fingerprint}"
        now = time.monotonic()
        async with _UPLOAD_DEDUP_LOCK:
            _purge_recent_uploads(now, dedup_window)
            existing = _RECENT_UPLOADS.get(dedup_key)
            if existing and now - existing[0] <= dedup_window:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Upload duplicado detectado. Aguarde o processamento anterior."
                )
            _RECENT_UPLOADS[dedup_key] = (now, None)

    try:
        exames_obrigatorios_list = json.loads(exames_obrigatorios)
        logger.info(f"[REQUEST-STREAM] Exames obrigatórios: {len(exames_obrigatorios_list)}")
    except json.JSONDecodeError:
        logger.error("Formato inválido para exames_obrigatorios.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Exames obrigatórios devem ser um array JSON válido.")

    async def event_generator():
        """Gerador de eventos SSE."""
        try:
            # Enviar evento inicial
            yield f"data: {json.dumps({'progress': 0, 'step': 'inicio', 'message': 'Documento recebido, iniciando processamento...'})}\n\n"
            await asyncio.sleep(0.1)

            # Lista para coletar eventos de progresso
            progress_events = []

            # Callback para receber atualizações do workflow
            async def progress_callback(progress: int, step: str, message: str):
                event_data = json.dumps({'progress': progress, 'step': step, 'message': message})
                logger.info(f"[PROGRESS] {progress}% - {step}: {message}")
                progress_events.append(f"data: {event_data}\n\n")

            # Processar documento com callback
            resultado = await workflow_service.processar_documento_completo(
                arquivo,
                exames_obrigatorios_list,
                progress_callback=progress_callback,
                clinic_cnpj=_get_clinic_cnpj(current_user.clinic_id),
            )

            # Yield todos os eventos coletados
            for event in progress_events:
                yield event
                await asyncio.sleep(0.01)

            # Enviar resultado final
            yield f"data: {json.dumps({'progress': 100, 'step': 'concluido', 'message': 'Processamento concluído!', 'resultado': resultado})}\n\n"
            logger.info(f"[REQUEST-STREAM] Processamento concluído para: {arquivo.filename}")

        except Exception as e:
            logger.exception(f"Erro no processamento stream: {e}")
            error_data = json.dumps({'progress': -1, 'step': 'erro', 'message': f'Erro: {str(e)}'})
            yield f"data: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Desabilita buffering do nginx
        }
    )

@router.post("/processar-documento-async", summary="Processar documento em background (assíncrono)")
async def processar_documento_async_api(
    arquivo: UploadFile = File(...),
    exames_obrigatorios: str = Body(..., embed=True),
    current_user: User = Depends(require_upload_sender)
):
    """
    Inicia processamento de documento em background e retorna job_id imediatamente.

    Este endpoint evita timeouts de workers ao processar documentos grandes.
    Use GET /v1/jobs/{job_id} para consultar o progresso e resultado.

    Retorna:
    - job_id: ID único do job para consultar status
    - status: "pending" (job criado e aguardando processamento)
    - message: Mensagem informativa
    """
    if not arquivo:
        logger.warning("Arquivo não enviado na requisição async.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Arquivo não enviado.")

    # Log de entrada
    file_size = "desconhecido"
    content = b""
    try:
        content = await arquivo.read()
        file_size = f"{len(content) / 1024 / 1024:.2f}MB"
        await arquivo.seek(0)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[REQUEST-ASYNC] Falha ao ler arquivo enviado: %s", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Falha ao ler arquivo enviado.") from exc

    logger.info(
        "[REQUEST-ASYNC] Documento recebido uploader_id=%s email=%s role=%s clinic_id=%s file=%s size=%s",
        current_user.id,
        current_user.email,
        current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
        current_user.clinic_id,
        arquivo.filename,
        file_size,
    )

    # Parse exames obrigatórios
    try:
        exames_obrigatorios_list = json.loads(exames_obrigatorios)
        logger.info(f"[REQUEST-ASYNC] Exames obrigatórios: {len(exames_obrigatorios_list)}")
    except json.JSONDecodeError:
        logger.error("Formato inválido para exames_obrigatorios.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Exames obrigatórios devem ser um array JSON válido."
        )

    # Deduplicação persistente (DB) e in-memory
    dedup_window = int(os.getenv("UPLOAD_DEDUP_WINDOW_SECONDS", "0"))
    fingerprint = hashlib.sha256(content or b"").hexdigest() if dedup_window > 0 and content else ""
    content_hash = fingerprint or None
    dedup_key = f"{current_user.id}:{fingerprint}" if fingerprint else ""
    now = time.monotonic()
    job_id = None

    if content_hash:
        dedup_hard = os.getenv("UPLOAD_DEDUP_HARD", "false").lower() == "true"
        if dedup_hard:
            get_any = getattr(user_db, "get_document_by_hash", None)
            if callable(get_any):
                try:
                    existing_doc = get_any(
                        uploaded_by_user_id=current_user.id,
                        content_hash=content_hash,
                        clinic_id=current_user.clinic_id,
                    )
                    if existing_doc:
                        result_payload = existing_doc.result_payload if isinstance(existing_doc.result_payload, dict) else {}
                        if not isinstance(result_payload, dict):
                            result_payload = {}
                        if existing_doc.id and result_payload.get("document_id") is None:
                            result_payload = dict(result_payload)
                            result_payload["document_id"] = existing_doc.id
                        job_id = await job_manager.create_job(
                            job_type="document_processing",
                            metadata={
                                "filename": existing_doc.filename,
                                "file_size": file_size,
                                "num_exames_obrigatorios": len(exames_obrigatorios_list),
                                "uploaded_by_user_id": current_user.id,
                                "uploaded_by_user_email": current_user.email,
                                "clinic_id": current_user.clinic_id,
                                "duplicate_of": existing_doc.id,
                            },
                        )
                        await job_manager.complete_job(job_id, result_payload)
                        logger.warning(
                            "[REQUEST-ASYNC] Upload duplicado (hard) detectado (doc=%s). Resultado reutilizado.",
                            existing_doc.id,
                        )
                        return {
                            "job_id": job_id,
                            "status": "duplicate",
                            "message": "Upload duplicado detectado. Resultado reutilizado.",
                            "poll_url": f"/v1/jobs/{job_id}",
                            "document_id": existing_doc.id,
                        }
                except Exception as dedup_error:
                    logger.warning("[REQUEST-ASYNC] Falha ao verificar duplicidade hard: %s", dedup_error)

    if dedup_window > 0 and content_hash:
        get_recent = getattr(user_db, "get_recent_document_by_hash", None)
        if callable(get_recent):
            try:
                since = datetime.utcnow() - timedelta(seconds=dedup_window)
                existing_doc = get_recent(
                    uploaded_by_user_id=current_user.id,
                    content_hash=content_hash,
                    since=since,
                    clinic_id=current_user.clinic_id,
                )
                if existing_doc:
                    result_payload = existing_doc.result_payload if isinstance(existing_doc.result_payload, dict) else {}
                    if not isinstance(result_payload, dict):
                        result_payload = {}
                    if existing_doc.id and result_payload.get("document_id") is None:
                        result_payload = dict(result_payload)
                        result_payload["document_id"] = existing_doc.id
                    job_id = await job_manager.create_job(
                        job_type="document_processing",
                        metadata={
                            "filename": existing_doc.filename,
                            "file_size": file_size,
                            "num_exames_obrigatorios": len(exames_obrigatorios_list),
                            "uploaded_by_user_id": current_user.id,
                            "uploaded_by_user_email": current_user.email,
                            "clinic_id": current_user.clinic_id,
                            "duplicate_of": existing_doc.id,
                        },
                    )
                    await job_manager.complete_job(job_id, result_payload)
                    logger.warning(
                        "[REQUEST-ASYNC] Upload duplicado detectado (doc=%s). Resultado reutilizado.",
                        existing_doc.id,
                    )
                    return {
                        "job_id": job_id,
                        "status": "duplicate",
                        "message": "Upload duplicado detectado. Resultado reutilizado.",
                        "poll_url": f"/v1/jobs/{job_id}",
                        "document_id": existing_doc.id,
                    }
            except Exception as dedup_error:
                logger.warning("[REQUEST-ASYNC] Falha ao verificar duplicidade persistente: %s", dedup_error)

    if dedup_window > 0 and dedup_key:
        async with _UPLOAD_DEDUP_LOCK:
            _purge_recent_uploads(now, dedup_window)
            existing = _RECENT_UPLOADS.get(dedup_key)
            if existing and existing[1] and now - existing[0] <= dedup_window:
                logger.warning(
                    "[REQUEST-ASYNC] Upload duplicado ignorado (job=%s filename=%s)",
                    existing[1],
                    arquivo.filename,
                )
                return {
                    "job_id": existing[1],
                    "status": "duplicate",
                    "message": "Upload duplicado detectado. Reutilizando job existente.",
                    "poll_url": f"/v1/jobs/{existing[1]}",
                }

            job_id = await job_manager.create_job(
                job_type="document_processing",
                metadata={
                    "filename": arquivo.filename,
                    "file_size": file_size,
                    "num_exames_obrigatorios": len(exames_obrigatorios_list),
                    "uploaded_by_user_id": current_user.id,
                    "uploaded_by_user_email": current_user.email,
                    "clinic_id": current_user.clinic_id,
                }
            )
            _RECENT_UPLOADS[dedup_key] = (now, job_id)
    else:
        job_id = await job_manager.create_job(
            job_type="document_processing",
            metadata={
                "filename": arquivo.filename,
                "file_size": file_size,
                "num_exames_obrigatorios": len(exames_obrigatorios_list),
                "uploaded_by_user_id": current_user.id,
                "uploaded_by_user_email": current_user.email,
                "clinic_id": current_user.clinic_id,
            }
        )

    # Salvar arquivo temporariamente (UploadFile não pode ser passado para background task)
    temp_file_path = None
    stored_path = None
    try:
        # Criar arquivo temporário
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file_path = temp_file.name
            if not content:
                content = await arquivo.read()
            temp_file.write(content)

        logger.info(f"[JOB {job_id}] Arquivo salvo temporariamente: {temp_file_path}")
        try:
            stored_path = _store_upload_file(temp_file_path, arquivo.filename, job_id)
            logger.info(f"[JOB {job_id}] Arquivo salvo para visualização: {stored_path}")
        except Exception as store_error:
            logger.warning(f"[JOB {job_id}] Falha ao salvar arquivo para visualização: {store_error}")

        thread_kwargs = {
            "job_id": job_id,
            "file_path": temp_file_path,
            "stored_path": stored_path,
            "filename": arquivo.filename,
            "exames_obrigatorios": exames_obrigatorios_list,
            "uploaded_by_user_id": current_user.id,
            "clinic_id": current_user.clinic_id,
            "clinic_cnpj": _get_clinic_cnpj(current_user.clinic_id),
            "uploaded_by_user_email": current_user.email,
            "content_hash": content_hash,
        }
        worker = threading.Thread(
            target=_run_background_job_in_thread,
            kwargs=thread_kwargs,
            daemon=True,
            name=f"job-worker-{job_id[:8]}",
        )
        worker.start()

        logger.info(f"[JOB {job_id}] Task iniciada em thread dedicada ({worker.name})")

        return {
            "job_id": job_id,
            "status": "pending",
            "message": f"Documento {arquivo.filename} recebido. Processamento iniciado em background.",
            "poll_url": f"/v1/jobs/{job_id}"
        }

    except Exception as e:
        if dedup_window > 0 and dedup_key and job_id:
            async with _UPLOAD_DEDUP_LOCK:
                _RECENT_UPLOADS.pop(dedup_key, None)
        # Cleanup em caso de erro
        if temp_file_path:
            try:
                os.unlink(temp_file_path)
            except:
                pass
        logger.exception(f"Erro ao iniciar processamento assíncrono: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao iniciar processamento: {str(e)}"
        )


async def process_document_background(
    job_id: str,
    file_path: str,
    stored_path: str | None,
    filename: str,
    exames_obrigatorios: list[str],
    uploaded_by_user_id: str,
    clinic_id: str | None,
    clinic_cnpj: str | None,
    uploaded_by_user_email: str,
    content_hash: str | None
):
    """
    Processa documento em background task.

    Args:
        job_id: ID do job
        file_path: Caminho do arquivo temporário
        filename: Nome original do arquivo
        exames_obrigatorios: Lista de exames obrigatórios
    """
    try:
        logger.info(
            "[JOB %s] Iniciando processamento em background uploader_id=%s email=%s clinic_id=%s file=%s",
            job_id,
            uploaded_by_user_id,
            uploaded_by_user_email,
            clinic_id,
            filename,
        )
        await job_manager.start_job(job_id)

        # Criar callback de progresso
        progress_callback = await job_manager.create_progress_callback(job_id)

        # Criar UploadFile a partir do arquivo temporário
        # Nota: FastAPI UploadFile não pode ser recriado facilmente de um path
        # então vamos ler o arquivo e processar diretamente
        from fastapi import UploadFile
        from io import BytesIO

        with open(file_path, "rb") as f:
            file_content = f.read()
        if not content_hash and file_content:
            content_hash = hashlib.sha256(file_content).hexdigest()

        # Criar UploadFile fake
        upload_file = UploadFile(
            filename=filename,
            file=BytesIO(file_content)
        )

        # Processar documento
        resultado = await workflow_service.processar_documento_completo(
            upload_file,
            exames_obrigatorios,
            progress_callback=progress_callback,
            clinic_cnpj=clinic_cnpj,
        )

        # Salvar documento no banco
        try:
            cpf = (
                resultado.get('cpf_processado')
                or resultado.get('cpf')
                or resultado.get("identificador_consulta")
            )
            exams_ocr = resultado.get('exames_ocr', []) or resultado.get('ocr_result', {}).get('exames_extraidos', [])
            exams_brnet = resultado.get('exames_brnet', []) or resultado.get('brmed_result', {}).get('exames_obrigatorios', [])
            exams_found = exams_ocr
            ocr_markdown = resultado.get('ocr_result', {}).get('text', '')
            business_error = resultado.get("business_error") if isinstance(resultado.get("business_error"), dict) else {}
            rejection_reason = (
                business_error.get("message")
                or resultado.get("erro")
                or resultado.get("error")
            )
            validation_status = 'validated' if not resultado.get('validation_result', {}).get('exames_faltantes') and resultado.get('status') == 'success' else 'pending'
            if resultado.get('status') == 'error':
                validation_status = 'rejected'

            clinic_id_to_use = clinic_id
            if not clinic_id_to_use:
                clinics = user_db.get_all_clinics()
                clinic_id_to_use = clinics[0].id if clinics else None
            if not clinic_id_to_use:
                try:
                    clinic = user_db.create_clinic(name="Clinica Dev")
                    clinic_id_to_use = clinic.id
                    logger.info(f"[DB] Clinica criada automaticamente para salvar documento (job_id={job_id})")
                except Exception as clinic_error:
                    logger.error(f"[DB] Falha ao criar clinica automaticamente (job_id={job_id}): {clinic_error}")
            if not clinic_id_to_use:
                raise ValueError("clinic_id não encontrado para salvar documento")

            document = user_db.create_document(
                clinic_id=clinic_id_to_use,
                uploaded_by_user_id=uploaded_by_user_id,
                filename=filename,
                file_path=stored_path,
                content_hash=content_hash,
                uploaded_by_user_email=uploaded_by_user_email,
                cpf=cpf,
                exams_found=exams_found,
                exams_ocr=exams_ocr,
                exams_brnet=exams_brnet,
                validation_status=validation_status,
                ocr_markdown=ocr_markdown,
                run_id=resultado.get("run_id"),
                result_payload=resultado,
                confidence_score=resultado.get("confidence_score"),
                quality_score=(resultado.get("confidence_details") or {}).get("quality_score"),
                mandatory_coverage=(resultado.get("confidence_details") or {}).get("mandatory_coverage"),
                rejection_reason=rejection_reason if validation_status == "rejected" else None,
            )
            logger.info(f"[DB] Documento salvo via async com ID: {document.id} (job_id={job_id})")
            try:
                resultado["document_id"] = document.id
            except Exception:
                pass
            try:
                user_role = None
                try:
                    audit_user = user_db.get_user_by_id(uploaded_by_user_id)
                    if audit_user and getattr(audit_user, "role", None):
                        user_role = audit_user.role.value if hasattr(audit_user.role, "value") else str(audit_user.role)
                except Exception:
                    user_role = None
                user_db.create_audit_log(
                    AuditLogCreate(
                        user_id=uploaded_by_user_id,
                        user_email=uploaded_by_user_email,
                        user_role=user_role,
                        action="documents.processed",
                        resource="documents",
                        resource_id=document.id,
                        method="BACKGROUND",
                        path="/v1/processar-documento-async",
                        status_code=200,
                        request_id=job_id,
                        metadata={
                            "document_id": document.id,
                            "cpf": cpf,
                            "filename": filename,
                            "run_id": resultado.get("run_id"),
                            "validation_status": validation_status,
                            "error_code": resultado.get("error_code"),
                            "error_type": resultado.get("error_type"),
                            "error_source": resultado.get("error_source"),
                            "error_http_status": resultado.get("error_http_status"),
                            "business_error_trace_id": (business_error or {}).get("trace_id"),
                            "async": True,
                            "job_id": job_id,
                        },
                    )
                )
            except Exception as audit_error:
                logger.warning(f"[AUDIT] Falha ao registrar processamento async (job_id={job_id}): {audit_error}")
        except Exception as db_error:
            logger.error(f"[DB] Erro ao salvar documento (job_id={job_id}): {db_error}")

        # Marcar job como completo
        await job_manager.complete_job(job_id, resultado)
        logger.info(f"[JOB {job_id}] Concluído com sucesso")

    except Exception as e:
        logger.exception(f"[JOB {job_id}] Erro durante processamento: {e}")
        await job_manager.fail_job(job_id, str(e))

    finally:
        # Cleanup: remover arquivo temporário
        try:
            os.unlink(file_path)
            logger.debug(f"[JOB {job_id}] Arquivo temporário removido: {file_path}")
        except Exception as cleanup_error:
            logger.warning(f"[JOB {job_id}] Erro ao remover arquivo temporário: {cleanup_error}")


@router.post("/consultar-brmed", summary="Consultar exames BRMED por CPF/Passaporte")
async def consultar_brmed_api(
    payload: ConsultarBrmedRequest,
    current_user: User = Depends(require_sender),
):
    cpf = payload.cpf
    passaporte = payload.passaporte
    cnpj = payload.cnpj

    if cpf and passaporte:
        logger.info("[CONSULTAR-BRMED] CPF e passaporte informados; priorizando CPF para consulta.")
        passaporte = None

    if not cpf and not passaporte:
        logger.warning("Nenhum identificador fornecido para consulta BRMED/ProntuAI.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Informe cpf ou passaporte.")

    try:
        cnpj_efetivo = cnpj or _get_clinic_cnpj(current_user.clinic_id)
        if not cnpj_efetivo:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Para consultar exames obrigatórios é necessário informar o cnpj.",
            )
        resultado = await brmed_service.consultar_exames_prontuai(
            cpf=cpf,
            passaporte=passaporte,
            cnpj=cnpj_efetivo,
        )

        if "erro" in resultado:
            logger.error(
                "[CONSULTAR-BRMED] erro source=%s type=%s cpf=%s passaporte=%s cnpj=%s erro=%s",
                resultado.get("source"),
                resultado.get("error_type"),
                "***" if cpf else None,
                "***" if passaporte else None,
                cnpj,
                resultado["erro"],
            )
            if resultado.get("http_status") in (400, 404):
                raise HTTPException(status_code=resultado["http_status"], detail=resultado["erro"])
            if resultado.get("error_type") == "semantic":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=resultado["erro"])
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=resultado["erro"])
        return resultado
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro inesperado ao consultar BRMED/ProntuAI para identificadores fornecidos: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro inesperado ao consultar BRMED.")
 
