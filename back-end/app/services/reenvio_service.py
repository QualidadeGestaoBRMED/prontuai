"""
Reenvio de prontuário já liberado.

Clínicas reenviam prontuários que já foram aprovados. O reenvio virava um item
novo na Checagem, e a clínica entendia que o documento não tinha sido aprovado.
"Liberado" é aprovado pelo revisor — o que a clínica vê como "Aprovado".
Reconstruído sobre jun a 19/10/2026: 184 reenvios de documento já liberado
(109 tinham sido aprovados de novo, 72 rejeitados), por três critérios, nesta
ordem:

  1. mesmo arquivo de um liberado (9) — o hash do PDF;
  2. mesmo pedido do BRNET de um liberado da mesma clínica (74);
  3. sem pedido do BRNET: liberado do mesmo CPF e da mesma empresa (CNPJ lido do
     ASO), da mesma clínica, nos 30 dias anteriores (101). Sem pedido porque o
     BRNET não devolve pedido de expedição já fechada ("Expedição em aberto não
     encontrada") — é justamente o que acontece quando o pedido já foi liberado.

O CPF sozinho não basta: a mesma pessoa tem ASOs de tipos diferentes. O tipo de
ASO, que o ticket pedia junto, vem da mesma consulta ao BRNET que o pedido —
sem pedido, também não há tipo (nenhum documento do histórico tem um sem o
outro). Daí empresa + janela de 30 dias no lugar dele.

"Mesma clínica" é o mesmo cadastro ou o mesmo credenciado do BRNET. Dos 184,
35 vinham de outra clínica — 33 das duas unidades da N1MED, credenciados
diferentes no BRNET — e voltam para a Checagem.

Uma expedição pode ter vários prontuários, então casar com um liberado não
basta: é complemento, e segue para a Checagem, o envio que traz um exame que
faltava nos liberados (12 no período, 11 aprovados de novo pelo revisor) ou que
não tem nenhum exame em comum com eles (15 — outra parte da expedição, como o
laudo de laboratório). "Trouxe exame a mais" NÃO é sinal: o mesmo arquivo
reprocessado sai com 2+ exames diferentes em 4 de 9 casos, porque a extração
pela IA varia. Com clínica e complemento, os 184 viram 122.

O que a IA não enxerga — o laudo de um exame que ela deu como encontrado porque
estava listado no ASO — a clínica ou o revisor devolvem à Checagem pelo botão
"É um complemento" (`POST /v1/documents/{id}/complemento`); para isso o
resultado guarda o que a IA tinha decidido (`status_ia`, `motivo_ia`).

**Envio repetido ANTES da revisão (out/2026).** O mesmo prontuário mandado de
novo enquanto o primeiro ainda espera o revisor — pendente, ou aprovado ou
rejeitado só pela IA — virava mais um item na Checagem. Na cópia de produção de
23/10 eram 160 casos (contra 63 depois da liberação), e em 104 o revisor revisou
os dois. Os mesmos três critérios e a mesma separação de complemento valem para
ele; o liberado tem precedência. A clínica vê "já está em revisão" em vez de
"já foi liberado". Desliga sem deploy: REENVIO_EM_REVISAO=false.

**Mesmo arquivo, sem processar.** O arquivo idêntico a um liberado ou em revisão
(o hash do PDF) é reenvio de qualquer jeito: `mesmo_arquivo` acha o original
antes do OCR, e o job reaproveita o resultado dele (`resultado_reaproveitado`)
em vez de gastar Textract, BRNET e IA de novo. São poucos — 15 dos 223
reenvios do período —, mas custam um processamento inteiro cada.

Quem não é reenvio continua igual e segue para a Checagem: reenvio corrigido
depois de rejeição (100 no período) e complemento.
"""
import copy
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Any, Iterable, Optional

from app.core.pii import mask_identifier
from app.models.document import pedido_exame_id_do_payload

logger = logging.getLogger(__name__)

# 91 dos 92 envios repetidos por CPF + empresa do período chegaram em até 30 dias.
JANELA_CPF_EMPRESA = timedelta(days=30)
EM_REVISAO = os.getenv("REENVIO_EM_REVISAO", "true").strip().lower() not in ("0", "false", "nao", "no")


def _cnpj_da_empresa(resultado: dict) -> Optional[str]:
    cnpj = re.sub(r"\D", "", str(resultado.get("cnpj_processado") or ""))
    return cnpj if len(cnpj) == 14 else None


def _canonico(nome: str) -> str:
    """Nome do exame normalizado e trocado pelo representante do seu grupo de sinônimos."""
    # Import tardio: validacao_service carrega o índice FAISS no import.
    from app.services.validacao_service import _normalizar_exame, obter_sinonimos

    normalizado = _normalizar_exame(nome)
    return min(obter_sinonimos(normalizado) | {normalizado})


def _exames(itens: Iterable[Any]) -> set[str]:
    nomes = set()
    for item in itens or []:
        nome = item.get("nome") if isinstance(item, dict) else item
        if nome:
            canonico = _canonico(str(nome))
            if canonico:
                nomes.add(canonico)
    return nomes


def _motivo_de_complemento(resultado: dict, anterior: dict) -> Optional[str]:
    """Por que o envio é complemento dos liberados, e não reenvio; None se é reenvio."""
    novos = _exames(
        resultado.get("exames_ocr") or (resultado.get("ocr_result") or {}).get("exames_extraidos") or []
    )
    liberados = _exames(anterior.get("exames") or [])
    faltavam = _exames(anterior.get("faltantes") or []) - liberados
    if novos & faltavam:
        return "traz_exame_que_faltava"
    if novos and not novos & liberados:
        return "sem_exame_em_comum"
    return None


