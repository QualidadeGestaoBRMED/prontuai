import asyncio
import logging
import os
from datetime import timedelta

from app.core.database import user_db
from app.core.job_manager import job_manager
from app.models.notification import NotificationCreate

logger = logging.getLogger(__name__)


def _int_env(name: str, default_value: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default_value
    try:
        return int(raw)
    except ValueError:
        logger.warning("Valor inválido para %s=%s. Usando %s.", name, raw, default_value)
        return default_value


async def job_watchdog_loop():
    """
    Loop que detecta jobs "travados" (sem atualização) e gera notificação.
    """
    interval = _int_env("JOB_WATCHDOG_INTERVAL_SECONDS", 60)
    stale_seconds = _int_env("JOB_STALE_SECONDS", 900)
    logger.info(
        "[JobWatchdog] Ativo (interval=%ss, stale_after=%ss)",
        interval,
        stale_seconds,
    )
    while True:
        try:
            await asyncio.sleep(interval)
            stale_jobs = await job_manager.collect_stale_jobs(timedelta(seconds=stale_seconds))
            if not stale_jobs:
                continue
            for job in stale_jobs:
                metadata = dict(job.metadata or {})
                filename = metadata.get("filename") or "Documento"
                clinic_id = metadata.get("clinic_id")
                document_id = metadata.get("document_id")
                uploaded_by_user_id = metadata.get("uploaded_by_user_id")
                uploaded_by_email = metadata.get("uploaded_by_user_email")
                if uploaded_by_user_id and not uploaded_by_email:
                    try:
                        user = user_db.get_user_by_id(uploaded_by_user_id)
                        if user and getattr(user, "email", None):
                            uploaded_by_email = user.email
                    except Exception:
                        pass
                if uploaded_by_email and not uploaded_by_user_id:
                    try:
                        user = user_db.get_user_by_email(uploaded_by_email)
                        if user and getattr(user, "id", None):
                            uploaded_by_user_id = user.id
                    except Exception:
                        pass
                metadata.update(
                    {
                        "job_id": job.job_id,
                        "job_type": job.job_type,
                        "stale_seconds": stale_seconds,
                        "uploaded_by_user_email": uploaded_by_email,
                        "uploaded_by_user_id": uploaded_by_user_id,
                    }
                )
                try:
                    user_db.create_notification(
                        NotificationCreate(
                            user_id=uploaded_by_user_id,
                            user_email=uploaded_by_email,
                            clinic_id=clinic_id,
                            document_id=document_id,
                            type="process_error",
                            title="Processamento travado",
                            message=(
                                f"O processamento de '{filename}' não recebeu atualizações por "
                                f"{int(stale_seconds / 60)} min e foi encerrado automaticamente. "
                                "Se necessário, reenvie o arquivo."
                            ),
                            variant="error",
                            metadata=metadata,
                        )
                    )
                    logger.warning(
                        "[JobWatchdog] Job %s marcado como FAILED (stale).",
                        job.job_id,
                    )
                except Exception as notify_error:
                    logger.warning(
                        "[JobWatchdog] Falha ao criar notificação para job %s: %s",
                        job.job_id,
                        notify_error,
                    )
        except asyncio.CancelledError:
            logger.info("[JobWatchdog] Encerrado")
            raise
        except Exception as e:
            logger.warning("[JobWatchdog] Erro no loop: %s", e)
