"""
Onde cada exame da Comparação Detalhada aparece no PDF.

- `GET /documents/{id}/localizacoes`: para cada exame da tabela de comparação,
  as linhas do documento onde ele aparece (página e caixa), na ordem em que a
  tela deve oferecer. O revisor clica no exame e o visualizador rola até lá,
  com a linha destacada.
- `GET /documents/{id}/texto`: o texto lido pelo OCR, linha a linha, com a
  posição na página. É o que a busca do visualizador usa: PDF escaneado não tem
  texto próprio, e a busca do navegador não acha nada nele.

Calculado na hora sobre o `ocr_markdown` e o layout gravados (ver
`app/services/layout_ocr.py`): melhorar o catálogo de sinônimos vale também para
documentos já processados. Documento sem layout responde `disponivel: false`.

É só navegação: nada aqui muda status, faltantes ou decisão. O SENDER fica de
fora, como na leitura de normalidade: é apoio à checagem.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import require_roles
from app.core.database import user_db
from app.models.localizacao import LocalizacoesDocumento, TextoDocumento
from app.models.user import User, UserRole
from app.services import layout_ocr, workflow_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Localização no PDF"])

# Quem checa ou acompanha a checagem. Espelha o modal: CHECKER decide, CURATOR
# acompanha em modo leitura, gestão vê tudo.
_LEITORES = [UserRole.ADMIN, UserRole.MANAGER, UserRole.CHECKER, UserRole.CURATOR]


def _termos_do_exame(*nomes: str | None) -> set[str]:
    """O nome do exame e o lido no OCR, com os sinônimos do catálogo — o laudo
    de GLICEMIA DE JEJUM se chama GLICOSE, o de AUDIOMETRIA TONAL, AUDIOGRAMA."""
    termos: set[str] = set()
    for nome in nomes:
        normalizado = workflow_service._normalizar_busca(nome or "")
        if normalizado:
            termos.add(normalizado)
            termos |= workflow_service.obter_sinonimos(normalizado)
    return termos


@router.get("/documents/{document_id}/localizacoes", response_model=LocalizacoesDocumento)
def localizacoes_do_documento(
    document_id: str,
    current_user: User = Depends(require_roles(_LEITORES)),
) -> LocalizacoesDocumento:
    """Para cada exame da Comparação Detalhada, onde ele aparece no PDF."""
    document = user_db.get_document_by_id(document_id)
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento não encontrado")
    try:
        linhas = layout_ocr.alinhar(document.ocr_markdown or "", user_db.get_document_layout(document_id))
        if linhas is None:
            return LocalizacoesDocumento(disponivel=False)

        payload = document.result_payload if isinstance(document.result_payload, dict) else {}
        detalhes = (payload.get("analysis_details") or {}).get("match_confidence") or []
        lido_no_ocr = {d.get("exame"): d.get("ocr_match") for d in detalhes if isinstance(d, dict)}

        normalizadas = layout_ocr.normalizar_linhas(linhas, workflow_service._normalizar_busca)
        paginas_aso = layout_ocr.paginas_da_lista_aso(linhas)
        exames = []
        for item in payload.get("tabela_comparacao") or []:
            exame = item.get("exame") if isinstance(item, dict) else None
            if not exame:
                continue
            ocorrencias = layout_ocr.localizar_termos(
                linhas, normalizadas, _termos_do_exame(exame, lido_no_ocr.get(exame)), paginas_aso
            )
            if ocorrencias:
                exames.append({"exame": exame, "ocorrencias": ocorrencias})
    except Exception as e:
        # Navegação é apoio: falha aqui não pode travar a checagem. Só o tipo do
        # erro vai para o log; a mensagem pode carregar trecho do documento.
        logger.warning(f"[LOCALIZACAO] Falhou no documento {document_id}: {type(e).__name__}")
        return LocalizacoesDocumento(disponivel=False)
    return LocalizacoesDocumento(disponivel=True, exames=exames)


@router.get("/documents/{document_id}/texto", response_model=TextoDocumento)
def texto_do_documento(
    document_id: str,
    current_user: User = Depends(require_roles(_LEITORES)),
) -> TextoDocumento:
    """O texto do OCR com a posição de cada linha, para a busca no documento.

    É o mesmo texto que o revisor já vê no PDF; nada sai do que a checagem mostra.
    """
    document = user_db.get_document_by_id(document_id)
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento não encontrado")
    try:
        linhas = layout_ocr.alinhar(document.ocr_markdown or "", user_db.get_document_layout(document_id))
    except Exception as e:
        logger.warning(f"[LOCALIZACAO] Texto indisponível no documento {document_id}: {type(e).__name__}")
        linhas = None
    if not linhas:
        return TextoDocumento(disponivel=False)
    escala = layout_ocr.ESCALA
    return TextoDocumento(
        disponivel=True,
        linhas=[
            {
                "pagina": linha.pagina,
                "texto": linha.texto,
                **layout_ocr.caixa_json(linha.caixa),
                "palavras": [[x / escala, w / escala] for x, w in linha.palavras],
            }
            for linha in linhas
        ],
    )