def liberado_anterior(
    user_db: Any,
    resultado: Any,
    *,
    cpf: Optional[str],
    content_hash: Optional[str],
    clinic_id: Optional[str],
    agora: Optional[datetime] = None,
) -> Optional[dict]:
    """
    O documento já liberado, ou ainda em revisão, de que este envio é reenvio,
    ou None.

    Devolve `{"documento_id", "liberado_em", "enviado_em" (ISO), "criterio",
    "situacao"}` — `criterio` é "arquivo", "pedido" ou "cpf_empresa";
    `situacao` é "liberado" ou "em_revisao" (sem `liberado_em`). Complemento dos liberados não é
    reenvio (ver o cabeçalho). Falha na consulta não bloqueia o envio: o
    documento segue como sempre, e o erro fica no log.
    """
    if not isinstance(resultado, dict):
        resultado = {}
    buscar = getattr(user_db, "buscar_liberado_anterior", None)
    if not callable(buscar):
        return None
    cpf_limpo = re.sub(r"\D", "", cpf or "")
    try:
        anterior = buscar(
            content_hash=content_hash or None,
            pedido_exame_id=pedido_exame_id_do_payload(resultado),
            cpf=cpf_limpo if len(cpf_limpo) == 11 else None,
            cnpj_empresa=_cnpj_da_empresa(resultado),
            clinic_id=clinic_id,
            desde=(agora or datetime.utcnow()) - JANELA_CPF_EMPRESA,
            incluir_em_revisao=EM_REVISAO,
        )
        if not anterior:
            return None
        # O mesmo arquivo é o mesmo documento, traga o que a IA ler desta vez.
        complemento = None if anterior["criterio"] == "arquivo" else _motivo_de_complemento(resultado, anterior)
    except Exception as exc:  # a detecção nunca derruba o processamento
        logger.warning("[REENVIO] falha ao procurar liberado anterior: %s", type(exc).__name__)
        return None
    if complemento:
        logger.info(
            "[REENVIO] complemento de liberado, segue para a Checagem: motivo=%s criterio=%s original=%s cpf=%s",
            complemento,
            anterior.get("criterio"),
            anterior.get("documento_id"),
            mask_identifier(cpf_limpo),
        )
        return None
    logger.info(
        "[REENVIO] reenvio: situacao=%s criterio=%s original=%s cpf=%s",
        anterior.get("situacao", "liberado"),
        anterior.get("criterio"),
        anterior.get("documento_id"),
        mask_identifier(cpf_limpo),
    )
    chaves = ("documento_id", "liberado_em", "enviado_em", "criterio", "situacao")
    return {"situacao": "liberado", **{chave: anterior[chave] for chave in chaves if chave in anterior}}


def mesmo_arquivo(user_db: Any, content_hash: Optional[str]) -> Optional[dict]:
    """
    O documento liberado ou em revisão com este mesmo arquivo (hash do PDF), ou
    None. Roda ANTES do processamento: achado, o job não refaz OCR, BRNET e IA
    (ver `resultado_reaproveitado`). Falha na consulta não bloqueia o envio.
    """
    buscar = getattr(user_db, "buscar_liberado_anterior", None)
    if not content_hash or not callable(buscar):
        return None
    try:
        achado = buscar(
            content_hash=content_hash,
            pedido_exame_id=None,
            cpf=None,
            cnpj_empresa=None,
            clinic_id=None,
            desde=datetime.utcnow() - JANELA_CPF_EMPRESA,
            incluir_em_revisao=EM_REVISAO,
        )
    except Exception as exc:
        logger.warning("[REENVIO] falha ao procurar o mesmo arquivo: %s", type(exc).__name__)
        return None
    # Só o arquivo idêntico pula o processamento; sem clínica, pedido e CPF a
    # consulta não casa por outro critério, e aqui não se confia nisso.
    return achado if achado and achado.get("criterio") == "arquivo" else None


# O que é do documento original, e não do resultado da leitura: a decisão do
# revisor e o aviso de um reenvio anterior. Copiar para o envio novo levaria o
# `reviewed_by` do payload para a coluna e tiraria o documento da fila.
_DO_DOCUMENTO = (
    "document_id", "reenvio", "reenvio_desfeito", "reviewed_by", "reviewed_at",
    "approvalReason", "approval_reason", "rejectionReason", "rejection_reason",
)


def resultado_reaproveitado(original: Any) -> Optional[dict]:
    """
    O resultado do processamento do documento original, para o envio do mesmo
    arquivo: a leitura é a mesma, sem refazer OCR, BRNET e IA. Sai sem o que é
    do documento (`_DO_DOCUMENTO`), com o texto do OCR de volta. None se o
    original não tem resultado gravado — aí o envio é processado como sempre.
    """
    payload = getattr(original, "result_payload", None)
    if not isinstance(payload, dict) or not payload:
        return None
    resultado = copy.deepcopy(payload)
    for chave in _DO_DOCUMENTO:
        resultado.pop(chave, None)
    ocr = resultado.get("ocr_result") if isinstance(resultado.get("ocr_result"), dict) else {}
    if not ocr.get("text") and getattr(original, "ocr_markdown", None):
        resultado["ocr_result"] = {**ocr, "text": original.ocr_markdown}
    resultado["reaproveitado_de"] = getattr(original, "id", None)
    return resultado


def marcar(resultado: dict, reenvio: dict, *, status_ia: str, motivo_ia: Optional[str]) -> None:
    """
    Grava no resultado o aviso do reenvio e o que a IA tinha decidido.

    A decisão da IA é o que o documento volta a ser se a clínica ou o revisor
    disserem que era complemento (`desfazer_reenvio`).
    """
    resultado["reenvio"] = {
        **reenvio,
        "status_ia": status_ia,
        "motivo_ia": motivo_ia if status_ia == "rejected" else None,
    }
