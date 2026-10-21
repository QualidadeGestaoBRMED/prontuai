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
import unicodedata
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
# A API filtra pelo mês de SOLICITAÇÃO e o painel conta pelo dia de LIBERAÇÃO,
# que é o que a 1.2 define como realizado. A liberação é posterior ao
# atendimento, então a defasagem entre o mês de solicitação e o mês contado é ao
# menos a medida para o atendimento: em mar–ago/26, 86% dos atendimentos caem no
# mês da solicitação, 13% no seguinte e 0,2% dois meses depois. Daí as duas
# constantes (dimensionadas pelo atendimento, teto inferior para a liberação):
#   * busca-se desde dois meses antes do primeiro documento, para o primeiro mês
#     do painel sair completo;
#   * os três meses de solicitação mais recentes ainda ganham atendimentos e são
#     buscados de novo a cada cálculo; os mais antigos ficam no cache do processo.
# Cada mês custa ~7 s e ~10 MB, por isso a busca é paralela e limitada.
MESES_ANTES_DO_ATENDIMENTO = 2
MESES_EM_ABERTO = 3
# Piso para aceitar o documento como prova de que o credenciado é atendido por
# um cadastro — não é critério de "usa o ProntuAI", que é ter cadastro ativo.
MIN_DOCUMENTOS_CADASTRO = 3
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
    # ISO da liberação, None enquanto não expedido. É a datação de realizado:
    # a 1.2 define realizado como documento EFETIVAMENTE EXPEDIDO, não atendido.
    liberacao: Optional[str]


# (ano, mês) de solicitação -> pedido_exame_id -> resumo.
_pedidos_mes: dict[tuple[int, int], dict[int, _Pedido]] = {}

# Documentos por pedido do BRNET, das mesmas clínicas que o painel conta.
# Conta documentos, sem olhar `validation_status`: um pedido "passou pelo
# ProntuAI" quando foi PROCESSADO por ele. Prontuário que entrou, foi processado
# e acabou rejeitado ou pendente passou pela plataforma do mesmo jeito — medir só
# o liberado confundiria adoção com desfecho da revisão.
# `clinica` é o nome da clínica que enviou o documento — é a ÚNICA ligação entre
# o credenciado do BRNET e o cadastro do ProntuAI, porque a API de monitoramento
# não manda id nem CNPJ do credenciado, só o rótulo "CIDADE - UF - NOME". É o que
# permite levar o total de previstos para a tabela "Adoção por clínica".
# `mode()` resolve o pedido que tem documento de mais de uma clínica (reenvio por
# outra unidade): vence a que mais enviou.
#
# `revisado` responde "alguém do time abriu este pedido?". Mesma definição de
# revisão do painel (`sql/dashboard_indicadores.sql`), para os dois não
# divergirem: audit_log de update por ADMIN/CHECKER/MANAGER que terminou em
# validated/rejected. É `bool_or` porque basta um documento do pedido ter sido
# conferido — o pedido passou por olho humano.
_SQL_DOCS_POR_PEDIDO = r"""
WITH humano AS (
    SELECT DISTINCT al.resource_id AS document_id
    FROM audit_logs al
    JOIN documents d ON d.id = al.resource_id
    WHERE al.resource = 'documents'
      AND (al.action = 'documents.update' OR al.action LIKE 'patch:/v1/documents/%')
      AND al.user_role IN ('ADMIN', 'CHECKER', 'MANAGER')
      AND al.status_code BETWEEN 200 AND 299
      AND COALESCE(al.metadata_json::jsonb ->> 'after_status', d.validation_status)
          IN ('validated', 'rejected')
),
d AS (
    SELECT d.created_at, c.name AS clinica,
           (h.document_id IS NOT NULL) AS revisado,
           CASE WHEN d.result_payload LIKE '{%' AND pg_input_is_valid(d.result_payload, 'jsonb')
                THEN d.result_payload::jsonb #>> '{brmed_result,pedido_exame_id}' END AS pedido
    FROM documents d
    JOIN clinics c ON c.id = d.clinic_id
    LEFT JOIN humano h ON h.document_id = d.id
    WHERE c.name NOT IN ('teste', 'testando', 'Clinica Default')
)
SELECT pedido::bigint, count(*), min(created_at)::date,
       mode() WITHIN GROUP (ORDER BY clinica) AS clinica,
       bool_or(revisado) AS revisado
FROM d WHERE pedido ~ '^\d{1,18}$'
GROUP BY pedido
"""

# Cadastros habilitados. É a definição de "clínica no ProntuAI": ter cadastro
# ativo, e não ter volume. A API de monitoramento não manda id nem CNPJ do
# credenciado, então a ponte é pelo nome — ver `_indexar_cadastros`.
_SQL_CADASTROS_ATIVOS = """
SELECT name FROM clinics
WHERE is_active AND name NOT IN ('teste', 'testando', 'Clinica Default')
"""

