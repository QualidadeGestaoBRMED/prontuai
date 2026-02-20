"""
Sistema de gerenciamento de jobs assíncronos para processamento OCR.
Evita timeouts de workers ao executar tarefas longas em background.
"""
import asyncio
import uuid
import os
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timedelta
from enum import Enum
import logging

from app.core.database import user_db

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    """Status possíveis de um job."""
    PENDING = "pending"           # Aguardando processamento
    IN_PROGRESS = "in_progress"   # Em processamento
    COMPLETED = "completed"       # Concluído com sucesso
    FAILED = "failed"             # Falhou com erro
    CANCELLED = "cancelled"       # Cancelado pelo usuário


class Job:
    """Representa um job de processamento."""

    def __init__(self, job_id: str, job_type: str, metadata: Dict[str, Any] = None):
        self.job_id = job_id
        self.job_type = job_type
        self.status = JobStatus.PENDING
        self.created_at = datetime.utcnow()
        self.updated_at = self.created_at
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.progress = 0  # 0-100
        self.current_step = "pending"
        self.message = "Job criado, aguardando processamento"
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        """Serializa o job para dict."""
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "status": self.status,
            "progress": self.progress,
            "current_step": self.current_step,
            "message": self.message,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata
        }

    def update_progress(self, progress: int, step: str, message: str):
        """Atualiza o progresso do job."""
        self.progress = progress
        self.current_step = step
        self.message = message
        self.updated_at = datetime.utcnow()
        logger.debug(f"[JOB {self.job_id}] {progress}% - {step}: {message}")

    def start(self):
        """Marca o job como iniciado."""
        self.status = JobStatus.IN_PROGRESS
        self.started_at = datetime.utcnow()
        self.updated_at = self.started_at
        logger.info(f"[JOB {self.job_id}] Iniciado")

    def complete(self, result: Dict[str, Any]):
        """Marca o job como completo."""
        self.status = JobStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.updated_at = self.completed_at
        self.progress = 100
        self.result = result
        logger.info(f"[JOB {self.job_id}] Concluído com sucesso")

    def fail(self, error: str):
        """Marca o job como falho."""
        self.status = JobStatus.FAILED
        self.completed_at = datetime.utcnow()
        self.updated_at = self.completed_at
        self.error = error
        logger.error(f"[JOB {self.job_id}] Falhou: {error}")


