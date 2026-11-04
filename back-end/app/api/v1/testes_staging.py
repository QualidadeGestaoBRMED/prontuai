"""
Chave dos pedidos guardados, para o card de `/admin/ops-manutencao` (STC-981).

Fora de staging as rotas respondem 404 para qualquer pessoa, antes mesmo da
autenticação, e a tela esconde o card. Ver `app/services/pedidos_guardados.py`.
Toda troca da chave cai em `audit_logs` pelo middleware.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.core.auth import require_admin
from app.models.user import User
from app.services import pedidos_guardados


def _so_em_staging() -> None:
    if not pedidos_guardados.disponivel():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


router = APIRouter(
    prefix="/testes-staging",
    tags=["Testes em staging"],
    include_in_schema=False,
    dependencies=[Depends(_so_em_staging)],
)


class ResumoPedidosGuardados(BaseModel):
    ligada: bool
    chave_atualizada_em: Optional[datetime] = None
    chave_atualizada_por: Optional[str] = None
    total_pedidos: int
    ultimo_pedido_em: Optional[datetime] = None


class ChavePedidosGuardados(BaseModel):
    ligada: bool


@router.get("/pedidos-guardados", response_model=ResumoPedidosGuardados)
def ler_pedidos_guardados(current_user: User = Depends(require_admin)) -> ResumoPedidosGuardados:
    return ResumoPedidosGuardados(**pedidos_guardados.resumo())


@router.put("/pedidos-guardados", response_model=ResumoPedidosGuardados)
def trocar_pedidos_guardados(
    payload: ChavePedidosGuardados,
    request: Request,
    current_user: User = Depends(require_admin),
) -> ResumoPedidosGuardados:
    pedidos_guardados.definir_chave(payload.ligada, current_user.email)
    request.state.audit = {
        "action": "testes_staging.pedidos_guardados.ligar"
        if payload.ligada
        else "testes_staging.pedidos_guardados.desligar",
        "resource": "pedidos_guardados",
    }
    return ResumoPedidosGuardados(**pedidos_guardados.resumo())
