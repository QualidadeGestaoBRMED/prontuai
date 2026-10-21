"""
Reenvio de prontuário já liberado.

Clínicas reenviam prontuários que já foram aprovados. O reenvio virava um item
novo na Checagem, e a clínica entendia que o documento não tinha sido aprovado.
"Liberado" é aprovado pelo revisor — o que a clínica vê como "Aprovado".
Reconstruído sobre jun a 19/10/2026: 184 reenvios de documento já liberado
(109 tinham sido aprovados de novo, 72 rejeitados), por três critérios, nesta
ordem:

  1. mesmo arquivo de um liberado (9) — o hash do PDF;
  2. mesmo pedido do BRNET de um liberado (74);
  3. sem pedido do BRNET: liberado do mesmo CPF e da mesma empresa (CNPJ lido do
     ASO) nos 30 dias anteriores (101). Sem pedido porque o BRNET não devolve
     pedido de expedição já fechada ("Expedição em aberto não encontrada") —
     é justamente o que acontece quando o pedido já foi liberado.

O CPF sozinho não basta: a mesma pessoa tem ASOs de tipos diferentes. O tipo de
ASO, que o ticket pedia junto, vem da mesma consulta ao BRNET que o pedido —
sem pedido, também não há tipo (nenhum documento do histórico tem um sem o
outro). Daí empresa + janela de 30 dias no lugar dele.

Quem não é reenvio continua igual e segue para a Checagem: reenvio corrigido
depois de rejeição, complemento de pendente e reenvio de documento aprovado só
pela IA, ainda aguardando o revisor (~90 no período — a clínica o vê como
"Aguardando Revisão"; fica para o complemento com histórico).
"""
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Optional

from app.core.pii import mask_identifier
from app.models.document import pedido_exame_id_do_payload

logger = logging.getLogger(__name__)

JANELA_CPF_EMPRESA = timedelta(days=30)


def _cnpj_da_empresa(resultado: dict) -> Optional[str]:
    cnpj = re.sub(r"\D", "", str(resultado.get("cnpj_processado") or ""))
    return cnpj if len(cnpj) == 14 else None


def liberado_anterior(
    user_db: Any,
    resultado: Any,
    *,
    cpf: Optional[str],
    content_hash: Optional[str],
    agora: Optional[datetime] = None,
) -> Optional[dict]:
    """
    O documento já liberado de que este envio é reenvio, ou None.

    Devolve `{"documento_id", "liberado_em" (ISO), "criterio"}` — `criterio` é
    "arquivo", "pedido" ou "cpf_empresa". Falha na consulta não bloqueia o envio:
    o documento segue como sempre, e o erro fica no log.
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
            desde=(agora or datetime.utcnow()) - JANELA_CPF_EMPRESA,
        )
    except Exception as exc:  # a detecção nunca derruba o processamento
        logger.warning("[REENVIO] falha ao procurar liberado anterior: %s", type(exc).__name__)
        return None
    if anterior:
        logger.info(
            "[REENVIO] reenvio de liberado: criterio=%s original=%s cpf=%s",
            anterior.get("criterio"),
            anterior.get("documento_id"),
            mask_identifier(cpf_limpo),
        )
    return anterior
