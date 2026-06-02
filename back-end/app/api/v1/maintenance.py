"""
Endpoints para operação de janelas de manutenção.
"""
from datetime import datetime, timezone
from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, or_

from app.core.auth import require_admin
from app.core.database import user_db
from app.core.db.models import MaintenanceWindowModel
from app.models.maintenance import (
    MaintenancePublicStatus,
    MaintenanceStatusResponse,
    MaintenanceWindow,
    MaintenanceWindowCreate,
    MaintenanceWindowStatus,
    MaintenanceWindowUpdate,
)
from app.models.user import User

router = APIRouter(prefix="/maintenance", tags=["Manutenção"])


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _to_utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _model_to_window(model: MaintenanceWindowModel) -> MaintenanceWindow:
    return MaintenanceWindow(
        id=model.id,
        status=MaintenanceWindowStatus(model.status),
        title=model.title,
        message=model.message,
        starts_at=model.starts_at,
        ends_at=model.ends_at,
        eta=model.eta,
        created_by=model.created_by,
        created_by_email=model.created_by_email,
        created_at=model.created_at,
        updated_at=model.updated_at,
        activated_at=model.activated_at,
        cancelled_at=model.cancelled_at,
        completed_at=model.completed_at,
    )


def _version_for(model: MaintenanceWindowModel) -> str:
    stamp = model.updated_at or model.created_at or _utc_now_naive()
    return f"{model.id}:{int(stamp.timestamp())}"


def _active_or_scheduled_model(session) -> Optional[MaintenanceWindowModel]:
    now = _utc_now_naive()
    candidates = (
        session.query(MaintenanceWindowModel)
        .filter(
            MaintenanceWindowModel.status.in_(
                [
                    MaintenanceWindowStatus.SCHEDULED.value,
                    MaintenanceWindowStatus.ACTIVE.value,
                ]
            )
        )
        .filter(
            or_(
                MaintenanceWindowModel.ends_at.is_(None),
                MaintenanceWindowModel.ends_at > now,
            )
        )
        .order_by(desc(MaintenanceWindowModel.updated_at))
        .all()
    )
    active = [
        item
        for item in candidates
        if item.status == MaintenanceWindowStatus.ACTIVE.value or item.starts_at <= now
    ]
    if active:
        return active[0]
    future = [item for item in candidates if item.starts_at > now]
    if future:
        return sorted(future, key=lambda item: item.starts_at)[0]
    return None


@router.get("/status", response_model=MaintenanceStatusResponse)
async def get_maintenance_status():
    """Status público usado pelo frontend para avisar/bloquear a aplicação."""
    session = user_db._get_session()
    try:
        window = _active_or_scheduled_model(session)
        if not window:
            return MaintenanceStatusResponse(status=MaintenancePublicStatus.NONE)

        now = _utc_now_naive()
        public_status = (
            MaintenancePublicStatus.ACTIVE
            if window.status == MaintenanceWindowStatus.ACTIVE.value or window.starts_at <= now
            else MaintenancePublicStatus.SCHEDULED
        )
        return MaintenanceStatusResponse(
            status=public_status,
            id=window.id,
            title=window.title,
            message=window.message,
            eta=window.eta or "",
            starts_at=window.starts_at,
            ends_at=window.ends_at,
            version=_version_for(window),
        )
    finally:
        session.close()


@router.get("/windows", response_model=List[MaintenanceWindow])
async def list_maintenance_windows(current_user: User = Depends(require_admin)):
    session = user_db._get_session()
    try:
        models = (
            session.query(MaintenanceWindowModel)
            .order_by(desc(MaintenanceWindowModel.created_at))
            .limit(20)
            .all()
        )
        return [_model_to_window(model) for model in models]
    finally:
        session.close()


