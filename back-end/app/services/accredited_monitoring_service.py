"""
Cliente da API BRNET de monitoramento de credenciados.

    GET {PRONTUAI_API_BASE_URL}/api/accrediteds/get-accredited-monitoring/?month=9&year=2026
    Headers: Service-Token / Username (token é por usuário)

Contrato medido em set/2026:
- `month` e `year` obrigatórios; filtram pela *data de solicitação* do pedido.
  Mês ainda sem solicitações devolve `[]`.
- Sem paginação: o mês inteiro vem numa lista só (~6.5k itens, ~7 MB, ~4 s).
- Erros 400 vêm em text/html com a mensagem crua ("O mês informado é inválido");
  credencial ausente ou inválida devolve 403 JSON `{"detail": ...}`.
- Auth: `Username` inexistente → 403 "Usuário inexistente."; token de outro usuário →
  403 "Você não tem persmissao...". `Authorization: Token ...` é ignorado.
"""
import logging
import re
import time
from datetime import date, datetime
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.models.accredited_monitoring import AtendimentoCredenciado, CredenciadoRef
from app.services.brmed_service import _parse_response_error

logger = logging.getLogger(__name__)

ENDPOINT_PATH = "/api/accrediteds/get-accredited-monitoring/"

# A API usa hífen ou travessão, às vezes sem espaço ("ITAPEVA - SP- SAME").
# A UF entre separadores é a âncora, para não quebrar cidade com hífen (EMBU-GUAÇU).
_CREDENCIADO_RE = re.compile(r"^(?P<cidade>.+?)\s*[-–]\s*(?P<uf>[A-Z]{2})\s*[-–]\s*(?P<nome>.+)$")


class MonitoramentoCredenciadosError(Exception):
    def __init__(self, mensagem: str, error_type: str, http_status: Optional[int] = None):
        super().__init__(mensagem)
        self.error_type = error_type  # "semantic" (parâmetro/contrato) ou "technical"
        self.http_status = http_status


