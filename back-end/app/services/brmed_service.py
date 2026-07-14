import re
from datetime import datetime
from typing import Dict, Any, Optional
import logging
import time
import httpx
from app.core.config import settings
from app.core import metrics

logger = logging.getLogger(__name__)


def _digits_only(value: Optional[str]) -> str:
    return re.sub(r"\D", "", value or "")


def _normalize_cpf(cpf: Optional[str]) -> Optional[str]:
    if not cpf:
        return None
    digits = _digits_only(cpf)
    return digits if len(digits) == 11 else None


def _normalize_cnpj(cnpj: Optional[str]) -> Optional[str]:
    if not cnpj:
        return None
    digits = _digits_only(cnpj)
    return digits if len(digits) == 14 else None


def _normalize_passport(passaporte: Optional[str]) -> Optional[str]:
    if not passaporte:
        return None
    clean = re.sub(r"\s+", "", passaporte).upper()
    if not clean:
        return None
    if not re.fullmatch(r"[A-Z0-9]+", clean):
        return None
    return clean


def _parse_response_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, str):
            return payload
        if isinstance(payload, list) and payload:
            return str(payload[0])
        if isinstance(payload, dict):
            detail = payload.get("detail")
            if isinstance(detail, str):
                return detail
            if isinstance(detail, list) and detail:
                return str(detail[0])
            message = payload.get("message")
            if isinstance(message, str):
                return message
            if payload:
                return str(payload)
    except Exception:
        pass
    return (response.text or "").strip() or f"HTTP {response.status_code}"


def _parse_br_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%d/%m/%Y")
    except Exception:
        return None


def _select_latest_pedido(pedidos: list[dict]) -> Optional[dict]:
    if not pedidos:
        return None

    latest_with_date: Optional[dict] = None
    latest_date: Optional[datetime] = None
    for pedido in pedidos:
        data = _parse_br_date((pedido or {}).get("data_previsao_liberacao"))
        if not data:
            continue
        # Em empate de data, mantém o último na ordem de retorno.
        if latest_date is None or data >= latest_date:
            latest_date = data
            latest_with_date = pedido

    if latest_with_date is not None:
        return latest_with_date
    return pedidos[-1]


def _build_api_success_payload(
    payload: dict,
    cpf: Optional[str],
    passaporte: Optional[str],
    cnpj: str,
) -> Dict[str, Any]:
    pedidos = payload.get("pedidos_exames") or []
    pedidos = [p for p in pedidos if isinstance(p, dict)]
    pedido = _select_latest_pedido(pedidos)
    exames = (pedido or {}).get("exames") or []
    exames_nomes = []
    for exame in exames:
        if isinstance(exame, dict):
            nome = (exame.get("nome") or "").strip()
            if nome:
                exames_nomes.append(nome)
        elif isinstance(exame, str) and exame.strip():
            exames_nomes.append(exame.strip())

    tipo_identificador = "cpf" if cpf else "passaporte"
    identificador = cpf or passaporte

    return {
        "nome": payload.get("nome"),
        "id": payload.get("id"),
        "exames": exames_nomes,
        "source": "prontuai_api",
        "tipo_identificador_consulta": tipo_identificador,
        "identificador_consulta": identificador,
        "cpf_processado": cpf,
        "passaporte_processado": passaporte,
        "cnpj_processado": cnpj,
        "pedido_exame_id": (pedido or {}).get("pedido_exame_id"),
        "tipo_pedido_exame": (pedido or {}).get("tipo_pedido_exame"),
        "data_previsao_liberacao": (pedido or {}).get("data_previsao_liberacao"),
        "atendimento_realizado_em": (pedido or {}).get("atendimento_realizado_em"),
    }


