"""Indicadores do dashboard, lidos do banco do ambiente em que a API roda.

O painel nasceu de uma extração congelada (JSON commitado no front). Isso fazia
dev e staging exibirem número de produção, que é a pior forma de errar: parece
certo. Aqui o dado vem sempre do `DATABASE_URL` do processo — em dev, dado de
dev; em produção, produção.

A consulta (`sql/dashboard_indicadores.sql`) é analítica: varre `documents`,
`audit_logs` e o `result_payload` inteiro em três granularidades, e leva alguns
segundos. Por isso ela NÃO roda a cada acesso.

Quando ela roda:
  * uma vez por dia, no horário de virada (7h em São Paulo, por padrão), numa
    tarefa de fundo — assim o primeiro acesso da manhã já encontra o número pronto;
  * no primeiro acesso depois de o processo subir, ou depois da virada, se a
    tarefa de fundo não tiver rodado (deploy no meio do dia, por exemplo);
  * sob demanda, pelo botão "Atualizar" da tela, que chama `?forcar=true`.

O cache é por processo. Com mais de um worker cada um tem o seu, e cada um roda
a própria atualização diária — aceitável porque o dado é agregado e a janela é
a mesma; se virar problema, o caminho é Redis, como no rate limit.
"""
import asyncio
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.core.config import Settings

logger = logging.getLogger(__name__)

_SQL_PATH = os.path.join(os.path.dirname(__file__), "sql", "dashboard_indicadores.sql")

# Seções que o dashboard consome. O resto do que a consulta devolve ('revisao',
# 'extracao_dia') é descartado para não trafegar ~30 KB que ninguém lê.
SECOES = ("periodo", "totais", "series", "acuracia", "clinicas", "exames")

# Virada do dia: a partir daqui o número do dia anterior é considerado velho.
# O fuso é explícito porque o container roda em UTC — sem isso, "7h" viraria 4h
# da manhã no Brasil.
HORA_ATUALIZACAO = int(os.getenv("DASHBOARD_REFRESH_HOUR", "7"))
MINUTO_ATUALIZACAO = int(os.getenv("DASHBOARD_REFRESH_MINUTE", "0"))
FUSO = ZoneInfo(os.getenv("DASHBOARD_REFRESH_TZ", "America/Sao_Paulo"))

# Teto de execução no banco. Estourar vira erro claro para o usuário em vez de
# uma conexão presa segurando worker.
TIMEOUT_MS = int(os.getenv("DASHBOARD_STATEMENT_TIMEOUT_MS", "120000"))

# Expedições de clínicas credenciadas, por dia: denominador do indicador
# "Expedições via ProntuAI". É o único dado do painel que NÃO sai do banco — vem
# de uma extração do BRNET (rel_expedição_credenciadas_final.xlsx) convertida
# para JSON no formato {"YYYY-MM-DD": inteiro}.
#
# Fica fora do repositório de propósito: é volume de operação, e dado de
# produção não tem por que viajar no git nem no bundle do browser. Sem o
# arquivo, o painel de cobertura some e o KPI cai no total absoluto — degradar
# assim é melhor do que inventar um denominador.
EXPEDICOES_PATH = os.getenv(
    "DASHBOARD_EXPEDICOES_PATH",
    os.path.join(Settings.BASE_DIR, "data", "expedicoes_credenciadas.json"),
)

_sql: Optional[str] = None
_expedicoes: Optional[dict[str, int]] = None
# (validade, dados): a partir de `validade` o cache é considerado vencido.
_cache: Optional[tuple[datetime, dict[str, Any]]] = None
_lock = threading.Lock()


_DIA = re.compile(r"\d{4}-\d{2}-\d{2}")


class DashboardIndisponivel(RuntimeError):
    """A consulta não pôde ser executada — timeout, banco fora, SQL inválido."""


def agora() -> datetime:
    """Ponto único de leitura do relógio — os testes trocam esta função."""
    return datetime.now(FUSO)


def proxima_virada(referencia: Optional[datetime] = None) -> datetime:
    """Próximo horário de atualização depois de `referencia`."""
    base = referencia or agora()
    virada = base.replace(
        hour=HORA_ATUALIZACAO, minute=MINUTO_ATUALIZACAO, second=0, microsecond=0
    )
    if virada <= base:
        virada += timedelta(days=1)
    return virada


def _carregar_sql() -> str:
    global _sql
    if _sql is None:
        with open(_SQL_PATH, encoding="utf-8") as fh:
            _sql = fh.read()
    return _sql


