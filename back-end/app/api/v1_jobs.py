"""
Endpoints para gerenciamento de jobs assíncronos.
Permite consultar status e resultados de processamentos OCR.
"""
from fastapi import APIRouter, HTTPException, status, Depends
from typing import Optional, Any
from app.core.job_manager import job_manager, JobStatus
from app.core.auth import get_current_user
from app.core.database import user_db
from app.models.user import User, UserRole
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


def _job_metadata(job_payload: dict[str, Any]) -> dict[str, Any]:
    metadata = job_payload.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _can_access_job(current_user: User, job_payload: dict[str, Any]) -> bool:
    if current_user.role == UserRole.ADMIN:
        return True

    metadata = _job_metadata(job_payload)
    job_user_id = metadata.get("uploaded_by_user_id")
    job_clinic_id = metadata.get("clinic_id")

    if current_user.role in (UserRole.SENDER, UserRole.MANAGER):
        # MANAGER só enxerga/cancela os próprios jobs (não é role destrutiva)
        return bool(job_user_id and job_user_id == current_user.id)

    if current_user.role == UserRole.CHECKER:
        # Política mínima: checker só enxerga jobs da própria clínica quando clinic_id existe.
        return bool(current_user.clinic_id and job_clinic_id == current_user.clinic_id)

    return False


@router.get("/jobs/{job_id}", summary="Consultar status de um job")
async def get_job_status(job_id: str, current_user: User = Depends(get_current_user)):
    """
    Retorna o status e progresso de um job.

    Usado pelo frontend para fazer polling do progresso de processamento.

    Retorna:
    - job_id: ID do job
    - status: pending, in_progress, completed, failed, cancelled
    - progress: 0-100
    - current_step: Etapa atual (ocr, brmed, validacao, etc)
    - message: Mensagem descritiva do progresso
    - result: Resultado completo (apenas quando status=completed)
    - error: Mensagem de erro (apenas quando status=failed)
    """
    job_status = None
    if hasattr(user_db, "get_job_record_scoped"):
        try:
            job_status = user_db.get_job_record_scoped(
                job_id,
                role=current_user.role,
                user_id=current_user.id,
                clinic_id=current_user.clinic_id,
            )
        except Exception:
            job_status = None
    if not job_status:
        job_status = await job_manager.get_job_status(job_id)

    if not job_status:
        logger.warning(f"[JOBS] Job não encontrado: {job_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} não encontrado. O job pode ter expirado ou nunca existiu."
        )

    if not _can_access_job(current_user, job_status):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para acessar este job."
        )

    logger.debug(f"[JOBS] Status consultado para job {job_id}: {job_status['status']}")
    return job_status


@router.get("/jobs", summary="Listar jobs")
async def list_jobs(
    status_filter: Optional[str] = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
):
    """
    Lista jobs, opcionalmente filtrados por status.

    Parâmetros:
    - status_filter: Filtro opcional (pending, in_progress, completed, failed)
    - limit: Número máximo de jobs a retornar (padrão: 50)
    """
    # Validar status se fornecido
    job_status = None
    if status_filter:
        try:
            job_status = JobStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Status inválido: {status_filter}. Use: pending, in_progress, completed, failed, cancelled"
            )

    filtered_jobs = []
    if hasattr(user_db, "list_job_records_scoped"):
        try:
            filtered_jobs = user_db.list_job_records_scoped(
                role=current_user.role,
                status=job_status.value if isinstance(job_status, JobStatus) else None,
                limit=limit,
                user_id=current_user.id,
                clinic_id=current_user.clinic_id,
            )
        except Exception:
            filtered_jobs = []

    if not filtered_jobs:
        jobs = await job_manager.list_jobs(status=job_status, limit=limit)
        filtered_jobs = [job for job in jobs if _can_access_job(current_user, job)]
    logger.info(
        "[JOBS] Listados %d jobs (filtro=%s, role=%s)",
        len(filtered_jobs),
        status_filter,
        current_user.role.value,
    )

    return {
        "total": len(filtered_jobs),
        "jobs": filtered_jobs
    }


@router.delete("/jobs/{job_id}", summary="Cancelar um job")
async def cancel_job(job_id: str, current_user: User = Depends(get_current_user)):
    """
    Cancela um job em progresso.

    Nota: Jobs em background não podem ser realmente "cancelados" após iniciados,
    mas este endpoint marca o job como cancelado para que o frontend pare de fazer polling.
    """
    job_status_payload = await job_manager.get_job_status(job_id)
    if not job_status_payload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} não encontrado"
        )

    if not _can_access_job(current_user, job_status_payload):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para cancelar este job."
        )

    job = await job_manager.get_job(job_id)
    if not job:
        # Mesmo sem estar em memória, ainda tentamos atualizar persistência.
        cancelled = await job_manager.cancel_job(job_id)
        if not cancelled:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {job_id} não encontrado"
            )
        return {
            "job_id": job_id,
            "status": "cancelled",
            "message": "Job marcado como cancelado"
        }

    if job.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Não é possível cancelar um job já finalizado (status={job.status})"
        )

    # Marca como cancelado (persiste quando configurado)
    await job_manager.cancel_job(job_id)

    logger.info(f"[JOBS] Job cancelado: {job_id}")

    return {
        "job_id": job_id,
        "status": "cancelled",
        "message": "Job marcado como cancelado"
    }