@router.post("/windows", response_model=MaintenanceWindow, status_code=status.HTTP_201_CREATED)
async def create_maintenance_window(
    payload: MaintenanceWindowCreate,
    current_user: User = Depends(require_admin),
):
    starts_at = _to_utc_naive(payload.starts_at)
    ends_at = _to_utc_naive(payload.ends_at)
    if ends_at and starts_at and ends_at <= starts_at:
        raise HTTPException(status_code=400, detail="ends_at deve ser posterior a starts_at.")

    session = user_db._get_session()
    try:
        now = _utc_now_naive()
        model = MaintenanceWindowModel(
            id=str(uuid.uuid4()),
            status=MaintenanceWindowStatus.SCHEDULED.value,
            title=payload.title,
            message=payload.message,
            starts_at=starts_at or now,
            ends_at=ends_at,
            eta=payload.eta,
            created_by=current_user.id,
            created_by_email=current_user.email,
            created_at=now,
            updated_at=now,
        )
        session.add(model)
        session.commit()
        session.refresh(model)
        return _model_to_window(model)
    finally:
        session.close()


@router.patch("/windows/{window_id}", response_model=MaintenanceWindow)
async def update_maintenance_window(
    window_id: str,
    payload: MaintenanceWindowUpdate,
    current_user: User = Depends(require_admin),
):
    session = user_db._get_session()
    try:
        model = session.query(MaintenanceWindowModel).filter(MaintenanceWindowModel.id == window_id).first()
        if not model:
            raise HTTPException(status_code=404, detail="Janela de manutenção não encontrada.")
        if model.status in {MaintenanceWindowStatus.CANCELLED.value, MaintenanceWindowStatus.COMPLETED.value}:
            raise HTTPException(status_code=400, detail="Janela encerrada não pode ser editada.")

        if payload.title is not None:
            model.title = payload.title
        if payload.message is not None:
            model.message = payload.message
        if payload.starts_at is not None:
            model.starts_at = _to_utc_naive(payload.starts_at)
        if payload.ends_at is not None:
            model.ends_at = _to_utc_naive(payload.ends_at)
        if payload.eta is not None:
            model.eta = payload.eta
        if model.ends_at and model.ends_at <= model.starts_at:
            raise HTTPException(status_code=400, detail="ends_at deve ser posterior a starts_at.")

        model.updated_at = _utc_now_naive()
        session.commit()
        session.refresh(model)
        return _model_to_window(model)
    finally:
        session.close()


@router.post("/windows/{window_id}/activate", response_model=MaintenanceWindow)
async def activate_maintenance_window(window_id: str, current_user: User = Depends(require_admin)):
    return _set_terminal_or_active_status(window_id, MaintenanceWindowStatus.ACTIVE)


@router.post("/windows/{window_id}/cancel", response_model=MaintenanceWindow)
async def cancel_maintenance_window(window_id: str, current_user: User = Depends(require_admin)):
    return _set_terminal_or_active_status(window_id, MaintenanceWindowStatus.CANCELLED)


@router.post("/windows/{window_id}/complete", response_model=MaintenanceWindow)
async def complete_maintenance_window(window_id: str, current_user: User = Depends(require_admin)):
    return _set_terminal_or_active_status(window_id, MaintenanceWindowStatus.COMPLETED)


def _set_terminal_or_active_status(window_id: str, next_status: MaintenanceWindowStatus) -> MaintenanceWindow:
    session = user_db._get_session()
    try:
        model = session.query(MaintenanceWindowModel).filter(MaintenanceWindowModel.id == window_id).first()
        if not model:
            raise HTTPException(status_code=404, detail="Janela de manutenção não encontrada.")

        now = _utc_now_naive()
        model.status = next_status.value
        model.updated_at = now
        if next_status == MaintenanceWindowStatus.ACTIVE:
            model.activated_at = now
            if model.starts_at > now:
                model.starts_at = now
        elif next_status == MaintenanceWindowStatus.CANCELLED:
            model.cancelled_at = now
        elif next_status == MaintenanceWindowStatus.COMPLETED:
            model.completed_at = now

        session.commit()
        session.refresh(model)
        return _model_to_window(model)
    finally:
        session.close()