# Um documento por linha, para "Expedições por prazo". Datas convertidas de UTC
# (é como created_at/reviewed_at são gravados) para o fuso do painel antes de
# virar dia: prontuário enviado às 22h do dia da previsão é "no dia", não
# atrasado. `liberado_pelo_tecnico` só existe quando um revisor humano aprovou —
# aprovação automática da IA não é trabalho do técnico e fica fora da conta.
#
# `prazo_brmed` é a `data_previsao_liberacao` que o patients_exams do BRNET
# devolve no processamento. O BRNET mantém DUAS previsões para o mesmo pedido e
# devolve uma em cada endpoint: medindo 3.794 documentos, esta fica 1 dia útil
# depois da `data_previsao` do monitoramento (2 dias em 3 casos), que por sua vez
# é atendimento + prazo do credenciado em dias úteis. Como o BRNET calcula esse
# dia a mais não está confirmado — só a diferença foi medida. É a previsão certa
# para cobrar o técnico porque é a que o ProntuAI recebe no processamento.
_SQL_PRAZOS = r"""
SELECT
    (d.result_payload::jsonb #>> '{brmed_result,pedido_exame_id}')::bigint AS pedido,
    (d.created_at AT TIME ZONE 'UTC' AT TIME ZONE :fuso)::date AS enviado,
    CASE WHEN d.validation_status = 'validated' AND d.reviewed_by IS NOT NULL
         THEN (d.reviewed_at AT TIME ZONE 'UTC' AT TIME ZONE :fuso)::date END AS liberado_pelo_tecnico,
    CASE WHEN d.result_payload::jsonb #>> '{brmed_result,data_previsao_liberacao}' ~ '^\d{2}/\d{2}/\d{4}$'
         THEN to_date(d.result_payload::jsonb #>> '{brmed_result,data_previsao_liberacao}', 'DD/MM/YYYY')
    END AS prazo_brmed
FROM documents d
JOIN clinics c ON c.id = d.clinic_id
WHERE c.name NOT IN ('teste', 'testando', 'Clinica Default')
  AND d.result_payload LIKE '{%'
  AND pg_input_is_valid(d.result_payload, 'jsonb')
  AND d.result_payload::jsonb #>> '{brmed_result,pedido_exame_id}' ~ '^\d{1,18}$'
"""

# Acurácia por exame, do parecer do revisor no modal de feedback (migration 008).
# Um documento com parecer por linha. Os exames avaliados são os exigidos pelo
# BRNET — a lista que o modal mostra ao revisor —, e `comparou` separa o
# documento em que a IA chegou a julgar os exames da falha técnica, que fica
# fora como em toda acurácia do painel.
_SQL_PARECERES_EXAMES = r"""
SELECT
    d.created_at,
    f.status,
    COALESCE(
        CASE WHEN cardinality(d.exams_brnet) > 0 THEN to_jsonb(d.exams_brnet) END,
        p.payload #> '{brmed_result,exames_obrigatorios}'
    ) AS exames,
    f.issue_items,
    jsonb_typeof(p.payload -> 'tabela_comparacao') = 'array' AS comparou
FROM document_feedbacks f
JOIN documents d ON d.id = f.document_id
JOIN clinics c ON c.id = d.clinic_id
CROSS JOIN LATERAL (
    SELECT CASE WHEN d.result_payload LIKE '{%' AND pg_input_is_valid(d.result_payload, 'jsonb')
                THEN d.result_payload::jsonb END AS payload
) p
WHERE c.name NOT IN ('teste', 'testando', 'Clinica Default')
"""

# Denominador da adesão ao parecer: decisões humanas desde o primeiro parecer
# gravado (o dia em que o modal entrou) — antes disso não havia como dar parecer,
# e contar aquelas decisões faria a adesão parecer pior do que é —, MAIS todo
# documento que tem parecer. Esta segunda parte existe porque o "Avaliar IA"
# deixa dar parecer em documento decidido antes do modal: sem ela, há parecer
# fora do denominador e a adesão passa de 100%.
_SQL_DECISOES_DESDE_O_MODAL = """
SELECT d.created_at
FROM documents d
JOIN clinics c ON c.id = d.clinic_id
WHERE c.name NOT IN ('teste', 'testando', 'Clinica Default')
  AND (
        (d.reviewed_by IS NOT NULL
         AND d.reviewed_at >= (SELECT min(created_at) FROM document_feedbacks))
     OR EXISTS (SELECT 1 FROM document_feedbacks f WHERE f.document_id = d.id)
  )
"""

# O que o parecer conta como ERRO da IA no reconhecimento de um exame exigido.
# As categorias são as que o revisor escolhe no modal (front-end/types/feedback.ts,
# OPCOES_EXAME) conforme o que a IA disse do exame:
#   * falta indevida — a IA disse "faltante" e o revisor marcou "Estava no
#     documento" ou "Com outro nome";
#   * presença indevida — a IA disse "encontrado" e o revisor marcou "Não estava".
# Ficam FORA: "Não é exigido" (DADO_BRNET, o erro é da exigência do BRNET, não
# da IA) e os problemas de qualidade do exame — outra data, ilegível, sem
# carimbo, validade. A IA ainda não confere essas coisas, e se elas entram na
# conta é decisão de produto em aberto (20/10/2026); mudar é mexer só aqui.
FALTA_INDEVIDA = frozenset({"FALTANTE_INCORRETO", "SINONIMO_NAO_RECONHECIDO"})
PRESENCA_INDEVIDA = frozenset({"ENCONTRADO_INCORRETO"})


