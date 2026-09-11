"""Indicadores do dashboard. Leitura agregada, restrita à gestão."""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import require_management
from app.services.dashboard_service import (
    DashboardIndisponivel,
    obter_indicadores,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/indicadores")
async def indicadores(
    forcar: bool = Query(False, description="Ignora o cache e recalcula agora."),
    current_user=Depends(require_management),
):
    """Séries de utilização, acurácia, clínicas e exames do ambiente atual.

    Sem filtro por clínica: o recorte por período é feito na tela, sobre a série
    completa, para trocar de período não custar uma ida ao banco.
    """
    try:
        # A consulta é I/O bloqueante de vários segundos. Num handler `async`
        # ela roda no event loop e trava TODA a API enquanto varre o banco —
        # medido: /health saiu de 1,5ms para 4,7s. Fora dele, só quem pediu espera.
        return await asyncio.to_thread(obter_indicadores, forcar)
    except DashboardIndisponivel as exc:
        logger.warning("[DASHBOARD] %s pediu indicadores e a consulta falhou", current_user.email)
        raise HTTPException(
            status_code=503,
            detail=f"Não foi possível calcular os indicadores: {exc}",
        ) from exc
