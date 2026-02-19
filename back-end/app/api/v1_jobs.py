"""
Endpoints para gerenciamento de jobs assíncronos.
Permite consultar status e resultados de processamentos OCR.
"""
from fastapi import APIRouter, HTTPException, status
from typing import Optional
from app.core.job_manager import job_manager, JobStatus
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/jobs/{job_id}", summary="Consultar status de um job")
async def get_job_status(job_id: str):
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
    job_status = await job_manager.get_job_status(job_id)

    if not job_status:
        logger.warning(f"[JOBS] Job não encontrado: {job_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} não encontrado. O job pode ter expirado ou nunca existiu."
        )

    logger.debug(f"[JOBS] Status consultado para job {job_id}: {job_status['status']}")
    return job_status


@router.get("/jobs", summary="Listar jobs")
async def list_jobs(
    status_filter: Optional[str] = None,
    limit: int = 50
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

    jobs = await job_manager.list_jobs(status=job_status, limit=limit)
    logger.info(f"[JOBS] Listados {len(jobs)} jobs (filtro={status_filter})")

    return {
        "total": len(jobs),
        "jobs": jobs
    }


@router.delete("/jobs/{job_id}", summary="Cancelar um job")
async def cancel_job(job_id: str):
    """
    Cancela um job em progresso.

    Nota: Jobs em background não podem ser realmente "cancelados" após iniciados,
    mas este endpoint marca o job como cancelado para que o frontend pare de fazer polling.
    """
    job = await job_manager.get_job(job_id)

    if not job:
        # Tenta cancelar via persistência (DB), se habilitado
        job = await job_manager.cancel_job(job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {job_id} não encontrado"
            )

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
