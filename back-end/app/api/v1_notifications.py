from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from typing import Optional
from app.core.auth import get_current_user
from app.core.database import user_db
from app.core.logging import set_audit_context
from app.models.user import UserRole, User
from app.models.notification import NotificationCreate, Notification
import logging
import time

logger = logging.getLogger(__name__)

# Papéis que decidem documentos e por isso avisam o autor do upload. Os demais
# (SENDER e CURATOR) só criam notificação para si mesmos.
_NOTIFICAM_AUTOR_DO_DOCUMENTO = (UserRole.ADMIN, UserRole.MANAGER, UserRole.CHECKER)


def _link_interno(url: str) -> bool:
    """Link de notificação só pode apontar para dentro do app.

    `//host` e `/\\host` são interpretados pelo navegador como outro domínio,
    por isso não basta começar com barra.
    """
    return url.startswith("/") and not url.startswith(("//", "/\\"))


router = APIRouter(prefix="/notifications", tags=["Notificações"])

@router.get("", response_model=list[Notification])
async def list_notifications(
    include_read: bool = Query(True),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    request: Request = None,
):
    try:
        start_time = time.perf_counter()
        notifications = user_db.list_notifications(
            user_id=current_user.id,
            limit=limit,
            include_read=include_read,
        )
        elapsed = time.perf_counter() - start_time
        user_agent = request.headers.get("user-agent", "-") if request else "-"
        referer = request.headers.get("referer", "-") if request else "-"
        forwarded_for = request.headers.get("x-forwarded-for", "-") if request else "-"
        logger.info(
            "[NOTIFICATIONS] %s listou %s notificações em %.2fs | ua=%s | referer=%s | xff=%s",
            current_user.email,
            len(notifications),
            elapsed,
            user_agent,
            referer,
            forwarded_for,
        )
        return notifications
    except Exception as e:
        logger.exception(f"Erro ao listar notificações: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao listar notificações")

@router.post("", response_model=Notification)
async def create_notification(
    payload: NotificationCreate,
    current_user: User = Depends(get_current_user)
):
    if payload.action_url and not _link_interno(payload.action_url):
        raise HTTPException(
            status_code=422,  # literal: o nome da constante mudou entre versões do Starlette
            detail="action_url deve ser um caminho interno do ProntuAI (ex.: /historico)",
        )
    try:
        clinic_id = payload.clinic_id
        # O destinatário NUNCA vem do payload. `user_id`/`user_email` deixavam
        # qualquer papel — inclusive o CURATOR, que é só leitura —
        # entregar título e mensagem livres a qualquer usuário (phishing interno).
        # O front nunca usou esses campos: quem recebe sai do documento ou é o
        # próprio autor da chamada.
        recipient_user_id = None
        recipient_user_email = None
        doc = None

        if payload.document_id:
            doc = user_db.get_document_by_id(payload.document_id)
            if not doc:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento não encontrado")
            clinic_id = doc.clinic_id or clinic_id
            # Avisar o autor do documento é o fluxo da Checagem (aprovado,
            # rejeitado). Só quem decide documentos notifica terceiros.
            if current_user.role in _NOTIFICAM_AUTOR_DO_DOCUMENTO:
                recipient_user_id = doc.uploaded_by_user_id
                recipient_user_email = doc.uploaded_by_user_email

        if current_user.role == UserRole.SENDER:
            recipient_user_id = current_user.id
            recipient_user_email = current_user.email
            clinic_id = current_user.clinic_id or clinic_id

        if recipient_user_id and not recipient_user_email:
            try:
                recipient_user = user_db.get_user_by_id(recipient_user_id)
                if recipient_user and getattr(recipient_user, "email", None):
                    recipient_user_email = recipient_user.email
            except Exception:
                pass

        if not recipient_user_id:
            recipient_user_id = current_user.id
        if not recipient_user_email:
            recipient_user_email = current_user.email

        notification = user_db.create_notification(NotificationCreate(
            user_id=recipient_user_id,
            user_email=recipient_user_email,
            clinic_id=clinic_id,
            document_id=payload.document_id,
            type=payload.type,
            title=payload.title,
            message=payload.message,
            variant=payload.variant,
            action_url=payload.action_url,
            action_label=payload.action_label,
            metadata=payload.metadata
        ))
        try:
            set_audit_context(
                {
                    "action": "notifications.create",
                    "resource": "notifications",
                    "resource_id": notification.id,
                    "metadata": {
                        "type": payload.type,
                        "document_id": payload.document_id,
                        "clinic_id": clinic_id,
                    },
                }
            )
        except Exception:
            pass
        return notification
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao criar notificação: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao criar notificação")

@router.post("/{notification_id}/read", response_model=Notification)
async def mark_notification_read(notification_id: str, current_user: User = Depends(get_current_user)):
    try:
        notification = user_db.mark_notification_read(notification_id, user_id=current_user.id)
        if not notification:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notificação não encontrada")
        try:
            set_audit_context(
                {
                    "action": "notifications.read",
                    "resource": "notifications",
                    "resource_id": notification_id,
                    "metadata": {
                        "clinic_id": notification.clinic_id,
                        "document_id": notification.document_id,
                    },
                }
            )
        except Exception:
            pass
        return notification
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao marcar notificação como lida: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao marcar notificação")

@router.post("/read-all")
async def mark_all_read(current_user: User = Depends(get_current_user)):
    try:
        updated = user_db.mark_all_notifications_read(user_id=current_user.id)
        try:
            set_audit_context(
                {
                    "action": "notifications.read_all",
                    "resource": "notifications",
                    "metadata": {
                        "user_id": current_user.id,
                        "updated": updated,
                    },
                }
            )
        except Exception:
            pass
        return {"updated": updated}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao marcar todas notificações: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao marcar notificações")

@router.delete("")
async def clear_notifications(current_user: User = Depends(get_current_user)):
    try:
        deleted = user_db.clear_notifications(user_id=current_user.id)
        try:
            set_audit_context(
                {
                    "action": "notifications.clear",
                    "resource": "notifications",
                    "metadata": {
                        "user_id": current_user.id,
                        "deleted": deleted,
                    },
                }
            )
        except Exception:
            pass
        return {"deleted": deleted}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao limpar notificações: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao limpar notificações")