def _vazio(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _texto(value: Any) -> Optional[str]:
    return None if _vazio(value) else str(value).strip()


def _sim_nao(value: Any) -> Optional[bool]:
    if _vazio(value):
        return None
    return str(value).strip().lower() == "sim"


def _data(value: Any) -> Optional[date]:
    if _vazio(value):
        return None
    return datetime.strptime(str(value).strip()[:10], "%d/%m/%Y").date()


def _data_hora(value: Any) -> Optional[datetime]:
    if _vazio(value):
        return None
    return datetime.strptime(str(value).strip(), "%d/%m/%Y %H:%M:%S")


def _inteiro(value: Any) -> Optional[int]:
    return None if _vazio(value) else int(value)


def _minutos(value: Any) -> int:
    horas, minutos = str(value).strip().split(":")
    return int(horas) * 60 + int(minutos)


def parse_credenciado(rotulo: str) -> CredenciadoRef:
    rotulo = (rotulo or "").strip()
    match = _CREDENCIADO_RE.match(rotulo)
    if not match:
        return CredenciadoRef(rotulo=rotulo)
    return CredenciadoRef(
        rotulo=rotulo,
        cidade=match.group("cidade").strip(),
        uf=match.group("uf"),
        nome=match.group("nome").strip(),
    )


def mapear_atendimento(item: dict) -> AtendimentoCredenciado:
    return AtendimentoCredenciado(
        pedido_exame_id=int(item["pedido_exame_id"]),
        credenciado=parse_credenciado(item.get("credenciado")),
        empresa=(item.get("empresa") or "").strip(),
        grupo=(item.get("grupo") or "").strip(),
        paciente=(item.get("paciente") or "").strip(),
        cpf_passaporte=(item.get("cpf_passaporte") or "").strip(),
        tipo_pedido_exame=(item.get("tipo_pedido_exame") or "").strip(),
        data_solicitacao=_data_hora(item.get("data_solicitacao")),
        data_confirmacao=_data_hora(item.get("data_confirmacao")),
        mes_agendamento=(item.get("mes_agendamento") or "").strip(),
        status_agendamento=(item.get("status_agendamento") or "").strip(),
        usuario_agendamento=(item.get("usuario_agendamento") or "").strip(),
        confirmacao_automatica=bool(_sim_nao(item.get("confirmacao_automatica"))),
        tempo_resposta_minutos=_minutos(item.get("tempo_resposta")),
        data_atendimento=_data(item.get("data_atendimento")),
        mes_atendimento=_texto(item.get("mes_atendimento")),
        data_cadastro_atendimento=_data(item.get("data_cadastro_atendimento")),
        usuario_atendimento=_texto(item.get("usuario_atendimento")),
        prazo_liberacao=_inteiro(item.get("prazo_liberacao")),
        data_previsao=_data(item.get("data_previsao")),
        utilizou_o_br_net=_sim_nao(item.get("utilizou_o_br_net")),
        status_expedicao_cliente=_texto(item.get("status_expedicao_cliente")),
        status_expedicao_brmed=_texto(item.get("status_expedicao_brmed")),
        data_liberacao=_data(item.get("data_liberacao")),
        usuario_expedicao=_texto(item.get("usuario_expedicao")),
        possui_anexo=bool(_sim_nao(item.get("possui_anexo"))),
        data_inclusao_exame_alterado=_data_hora(item.get("data_inclusao_exame_alterado")),
        data_inclusao_exame_nao_realizado=_data_hora(item.get("data_inclusao_exame_não_realizado")),
        data_inclusao_particularidade_nao_atendida=_data_hora(
            item.get("data_inclusao_particularidade_não_atendida")
        ),
        possui_observacao_cliente=bool(_sim_nao(item.get("possui_observacao_cliente"))),
        observacoes_cliente=_texto(item.get("observacoes_cliente")),
    )


async def consultar_monitoramento_credenciados(month: int, year: int) -> list[AtendimentoCredenciado]:
    """Pedidos de exame solicitados no mês/ano informado, já tipados."""
    if not 1 <= month <= 12:
        raise MonitoramentoCredenciadosError("month deve estar entre 1 e 12", "semantic", 400)

    if not settings.ACCREDITED_MONITORING_SERVICE_TOKEN or not settings.ACCREDITED_MONITORING_USERNAME:
        raise MonitoramentoCredenciadosError(
            "Integração com a API BRNET não configurada (Service-Token/Username).", "technical"
        )

    endpoint = f"{settings.PRONTUAI_API_BASE_URL.rstrip('/')}{ENDPOINT_PATH}"
    headers = {
        "Service-Token": settings.ACCREDITED_MONITORING_SERVICE_TOKEN,
        "Username": settings.ACCREDITED_MONITORING_USERNAME,
    }

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=settings.ACCREDITED_MONITORING_TIMEOUT_SECONDS) as client:
            response = await client.get(endpoint, params={"month": month, "year": year}, headers=headers)
    except (httpx.TimeoutException, httpx.RequestError) as exc:
        logger.warning(
            "[ACCREDITED-MONITORING] request.failed month=%s year=%s elapsed=%.3fs error=%s",
            month, year, time.perf_counter() - started, exc,
        )
        raise MonitoramentoCredenciadosError(f"Falha de comunicação com API externa: {exc}", "technical") from exc

    logger.info(
        "[ACCREDITED-MONITORING] request.done month=%s year=%s status=%s elapsed=%.3fs bytes=%s",
        month, year, response.status_code, time.perf_counter() - started, len(response.content),
    )

    if response.status_code != 200:
        error_type = "semantic" if response.status_code == 400 else "technical"
        raise MonitoramentoCredenciadosError(_parse_response_error(response), error_type, response.status_code)

    try:
        payload = response.json()
    except ValueError as exc:
        raise MonitoramentoCredenciadosError("Resposta inválida da API externa.", "technical", 200) from exc
    if not isinstance(payload, list):
        raise MonitoramentoCredenciadosError("Resposta inválida da API externa.", "technical", 200)

    registros: list[AtendimentoCredenciado] = []
    descartados = 0
    for item in payload:
        try:
            registros.append(mapear_atendimento(item))
        except Exception as exc:
            # Um item fora do contrato não derruba o mês inteiro; só o id vai para o log.
            descartados += 1
            logger.warning(
                "[ACCREDITED-MONITORING] item.descartado pedido_exame_id=%s error=%s",
                (item or {}).get("pedido_exame_id") if isinstance(item, dict) else None,
                type(exc).__name__,
            )
    if descartados:
        logger.warning("[ACCREDITED-MONITORING] %s de %s itens descartados", descartados, len(payload))
    return registros
