"""
Cliente da rede credenciada do BRNET — a lista que alimenta o vínculo entre a
clínica do ProntuAI e o credenciado do BRNET (coluna `clinics.brnet_id`).

    GET {PRONTUAI_API_BASE_URL}/api/rede/credenciada
    Headers: Service-Token / Username (as mesmas credenciais do monitoramento)

Contrato medido em out/2026:
- Sem paginação e sem filtro: devolve a rede inteira (~580 itens, ~146 KB) e
  ignora qualquer parâmetro na URL.
- Cada item: `identificador` ("C25414", único e estável entre chamadas), `nome`
  já no formato do rótulo do BRNET ("RECIFE - PE - QUALIMETRA"), `cidade`, `UF`,
  e também CNPJ, endereço e e-mail — que este cliente descarta: o CNPJ do
  credenciado ainda não é adotado (decisão de out/2026), e o campo `cnpj` da
  clínica alimenta a consulta de exames do BRNET.
- A lista parece trazer só a rede atual: 37 credenciados com pedido entre mai e
  out/2026 (3% dos pedidos) não aparecem nela.

O identificador é guardado como texto, com o "C": é assim que o BRNET o expõe,
e nada faz conta com ele.
"""
import asyncio
import logging
import time
import unicodedata
from typing import Any, Optional

import httpx
from pydantic import BaseModel

from app.core.config import settings
from app.services.brmed_service import _parse_response_error

logger = logging.getLogger(__name__)

ENDPOINT_PATH = "/api/rede/credenciada"

# A rede muda devagar (credenciamento é processo de dias), e a lista é lida a
# cada abertura do modal de clínica: uma hora de cache poupa o BRNET sem deixar
# um credenciado novo invisível por muito tempo.
CACHE_TTL_SECONDS = 3600


class CredenciadoRede(BaseModel):
    identificador: str
    nome: str
    cidade: Optional[str] = None
    uf: Optional[str] = None


class RedeCredenciadaIndisponivel(Exception):
    """A API não respondeu e não há lista anterior para usar no lugar."""


_lock = asyncio.Lock()
_cache: Optional[tuple[float, list[CredenciadoRede]]] = None


def _texto(valor: Any) -> Optional[str]:
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def mapear_rede(payload: Any) -> list[CredenciadoRede]:
    """Itens da API → credenciados. Item sem identificador ou sem nome fica de fora."""
    if not isinstance(payload, list):
        raise ValueError("Resposta da rede credenciada não é uma lista")
    rede: list[CredenciadoRede] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        identificador = _texto(item.get("identificador"))
        nome = _texto(item.get("nome"))
        if not identificador or not nome:
            continue
        rede.append(
            CredenciadoRede(
                identificador=identificador,
                nome=nome,
                cidade=_texto(item.get("cidade")),
                uf=_texto(item.get("UF")),
            )
        )
    # Ordem alfabética sem acento: com acento, "AÇAILÂNDIA" ia para depois de "ACARAU".
    rede.sort(key=lambda c: "".join(
        ch for ch in unicodedata.normalize("NFD", c.nome.upper()) if unicodedata.category(ch) != "Mn"
    ))
    return rede


async def _buscar_na_api() -> list[CredenciadoRede]:
    if not settings.ACCREDITED_MONITORING_SERVICE_TOKEN or not settings.ACCREDITED_MONITORING_USERNAME:
        raise RedeCredenciadaIndisponivel("Integração com a API BRNET não configurada (Service-Token/Username).")

    endpoint = f"{settings.PRONTUAI_API_BASE_URL.rstrip('/')}{ENDPOINT_PATH}"
    headers = {
        "Service-Token": settings.ACCREDITED_MONITORING_SERVICE_TOKEN,
        "Username": settings.ACCREDITED_MONITORING_USERNAME,
    }
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=settings.PRONTUAI_API_TIMEOUT_SECONDS) as client:
            response = await client.get(endpoint, headers=headers)
    except (httpx.TimeoutException, httpx.RequestError) as exc:
        logger.warning("[REDE-CREDENCIADA] request.failed elapsed=%.3fs error=%s", time.perf_counter() - started, exc)
        raise RedeCredenciadaIndisponivel(f"Falha de comunicação com a API do BRNET: {exc}") from exc

    logger.info(
        "[REDE-CREDENCIADA] request.done status=%s elapsed=%.3fs bytes=%s",
        response.status_code, time.perf_counter() - started, len(response.content),
    )
    if response.status_code != 200:
        raise RedeCredenciadaIndisponivel(_parse_response_error(response))
    try:
        return mapear_rede(response.json())
    except ValueError as exc:
        raise RedeCredenciadaIndisponivel("Resposta inválida da API do BRNET.") from exc


async def listar_rede_credenciada() -> list[CredenciadoRede]:
    """A rede credenciada, do cache quando ainda vale.

    Se a API falhar com o cache vencido, devolve a lista anterior: um credenciado
    que saiu da rede na última hora atrapalha menos que o cadastro de clínica
    parado. Só sem lista nenhuma é que a falha sobe.
    """
    global _cache
    async with _lock:
        agora = time.monotonic()
        if _cache and agora - _cache[0] < CACHE_TTL_SECONDS:
            return _cache[1]
        try:
            rede = await _buscar_na_api()
        except RedeCredenciadaIndisponivel:
            if _cache:
                logger.warning("[REDE-CREDENCIADA] usando lista de %.0f min atrás", (agora - _cache[0]) / 60)
                return _cache[1]
            raise
        _cache = (agora, rede)
        return rede


async def buscar_credenciado(identificador: str) -> Optional[CredenciadoRede]:
    """O credenciado com esse identificador, ou None se ele não está na rede."""
    alvo = identificador.strip().upper()
    for credenciado in await listar_rede_credenciada():
        if credenciado.identificador.upper() == alvo:
            return credenciado
    return None