def _chave_exame(nome: Optional[str]) -> str:
    """Nome de exame sem acento, sem caixa e com espaços colapsados.

    Diferente de `_chave_nome`, NÃO tira o que está entre parênteses: em nome de
    exame ele distingue exames diferentes ("AVALIAÇÃO OFTALMOLÓGICA (ACUIDADE
    VISUAL ...)" tem variantes que não são o mesmo exame).
    """
    texto = unicodedata.normalize("NFD", (nome or "").strip().lower())
    return " ".join("".join(c for c in texto if unicodedata.category(c) != "Mn").split())


def _chaves_periodo(criado: datetime) -> dict[str, str]:
    """Chaves semanal e mensal, no mesmo formato das séries da consulta principal
    (`date_trunc` sobre `created_at` gravado em UTC): o front soma pelas chaves dos
    pontos do período escolhido, então as duas pontas precisam concordar."""
    dia = criado.date()
    return {
        "semanal": (dia - timedelta(days=dia.weekday())).isoformat(),
        "mensal": dia.replace(day=1).isoformat(),
    }


def _agregar_pareceres(pareceres, decisoes) -> dict[str, Any]:
    """Acurácia por exame a partir dos pareceres do modal de feedback.

    Cada exame exigido de cada documento com parecer é uma AVALIAÇÃO; ela é erro
    quando o revisor marcou o exame com uma categoria de `FALTA_INDEVIDA` ou
    `PRESENCA_INDEVIDA`. Parecer "Acertou" não tem item nenhum: todos os exames
    do documento contam como acerto. Exame digitado pelo revisor, fora da lista
    do BRNET, não entra — a conta é sobre os exames exigidos.

    Formato, por granularidade e chave de período:
        {"pareceres": n, "com_parecer": n', "decisoes": m,
         "exames": {nome: [avaliações, falta, presença]}}
    `pareceres` são os que entram na acurácia (a IA julgou os exames);
    `com_parecer` conta também os de falha técnica e é o numerador da adesão,
    sobre `decisoes`. `desde` é a data de envio do documento mais antigo com
    parecer — não a do primeiro parecer, porque dá para avaliar documento antigo.
    """
    series: dict[str, dict[str, dict[str, Any]]] = {"semanal": {}, "mensal": {}}
    nome_de: dict[str, str] = {}
    primeiro: Optional[date] = None

    def bloco(gran: str, chave: str) -> dict[str, Any]:
        return series[gran].setdefault(
            chave, {"pareceres": 0, "com_parecer": 0, "decisoes": 0, "exames": {}}
        )

    for criado, _status, exames, itens, comparou in pareceres:
        primeiro = min(primeiro, criado.date()) if primeiro else criado.date()
        for gran, chave_periodo in _chaves_periodo(criado).items():
            bloco(gran, chave_periodo)["com_parecer"] += 1
        if not comparou:
            continue
        exigidos: dict[str, str] = {}
        for nome in exames or []:
            chave = _chave_exame(nome)
            if chave and chave not in exigidos:
                exigidos[chave] = nome_de.setdefault(chave, str(nome).strip())
        if not exigidos:
            continue
        erros: dict[str, str] = {}
        for item in itens or []:
            chave = _chave_exame((item or {}).get("exame"))
            categoria = (item or {}).get("categoria")
            if chave not in exigidos:
                continue
            if categoria in FALTA_INDEVIDA:
                erros[chave] = "falta"
            elif categoria in PRESENCA_INDEVIDA:
                erros.setdefault(chave, "presenca")
        for gran, chave_periodo in _chaves_periodo(criado).items():
            b = bloco(gran, chave_periodo)
            b["pareceres"] += 1
            for chave, nome in exigidos.items():
                conta = b["exames"].setdefault(nome, [0, 0, 0])
                conta[0] += 1
                if erros.get(chave) == "falta":
                    conta[1] += 1
                elif erros.get(chave) == "presenca":
                    conta[2] += 1

    for (criado,) in decisoes:
        for gran, chave_periodo in _chaves_periodo(criado).items():
            bloco(gran, chave_periodo)["decisoes"] += 1

    return {"desde": primeiro.isoformat() if primeiro else None, "series": series}

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
            liberacao=r.data_liberacao.isoformat() if r.data_liberacao else None,
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


def _chave_nome(valor: Optional[str]) -> str:
    """Normaliza um nome para casar rótulo do BRNET com cadastro do ProntuAI.

    Sem acento, sem caixa e com espaços colapsados. O rótulo do BRNET e o nome do
    cadastro são digitados por pessoas diferentes, em sistemas diferentes: no dev
    convivem "Qualimetra" e "QUALIMETRA", e cidade com e sem acento.
    """
    texto = unicodedata.normalize("NFD", (valor or "").strip().lower())
    sem_acento = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    # Travessão, meia-risca e afins viram hífen. 28 dos 584 rótulos do BRNET
    # (out/26) separam cidade, UF e nome com "–", e os cadastros misturam os
    # dois: "PIRAPORA – MG – TRINUS" não casaria com um cadastro digitado com
    # "-". Medido em out/26 nenhum cadastro estava nessa situação; o risco era
    # do próximo cadastro.
    sem_traco_variante = _TRACOS.sub("-", sem_acento)
    # O BRNET anexa qualificadores entre parênteses ao rótulo ("(CONDIÇÃO
    # ESPECIAL)") que o cadastro não tem. Sem tirá-los, CISVIVER e CLÍNICA SOMA
    # deixam de casar com o próprio cadastro.
    return " ".join(re.sub(r"\([^)]*\)", " ", sem_traco_variante).split())


