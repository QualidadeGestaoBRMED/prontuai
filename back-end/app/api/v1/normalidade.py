"""
Normalidade e alteração de exames.

- `GET /documents/{id}/normalidade`: valores lidos no PDF para cada exame da
  Comparação Detalhada, com a situação (normal, acima, abaixo). Calculado na
  hora sobre o `ocr_markdown` gravado e as faixas em vigor: mudar uma faixa vale
  para documentos já processados, sem reprocessar.
- `GET/PUT/DELETE /normalidade/faixas`: a tela de Normalidade. Todos que
  checam documentos leem; só a gestão (ADMIN e MANAGER) ajusta.

É só informação para quem checa: nada aqui muda status, faltantes ou decisão.
O SENDER fica de fora: a leitura é apoio à checagem, não devolutiva à clínica.
"""
import logging
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.auth import require_management, require_roles
from app.core.database import user_db
from app.models.normalidade import Faixa, FaixaInput, NormalidadeDocumento
from app.models.user import User, UserRole
from app.services import layout_ocr, normalidade_exames as ne

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Normalidade de Exames"])

# Quem checa ou acompanha a checagem. Espelha o modal: CHECKER decide, CURATOR
# acompanha em modo leitura, gestão vê tudo.
_LEITORES = [UserRole.ADMIN, UserRole.MANAGER, UserRole.CHECKER, UserRole.CURATOR]


def _ajustes() -> dict[str, dict[str, Any]]:
    return {a.parametro: a.model_dump() for a in user_db.list_faixas_normalidade()}


def _faixas(ajustes: dict[str, dict[str, Any]]) -> List[Faixa]:
    efetivas = ne.faixas_efetivas(ajustes)
    out = []
    for k, p in ne.PARAMETROS.items():
        a = ajustes.get(k) or {}
        mn, mx = efetivas.get(k, (None, None))
        out.append(Faixa(
            parametro=k,
            nome=p.nome,
            unidade=p.unidade,
            qualitativo=p.qualitativo,
            normal_texto=p.normal_texto or None,
            padrao_minimo=p.padrao_min,
            padrao_maximo=p.padrao_max,
            minimo=mn,
            maximo=mx,
            referencia=ne.texto_faixa(k, (mn, mx)),
            ajustada=bool(a),
            atualizado_por_email=a.get("atualizado_por_email"),
            atualizado_por_nome=a.get("atualizado_por_nome"),
            atualizado_em=a.get("atualizado_em"),
        ))
    return out


def _parametro_editavel(parametro: str) -> ne.Parametro:
    p = ne.PARAMETROS.get(parametro)
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parâmetro desconhecido")
    if p.qualitativo:
        raise HTTPException(
            status_code=422,  # literal: o nome da constante mudou entre versões do Starlette
            detail=f"{p.nome} é qualitativo: não tem faixa numérica para ajustar",
        )
    return p


def _trilha(request: Request, user: User, action: str, parametro: str, antes: Any, depois: Any) -> None:
    # A linha do audit_logs é do middleware; daqui vai o antes e o depois, como
    # em `dashboard.py::salvar_abordagem`. Faixa não tem dado de paciente.
    request.state.audit = {
        "action": action,
        "resource": "faixas_normalidade",
        "resource_id": parametro,
        "user_id": user.id,
        "user_email": user.email,
        "user_role": user.role.value if hasattr(user.role, "value") else str(user.role),
        "metadata": {"parametro": parametro, "antes": antes, "depois": depois},
    }


@router.get("/normalidade/faixas", response_model=List[Faixa])
def listar_faixas(current_user: User = Depends(require_roles(_LEITORES))) -> List[Faixa]:
    """Todos os parâmetros, com a faixa padrão e a que está valendo."""
    return _faixas(_ajustes())


@router.put("/normalidade/faixas/{parametro}", response_model=Faixa)
def ajustar_faixa(
    parametro: str,
    payload: FaixaInput,
    request: Request,
    current_user: User = Depends(require_management),
) -> Faixa:
    """Ajusta a faixa de um parâmetro numérico. Vale na hora para todo documento."""
    _parametro_editavel(parametro)
    ajustes = _ajustes()
    antes = ne.faixas_efetivas(ajustes)[parametro]
    user_db.upsert_faixa_normalidade(
        parametro=parametro,
        minimo=payload.minimo,
        maximo=payload.maximo,
        atualizado_por_id=current_user.id,
        atualizado_por_email=current_user.email,
        atualizado_por_nome=current_user.name,
    )
    _trilha(request, current_user, "normalidade.faixa.ajuste", parametro,
            {"minimo": antes[0], "maximo": antes[1]}, {"minimo": payload.minimo, "maximo": payload.maximo})
    return next(f for f in _faixas(_ajustes()) if f.parametro == parametro)


@router.delete("/normalidade/faixas/{parametro}", response_model=Faixa)
def restaurar_faixa(
    parametro: str,
    request: Request,
    current_user: User = Depends(require_management),
) -> Faixa:
    """Volta o parâmetro à faixa padrão. Apaga só o ajuste, não o parâmetro."""
    p = _parametro_editavel(parametro)
    antes = ne.faixas_efetivas(_ajustes())[parametro]
    user_db.delete_faixa_normalidade(parametro)
    _trilha(request, current_user, "normalidade.faixa.restaurar", parametro,
            {"minimo": antes[0], "maximo": antes[1]}, {"minimo": p.padrao_min, "maximo": p.padrao_max})
    return next(f for f in _faixas(_ajustes()) if f.parametro == parametro)


@router.get("/documents/{document_id}/normalidade", response_model=NormalidadeDocumento)
def normalidade_do_documento(
    document_id: str,
    current_user: User = Depends(require_roles(_LEITORES)),
) -> NormalidadeDocumento:
    """Valores lidos no PDF para os exames encontrados, com a situação de cada um."""
    if not ne.HABILITADA:
        return NormalidadeDocumento(habilitada=False)
    document = user_db.get_document_by_id(document_id)
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento não encontrado")
    payload = document.result_payload if isinstance(document.result_payload, dict) else {}
    try:
        # Posição no PDF de cada valor lido. Sem layout (documento antigo, OCR
        # local), a leitura sai igual, só sem o atalho até o valor.
        linhas = layout_ocr.alinhar(document.ocr_markdown or "", user_db.get_document_layout(document_id))
    except Exception as e:
        logger.warning(f"[NORMALIDADE] Layout indisponível no documento {document_id}: {type(e).__name__}")
        linhas = None
    try:
        itens = ne.avaliar_documento(
            document.ocr_markdown or "",
            payload.get("tabela_comparacao") or [],
            _ajustes(),
            linhas,
        )
    except Exception as e:
        # Leitura é informativa: falha aqui não pode travar a checagem. Só o tipo
        # do erro vai para o log; a mensagem pode carregar trecho do laudo.
        logger.warning(f"[NORMALIDADE] Leitura falhou no documento {document_id}: {type(e).__name__}")
        return NormalidadeDocumento(habilitada=True, itens=[])
    return NormalidadeDocumento(habilitada=True, itens=itens)
