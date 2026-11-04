"""
Normalidade e alteração de exames.

- `GET /documents/{id}/normalidade`: valores lidos no PDF para cada exame da
  Comparação Detalhada, com a situação (normal, acima, abaixo) pela faixa que o
  laboratório imprimiu no laudo. Calculado na hora sobre o `ocr_markdown` gravado:
  melhorar a leitura vale para documentos já processados, sem reprocessar.
- `GET /normalidade/parametros`: a tela de Normalidade, só leitura. Decisão da
  Saúde em 28/10/2026: não se cadastra faixa de referência.

É só informação para quem checa: nada aqui muda status, faltantes ou decisão.
O SENDER fica de fora: a leitura é apoio à checagem, não devolutiva à clínica.
"""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import require_roles
from app.core.database import user_db
from app.models.normalidade import NormalidadeDocumento, ParametroLeitura
from app.models.user import User, UserRole
from app.services import layout_ocr, normalidade_exames as ne

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Normalidade de Exames"])

# Quem checa ou acompanha a checagem. Espelha o modal: CHECKER decide, CURATOR
# acompanha em modo leitura, gestão vê tudo.
_LEITORES = [UserRole.ADMIN, UserRole.MANAGER, UserRole.CHECKER, UserRole.CURATOR]


@router.get("/normalidade/parametros", response_model=List[ParametroLeitura])
def listar_parametros(current_user: User = Depends(require_roles(_LEITORES))) -> List[ParametroLeitura]:
    """O que o ProntuAI lê nos laudos. A faixa vem de cada laudo, não daqui."""
    return [
        ParametroLeitura(parametro=k, nome=p.nome, unidade=p.unidade, qualitativo=p.qualitativo,
                         normal_texto=p.normal_texto or None)
        for k, p in ne.PARAMETROS.items()
    ]


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
            linhas,
        )
    except Exception as e:
        # Leitura é informativa: falha aqui não pode travar a checagem. Só o tipo
        # do erro vai para o log; a mensagem pode carregar trecho do laudo.
        logger.warning(f"[NORMALIDADE] Leitura falhou no documento {document_id}: {type(e).__name__}")
        return NormalidadeDocumento(habilitada=True, itens=[])
    return NormalidadeDocumento(habilitada=True, itens=itens)
