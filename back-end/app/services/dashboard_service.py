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
import threading
import time
from datetime import date, datetime, timedelta
from typing import Any, NamedTuple, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.core.config import Settings

logger = logging.getLogger(__name__)

_SQL_PATH = os.path.join(os.path.dirname(__file__), "sql", "dashboard_indicadores.sql")

# Seções que o dashboard consome. O resto do que a consulta devolve ('revisao',
# 'extracao_dia' e 'exames', que alimentava a aba "Onde atuar", removida) é
# descartado para não trafegar ~70 KB que ninguém lê.
SECOES = ("periodo", "totais", "series", "acuracia", "clinicas")

# Virada do dia: a partir daqui o número do dia anterior é considerado velho.
# O fuso é explícito porque o container roda em UTC — sem isso, "7h" viraria 4h
# da manhã no Brasil.
HORA_ATUALIZACAO = int(os.getenv("DASHBOARD_REFRESH_HOUR", "7"))
MINUTO_ATUALIZACAO = int(os.getenv("DASHBOARD_REFRESH_MINUTE", "0"))
FUSO = ZoneInfo(os.getenv("DASHBOARD_REFRESH_TZ", "America/Sao_Paulo"))

# Teto de execução no banco. Estourar vira erro claro para o usuário em vez de
# uma conexão presa segurando worker.
TIMEOUT_MS = int(os.getenv("DASHBOARD_STATEMENT_TIMEOUT_MS", "120000"))

# Expedições de clínicas credenciadas: o único dado do painel que NÃO sai do
# banco — vem da API de monitoramento de credenciados do BRNET. Substituiu a
# planilha exportada à mão (rel_expedição_credenciadas_final.xlsx), que parava
# no dia da exportação; em jul/26 as duas fontes diferem em 0,3%.
#
# Cada documento guarda o `pedido_exame_id` do BRNET no result_payload desde
# 29/05/26, e 99,6% deles aparecem na API. Essa ligação exata alimenta:
#   * "Expedições via ProntuAI": pedidos atendidos no dia que têm documento
#     liberado ÷ pedidos atendidos no dia. Contar pedido, e não documento, tira
#     o reenvio da conta (127 pedidos com mais de um documento liberado inflavam
#     o KPI em 4–5 pp em ago–set/26);
#   * a lista de credenciados com previsão futura que não usam o ProntuAI.
#
# A API filtra pelo mês de SOLICITAÇÃO e o painel conta pelo dia de ATENDIMENTO.
# Medido em mar–ago/26: 86% dos atendimentos caem no mês da solicitação, 13% no
# seguinte e 0,2% dois meses depois. Daí as duas constantes:
#   * busca-se desde dois meses antes do primeiro documento, para o primeiro mês
#     do painel sair completo;
#   * os três meses de solicitação mais recentes ainda ganham atendimentos e são
#     buscados de novo a cada cálculo; os mais antigos ficam no cache do processo.
# Cada mês custa ~7 s e ~10 MB, por isso a busca é paralela e limitada.
MESES_ANTES_DO_ATENDIMENTO = 2
MESES_EM_ABERTO = 3
# A partir de quantos documentos ligados um credenciado "usa o ProntuAI". Um
# documento avulso (unidade vizinha, conta interna enviando por outra clínica)
# não pode tirar o credenciado da lista.
MIN_DOCUMENTOS_USA_PRONTUAI = 3
BUSCAS_SIMULTANEAS = int(os.getenv("DASHBOARD_EXPEDICOES_CONCORRENCIA", "4"))
# Calcular o painel no startup. Os testes desligam: a app sobe a cada teste e
# cada subida iria ao banco e ao BRNET de verdade.
AQUECER_NO_STARTUP = os.getenv("DASHBOARD_AQUECER_NO_STARTUP", "true").lower() == "true"

_sql: Optional[str] = None