class JobManager:
    """
    Gerenciador de jobs assíncronos.

    Thread-safe para uso em múltiplos workers do Gunicorn.
    Jobs são armazenados em memória (para produção, considerar Redis).
    """

    def __init__(self, max_jobs_history: int = 1000, cleanup_after_hours: int = 24):
        self._jobs: Dict[str, Job] = {}
        self._lock = asyncio.Lock()
        self.max_jobs_history = max_jobs_history
        self.cleanup_after_hours = cleanup_after_hours
        self._persist_enabled = os.getenv("JOB_PERSISTENCE", "true").lower() == "true"
        logger.info(f"[JobManager] Inicializado (max_jobs={max_jobs_history}, cleanup_after={cleanup_after_hours}h)")

    def _db_enabled(self) -> bool:
        return self._persist_enabled and hasattr(user_db, "create_job_record")

    def _parse_dt(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except Exception:
            return None

    def _hydrate_job_from_record(self, record: dict) -> Job:
        job = Job(record.get("job_id"), record.get("job_type"), record.get("metadata") or {})
        status_raw = record.get("status") or JobStatus.PENDING.value
        try:
            job.status = JobStatus(status_raw)
        except Exception:
            job.status = JobStatus.PENDING
        job.progress = record.get("progress") or 0
        job.current_step = record.get("current_step") or "pending"
        job.message = record.get("message") or "Job carregado"
        job.created_at = self._parse_dt(record.get("created_at")) or job.created_at
        job.updated_at = self._parse_dt(record.get("updated_at")) or job.updated_at
        job.started_at = self._parse_dt(record.get("started_at"))
        job.completed_at = self._parse_dt(record.get("completed_at"))
        job.result = record.get("result")
        job.error = record.get("error")
        return job

    def _persist_create(self, job: Job) -> None:
        if not self._db_enabled():
            return
        try:
            user_db.create_job_record(job.job_id, job.job_type, metadata=job.metadata)
        except Exception as exc:
            logger.warning("[JobManager] Falha ao persistir job %s: %s", job.job_id, exc)

    def _persist_update(
        self,
        job: Job,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        if not self._db_enabled():
            return
        try:
            user_db.update_job_record(
                job_id=job.job_id,
                status=job.status.value if isinstance(job.status, JobStatus) else str(job.status),
                progress=job.progress,
                current_step=job.current_step,
                message=job.message,
                result=result,
                error=error,
                started_at=job.started_at,
                completed_at=job.completed_at,
                metadata=job.metadata,
            )
        except Exception as exc:
            logger.warning("[JobManager] Falha ao atualizar job %s: %s", job.job_id, exc)

    async def create_job(self, job_type: str, metadata: Dict[str, Any] = None) -> str:
        """
        Cria um novo job e retorna o job_id.

        Args:
            job_type: Tipo do job (ex: "ocr", "document_processing")
            metadata: Metadados adicionais do job

        Returns:
            str: ID único do job
        """
        job_id = str(uuid.uuid4())
        job = Job(job_id, job_type, metadata)

        async with self._lock:
            self._jobs[job_id] = job
            # Limpeza preventiva se houver muitos jobs
            if len(self._jobs) > self.max_jobs_history:
                await self._cleanup_old_jobs()

        self._persist_create(job)
        logger.info(f"[JobManager] Job criado: {job_id} (tipo={job_type})")
        return job_id

    async def get_job(self, job_id: str) -> Optional[Job]:
        """Retorna um job pelo ID."""
        async with self._lock:
            job = self._jobs.get(job_id)
        if job is None and self._db_enabled():
            try:
                record = user_db.get_job_record(job_id)
                if record:
                    job = self._hydrate_job_from_record(record)
                    async with self._lock:
                        self._jobs[job_id] = job
            except Exception as exc:
                logger.warning("[JobManager] Falha ao buscar job %s no DB: %s", job_id, exc)
        return job

    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retorna o status de um job em formato dict."""
        if self._db_enabled():
            try:
                record = user_db.get_job_record(job_id)
                if record:
                    return record
            except Exception as exc:
                logger.warning("[JobManager] Falha ao consultar job %s no DB: %s", job_id, exc)
        job = await self.get_job(job_id)
        return job.to_dict() if job else None

    async def update_job_progress(self, job_id: str, progress: int, step: str, message: str):
        """Atualiza o progresso de um job."""
        job = None
        async with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.update_progress(progress, step, message)
        if job:
            self._persist_update(job)
        elif self._db_enabled():
            try:
                user_db.update_job_record(
                    job_id=job_id,
                    progress=progress,
                    current_step=step,
                    message=message,
                )
            except Exception as exc:
                logger.warning("[JobManager] Falha ao atualizar job %s no DB: %s", job_id, exc)

    async def start_job(self, job_id: str):
        """Marca um job como iniciado."""
        job = None
        async with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.start()
        if job:
            self._persist_update(job)

    async def complete_job(self, job_id: str, result: Dict[str, Any]):
        """Marca um job como completo."""
        job = None
        async with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.complete(result)
        if job:
            self._persist_update(job, result=result)

    async def fail_job(self, job_id: str, error: str):
        """Marca um job como falho."""
        job = None
        async with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.fail(error)
        if job:
            self._persist_update(job, error=error)

    async def cancel_job(self, job_id: str) -> Optional[Job]:
        """Cancela um job e persiste no banco, se habilitado."""
        job = None
        async with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = JobStatus.CANCELLED
                job.message = "Job cancelado pelo usuário"
                job.updated_at = datetime.utcnow()
        if job:
            self._persist_update(job)
            return job
        if self._db_enabled():
            try:
                user_db.update_job_record(
                    job_id=job_id,
                    status=JobStatus.CANCELLED.value,
                    message="Job cancelado pelo usuário",
                    completed_at=datetime.utcnow(),
                )
                record = user_db.get_job_record(job_id)
                return self._hydrate_job_from_record(record) if record else None
            except Exception as exc:
                logger.warning("[JobManager] Falha ao cancelar job %s no DB: %s", job_id, exc)
        return None

    async def list_jobs(self, status: Optional[JobStatus] = None, limit: int = 50) -> list[Dict[str, Any]]:
        """
        Lista jobs, opcionalmente filtrados por status.

        Args:
            status: Filtro opcional de status
            limit: Número máximo de jobs a retornar

        Returns:
            Lista de jobs em formato dict
        """
        if self._db_enabled():
            try:
                status_value = status.value if isinstance(status, JobStatus) else None
                return user_db.list_job_records(status=status_value, limit=limit)
            except Exception as exc:
                logger.warning("[JobManager] Falha ao listar jobs no DB: %s", exc)
        async with self._lock:
            jobs = list(self._jobs.values())

        if status:
            jobs = [j for j in jobs if j.status == status]

        # Ordena por data de criação (mais recentes primeiro)
        jobs.sort(key=lambda j: j.created_at, reverse=True)

        return [job.to_dict() for job in jobs[:limit]]

    async def collect_stale_jobs(self, stale_after: timedelta) -> list[Job]:
        """
        Marca jobs "travados" como FAILED e retorna a lista para notificação.

        Args:
            stale_after: Tempo máximo sem atualização.
        """
        now = datetime.utcnow()
        cutoff_time = now - stale_after
        stale_jobs: list[Job] = []
        async with self._lock:
            for job in self._jobs.values():
                if job.status not in [JobStatus.PENDING, JobStatus.IN_PROGRESS]:
                    continue
                last_update = job.updated_at or job.created_at
                if last_update and last_update < cutoff_time:
                    elapsed = int((now - last_update).total_seconds())
                    job.fail(f"Job sem atualização há {elapsed}s")
                    stale_jobs.append(job)
        return stale_jobs

    async def _cleanup_old_jobs(self):
        """Remove jobs antigos e completos da memória."""
        cutoff_time = datetime.utcnow() - timedelta(hours=self.cleanup_after_hours)

        jobs_to_remove = [
            job_id for job_id, job in self._jobs.items()
            if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]
            and job.completed_at
            and job.completed_at < cutoff_time
        ]

        for job_id in jobs_to_remove:
            del self._jobs[job_id]

        if jobs_to_remove:
            logger.info(f"[JobManager] Removidos {len(jobs_to_remove)} jobs antigos")

    async def create_progress_callback(self, job_id: str) -> Callable:
        """
        Cria um callback de progresso para um job.

        Retorna uma função async que pode ser passada para workflow_service.
        """
        async def progress_callback(progress: int, step: str, message: str):
            await self.update_job_progress(job_id, progress, step, message)

        return progress_callback


# Instância global do JobManager (singleton)
job_manager = JobManager()
