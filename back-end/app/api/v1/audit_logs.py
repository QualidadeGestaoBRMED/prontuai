from fastapi import APIRouter, Depends, Query
from typing import Optional, List
from datetime import datetime
from app.core.auth import require_admin
from app.core.database import user_db
from app.models.audit_log import AuditLog
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit-logs", tags=["Auditoria"])


@router.get("", response_model=List[AuditLog])
async def list_audit_logs(
    limit: int = Query(200, ge=1, le=1000),
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
    action: Optional[str] = None,
    request_id: Optional[str] = None,
    since: Optional[datetime] = None,
    current_user=Depends(require_admin),
):
    logs = user_db.list_audit_logs(
        limit=limit,
        user_id=user_id,
        user_email=user_email,
        action=action,
        request_id=request_id,
        since=since,
    )
    logger.info(
        "[AUDIT] %s listou logs de auditoria (%s itens)",
        current_user.email,
        len(logs),
    )
    return logs
