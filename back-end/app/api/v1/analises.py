"""API de Normalidade e Conduta Sugerida (doc "ProntuAI: API de Normalidade e Conduta Sugerida", Gabriel, 18/11/2026).

Ambiente de homologação: o contrato é o final, mas a conduta vem do modelo mock (`versao_modelo: "mock"`), para o
consumidor integrar antes de o modelo ficar pronto. As decisões da homologação não viram dado de treino.

Rotas (todas sob /v1):
    POST /v1/analises                       envia o PDF e abre uma análise (202 + analise_id)
    GET  /v1/analises/{analise_id}          estado e resultado
    POST /v1/analises/{analise_id}/decisao  decisão do médico (204)

Autenticação: headers `Service-Token` e `Username`, um par por consumidor (variável API_CONSUMIDORES,
"usuario:token,usuario2:token2"). Credencial de um ambiente não vale no outro.

Limitação desta primeira versão: as análises ficam em memória (somem num restart). A tabela própria vem em seguida.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ValidationError

router = APIRouter(tags=["Análises (Normalidade e Conduta Sugerida)"])

VERSAO_MODELO = "mock"
TAMANHO_MAXIMO = int(os.getenv("API_ANALISES_TAMANHO_MAXIMO_MB", "30")) * 1024 * 1024
PRAZO_RESULTADO = timedelta(days=int(os.getenv("API_ANALISES_DIAS_RESULTADO", "90")))
PRAZO_DECISAO = timedelta(days=int(os.getenv("API_ANALISES_DIAS_DECISAO", "90")))
JANELA_IDEMPOTENCIA = timedelta(hours=24)
ATRASO_MOCK_S = float(os.getenv("API_ANALISES_ATRASO_MOCK_S", "3"))

SituacaoASO = Literal["LIBERADO", "LIBERADO_COM_ENCAMINHAMENTO", "RETIDO", "INAPTO"]
Classificacao = Literal["normal", "alterado", "inconclusivo"]

_lock = threading.Lock()
_analises: dict[str, dict] = {}
_idempotencia: dict[tuple[str, str], tuple[str, str, datetime]] = {}


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _consumidores() -> dict[str, str]:
    pares = [p.strip() for p in os.getenv("API_CONSUMIDORES", "").split(",") if ":" in p]
    return {u.strip(): t.strip() for u, t in (p.split(":", 1) for p in pares)}


def _consumidor(service_token: Optional[str], username: Optional[str]) -> str:
    esperado = _consumidores().get(username or "")
    if not service_token or not username or not esperado or not hmac.compare_digest(esperado, service_token):
        raise HTTPException(status_code=401, detail="Token ausente, inválido ou expirado.")
    return username


def _analise_do_consumidor(analise_id: str, consumidor: str) -> dict:
    with _lock:
        a = _analises.get(analise_id)
    if a is None or a["consumidor"] != consumidor:
        raise HTTPException(status_code=404, detail="analise_id não existe ou não pertence ao consumidor.")
    return a


# ---------------------------------------------------------------------------------------------------------------
# Modelo mock: devolve o resultado no formato final (o exemplo da doc), com o pedido desta análise.
# ---------------------------------------------------------------------------------------------------------------

def _resultado_mock(a: dict) -> dict:
    return {
        "contexto": {
            "empresa": "Modec",
            "tipo_exame": "PERIODICO",
            "funcao": "Técnico de manutenção",
            "riscos": ["Ruído", "Benzeno"],
            "atividades_criticas": ["NR_35"],
            "particularidades": ["Glicemia: seguir a planilha de conduta da empresa"],
            "ficha_medica": [
                {"campo": "doencas_cronicas_diabetes_mellitus", "valor": "sim"},
                {"campo": "doencas_cronicas_diabetes_mellitus_uso_medicamento", "valor": "nao"},
                {"campo": "doencas_cronicas_hipertensao", "valor": "nao_informado"},
            ],
        },
        "presenca_exames": {
            "todos_encontrados": False,
            "exames": [
                {"exame_id": "101", "exame": "Hemograma completo", "encontrado": True, "pagina": 2},
                {"exame_id": "102", "exame": "Glicemia de jejum", "encontrado": True, "pagina": 3},
                {"exame_id": "103", "exame": "Audiometria", "encontrado": True, "pagina": 5},
                {"exame_id": "104", "exame": "Eletrocardiograma", "encontrado": False, "pagina": None},
            ],
        },
        "normalidade": [
            {"exame_id": "101", "exame": "Hemograma completo", "classificacao": "normal", "direcao": None, "desvio": None,
             "valor": "Sem alterações", "unidade": None, "faixa_referencia": None, "pagina": 2},
            {"exame_id": "102", "exame": "Glicemia de jejum", "classificacao": "alterado", "direcao": "acima",
             "desvio": 0.92, "valor": "192", "unidade": "mg/dL",
             "faixa_referencia": {"min": 70, "max": 100, "texto": "70 a 100 mg/dL"}, "pagina": 3},
            {"exame_id": "103", "exame": "Audiometria", "classificacao": "inconclusivo", "direcao": None, "desvio": None,
             "valor": None, "unidade": None, "faixa_referencia": None, "pagina": 5},
        ],
        "conduta_sugerida": {
            "situacao_aso": "RETIDO",
            "confianca": 0.71,
            "fatores": [
                "Glicemia de jejum 92% acima da faixa",
                "Trabalho em altura (NR-35)",
                "Diabetes informado na ficha, sem uso de medicamento",
            ],
            "explicacao": "Glicemia muito acima da faixa em função com trabalho em altura, com diabetes informado e "
                          "sem uso de medicamento. Sugere reter o ASO.",
            "alertas": [
                "Eletrocardiograma previsto e não encontrado no documento",
                "Audiometria inconclusiva: não foi possível ler o resultado",
            ],
            "regras_cliente": [
                {"exame_id": "102", "regra": "Glicemia acima da referência em trabalho em altura: reter ASO",
                 "efeito": "RETIDO"},
            ],
        },
        "motivo_sem_sugestao": None,
    }


def _aplicar_regras_de_uso(r: dict) -> dict:
    """Regras de uso da doc, aplicadas sobre a saída do modelo (mock ou real)."""
    c = r.get("conduta_sugerida")
    if not c:
        return r
    # INAPTO nunca é sugerido: inaptidão sai como RETIDO.
    if c["situacao_aso"] == "INAPTO":
        c["situacao_aso"] = "RETIDO"
    # Exame previsto ausente ou inconclusivo nunca libera; cada um entra em alertas.
    ausentes = [e["exame"] for e in r["presenca_exames"]["exames"] if not e["encontrado"]]
    inconclusivos = [n["exame"] for n in r["normalidade"] if n["classificacao"] == "inconclusivo"]
    if (ausentes or inconclusivos) and c["situacao_aso"] in ("LIBERADO", "LIBERADO_COM_ENCAMINHAMENTO"):
        c["situacao_aso"] = "RETIDO"
    for nome in ausentes:
        alerta = f"{nome} previsto e não encontrado no documento"
        if alerta not in c["alertas"]:
            c["alertas"].append(alerta)
    for nome in inconclusivos:
        if not any(a.startswith(nome) and "inconclusiv" in a for a in c["alertas"]):
            c["alertas"].append(f"{nome} inconclusiva: não foi possível ler o resultado")
    # Regra do cliente vale sobre o modelo: a sugestão nunca é menos restritiva que ela.
    ordem = {"LIBERADO": 0, "LIBERADO_COM_ENCAMINHAMENTO": 1, "RETIDO": 2}
    for regra in c.get("regras_cliente") or []:
        if ordem.get(regra["efeito"], 0) > ordem[c["situacao_aso"]]:
            c["situacao_aso"] = regra["efeito"]
    return r


async def _processar(analise_id: str) -> None:
    await asyncio.sleep(ATRASO_MOCK_S)
    with _lock:
        a = _analises.get(analise_id)
    if a is None:
        return
    try:
        r = _aplicar_regras_de_uso(_resultado_mock(a))
        with _lock:
            a.update(r, status="concluido")
    except Exception as exc:  # noqa: BLE001 — falha no processamento não é erro HTTP
        with _lock:
            a.update(status="erro", erro={"mensagem": f"Falha no processamento: {exc.__class__.__name__}"})


# ---------------------------------------------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------------------------------------------

@router.post("/analises", status_code=202)
async def criar_analise(
    request: Request,
    arquivo: Optional[UploadFile] = File(None),
    pedido_exame_id: Optional[str] = Form(None),
    service_token: Optional[str] = Header(None, alias="Service-Token"),
    username: Optional[str] = Header(None, alias="Username"),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    consumidor = _consumidor(service_token, username)
    if arquivo is None:
        raise HTTPException(status_code=400, detail="Arquivo ausente.")
    conteudo = await arquivo.read()
    if len(conteudo) > TAMANHO_MAXIMO:
        raise HTTPException(status_code=413, detail=f"Arquivo acima do tamanho máximo ({TAMANHO_MAXIMO // 1024 // 1024} MB).")
    if not conteudo.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="O arquivo não é PDF.")
    pedido = (pedido_exame_id or "").strip() or None
    # Na homologação não há consulta ao BR NET: o pedido informado precisa ao menos ser numérico.
    if pedido is not None and not pedido.isdigit():
        raise HTTPException(status_code=422, detail="pedido_exame_id informado não existe no BR NET.")
    hash_arquivo = hashlib.sha256(conteudo).hexdigest()
    agora = _agora()

    if idempotency_key:
        chave = (consumidor, idempotency_key)
        with _lock:
            anterior = _idempotencia.get(chave)
        if anterior and agora - anterior[2] <= JANELA_IDEMPOTENCIA:
            if anterior[1] != hash_arquivo:
                raise HTTPException(status_code=409, detail="Idempotency-Key já usada com outro arquivo.")
            return JSONResponse(status_code=202, content={"analise_id": anterior[0], "status": "processando"})

    analise_id = str(uuid.uuid4())
    a = {
        "analise_id": analise_id, "status": "processando", "consumidor": consumidor,
        "pedido_exame_id": pedido or "000123", "origem_pedido": "informado" if pedido else "encontrado",
        "criado_em": agora, "disponivel_ate": agora + PRAZO_RESULTADO, "decisao_ate": agora + PRAZO_DECISAO,
        "hash_arquivo": hash_arquivo, "decisao": None,
    }
    with _lock:
        _analises[analise_id] = a
        if idempotency_key:
            _idempotencia[(consumidor, idempotency_key)] = (analise_id, hash_arquivo, agora)
    asyncio.create_task(_processar(analise_id))
    return JSONResponse(status_code=202, content={"analise_id": analise_id, "status": "processando"})


@router.get("/analises/{analise_id}")
async def consultar_analise(
    analise_id: str,
    service_token: Optional[str] = Header(None, alias="Service-Token"),
    username: Optional[str] = Header(None, alias="Username"),
):
    consumidor = _consumidor(service_token, username)
    a = _analise_do_consumidor(analise_id, consumidor)
    if _agora() > a["disponivel_ate"]:
        raise HTTPException(status_code=410, detail="Análise expirada.")
    if a["status"] == "processando":
        return {"analise_id": analise_id, "status": "processando"}
    corpo = {
        "analise_id": analise_id, "status": a["status"], "pedido_exame_id": a["pedido_exame_id"],
        "origem_pedido": a["origem_pedido"], "disponivel_ate": _iso(a["disponivel_ate"]),
        "decisao_ate": _iso(a["decisao_ate"]), "versao_modelo": VERSAO_MODELO, "confianca_calibrada": False,
    }
    if a["status"] == "erro":
        return {**corpo, "erro": a["erro"]}
    return {**corpo, "contexto": a["contexto"], "presenca_exames": a["presenca_exames"], "normalidade": a["normalidade"],
            "conduta_sugerida": a["conduta_sugerida"], "motivo_sem_sugestao": a["motivo_sem_sugestao"]}


class _CondutaFinal(BaseModel):
    situacao_aso: SituacaoASO
    observacao: Optional[str] = None


class _NormalidadeFinal(BaseModel):
    exame_id: str
    classificacao: Classificacao


class _Decisao(BaseModel):
    concordou_com_sugestao: Optional[bool] = None
    sugestao_exibida: bool
    conduta_final: _CondutaFinal
    normalidade_final: list[_NormalidadeFinal] = []
    decidido_em: datetime


@router.post("/analises/{analise_id}/decisao", status_code=204)
async def registrar_decisao(
    analise_id: str,
    request: Request,
    service_token: Optional[str] = Header(None, alias="Service-Token"),
    username: Optional[str] = Header(None, alias="Username"),
):
    consumidor = _consumidor(service_token, username)
    a = _analise_do_consumidor(analise_id, consumidor)
    try:
        decisao = _Decisao.model_validate(await request.json())
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Corpo da decisão fora do formato ou fora das enumerações: {exc.__class__.__name__}")
    if not decisao.sugestao_exibida and decisao.concordou_com_sugestao is not None:
        raise HTTPException(status_code=422, detail="Sem sugestão exibida, concordou_com_sugestao deve ser null.")
    if a["status"] == "processando":
        raise HTTPException(status_code=409, detail="A análise ainda está em processamento.")
    if _agora() > a["decisao_ate"]:
        raise HTTPException(status_code=410, detail="Decisão enviada depois de decisao_ate.")
    with _lock:
        a["decisao"] = {**decisao.model_dump(mode="json"), "recebida_em": _iso(_agora()), "versao_modelo": VERSAO_MODELO,
                        "vira_treino": False}  # homologação: decisão não vira dado de treino
    return Response(status_code=204)