class _Pedido(NamedTuple):
    """O mínimo de um pedido do BRNET que o painel usa — sem dado de paciente."""

    atendimento: Optional[str]  # ISO; None enquanto não atendido
    credenciado: str            # rótulo "CIDADE - UF - NOME"
    cidade: Optional[str]
    uf: Optional[str]
    nome: Optional[str]
    previsao: Optional[str]     # ISO da previsão de liberação
    liberado: bool


# (ano, mês) de solicitação -> pedido_exame_id -> resumo.
_pedidos_mes: dict[tuple[int, int], dict[int, _Pedido]] = {}

# Documentos por pedido do BRNET, das mesmas clínicas que o painel conta.
_SQL_DOCS_POR_PEDIDO = r"""
WITH d AS (
    SELECT d.validation_status, d.created_at,
           CASE WHEN d.result_payload LIKE '{%' AND pg_input_is_valid(d.result_payload, 'jsonb')
                THEN d.result_payload::jsonb #>> '{brmed_result,pedido_exame_id}' END AS pedido
    FROM documents d
    JOIN clinics c ON c.id = d.clinic_id
    WHERE c.name NOT IN ('teste', 'testando', 'Clinica Default')
)
SELECT pedido::bigint, count(*), bool_or(validation_status = 'validated'), min(created_at)::date
FROM d WHERE pedido ~ '^\d{1,18}$'
GROUP BY pedido
"""

# (validade, dados): a partir de `validade` o cache é considerado vencido.
_cache: Optional[tuple[datetime, dict[str, Any]]] = None
# Sobe a cada cálculo concluído. Serve para quem esperou no lock descobrir que
# outra thread já fez o trabalho — inclusive num `forcar`, onde a validade do
# cache é a mesma antes e depois e não daria para comparar.
_versao = 0
_lock = threading.Lock()


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


def _meses_entre(inicio: tuple[int, int], fim: tuple[int, int]) -> list[tuple[int, int]]:
    ano, mes = inicio
    meses = []
    while (ano, mes) <= fim:
        meses.append((ano, mes))
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return meses


def _mes_deslocado(ano: int, mes: int, delta: int) -> tuple[int, int]:
    total = ano * 12 + (mes - 1) + delta
    return total // 12, total % 12 + 1


async def _buscar_pedidos_mes(ano: int, mes: int, sem: asyncio.Semaphore) -> dict[int, _Pedido]:
    from app.services.accredited_monitoring_service import consultar_monitoramento_credenciados

    async with sem:
        registros = await consultar_monitoramento_credenciados(mes, ano)
    return {
        r.pedido_exame_id: _Pedido(
            atendimento=r.data_atendimento.isoformat() if r.data_atendimento else None,
            credenciado=r.credenciado.rotulo,
            cidade=r.credenciado.cidade,
            uf=r.credenciado.uf,
            nome=r.credenciado.nome,
            previsao=r.data_previsao.isoformat() if r.data_previsao else None,
            liberado=r.data_liberacao is not None,
        )
        for r in registros
    }


async def _buscar_pedidos(meses: list[tuple[int, int]]) -> list[Any]:
    sem = asyncio.Semaphore(BUSCAS_SIMULTANEAS)
    return await asyncio.gather(
        *(_buscar_pedidos_mes(ano, mes, sem) for ano, mes in meses),
        return_exceptions=True,
    )


