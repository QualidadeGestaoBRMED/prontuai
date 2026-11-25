"""Conduta sugerida para a tela do médico (Conduta Médica): o objeto Conduta da API de Normalidade e Conduta
Sugerida, calculado para um documento já processado pelo ProntuAI, e a decisão do médico.

Trilha (migration 020, só linhas novas): cada chamada ao ml-exams em `conduta_sugestoes`, cada exibição da sugestão
em `conduta_exibicoes` (quem viu e quando) e cada decisão em `conduta_decisoes`. O POST da decisão também entra no
`audit_log` pelo middleware, enriquecido via `request.state.audit`.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.auth import require_roles
from app.core.database import user_db
from app.models.user import User, UserRole
from app.services.conduta import conduta_sugerida as cs

logger = logging.getLogger(__name__)

SituacaoAso = Literal["LIBERADO", "LIBERADO_COM_ENCAMINHAMENTO", "RETIDO", "INAPTO"]


class _Guardada:
    """As chamadas ao ml-exams do documento na tabela conduta_sugestoes."""

    def __init__(self, document_id: str):
        self.document_id = document_id

    def ler(self, features_hash):
        return user_db.ultima_conduta_sugestao(self.document_id, features_hash)

    def gravar(self, features_hash, features, versao_modelo, resposta, status_http, erro, duracao_ms, request_id):
        return user_db.registrar_conduta_sugestao(self.document_id, features_hash, cs.VERSAO_FEATURES, versao_modelo,
                                                  features, resposta, status_http, erro, duracao_ms, request_id)


router = APIRouter(tags=["Conduta sugerida"])


def _iso(valor) -> Optional[str]:
    return valor.isoformat() if hasattr(valor, "isoformat") else valor


@router.get("/documents/{document_id}/conduta-sugerida")
async def conduta_do_documento(
    document_id: str,
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.MANAGER])),
) -> dict:
    document = user_db.get_document_by_id(document_id)
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento não encontrado")
    payload = document.result_payload if isinstance(document.result_payload, dict) else {}
    ausentes = [t.get("exame") for t in payload.get("tabela_comparacao") or [] if isinstance(t, dict)
                and t.get("status") == "faltante" and t.get("exame")]
    data = document.uploaded_at.date().isoformat() if getattr(document, "uploaded_at", None) else None
    # Leitura + chamada ao modelo fora do loop (são síncronas).
    out = await asyncio.to_thread(cs.sugerir, document.ocr_markdown or "", data, ausentes,
                                  document.exams_ocr or [], document.exams_brnet or [], _Guardada(document_id))
    sugestao = out.get("conduta_sugerida") or {}
    out["exibicao_id"] = None
    try:
        out["exibicao_id"] = await asyncio.to_thread(
            user_db.registrar_conduta_exibicao, document_id, out.get("sugestao_id"), sugestao.get("situacao_aso"),
            out.get("motivo_sem_sugestao"), sugestao.get("confianca"), out.get("versao_modelo"),
            current_user.id, current_user.email,
        )
    except Exception as exc:  # noqa: BLE001 — a trilha não pode impedir o médico de ver a sugestão
        logger.warning(f"[CONDUTA] Falha ao registrar a exibição: {type(exc).__name__}")
    out["decisao_registrada"] = None
    try:
        decisao = await asyncio.to_thread(user_db.ultima_conduta_decisao, document_id)
        if decisao:
            out["decisao_registrada"] = {
                "situacao_aso": decisao["situacao_final"],
                "decidido_em": _iso(decisao["decidido_em"]),
                "registrado_em": _iso(decisao["registrado_em"]),
                "decidido_por": decisao["user_email"],
            }
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[CONDUTA] Falha ao ler a decisão registrada: {type(exc).__name__}")
    return out


class CondutaFinal(BaseModel):
    situacao_aso: SituacaoAso
    observacao: Optional[str] = Field(None, max_length=4000)


class NormalidadeFinal(BaseModel):
    exame_id: str = Field(..., min_length=1, max_length=200)
    classificacao: Literal["normal", "alterado", "inconclusivo"]


class DecisaoMedico(BaseModel):
    """Corpo da decisão, no formato do `POST /v1/analises/{id}/decisao` da API. A sugestão que o médico viu e se ele
    concordou são conferidos aqui pela exibição registrada, não confiados ao cliente."""
    exibicao_id: Optional[int] = None
    sugestao_exibida: bool = False
    concordou_com_sugestao: Optional[bool] = None
    conduta_final: CondutaFinal
    normalidade_final: List[NormalidadeFinal] = Field(default_factory=list, max_length=200)
    decidido_em: datetime


@router.post("/documents/{document_id}/conduta-decisao", status_code=status.HTTP_201_CREATED)
async def registrar_decisao(
    document_id: str,
    corpo: DecisaoMedico,
    request: Request,
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.MANAGER])),
) -> dict:
    if not user_db.get_document_by_id(document_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento não encontrado")
    exibicao = user_db.obter_conduta_exibicao(document_id, exibicao_id=corpo.exibicao_id) if corpo.exibicao_id \
        else user_db.obter_conduta_exibicao(document_id, user_id=current_user.id)
    if corpo.exibicao_id and not exibicao:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Exibição não é deste documento")
    situacao_sugerida = (exibicao or {}).get("situacao_aso")
    sugestao_exibida = bool(situacao_sugerida)
    final = corpo.conduta_final.situacao_aso
    # Sem sugestão exibida não há concordância a registrar (regra do PDF da API).
    concordou = (final == situacao_sugerida) if sugestao_exibida else None
    # Gravado em UTC sem fuso, como o resto do banco.
    decidido_em = corpo.decidido_em if corpo.decidido_em.tzinfo is None \
        else corpo.decidido_em.astimezone(timezone.utc).replace(tzinfo=None)
    registro = user_db.registrar_conduta_decisao(
        document_id, (exibicao or {}).get("id"), sugestao_exibida, situacao_sugerida, concordou, final,
        (corpo.conduta_final.observacao or "").strip() or None, [n.model_dump() for n in corpo.normalidade_final],
        (exibicao or {}).get("versao_modelo"), decidido_em, current_user.id, current_user.email,
    )
    request.state.audit = {
        "action": "conduta.decisao.registrada",
        "resource": "document",
        "resource_id": document_id,
        "user_id": current_user.id,
        "user_email": current_user.email,
        "user_role": current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
        "clinic_id": current_user.clinic_id,
        "metadata": {"decisao_id": registro["id"], "situacao_final": final, "situacao_sugerida": situacao_sugerida,
                     "concordou_com_sugestao": concordou, "versao_modelo": (exibicao or {}).get("versao_modelo")},
    }
    return {"decisao_id": registro["id"], "registrado_em": _iso(registro["registrado_em"]),
            "sugestao_exibida": sugestao_exibida, "situacao_sugerida": situacao_sugerida,
            "concordou_com_sugestao": concordou}