# U+2010..U+2015 (hífen tipográfico, figura, meia-risca, travessão, barra
# horizontal) e U+2212 (sinal de menos).
_TRACOS = re.compile(r"[‐-―−]")


def _indexar_cadastros(nomes: list[str]) -> dict[str, str]:
    """{nome normalizado: nome original} dos cadastros habilitados.

    Chave única possível, já que a API do BRNET não manda id nem CNPJ do
    credenciado. Cadastro duplicado com a mesma chave fica com o primeiro em
    ordem alfabética, para a saída não variar entre execuções.
    """
    indice: dict[str, str] = {}
    for nome in sorted(nomes):
        indice.setdefault(_chave_nome(nome), nome)
    return indice


def _cadastro_do_credenciado(p: _Pedido, cadastros: dict[str, str]) -> Optional[str]:
    """Cadastro habilitado que corresponde a este credenciado, se houver.

    Tenta o rótulo inteiro ("RECIFE - PE - QUALIMETRA") e depois só o nome
    ("QUALIMETRA"): parte das clínicas é cadastrada com o rótulo completo e parte
    só com o nome curto. Sem match, o credenciado não tem cadastro habilitado — é
    o lado da prioridade de inclusão.
    """
    return cadastros.get(_chave_nome(p.credenciado)) or cadastros.get(_chave_nome(p.nome))