def _carregar_pedidos(doc_mais_antigo: Optional[str]) -> Optional[dict[int, _Pedido]]:
    """Pedidos do BRNET desde antes do primeiro documento. None se incompleto.

    Mês que nunca foi buscado com sucesso deixa o resultado incompleto, e
    denominador faltando inflaria a cobertura: melhor não mostrar. Mês em aberto
    que falha reaproveita a última busca boa.
    """
    if not doc_mais_antigo:
        return None

    primeiro = datetime.strptime(str(doc_mais_antigo)[:10], "%Y-%m-%d")
    hoje = agora()
    atual = (hoje.year, hoje.month)
    meses = _meses_entre(_mes_deslocado(primeiro.year, primeiro.month, -MESES_ANTES_DO_ATENDIMENTO), atual)
    em_aberto = set(_meses_entre(_mes_deslocado(*atual, -(MESES_EM_ABERTO - 1)), atual))
    buscar = [m for m in meses if m in em_aberto or m not in _pedidos_mes]

    inicio = time.monotonic()
    # Roda em thread (asyncio.to_thread no router e no loop diário): não há event
    # loop aqui, então asyncio.run é seguro.
    resultados = asyncio.run(_buscar_pedidos(buscar)) if buscar else []
    falhas = []
    for mes, resultado in zip(buscar, resultados):
        if isinstance(resultado, BaseException):
            falhas.append(mes)
            logger.error("[DASHBOARD] expedições %02d/%s indisponíveis: %s", mes[1], mes[0], resultado)
        else:
            _pedidos_mes[mes] = resultado

    faltando = [m for m in meses if m not in _pedidos_mes]
    logger.info(
        "[DASHBOARD] expedições: %s meses buscados em %.1fs, %s falhas, %s sem dado",
        len(buscar), time.monotonic() - inicio, len(falhas), len(faltando),
    )
    if faltando:
        return None

    pedidos: dict[int, _Pedido] = {}
    for mes in meses:
        pedidos.update(_pedidos_mes[mes])
    return pedidos


def _primeiro_dia_ligado(primeiro_doc: Optional[date]) -> Optional[str]:
    """Primeiro dia com cobertura medível: o 1º do mês do primeiro documento
    com pedido. Começar no dia exato deixaria o primeiro ponto do gráfico mensal
    com poucos dias rotulado como o mês inteiro; pular o mês perderia jun/26,
    que já tem 89% dos documentos ligados."""
    if not primeiro_doc:
        return None
    return date(primeiro_doc.year, primeiro_doc.month, 1).isoformat()


def _cruzar_expedicoes(
    pedidos: Optional[dict[int, _Pedido]],
    docs_por_pedido: dict[int, tuple[int, bool]],
    hoje: date,
) -> dict[str, Any]:
    """Liga pedidos do BRNET a documentos do ProntuAI pelo pedido_exame_id."""
    if pedidos is None:
        return {"expedicoes_dia": {}, "expedicoes_prontuai_dia": {}, "clinicas_sem_prontuai": None}

    atendidos: dict[str, int] = {}
    via_prontuai: dict[str, int] = {}
    docs_por_credenciado: dict[str, int] = {}
    for pid, p in pedidos.items():
        qtd_docs, liberado_no_prontuai = docs_por_pedido.get(pid, (0, False))
        if qtd_docs:
            docs_por_credenciado[p.credenciado] = docs_por_credenciado.get(p.credenciado, 0) + qtd_docs
        if p.atendimento:
            atendidos[p.atendimento] = atendidos.get(p.atendimento, 0) + 1
            if liberado_no_prontuai:
                via_prontuai[p.atendimento] = via_prontuai.get(p.atendimento, 0) + 1

    hoje_iso = hoje.isoformat()
    previstos: dict[str, dict[str, Any]] = {}
    for p in pedidos.values():
        if p.liberado or not p.previsao or p.previsao < hoje_iso:
            continue
        if docs_por_credenciado.get(p.credenciado, 0) >= MIN_DOCUMENTOS_USA_PRONTUAI:
            continue
        item = previstos.setdefault(p.credenciado, {
            "credenciado": p.credenciado,
            "nome": p.nome or p.credenciado,
            "cidade": p.cidade,
            "uf": p.uf,
            "pedidos_previstos": 0,
            "proxima_previsao": p.previsao,
            "documentos": docs_por_credenciado.get(p.credenciado, 0),
        })
        item["pedidos_previstos"] += 1
        item["proxima_previsao"] = min(item["proxima_previsao"], p.previsao)

    return {
        "expedicoes_dia": atendidos,
        "expedicoes_prontuai_dia": via_prontuai,
        "clinicas_sem_prontuai": sorted(
            previstos.values(), key=lambda c: (-c["pedidos_previstos"], c["credenciado"])
        ),
    }


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
            docs_por_pedido: dict[int, tuple[int, bool]] = {}
            primeiro_doc_ligado: Optional[date] = None
            for pedido, qtd, liberado, criado in conn.execute(text(_SQL_DOCS_POR_PEDIDO)):
                docs_por_pedido[int(pedido)] = (int(qtd), bool(liberado))
                if primeiro_doc_ligado is None or criado < primeiro_doc_ligado:
                    primeiro_doc_ligado = criado

    if not linha:
        raise DashboardIndisponivel("a consulta não devolveu nada")

    bruto = json.loads(linha)
    dados = {secao: bruto.get(secao) for secao in SECOES}
    momento = agora()
    pedidos = _carregar_pedidos((bruto.get("periodo") or {}).get("doc_mais_antigo"))
    dados.update(_cruzar_expedicoes(pedidos, docs_por_pedido, momento.date()))
    dados["expedicoes_desde"] = _primeiro_dia_ligado(primeiro_doc_ligado)
    dados["ambiente"] = Settings.APP_ENV
    dados["gerado_em"] = momento.isoformat()
    dados["proxima_atualizacao"] = proxima_virada(momento).isoformat()

    logger.info(
        "[DASHBOARD] indicadores calculados em %.1fs (ambiente=%s, clinicas=%s)",
        time.monotonic() - inicio,
        dados["ambiente"],
        len(dados.get("clinicas") or []),
    )
    return dados