def _carregar_expedicoes() -> dict[str, int]:
    """Lê a extração do BRNET do disco. Ausência e formato torto não são erro.

    Este número não é do banco, então não pode derrubar o resto do painel: se o
    arquivo não existir, o dashboard funciona inteiro menos a cobertura.
    """
    global _expedicoes
    if _expedicoes is not None:
        return _expedicoes

    if not os.path.exists(EXPEDICOES_PATH):
        logger.warning(
            "[DASHBOARD] %s não existe: cobertura de expedições fica indisponível",
            EXPEDICOES_PATH,
        )
        _expedicoes = {}
        return _expedicoes

    try:
        with open(EXPEDICOES_PATH, encoding="utf-8") as fh:
            bruto = json.load(fh)
        # O arquivo é gerado por conversão manual de planilha: valida a forma em
        # vez de confiar. Entrada torta é descartada, não derruba o resto.
        limpo = {
            str(dia): int(qtd)
            for dia, qtd in (bruto or {}).items()
            if _DIA.fullmatch(str(dia)) and isinstance(qtd, (int, float))
        }
        descartadas = len(bruto or {}) - len(limpo)
        if descartadas:
            logger.warning("[DASHBOARD] %s entradas inválidas em %s", descartadas, EXPEDICOES_PATH)
        logger.info("[DASHBOARD] %s dias de expedições carregados", len(limpo))
        _expedicoes = limpo
    except Exception as exc:  # noqa: BLE001 - arquivo externo, nunca derruba o painel
        logger.error("[DASHBOARD] falha ao ler %s: %s", EXPEDICOES_PATH, exc)
        _expedicoes = {}
    return _expedicoes


def _consultar() -> dict[str, Any]:
    """Roda a consulta e devolve só as seções do dashboard."""
    # Import tardio: `app.core.database` falha em fail-fast sem DATABASE_URL, e
    # o cache deste módulo precisa ser testável sem banco nenhum.
    from app.core.database import user_db

    inicio = time.monotonic()
    with user_db.engine.connect() as conn:
        with conn.begin():
            # Transação só de leitura e com teto de tempo: este endpoint não
            # escreve nada e não pode prender o banco.
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(
                text("SELECT set_config('statement_timeout', :ms, true)"),
                {"ms": str(TIMEOUT_MS)},
            )
            linha = conn.execute(text(_carregar_sql())).scalar()

    if not linha:
        raise DashboardIndisponivel("a consulta não devolveu nada")

    bruto = json.loads(linha)
    dados = {secao: bruto.get(secao) for secao in SECOES}
    momento = agora()
    dados["expedicoes_dia"] = _carregar_expedicoes()
    dados["ambiente"] = Settings.APP_ENV
    dados["gerado_em"] = momento.isoformat()
    dados["proxima_atualizacao"] = proxima_virada(momento).isoformat()

    logger.info(
        "[DASHBOARD] indicadores calculados em %.1fs (ambiente=%s, clinicas=%s, exames=%s)",
        time.monotonic() - inicio,
        dados["ambiente"],
        len(dados.get("clinicas") or []),
        len(dados.get("exames") or []),
    )
    return dados


def obter_indicadores(forcar: bool = False) -> dict[str, Any]:
    """Indicadores do ambiente atual, do cache enquanto ele valer.

    O lock serializa o cálculo: sem ele, N requisições simultâneas com o cache
    frio disparariam N varreduras no banco ao mesmo tempo.
    """
    global _cache, _expedicoes

    if not forcar and _cache and agora() < _cache[0]:
        return _cache[1]

    if forcar:
        # Releitura da extração do BRNET junto: trocar a planilha no disco e
        # apertar "Atualizar" na tela basta, sem reiniciar o processo.
        _expedicoes = None

    with _lock:
        # Outra thread pode ter preenchido o cache enquanto esperávamos.
        if not forcar and _cache and agora() < _cache[0]:
            return _cache[1]
        try:
            dados = _consultar()
        except Exception as exc:  # noqa: BLE001 - vira 503 no router
            logger.error("[DASHBOARD] falha ao calcular indicadores: %s", exc)
            raise DashboardIndisponivel(str(exc)) from exc
        _cache = (proxima_virada(agora()), dados)
        return dados


def invalidar_cache() -> None:
    """Usado por testes e por quem precisar derrubar o cache sem recalcular.

    Solta também a extração de expedições: trocar o arquivo no disco e pedir
    `?forcar=true` passa a ser suficiente, sem reiniciar o processo.
    """
    global _cache, _expedicoes
    _cache = None
    _expedicoes = None


async def atualizacao_diaria_loop() -> None:
    """Recalcula os indicadores todo dia no horário de virada.

    Dorme até o horário em vez de acordar de minuto em minuto; um `sleep` longo
    sobrevive a mudança de horário de verão porque o alvo é recalculado a cada
    volta, a partir do relógio com fuso.
    """
    logger.info(
        "[DASHBOARD] atualização diária ativa (%02d:%02d %s)",
        HORA_ATUALIZACAO,
        MINUTO_ATUALIZACAO,
        FUSO.key,
    )
    alvo = proxima_virada()
    while True:
        espera = (alvo - agora()).total_seconds()
        if espera > 0:
            # Dorme em fatias de no máximo uma hora: um sleep de 20h não
            # sobrevive a suspensão da máquina nem a ajuste de relógio.
            await asyncio.sleep(min(espera, 3600.0))
            if agora() < alvo:
                continue  # ainda não é a hora: só terminou uma fatia da espera
        try:
            obter_indicadores(forcar=True)
            logger.info("[DASHBOARD] indicadores atualizados pela rotina diária")
        except DashboardIndisponivel as exc:
            # Falhar aqui não pode derrubar o loop: no dia seguinte ele tenta de
            # novo, e o próximo acesso à tela recalcula sob demanda.
            logger.error("[DASHBOARD] atualização diária falhou: %s", exc)
        alvo = proxima_virada()
