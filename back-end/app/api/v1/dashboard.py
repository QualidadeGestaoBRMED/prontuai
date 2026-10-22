"""Indicadores do dashboard. Leitura agregada, restrita a quem tem o papel de indicadores."""
import asyncio
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.core.auth import require_dashboard, require_management
from app.core.database import user_db
from app.models.abordagem import Abordagem, AbordagemInput
from app.models.user import User
from app.services.dashboard_service import (
    DashboardIndisponivel,
    obter_indicadores,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/indicadores")
async def indicadores(
    forcar: bool = Query(False, description="Ignora o cache e recalcula agora."),
    current_user=Depends(require_dashboard),
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


@router.get("/abordagens", response_model=List[Abordagem])
def listar_abordagens(current_user=Depends(require_dashboard)) -> List[Abordagem]:
    """Status de abordagem de todas as credenciadas já marcadas em "Quem vale a pena incluir".

    Fica fora de /indicadores de propósito: os indicadores saem de um cache
    recalculado uma vez por dia, e o status tem de aparecer para o time assim
    que alguém o muda. Quem vê o dashboard lê; credenciada sem linha é
    "Não abordada".
    """
    return user_db.list_credenciado_abordagens()


@router.put("/abordagens", response_model=Abordagem)
def salvar_abordagem(
    payload: AbordagemInput,
    request: Request,
    current_user: User = Depends(require_management),
) -> Abordagem:
    """Grava o status de uma credenciada. Só a gestão (ADMIN e MANAGER) altera."""
    anterior = user_db.get_credenciado_abordagem(payload.credenciado)
    salvo = user_db.upsert_credenciado_abordagem(
        credenciado=payload.credenciado,
        status=payload.status,
        motivo=payload.motivo,
        atualizado_por_id=current_user.id,
        atualizado_por_email=current_user.email,
        atualizado_por_nome=current_user.name,
    )
    # A linha do audit_logs é do middleware; daqui vai o antes e o depois, que
    # é o histórico da credenciada. O motivo entra só pelo tamanho: é texto
    # livre e pode citar quem atendeu na clínica.
    # A identidade vai junto, como em `auth.py::_trilha`: a trilha diz quem
    # mudou mesmo quando o middleware não lê o Bearer (acesso de dev, por exemplo).
    request.state.audit = {
        "action": "dashboard.abordagem",
        "resource": "credenciado_abordagens",
        "resource_id": payload.credenciado,
        "user_id": current_user.id,
        "user_email": current_user.email,
        "user_role": current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
        "metadata": {
            "credenciado": payload.credenciado,
            "status": payload.status,
            "status_anterior": anterior.status if anterior else None,
            "motivo_len": len(payload.motivo or ""),
        },
    }
    return salvo