def obter_indicadores(forcar: bool = False) -> dict[str, Any]:
    """Indicadores do ambiente atual, do cache enquanto ele valer.

    O lock serializa o cálculo: sem ele, N requisições simultâneas com o cache
    frio disparariam N varreduras no banco ao mesmo tempo.
    """
    global _cache, _versao

    if not forcar and _cache and agora() < _cache[0]:
        return _cache[1]

    # Lido ANTES de disputar o lock: se mudar enquanto esperamos, foi porque
    # outra thread recalculou e o resultado dela serve — vários cliques no
    # "Atualizar" ao mesmo tempo custam uma varredura, não uma por clique.
    versao_ao_pedir = _versao

    with _lock:
        if _cache and _versao != versao_ao_pedir:
            return _cache[1]
        if not forcar and _cache and agora() < _cache[0]:
            return _cache[1]
        try:
            dados = _consultar()
        except Exception as exc:  # noqa: BLE001 - vira 503 no router
            logger.error("[DASHBOARD] falha ao calcular indicadores: %s", exc)
            raise DashboardIndisponivel(str(exc)) from exc
        _cache = (proxima_virada(agora()), dados)
        _versao += 1
        return dados


def invalidar_cache() -> None:
    """Usado por testes e por quem precisar derrubar o cache sem recalcular.

    Solta também os meses de pedidos já buscados no BRNET.
    """
    global _cache
    _cache = None
    _pedidos_mes.clear()


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
    # Aquecimento: sem ele, o primeiro acesso depois de um deploy esperaria a
    # varredura do banco mais a busca de todos os meses de expedição no BRNET.
    if AQUECER_NO_STARTUP:
        try:
            await asyncio.to_thread(obter_indicadores)
        except DashboardIndisponivel as exc:
            logger.error("[DASHBOARD] aquecimento falhou: %s", exc)

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
            # `obter_indicadores` faz I/O bloqueante de vários segundos; chamada
            # direta aqui congelaria o event loop e, com ele, a API inteira.
            await asyncio.to_thread(obter_indicadores, True)
            logger.info("[DASHBOARD] indicadores atualizados pela rotina diária")
        except DashboardIndisponivel as exc:
            # Falhar aqui não pode derrubar o loop: no dia seguinte ele tenta de
            # novo, e o próximo acesso à tela recalcula sob demanda.
            logger.error("[DASHBOARD] atualização diária falhou: %s", exc)
        alvo = proxima_virada()