def _semana(iso: str) -> str:
    """Segunda-feira da semana ISO de uma data, em ISO.

    Chave de todo agrupamento semanal do painel. Semana ISO (segunda a domingo)
    e não "últimos 7 dias" porque a leitura é sempre de semana fechada: a conta
    de uma semana não pode mudar de valor conforme o dia em que alguém abre a
    tela.
    """
    d = date.fromisoformat(iso)
    return (d - timedelta(days=d.weekday())).isoformat()


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
    docs_por_pedido: dict[int, int],
    hoje: date,
    clinica_por_pedido: Optional[dict[int, str]] = None,
    cadastros_ativos: Optional[dict[str, str]] = None,
    pedidos_revisados: Optional[set[int]] = None,
) -> dict[str, Any]:
    """Liga pedidos do BRNET a documentos do ProntuAI pelo pedido_exame_id.

    Devolve DUAS listas separadas por **ter ou não cadastro habilitado**:

      * `clinicas_com_prontuai` — credenciados que casam com um cadastro ativo,
        agregados por **cadastro**: dois credenciados do BRNET que apontam para a
        mesma clínica são uma linha só. Traz previstos, realizados e realizados
        via ProntuAI. Entra mesmo sem nunca ter mandado documento — cadastro
        habilitado que não usa a plataforma é adesão baixa, não ausência.
      * `clinicas_sem_prontuai` — agregada por **credenciado**, porque esses não
        têm cadastro para agregar por. Previstos mais o histórico semanal de
        liberações (`liberacoes_semana`), que é o que permite ranquear por volume
        recorrente em vez de pelo pico da janela. Entra quem tem previsão futura
        **ou** histórico de liberação.

    "Habilitada" é ter cadastro ativo em `clinics`, não ter volume. A ponte é por
    nome (`_cadastro_do_credenciado`), única chave possível.

    São complementares: todo pedido previsto cai em exatamente uma.

    Previsto e realizado nunca se somam nem se dividem um pelo outro. São
    grandezas diferentes e viajam em campos diferentes: previsto é pedido ainda
    NÃO liberado (`p.liberado` falso) com data futura; realizado é pedido já
    atendido.

    O único ponto em que os dois se encontram é `desfecho_previsao_semana`, e
    ele é legítimo porque não divide agregado por agregado: acompanha **o mesmo
    pedido**, ligado pelo id, da previsão até o desfecho. Para cada semana de
    previsão, a tripla `[via_prontuai, liberado_fora, nao_liberado]` — exclusiva
    e somando os previstos daquela semana.

    A quebra diária de realizados por clínica (`realizados_dia`,
    `realizados_prontuai_dia`) e os previstos por UF (`previstos_uf_dia`) saíram
    em out/2026 com os indicadores que os liam — a tabela de adesão por período
    e a comparação dentro × fora. Eram 35% do payload do painel. O realizado por
    dia continua existindo no agregado (`expedicoes_dia`), que é o que o KPI de
    cobertura usa; a UF de cada credenciado vai nas próprias linhas.

    A previsão sai **quebrada por data** (`previsoes`), não só a mais próxima: o
    prazo do credenciado é de 1 a 3 dias úteis após o atendimento, então quase
    toda clínica tem algo vencendo hoje e uma única data não distinguia ninguém
    (medido: 54% das linhas mostravam o dia corrente). É essa quebra que deixa o
    painel recortar os previstos por janela sem voltar ao banco.

    Pedido pendente com previsão já vencida não tem data futura para mostrar e
    sai só como contagem (`vencidos`), para não mudar o escopo da lista, que é de
    previsões futuras.

    Uma clínica habilitada entra em `clinicas_com_prontuai` mesmo sem nenhum
    previsto, desde que tenha realizados: a adesão dela existe e é justamente o
    que a tabela mede. Já um credenciado sem cadastro só entra se tiver previsto,
    porque a lista dele é de prioridade de inclusão.
    """
    if pedidos is None:
        return {
            "expedicoes_dia": {},
            "expedicoes_prontuai_dia": {},
            "expedicoes_prontuai_revisadas_dia": {},
            "clinicas_sem_prontuai": None,
            "clinicas_com_prontuai": None,
        }

    clinica_por_pedido = clinica_por_pedido or {}
    cadastros_ativos = cadastros_ativos or {}
    pedidos_revisados = pedidos_revisados or set()

    # ── documentos por credenciado, e o cadastro de cada um ───────────────────
    docs_por_credenciado: dict[str, int] = {}
    clinicas_do_credenciado: dict[str, dict[str, int]] = {}
    for pid, p in pedidos.items():
        qtd_docs = docs_por_pedido.get(pid, 0)
        if not qtd_docs:
            continue
        docs_por_credenciado[p.credenciado] = docs_por_credenciado.get(p.credenciado, 0) + qtd_docs
        clinica = clinica_por_pedido.get(pid)
        if clinica:
            por_clinica = clinicas_do_credenciado.setdefault(p.credenciado, {})
            por_clinica[clinica] = por_clinica.get(clinica, 0) + qtd_docs

    # Cadastro de cada credenciado, resolvido uma vez só (roda sobre dezenas de
    # milhares de pedidos). São DUAS evidências, nesta ordem:
    #
    #   1. o nome casa com um cadastro ativo — única via para o credenciado que
    #      nunca mandou documento, que é o caso que a regra por volume errava;
    #   2. os documentos dele vieram de um cadastro ativo — isso é FATO, vem do
    #      `clinic_id` do documento, e não depende de nome nenhum.
    #
    # A segunda é indispensável: medido no dev, o nome falha para 5 clínicas que
    # comprovadamente usam a plataforma, incluindo a maior delas (511 documentos,
    # cadastrada como "Mediar - Belo Horizonte" contra o rótulo "BELO HORIZONTE -
    # MG - MEDIAR"). Ordem invertida, sufixo "- FILIAL" e afins não se resolvem
    # por regra de texto sem inventar casamento errado.
    #
    # O piso de documentos vale só para a segunda: um documento avulso (unidade
    # vizinha mandando pela conta de outra) não pode dar cadastro a quem não tem.
    cadastro_de: dict[str, Optional[str]] = {}
    for p in pedidos.values():
        if p.credenciado in cadastro_de:
            continue
        casado = _cadastro_do_credenciado(p, cadastros_ativos)
        if casado is None and docs_por_credenciado.get(p.credenciado, 0) >= MIN_DOCUMENTOS_CADASTRO:
            por_clinica = clinicas_do_credenciado.get(p.credenciado) or {}
            dominante = max(sorted(por_clinica), key=lambda n: por_clinica[n]) if por_clinica else None
            if dominante and _chave_nome(dominante) in cadastros_ativos:
                casado = cadastros_ativos[_chave_nome(dominante)]
        cadastro_de[p.credenciado] = casado

    # A ponte por nome é a parte frágil da regra, e falha em silêncio: o
    # credenciado simplesmente aparece do lado errado. Quem tem documento e não
    # casou é o caso a vigiar — ou foi resgatado pelo piso de documentos, ou caiu
    # na lista de inclusão sendo cadastrado. Sai no log para dar um relatório sem
    # precisar de consulta manual. São nomes de clínica, não há PII aqui.
    nao_casaram = sorted(
        (
            (docs_por_credenciado.get(cred, 0), cred)
            for cred, casado in cadastro_de.items()
            if casado is None and docs_por_credenciado.get(cred, 0) > 0
        ),
        reverse=True,
    )
    if nao_casaram:
        logger.warning(
            "[DASHBOARD] %s credenciados com documento não casaram por nome "
            "(resgatados pelo piso de %s documentos: %s). Maiores: %s",
            len(nao_casaram),
            MIN_DOCUMENTOS_CADASTRO,
            sum(1 for qtd, _ in nao_casaram if qtd >= MIN_DOCUMENTOS_CADASTRO),
            ", ".join(f"{cred} ({qtd} docs)" for qtd, cred in nao_casaram[:10]),
        )

    def usa_prontuai(credenciado: str) -> bool:
        return cadastro_de.get(credenciado) is not None

    def cadastro(credenciado: str) -> str:
        """Nome do cadastro habilitado deste credenciado.

        Vem do casamento por nome. Se ele falhar mas os documentos apontarem uma
        clínica, usa a que mais mandou — cobre o cadastro renomeado depois de já
        ter volume. Último recurso é o próprio rótulo, para a lista nunca ficar
        sem chave.
        """
        casado = cadastro_de.get(credenciado)
        if casado:
            return casado
        por_clinica = clinicas_do_credenciado.get(credenciado)
        if not por_clinica:
            return credenciado
        return max(sorted(por_clinica), key=lambda nome: por_clinica[nome])

    # ── realizados: global (KPI de cobertura) ────────────────────────────────
    # Por clínica a quebra diária saiu: a adesão por clínica passou a ser medida
    # pela semana de previsão (`desfecho_previsao_semana`), que acompanha o
    # mesmo pedido dos dois lados. `realizados` continua só como conjunto de
    # cadastros com liberação, para o cadastro sem previsto não sumir da lista.
    atendidos: dict[str, int] = {}
    via_prontuai: dict[str, int] = {}
    # Subconjunto de `via_prontuai`: os que uma pessoa conferiu. É o que liga o
    # card de expedições ao de revisados — o revisado está DENTRO do expedido, e
    # o resto saiu com a IA decidindo sozinha. Sem esta quebra os dois cards
    # parecem brigar, e a divergência chega a trocar de sinal no meio da semana.
    via_prontuai_revisado: dict[str, int] = {}
    realizados: set[str] = set()
    for pid, p in pedidos.items():
        # Realizado é pedido EXPEDIDO, datado pelo dia da liberação — é o que a
        # 1.2 define ("realizados são documentos efetivamente expedidos"). Até
        # set/2026 o painel usava `atendimento`, o que punha no denominador
        # pedido atendido e ainda não liberado: medido em setembro, inflava o
        # denominador em 131 pedidos e deixava a adesão 3,1 pp abaixo da real
        # (52,9% contra 56,0%). Atendido sem liberação não é realizado; é
        # trabalho em curso, e aparece do lado dos previstos.
        if not p.liberacao:
            continue
        # Passou pelo ProntuAI = teve documento PROCESSADO por ele, qualquer que
        # tenha sido o desfecho da revisão. Rejeitado continua contando: a adesão
        # mede se a clínica usou a plataforma, e ela usou. Qualidade do envio é
        # outra medida — excluir rejeitado derrubaria a adesão 1,4 pp (54,6%) e
        # misturaria duas perguntas num número só.
        processado_no_prontuai = docs_por_pedido.get(pid, 0) > 0
        atendidos[p.liberacao] = atendidos.get(p.liberacao, 0) + 1
        if processado_no_prontuai:
            via_prontuai[p.liberacao] = via_prontuai.get(p.liberacao, 0) + 1
            if pid in pedidos_revisados:
                via_prontuai_revisado[p.liberacao] = via_prontuai_revisado.get(p.liberacao, 0) + 1
        if usa_prontuai(p.credenciado):
            realizados.add(cadastro(p.credenciado))

    # ── previstos: pedidos ainda não liberados, com data ─────────────────────
    hoje_iso = hoje.isoformat()
    com: dict[str, dict[str, Any]] = {}
    sem: dict[str, dict[str, Any]] = {}
    datas_com: dict[str, dict[str, int]] = {}
    datas_sem: dict[str, dict[str, int]] = {}

    def novo(chave: str, nome: str, p: _Pedido, habilitada: bool) -> dict[str, Any]:
        return {
            "credenciado": p.credenciado,
            # Só o lado habilitado tem cadastro no ProntuAI para apontar. Do
            # outro lado a chave é o rótulo do BRNET, e dizer que isso é uma
            # "clinica" faria a tela achar que existe cadastro.
            "clinica": chave if habilitada else None,
            "nome": nome,
            "cidade": p.cidade,
            "uf": p.uf,
            "pedidos_previstos": 0,
            "previsoes": [],
            "vencidos": 0,
            "documentos": 0,
        }

    for p in pedidos.values():
        if p.liberado or not p.previsao:
            continue
        habilitada = usa_prontuai(p.credenciado)
        chave = cadastro(p.credenciado) if habilitada else p.credenciado
        alvo, datas = (com, datas_com) if habilitada else (sem, datas_sem)
        item = alvo.setdefault(
            chave, novo(chave, chave if habilitada else (p.nome or p.credenciado), p, habilitada)
        )
        if p.previsao < hoje_iso:
            item["vencidos"] += 1
        else:
            item["pedidos_previstos"] += 1
            dias = datas.setdefault(chave, {})
            dias[p.previsao] = dias.get(p.previsao, 0) + 1

    # ── reconciliação previsto × expedido, e histórico de quem está fora ─────
    # Duas perguntas diferentes, uma varredura só.
    #
    # 1. Habilitadas (`desfecho_previsao_semana`): do que estava previsto para a
    #    semana, quanto saiu pela plataforma. Datado pelo dia da PREVISÃO, não
    #    pelo da liberação — a pergunta é sobre a promessa, não sobre o dia em
    #    que ela foi cumprida. Os três desfechos são exclusivos e somam os
    #    previstos da semana, então a barra empilhada da tela fecha em 100% sem
    #    fatia de resto, e o buraco fica decomposto: "liberou por fora" é com
    #    quem cuida de adesão, "não liberou" é atraso do credenciado.
    #
    #    É a única parte do painel em que previsto e realizado se encontram, e
    #    só por isto: o pedido é o MESMO dos dois lados, ligado pelo id, nunca um
    #    agregado dividido pelo outro.
    #
    # 2. Fora do ProntuAI (`liberacoes_semana`): quantas liberações o credenciado
    #    fez por semana. É o histórico que separa quem libera muito toda semana
    #    de quem teve um pico isolado — ranquear pelo previsto da janela não faz
    #    essa conta, e ainda favorece o credenciado lento, que é o único com
    #    pedido pendente no instante do cálculo.
    #
    # Semanal, e não diário: o prazo do credenciado é de 1 a 3 dias úteis, então
    # no dia a dia o pedido previsto para sexta e liberado na segunda apareceria
    # como descumprimento, e não é. A chave é a segunda-feira da semana ISO.
    #
    # Pedido liberado sem previsão fica fora do desfecho (não há semana a que
    # pertencer) mas continua em `realizados_dia` — as duas medidas respondem
    # perguntas diferentes e não precisam ter a mesma base.
    desfecho_semana: dict[str, dict[str, list[int]]] = {}
    liberacoes_semana: dict[str, dict[str, int]] = {}
    exemplo_sem: dict[str, _Pedido] = {}
    for pid, p in pedidos.items():
        habilitada = usa_prontuai(p.credenciado)
        if p.previsao and habilitada:
            semana = desfecho_semana.setdefault(cadastro(p.credenciado), {}).setdefault(
                _semana(p.previsao), [0, 0, 0]
            )
            # "Liberado" é ter data de liberação, a mesma definição de realizado
            # da 1.2 — não o campo `liberado` da API, que já apareceu marcado sem
            # data correspondente.
            if not p.liberacao:
                semana[2] += 1
            elif docs_por_pedido.get(pid, 0) > 0:
                semana[0] += 1
            else:
                semana[1] += 1
        if p.liberacao and not habilitada:
            dias = liberacoes_semana.setdefault(p.credenciado, {})
            chave_semana = _semana(p.liberacao)
            dias[chave_semana] = dias.get(chave_semana, 0) + 1
            exemplo_sem.setdefault(p.credenciado, p)

    # Credenciado sem cadastro que já liberou entra mesmo sem previsão futura: o
    # ranking de inclusão passa a ser por volume recorrente, e quem libera rápido
    # quase nunca tem pedido pendente na hora do cálculo — ficaria invisível
    # justamente por ser pontual.
    for credenciado, exemplo in exemplo_sem.items():
        sem.setdefault(credenciado, novo(credenciado, exemplo.nome or credenciado, exemplo, False))

    # Cadastro habilitado sem previsto também entra: a adesão dele existe, e
    # cadastro que não usa a plataforma é justamente o que a tabela revela.
    for nome in realizados:
        com.setdefault(nome, {
            "credenciado": nome, "clinica": nome, "nome": nome,
            "cidade": None, "uf": None,
            "pedidos_previstos": 0, "previsoes": [], "vencidos": 0, "documentos": 0,
        })

    # Documentos e cidade da clínica vêm dos credenciados que a alimentam.
    docs_por_cadastro: dict[str, int] = {}
    for credenciado, qtd in docs_por_credenciado.items():
        if usa_prontuai(credenciado):
            chave = cadastro(credenciado)
            docs_por_cadastro[chave] = docs_por_cadastro.get(chave, 0) + qtd
    for nome, item in com.items():
        item["documentos"] = docs_por_cadastro.get(nome, 0)
        item["desfecho_previsao_semana"] = desfecho_semana.get(nome, {})
    for credenciado, item in sem.items():
        item["documentos"] = docs_por_credenciado.get(credenciado, 0)
        item["liberacoes_semana"] = liberacoes_semana.get(credenciado, {})

    def finalizar(itens: dict[str, dict[str, Any]], datas: dict[str, dict[str, int]], so_com_movimento: bool):
        saida = []
        for chave, item in itens.items():
            dias = datas.get(chave, {})
            # Do lado de fora, "movimento" é ter previsão futura OU histórico de
            # liberação. Credenciado que nunca liberou nada e não tem previsto
            # (só vencidos, por exemplo) continua fora: não há o que ranquear.
            if so_com_movimento and not dias and not item.get("liberacoes_semana"):
                continue
            item["previsoes"] = [{"data": d, "pedidos": dias[d]} for d in sorted(dias)]
            saida.append(item)
        saida.sort(key=lambda c: (-c["pedidos_previstos"], c["nome"]))
        return saida

    return {
        "expedicoes_dia": atendidos,
        "expedicoes_prontuai_dia": via_prontuai,
        "expedicoes_prontuai_revisadas_dia": via_prontuai_revisado,
        # Credenciado sem cadastro e sem previsto não tem por que aparecer.
        "clinicas_sem_prontuai": finalizar(sem, datas_sem, True),
        "clinicas_com_prontuai": finalizar(com, datas_com, False),
    }