async def consultar_exames_prontuai_api(
    cpf: Optional[str] = None,
    passaporte: Optional[str] = None,
    cnpj: Optional[str] = None,
) -> Dict[str, Any]:
    cpf_norm = _normalize_cpf(cpf)
    passaporte_norm = _normalize_passport(passaporte)
    cnpj_norm = _normalize_cnpj(cnpj)

    if cpf and not cpf_norm:
        return {"erro": "cpf deve conter somente números e 11 dígitos", "error_type": "semantic", "source": "prontuai_api", "http_status": 400}
    if cnpj and not cnpj_norm:
        return {"erro": "cnpj deve conter somente números e 14 dígitos", "error_type": "semantic", "source": "prontuai_api", "http_status": 400}
    if passaporte and not passaporte_norm:
        return {"erro": "passport deve conter apenas letras e números", "error_type": "semantic", "source": "prontuai_api", "http_status": 400}
    if cpf_norm and passaporte_norm:
        return {"erro": "Informe apenas um: cpf ou passaporte", "error_type": "semantic", "source": "prontuai_api", "http_status": 400}
    if not cpf_norm and not passaporte_norm:
        return {"erro": "cpf ou passaporte é obrigatório", "error_type": "semantic", "source": "prontuai_api", "http_status": 400}
    if not cnpj_norm:
        return {"erro": "cnpj é obrigatório e deve ter 14 dígitos", "error_type": "semantic", "source": "prontuai_api", "http_status": 400}

    if not settings.PRONTUAI_SERVICE_TOKEN or not settings.PRONTUAI_CLIENT_NAME:
        return {
            "erro": "Integração com ProntuAI API não configurada (Service-Token/Client-Name).",
            "error_type": "technical",
            "source": "prontuai_api",
            "http_status": None,
        }

    params: Dict[str, str] = {"cnpj": cnpj_norm}
    if cpf_norm:
        params["cpf"] = cpf_norm
    else:
        params["passport"] = passaporte_norm  # contrato externo usa "passport"

    endpoint = f"{settings.PRONTUAI_API_BASE_URL.rstrip('/')}/api/prontuai/patients_exams/"
    headers = {
        "Service-Token": settings.PRONTUAI_SERVICE_TOKEN,
        "Client-Name": settings.PRONTUAI_CLIENT_NAME,
    }

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=settings.PRONTUAI_API_TIMEOUT_SECONDS) as client:
            response = await client.get(endpoint, params=params, headers=headers)
    except (httpx.TimeoutException, httpx.RequestError) as exc:
        elapsed = time.perf_counter() - started
        logger.warning(
            "[PRONTUAI-API] request.failed source=prontuai_api type=technical elapsed=%.3fs cpf=%s passport=%s cnpj=%s error=%s",
            elapsed,
            "***" if cpf_norm else None,
            "***" if passaporte_norm else None,
            cnpj_norm,
            exc,
        )
        return {"erro": f"Falha de comunicação com API externa: {exc}", "error_type": "technical", "source": "prontuai_api", "http_status": None}

    elapsed = time.perf_counter() - started
    logger.info(
        "[PRONTUAI-API] request.done source=prontuai_api status=%s elapsed=%.3fs cnpj=%s has_cpf=%s has_passport=%s",
        response.status_code,
        elapsed,
        cnpj_norm,
        bool(cpf_norm),
        bool(passaporte_norm),
    )

    if response.status_code == 200:
        try:
            payload = response.json()
            if not isinstance(payload, dict):
                return {
                    "erro": "Resposta inválida da API externa.",
                    "error_type": "technical",
                    "source": "prontuai_api",
                    "http_status": 200,
                }
            return _build_api_success_payload(payload, cpf_norm, passaporte_norm, cnpj_norm)
        except Exception as exc:
            return {
                "erro": f"Falha ao interpretar resposta da API externa: {exc}",
                "error_type": "technical",
                "source": "prontuai_api",
                "http_status": 200,
            }

    error_msg = _parse_response_error(response)
    if response.status_code in (400, 404):
        return {
            "erro": error_msg,
            "error_type": "semantic",
            "source": "prontuai_api",
            "http_status": response.status_code,
        }

    return {
        "erro": error_msg,
        "error_type": "technical",
        "source": "prontuai_api",
        "http_status": response.status_code,
    }


async def consultar_exames_prontuai(
    cpf: Optional[str] = None,
    passaporte: Optional[str] = None,
    cnpj: Optional[str] = None,
) -> Dict[str, Any]:
    resultado = await consultar_exames_prontuai_api(cpf=cpf, passaporte=passaporte, cnpj=cnpj)
    metrics.PRONTUAI_API_CONSULTAS.labels(resultado="falha" if "erro" in resultado else "sucesso").inc()
    return resultado