def _classificar_prazo(evento: date, alvo: date) -> int:
    """0 = antecipado, 1 = no dia, 2 = atrasado (posição na lista do dia)."""
    return 0 if evento < alvo else (1 if evento == alvo else 2)


def _cruzar_prazos(
    pedidos: Optional[dict[int, _Pedido]],
    documentos: list[tuple[int, date, Optional[date], Optional[date]]],
) -> dict[str, Any]:
    """Envio da clínica e liberação do técnico, cada um contra o próprio prazo.

    O BRNET tem dois prazos por pedido, e cada lado responde pelo seu:
      * clínica: o envio do prontuário contra o prazo do credenciado
        (data_previsao da API de monitoramento, buscada a cada atualização);
      * técnico de credenciados: a aprovação contra o prazo da BR MED
        (data_previsao_liberacao do patients_exams, um dia útil depois).
    Comparar o técnico com o prazo da clínica o cobraria por um dia que não é
    dele.

    Conta DOCUMENTO, não pedido: cada envio é uma entrega da clínica e cada
    aprovação é uma liberação do técnico. Cada lado é datado pelo próprio
    evento — a clínica pelo dia do envio, o técnico pelo dia da aprovação. Sem
    o prazo correspondente, o documento fica fora daquele lado.

    Formato: {"YYYY-MM-DD": [antecipado, no_dia, atrasado]}. Sem o BRNET o lado
    da clínica vem vazio; o do técnico não depende da API e continua.
    """
    clinica: dict[str, list[int]] = {}
    tecnico: dict[str, list[int]] = {}
    for pedido, enviado, liberado, prazo_brmed in documentos:
        p = (pedidos or {}).get(pedido)
        if p and p.previsao:
            prazo_clinica = date.fromisoformat(p.previsao)
            clinica.setdefault(enviado.isoformat(), [0, 0, 0])[_classificar_prazo(enviado, prazo_clinica)] += 1
        if liberado and prazo_brmed:
            tecnico.setdefault(liberado.isoformat(), [0, 0, 0])[_classificar_prazo(liberado, prazo_brmed)] += 1
    return {"prazo_clinica_dia": clinica, "prazo_tecnico_dia": tecnico}


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
            docs_por_pedido: dict[int, int] = {}
            clinica_por_pedido: dict[int, str] = {}
            pedidos_revisados: set[int] = set()
            primeiro_doc_ligado: Optional[date] = None
            for pedido, qtd, criado, clinica, revisado in conn.execute(text(_SQL_DOCS_POR_PEDIDO)):
                docs_por_pedido[int(pedido)] = int(qtd)
                if clinica:
                    clinica_por_pedido[int(pedido)] = clinica
                if revisado:
                    pedidos_revisados.add(int(pedido))
                if primeiro_doc_ligado is None or criado < primeiro_doc_ligado:
                    primeiro_doc_ligado = criado
            cadastros_ativos = _indexar_cadastros(
                [nome for (nome,) in conn.execute(text(_SQL_CADASTROS_ATIVOS)) if nome]
            )
            documentos = [
                (int(pedido), enviado, liberado, prazo_brmed)
                for pedido, enviado, liberado, prazo_brmed in conn.execute(text(_SQL_PRAZOS), {"fuso": FUSO.key})
            ]
            # Em savepoint: a acurácia por exame é um card só, e um erro aqui
            # (base sem a tabela de pareceres, por exemplo) não pode derrubar o
            # painel inteiro — numa transação abortada, nada mais roda.
            acuracia_exames: Optional[dict[str, Any]] = None
            try:
                with conn.begin_nested():
                    acuracia_exames = _agregar_pareceres(
                        conn.execute(text(_SQL_PARECERES_EXAMES)).all(),
                        conn.execute(text(_SQL_DECISOES_DESDE_O_MODAL)).all(),
                    )
            except Exception as exc:  # noqa: BLE001 - o card cai em "Em breve"
                logger.error("[DASHBOARD] acurácia por exame indisponível: %s", exc)

    if not linha:
        raise DashboardIndisponivel("a consulta não devolveu nada")

    bruto = json.loads(linha)
    dados = {secao: bruto.get(secao) for secao in SECOES}
    momento = agora()
    pedidos = _carregar_pedidos((bruto.get("periodo") or {}).get("doc_mais_antigo"))
    dados.update(
        _cruzar_expedicoes(
            pedidos,
            docs_por_pedido,
            momento.date(),
            clinica_por_pedido,
            cadastros_ativos,
            pedidos_revisados,
        )
    )
    dados.update(_cruzar_prazos(pedidos, documentos))
    dados["expedicoes_desde"] = _primeiro_dia_ligado(primeiro_doc_ligado)
    dados["acuracia_exames"] = acuracia_exames
    dados["ambiente"] = Settings.APP_ENV
    dados["gerado_em"] = momento.isoformat()
    dados["proxima_atualizacao"] = proxima_virada(momento).isoformat()

    logger.info(
        "[DASHBOARD] indicadores calculados em %.1fs (ambiente=%s, clinicas=%s)",
        time.monotonic() - inicio,
        dados["ambiente"],
        len(dados.get("clinicas") or []),
    )
    logger.info(
        "[DASHBOARD] cadastros habilitados=%s, linhas de adesão=%s, credenciados sem cadastro=%s",
        len(cadastros_ativos),
        len(dados.get("clinicas_com_prontuai") or []),
        len(dados.get("clinicas_sem_prontuai") or []),
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
