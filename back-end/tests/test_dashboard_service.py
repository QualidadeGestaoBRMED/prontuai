"""Testes do cache dos indicadores do dashboard.

A consulta em si não é testada aqui — ela precisa de um Postgres com o schema
real. O que se testa é a camada que decide QUANDO ir ao banco, porque é ela que
protege o banco de uma varredura por F5.

Rodar sem o conftest, que importa main.py e exige DATABASE_URL:

    PYTHONPATH=back-end pytest back-end/tests/test_dashboard_service.py -q --noconftest
"""
import threading
from datetime import date, datetime

import pytest

from app.services import dashboard_service as ds


@pytest.fixture(autouse=True)
def cache_limpo():
    ds.invalidar_cache()
    yield
    ds.invalidar_cache()


def resposta(n: int) -> dict:
    return {"totais": {"enviados": n}, "ambiente": "test", "gerado_em": 0.0}


def test_segunda_chamada_vem_do_cache(monkeypatch):
    chamadas = []

    def falso():
        chamadas.append(1)
        return resposta(len(chamadas))

    monkeypatch.setattr(ds, "_consultar", falso)

    primeira = ds.obter_indicadores()
    segunda = ds.obter_indicadores()

    assert chamadas == [1]
    assert primeira is segunda


def test_forcar_ignora_o_cache(monkeypatch):
    chamadas = []
    monkeypatch.setattr(ds, "_consultar", lambda: (chamadas.append(1), resposta(len(chamadas)))[1])

    ds.obter_indicadores()
    ds.obter_indicadores(forcar=True)

    assert len(chamadas) == 2


def test_cache_vence_na_virada_do_dia(monkeypatch):
    """O número de ontem não pode sobreviver às 7h de hoje."""
    chamadas = []
    monkeypatch.setattr(ds, "_consultar", lambda: (chamadas.append(1), resposta(len(chamadas)))[1])

    relogio = [datetime(2026, 9, 10, 6, 59, tzinfo=ds.FUSO)]
    monkeypatch.setattr(ds, "agora", lambda: relogio[0])

    ds.obter_indicadores()
    relogio[0] = datetime(2026, 9, 10, 6, 59, 59, tzinfo=ds.FUSO)
    ds.obter_indicadores()
    assert len(chamadas) == 1, "antes das 7h ainda serve o cache"

    relogio[0] = datetime(2026, 9, 10, 7, 0, 1, tzinfo=ds.FUSO)
    ds.obter_indicadores()
    assert len(chamadas) == 2, "passou das 7h, recalcula"

    relogio[0] = datetime(2026, 9, 10, 23, 30, tzinfo=ds.FUSO)
    ds.obter_indicadores()
    assert len(chamadas) == 2, "no mesmo dia depois das 7h, serve o cache até amanhã"

    relogio[0] = datetime(2026, 9, 11, 7, 0, 1, tzinfo=ds.FUSO)
    ds.obter_indicadores()
    assert len(chamadas) == 3, "virada seguinte recalcula"


@pytest.mark.parametrize(
    "momento, esperado",
    [
        (datetime(2026, 9, 10, 6, 59, tzinfo=ds.FUSO), datetime(2026, 9, 10, 7, 0, tzinfo=ds.FUSO)),
        (datetime(2026, 9, 10, 7, 0, tzinfo=ds.FUSO), datetime(2026, 9, 11, 7, 0, tzinfo=ds.FUSO)),
        (datetime(2026, 9, 10, 18, 0, tzinfo=ds.FUSO), datetime(2026, 9, 11, 7, 0, tzinfo=ds.FUSO)),
    ],
)
def test_proxima_virada(momento, esperado):
    assert ds.proxima_virada(momento) == esperado


def test_falha_no_banco_vira_erro_de_dominio(monkeypatch):
    def explode():
        raise RuntimeError("canceling statement due to statement timeout")

    monkeypatch.setattr(ds, "_consultar", explode)

    with pytest.raises(ds.DashboardIndisponivel):
        ds.obter_indicadores()

    # Falha não pode ficar em cache: a próxima chamada tenta de novo.
    with pytest.raises(ds.DashboardIndisponivel):
        ds.obter_indicadores()


def _dispara(n, forcar=False):
    threads = [threading.Thread(target=ds.obter_indicadores, args=(forcar,)) for _ in range(n)]
    for t in threads:
        t.start()
    return threads


def test_chamadas_simultaneas_consultam_uma_vez_so(monkeypatch):
    """Com o cache frio, N requisições ao mesmo tempo não podem virar N varreduras."""
    chamadas = []
    liberar = threading.Event()

    def lento():
        chamadas.append(1)
        liberar.wait(timeout=5)
        return resposta(len(chamadas))

    monkeypatch.setattr(ds, "_consultar", lento)

    threads = _dispara(4)
    liberar.set()
    for t in threads:
        t.join(timeout=10)

    assert chamadas == [1]


def test_forcar_simultaneo_nao_vira_uma_varredura_por_clique(monkeypatch):
    """Vários "Atualizar" ao mesmo tempo custam uma varredura, não uma por clique.

    Regressão real: o lock serializava mas não deduplicava o caminho `forcar`,
    e 6 pedidos simultâneos viravam 6 varreduras de 7s enfileiradas (40s no total).
    """
    chamadas = []
    liberar = threading.Event()

    def lento():
        chamadas.append(1)
        liberar.wait(timeout=5)
        return resposta(len(chamadas))

    monkeypatch.setattr(ds, "_consultar", lento)

    threads = _dispara(6, forcar=True)
    liberar.set()
    for t in threads:
        t.join(timeout=10)

    assert chamadas == [1], f"{len(chamadas)} varreduras para 6 cliques simultâneos"


def test_forcar_sequencial_continua_recalculando(monkeypatch):
    """A dedupe não pode transformar o botão em no-op para quem clica depois."""
    chamadas = []
    monkeypatch.setattr(ds, "_consultar", lambda: (chamadas.append(1), resposta(len(chamadas)))[1])

    ds.obter_indicadores(forcar=True)
    ds.obter_indicadores(forcar=True)
    ds.obter_indicadores(forcar=True)

    assert len(chamadas) == 3


# ── expedições do BRNET (API de monitoramento de credenciados) ─────────────

HOJE = datetime(2026, 9, 22, 10, 0, tzinfo=ds.FUSO)


def pedido(
    atendimento=None,
    credenciado="RECIFE - PE - CLINICA A",
    previsao=None,
    liberado=False,
    liberacao=...,
):
    """Pedido do BRNET para os testes.

    `liberacao` cai em `atendimento` por padrão. Estes fixtures nasceram quando
    realizado era "atendido", e passar só a data de atendimento era a forma de
    dizer "este pedido está concluído". Realizado passou a ser "liberado" (1.2),
    e o padrão mantém a intenção de cada caso sem reescrever os 55 usos.

    Para exercitar a diferença — atendido e ainda NÃO liberado —, passe
    `liberacao=None` explicitamente.
    """
    cidade, uf, nome = credenciado.split(" - ", 2)
    if liberacao is ...:
        liberacao = atendimento
    return ds._Pedido(atendimento, credenciado, cidade, uf, nome, previsao, liberado, liberacao)


def cadastros(*nomes):
    """Índice de cadastros habilitados, como `_consultar` monta."""
    return ds._indexar_cadastros(list(nomes))


def _api_falsa(monkeypatch, por_mes, hoje=HOJE):
    """Troca a busca de um mês por um dicionário; registra os meses pedidos."""
    pedidos = []

    async def falso(ano, mes, sem):
        pedidos.append((ano, mes))
        resultado = por_mes.get((ano, mes), {})
        if isinstance(resultado, Exception):
            raise resultado
        return resultado

    monkeypatch.setattr(ds, "_buscar_pedidos_mes", falso)
    monkeypatch.setattr(ds, "agora", lambda: hoje)
    return pedidos


def test_pedidos_de_meses_de_solicitacao_diferentes_se_juntam(monkeypatch):
    _api_falsa(monkeypatch, {(2026, 8): {1: pedido("2026-09-02")}, (2026, 9): {2: pedido("2026-09-02")}})
    assert set(ds._carregar_pedidos("2026-09-10")) == {1, 2}


def test_busca_dois_meses_antes_do_primeiro_documento(monkeypatch):
    meses = _api_falsa(monkeypatch, {})
    ds._carregar_pedidos("2026-08-15")
    assert sorted(meses) == [(2026, 6), (2026, 7), (2026, 8), (2026, 9)]


def test_so_meses_em_aberto_sao_buscados_de_novo(monkeypatch):
    meses = _api_falsa(monkeypatch, {})
    ds._carregar_pedidos("2026-05-01")
    meses.clear()
    ds._carregar_pedidos("2026-05-01")
    assert sorted(meses) == [(2026, 7), (2026, 8), (2026, 9)]


def test_mes_nunca_buscado_com_falha_deixa_incompleto(monkeypatch):
    """Denominador faltando inflaria a cobertura; melhor não mostrar."""
    _api_falsa(monkeypatch, {(2026, 7): RuntimeError("BRNET fora")})
    assert ds._carregar_pedidos("2026-09-01") is None


def test_mes_em_aberto_com_falha_reaproveita_a_ultima_busca(monkeypatch):
    _api_falsa(monkeypatch, {(2026, 9): {1: pedido("2026-09-01")}})
    ds._carregar_pedidos("2026-09-01")

    _api_falsa(monkeypatch, {(2026, 9): RuntimeError("BRNET fora")})
    assert set(ds._carregar_pedidos("2026-09-01")) == {1}


def test_sem_documento_nao_busca_nada(monkeypatch):
    meses = _api_falsa(monkeypatch, {})
    assert ds._carregar_pedidos(None) is None
    assert meses == []


def test_virada_de_ano(monkeypatch):
    meses = _api_falsa(monkeypatch, {}, hoje=datetime(2027, 1, 5, 10, 0, tzinfo=ds.FUSO))
    ds._carregar_pedidos("2026-12-20")
    assert sorted(meses) == [(2026, 10), (2026, 11), (2026, 12), (2027, 1)]


def test_cobertura_conta_pedido_e_nao_documento():
    """Pedido com dois documentos é uma expedição só."""
    pedidos = {1: pedido("2026-09-01"), 2: pedido("2026-09-01"), 3: pedido("2026-09-02"), 4: pedido(None)}
    docs = {1: 2, 3: 1}
    r = ds._cruzar_expedicoes(pedidos, docs, date(2026, 9, 22))
    assert r["expedicoes_dia"] == {"2026-09-01": 2, "2026-09-02": 1}
    assert r["expedicoes_prontuai_dia"] == {"2026-09-01": 1, "2026-09-02": 1}


def test_passou_pelo_prontuai_e_processado_nao_liberado():
    """Documento rejeitado ou pendente passou pela plataforma do mesmo jeito.

    Medir só o liberado confundiria adoção (usou o ProntuAI?) com desfecho da
    revisão (o prontuário estava completo?), que são perguntas diferentes.
    """
    pedidos = {1: pedido("2026-09-01"), 2: pedido("2026-09-01")}
    # nenhum dos dois foi liberado; os dois foram processados
    r = ds._cruzar_expedicoes(pedidos, {1: 1, 2: 3}, date(2026, 9, 22))
    assert r["expedicoes_prontuai_dia"] == {"2026-09-01": 2}


def test_cadastro_habilitado_decide_o_lado_nao_o_volume():
    """"Clínica no ProntuAI" é ter cadastro ativo, não ter mandado documento."""
    a, b, c = "RECIFE - PE - CLINICA A", "NATAL - RN - CLINICA B", "SALVADOR - BA - CLINICA C"
    pedidos = {
        # A: tem cadastro -> habilitada, sai da lista de prioridade
        1: pedido("2026-08-01", a), 2: pedido(None, a, "2026-09-25"),
        # B: 2 documentos mas SEM cadastro -> continua na lista
        3: pedido("2026-08-01", b), 4: pedido(None, b, "2026-09-30"), 5: pedido(None, b, "2026-09-23"),
        # C: sem cadastro e sem documento; previsão passada e pedido liberado não contam
        6: pedido(None, c, "2026-09-24"), 7: pedido(None, c, "2026-09-01"), 8: pedido(None, c, "2026-09-26", True),
    }
    r = ds._cruzar_expedicoes(pedidos, {1: 2, 3: 2}, date(2026, 9, 22), {}, cadastros("CLINICA A"))
    lista = r["clinicas_sem_prontuai"]
    assert [(x["credenciado"], x["pedidos_previstos"], x["documentos"]) for x in lista] == [
        (b, 2, 2),
        (c, 1, 0),
    ]
    assert lista[0]["nome"] == "CLINICA B" and lista[0]["uf"] == "RN"
    assert [x["clinica"] for x in r["clinicas_com_prontuai"]] == ["CLINICA A"]


def test_cadastro_sem_nenhum_documento_e_habilitado():
    """Cadastro que nunca usou a plataforma é adesão baixa, não prioridade de inclusão.

    Era o furo da regra por volume: a maior linha da lista de inclusão podia ser
    uma clínica que já estava cadastrada.
    """
    cred = "RECIFE - PE - QUALIMETRA"
    pedidos = {1: pedido("2026-09-01", cred), 2: pedido(None, cred, "2026-09-25")}
    r = ds._cruzar_expedicoes(pedidos, {}, date(2026, 9, 22), {}, cadastros("Qualimetra"))
    assert r["clinicas_sem_prontuai"] == []
    (linha,) = r["clinicas_com_prontuai"]
    assert linha["clinica"] == "Qualimetra" and linha["documentos"] == 0
    # realizou 1 e nenhum passou pelo ProntuAI: adesão 0%, que é diferente de nula
    assert sum(linha["realizados_dia"].values()) == 1
    assert linha["realizados_prontuai_dia"] == {}


@pytest.mark.parametrize(
    "cadastro_no_prontuai",
    ["RECIFE - PE - QUALIMETRA", "Qualimetra", "QUALIMETRA", "qualimetra"],
)
def test_ponte_por_nome_casa_rotulo_inteiro_e_nome_curto(cadastro_no_prontuai):
    """O rótulo do BRNET e o cadastro são digitados em sistemas diferentes."""
    pedidos = {1: pedido(None, "RECIFE - PE - QUALIMETRA", "2026-09-25")}
    r = ds._cruzar_expedicoes(pedidos, {}, date(2026, 9, 22), {}, cadastros(cadastro_no_prontuai))
    assert len(r["clinicas_com_prontuai"]) == 1 and r["clinicas_sem_prontuai"] == []


def test_ponte_por_nome_ignora_acento():
    pedidos = {1: pedido(None, "BRASÍLIA - DF - CLÍNICA SAÚDE", "2026-09-25")}
    r = ds._cruzar_expedicoes(pedidos, {}, date(2026, 9, 22), {}, cadastros("BRASILIA - DF - CLINICA SAUDE"))
    assert len(r["clinicas_com_prontuai"]) == 1


def test_previsoes_saem_quebradas_por_data_e_ordenadas():
    cred = "RECIFE - PE - CLINICA A"
    pedidos = {
        1: pedido(None, cred, "2026-09-30"),
        2: pedido(None, cred, "2026-09-23"),
        3: pedido(None, cred, "2026-09-23"),
        4: pedido(None, cred, "2026-09-01"),  # vencido: só contagem, sem data na lista
    }
    item = ds._cruzar_expedicoes(pedidos, {}, date(2026, 9, 22))["clinicas_sem_prontuai"][0]
    assert item["previsoes"] == [
        {"data": "2026-09-23", "pedidos": 2},
        {"data": "2026-09-30", "pedidos": 1},
    ]
    assert item["pedidos_previstos"] == 3
    assert item["vencidos"] == 1


def test_credenciado_so_com_vencidos_fica_de_fora():
    """A lista é de previsões futuras; sem nenhuma, o credenciado não entra."""
    pedidos = {1: pedido(None, "NATAL - RN - CLINICA B", "2026-09-01")}
    assert ds._cruzar_expedicoes(pedidos, {}, date(2026, 9, 22))["clinicas_sem_prontuai"] == []


def test_previsao_de_hoje_ainda_e_futura():
    pedidos = {1: pedido(None, previsao="2026-09-22")}
    assert len(ds._cruzar_expedicoes(pedidos, {}, date(2026, 9, 22))["clinicas_sem_prontuai"]) == 1


def test_brnet_indisponivel_esvazia_tudo_sem_inventar():
    r = ds._cruzar_expedicoes(None, {1: 1}, date(2026, 9, 22))
    assert r == {
        "expedicoes_dia": {},
        "expedicoes_prontuai_dia": {},
        "clinicas_sem_prontuai": None,
        "clinicas_com_prontuai": None,
        "previstos_uf_dia": None,
    }


# ── previstos: os dois lados do mesmo corte ────────────────────────────────


def test_os_dois_grupos_sao_complementares():
    """Todo pedido previsto cai em exatamente uma das listas.

    É o que sustenta o card de previstos: somar as duas dá o total, e nenhum
    credenciado aparece nas duas nem some no meio.
    """
    usa, nao_usa = "RECIFE - PE - CLINICA A", "NATAL - RN - CLINICA B"
    pedidos = {
        1: pedido("2026-08-01", usa), 2: pedido("2026-08-02", usa),
        3: pedido(None, usa, "2026-09-25"), 4: pedido(None, usa, "2026-09-26"),
        5: pedido("2026-08-01", nao_usa), 6: pedido(None, nao_usa, "2026-09-30"),
    }
    docs = {1: 2, 2: 1, 5: 2}
    r = ds._cruzar_expedicoes(pedidos, docs, date(2026, 9, 22), {}, cadastros("CLINICA A"))

    com = {c["clinica"]: c["pedidos_previstos"] for c in r["clinicas_com_prontuai"]}
    sem = {c["credenciado"]: c["pedidos_previstos"] for c in r["clinicas_sem_prontuai"]}
    assert com == {"CLINICA A": 2}  # tem cadastro habilitado
    assert sem == {nao_usa: 1}      # 2 documentos, mas sem cadastro
    assert set(com) & set(sem) == set()
    assert sum(com.values()) + sum(sem.values()) == 3


def test_previsto_nao_soma_com_realizado():
    """Pedido já liberado é expedição realizada e não pode virar previsto."""
    cred = "RECIFE - PE - CLINICA A"
    pedidos = {
        1: pedido("2026-09-20", cred, "2026-09-25", liberado=True),
        2: pedido("2026-09-20", cred, "2026-09-25"),
    }
    r = ds._cruzar_expedicoes(pedidos, {1: 1, 2: 1}, date(2026, 9, 22))
    previstos = r["clinicas_sem_prontuai"] + r["clinicas_com_prontuai"]
    assert sum(c["pedidos_previstos"] for c in previstos) == 1
    # os dois foram atendidos e processados: continuam contados como realizado
    assert r["expedicoes_prontuai_dia"] == {"2026-09-20": 2}


def test_cadastro_renomeado_cai_na_clinica_que_mais_enviou():
    """Quando a ponte por nome falha, o documento enviado ainda diz o cadastro.

    Cobre o cadastro renomeado depois de já ter volume: o rótulo do BRNET não
    casa com nenhum nome atual, mas os documentos apontam a clínica.
    """
    cred = "RECIFE - PE - CLINICA A"
    pedidos = {n: pedido("2026-08-01", cred) for n in (1, 2, 3)}
    pedidos[4] = pedido(None, cred, "2026-09-25")
    docs = {1: 2, 2: 1, 3: 1}
    clinicas = {1: "Clinica A Matriz", 2: "Clinica A Filial", 3: "Clinica A Matriz"}
    r = ds._cruzar_expedicoes(pedidos, docs, date(2026, 9, 22), clinicas, cadastros("CLINICA A"))
    assert r["clinicas_com_prontuai"][0]["clinica"] == "CLINICA A"

    # sem cadastro nenhum, o credenciado vai para a lista de inclusão
    r2 = ds._cruzar_expedicoes(pedidos, docs, date(2026, 9, 22), clinicas, cadastros())
    assert r2["clinicas_com_prontuai"] == [] and len(r2["clinicas_sem_prontuai"]) == 1


def test_credenciado_sem_documento_nao_tem_clinica():
    pedidos = {1: pedido(None, "NATAL - RN - CLINICA B", "2026-09-25")}
    assert ds._cruzar_expedicoes(pedidos, {}, date(2026, 9, 22))["clinicas_sem_prontuai"][0]["clinica"] is None


@pytest.mark.parametrize(
    "primeiro, esperado",
    [(date(2026, 6, 2), "2026-06-01"), (date(2026, 6, 1), "2026-06-01"), (date(2026, 12, 31), "2026-12-01"), (None, None)],
)
def test_primeiro_dia_ligado_e_o_primeiro_do_mes(primeiro, esperado):
    assert ds._primeiro_dia_ligado(primeiro) == esperado


# ── expedições por prazo: clínica x técnico de credenciados ─────────────────


def test_cada_lado_e_medido_contra_o_proprio_prazo():
    """Clínica tem até 03/09; a BR MED, um dia útil depois (04/09)."""
    pedidos = {1: pedido("2026-09-01", previsao="2026-09-03")}
    docs = [(1, date(2026, 9, 3), date(2026, 9, 4), date(2026, 9, 4))]
    r = ds._cruzar_prazos(pedidos, docs)
    assert r["prazo_clinica_dia"] == {"2026-09-03": [0, 1, 0]}   # clínica no dia
    assert r["prazo_tecnico_dia"] == {"2026-09-04": [0, 1, 0]}   # técnico no dia, não atrasado


def test_atraso_da_clinica_nao_vira_atraso_do_tecnico():
    pedidos = {1: pedido(previsao="2026-09-03")}
    docs = [(1, date(2026, 9, 4), date(2026, 9, 4), date(2026, 9, 4))]
    r = ds._cruzar_prazos(pedidos, docs)
    assert r["prazo_clinica_dia"] == {"2026-09-04": [0, 0, 1]}
    assert r["prazo_tecnico_dia"] == {"2026-09-04": [0, 1, 0]}


def test_prazo_classifica_antecipado_no_dia_e_atrasado():
    pedidos = {1: pedido(previsao="2026-09-10")}
    docs = [
        (1, date(2026, 9, 8), date(2026, 9, 10), date(2026, 9, 11)),
        (1, date(2026, 9, 10), date(2026, 9, 12), date(2026, 9, 11)),
    ]
    r = ds._cruzar_prazos(pedidos, docs)
    assert r["prazo_clinica_dia"] == {"2026-09-08": [1, 0, 0], "2026-09-10": [0, 1, 0]}
    assert r["prazo_tecnico_dia"] == {"2026-09-10": [1, 0, 0], "2026-09-12": [0, 0, 1]}


def test_prazo_conta_documento_e_nao_pedido():
    """Reenvio é outra entrega da clínica."""
    pedidos = {1: pedido(previsao="2026-09-10")}
    docs = [(1, date(2026, 9, 8), None, None), (1, date(2026, 9, 8), None, None)]
    assert ds._cruzar_prazos(pedidos, docs)["prazo_clinica_dia"] == {"2026-09-08": [2, 0, 0]}


def test_aprovacao_da_ia_nao_entra_no_tecnico():
    """Sem aprovação humana (None), o documento conta só do lado da clínica."""
    pedidos = {1: pedido(previsao="2026-09-10")}
    r = ds._cruzar_prazos(pedidos, [(1, date(2026, 9, 8), None, date(2026, 9, 11))])
    assert r["prazo_clinica_dia"] == {"2026-09-08": [1, 0, 0]}
    assert r["prazo_tecnico_dia"] == {}


def test_sem_prazo_o_documento_fica_fora_daquele_lado():
    pedidos = {1: pedido(previsao=None)}
    docs = [(1, date(2026, 9, 8), date(2026, 9, 8), None), (99, date(2026, 9, 8), None, None)]
    assert ds._cruzar_prazos(pedidos, docs) == {"prazo_clinica_dia": {}, "prazo_tecnico_dia": {}}


def test_sem_brnet_o_tecnico_continua():
    """O prazo da BR MED vem gravado no documento; só a clínica depende da API."""
    r = ds._cruzar_prazos(None, [(1, date(2026, 9, 8), date(2026, 9, 9), date(2026, 9, 9))])
    assert r == {"prazo_clinica_dia": {}, "prazo_tecnico_dia": {"2026-09-09": [0, 1, 0]}}


# ── 1.2: adesão por clínica (realizados via ProntuAI ÷ realizados) ─────────


def por_clinica(resultado, nome):
    return next(c for c in resultado["clinicas_com_prontuai"] if c["clinica"] == nome)


def test_realizados_por_clinica_saem_quebrados_por_dia_de_atendimento():
    """A adesão é o recorte por clínica do KPI de cobertura: mesma datação."""
    cred = "RECIFE - PE - CRED A"
    pedidos = {
        1: pedido("2026-09-01", cred), 2: pedido("2026-09-01", cred),
        3: pedido("2026-09-02", cred), 4: pedido(None, cred),  # não atendido
    }
    docs = {1: 1, 2: 1, 3: 1, 4: 1}
    clinicas = {n: "Clinica A" for n in (1, 2, 3, 4)}
    r = ds._cruzar_expedicoes(pedidos, docs, date(2026, 9, 22), clinicas, cadastros("CRED A"))
    c = por_clinica(r, "CRED A")
    assert c["realizados_dia"] == {"2026-09-01": 2, "2026-09-02": 1}
    assert c["realizados_prontuai_dia"] == {"2026-09-01": 2, "2026-09-02": 1}
    # o total por clínica fecha com o global, que alimenta o KPI de cobertura
    assert r["expedicoes_dia"] == c["realizados_dia"]
    assert r["expedicoes_prontuai_dia"] == c["realizados_prontuai_dia"]


def test_dois_credenciados_do_mesmo_cadastro_viram_uma_clinica():
    """Duas unidades do BRNET que mandam sob o mesmo cadastro somam juntas."""
    # As duas unidades do BRNET carregam o mesmo nome curto e casam com o mesmo
    # cadastro — é assim que uma rede com duas praças vira uma linha só.
    a, b = "RECIFE - PE - REDE X", "OLINDA - PE - REDE X"
    pedidos = {
        1: pedido("2026-09-01", a), 2: pedido("2026-09-01", a), 3: pedido("2026-09-02", a),
        4: pedido("2026-09-01", b), 5: pedido("2026-09-02", b), 6: pedido("2026-09-03", b),
        7: pedido(None, a, "2026-09-25"), 8: pedido(None, b, "2026-09-26"),
    }
    docs = {n: 1 for n in range(1, 7)}
    r = ds._cruzar_expedicoes(pedidos, docs, date(2026, 9, 22), {}, cadastros("Rede X"))
    assert len(r["clinicas_com_prontuai"]) == 1
    c = por_clinica(r, "Rede X")
    assert sum(c["realizados_dia"].values()) == 6
    assert sum(c["realizados_prontuai_dia"].values()) == 6   # todos processados
    assert c["pedidos_previstos"] == 2                       # os dois previstos somam
    assert c["documentos"] == 6


def test_clinica_habilitada_sem_previsto_ainda_aparece():
    """A adesão dela existe — é o que a tabela 1.3 mede. Zero previstos não a some."""
    cred = "RECIFE - PE - CRED A"
    pedidos = {n: pedido("2026-09-01", cred) for n in (1, 2, 3)}
    docs = {n: 1 for n in (1, 2, 3)}
    r = ds._cruzar_expedicoes(pedidos, docs, date(2026, 9, 22), {}, cadastros("CRED A"))
    c = por_clinica(r, "CRED A")
    assert c["pedidos_previstos"] == 0 and c["previsoes"] == []
    assert sum(c["realizados_dia"].values()) == 3


def test_credenciado_sem_cadastro_nao_gera_realizados_por_clinica():
    """Sem cadastro habilitado não há adesão a medir — nem entra na lista."""
    cred = "NATAL - RN - CRED B"
    pedidos = {1: pedido("2026-09-01", cred), 2: pedido(None, cred, "2026-09-25")}
    r = ds._cruzar_expedicoes(pedidos, {1: 2}, date(2026, 9, 22), {1: "Clinica B"})
    assert r["clinicas_com_prontuai"] == []
    assert r["clinicas_sem_prontuai"][0]["clinica"] is None
    # o realizado dele continua no global: a cobertura da empresa não muda
    assert r["expedicoes_dia"] == {"2026-09-01": 1}


def test_realizado_e_previsto_nunca_se_cruzam():
    """Pedido previsto (não liberado, com data futura) não vira realizado."""
    cred = "RECIFE - PE - CRED A"
    pedidos = {
        1: pedido("2026-09-01", cred), 2: pedido("2026-09-01", cred), 3: pedido("2026-09-01", cred),
        4: pedido(None, cred, "2026-09-25"),
    }
    docs = {n: 1 for n in (1, 2, 3)}
    c = por_clinica(
        ds._cruzar_expedicoes(pedidos, docs, date(2026, 9, 22), {}, cadastros("CRED A")),
        "CRED A",
    )
    assert sum(c["realizados_dia"].values()) == 3
    assert c["pedidos_previstos"] == 1
    assert "2026-09-25" not in c["realizados_dia"]


def test_parentese_do_rotulo_nao_impede_o_casamento():
    """O BRNET anexa "(CONDIÇÃO ESPECIAL)" ao rótulo; o cadastro não tem isso."""
    pedidos = {1: pedido(None, "SALVADOR - BA - CISVIVER (CONDIÇÃO ESPECIAL)", "2026-09-25")}
    r = ds._cruzar_expedicoes(pedidos, {}, date(2026, 9, 22), {}, cadastros("Cisviver"))
    assert [c["clinica"] for c in r["clinicas_com_prontuai"]] == ["Cisviver"]


def test_documento_prova_o_cadastro_quando_o_nome_nao_casa():
    """Nome em ordem invertida não pode tirar do ProntuAI quem manda 500 documentos.

    O `clinic_id` do documento é fato: diz de qual cadastro o prontuário saiu,
    sem depender de como o BRNET escreve o rótulo.
    """
    cred = "BELO HORIZONTE - MG - MEDIAR"
    pedidos = {n: pedido("2026-08-01", cred) for n in (1, 2, 3)}
    pedidos[4] = pedido(None, cred, "2026-09-25")
    docs = {1: 1, 2: 1, 3: 1}
    clinicas = {n: "Mediar - Belo Horizonte" for n in (1, 2, 3)}
    r = ds._cruzar_expedicoes(
        pedidos, docs, date(2026, 9, 22), clinicas, cadastros("Mediar - Belo Horizonte")
    )
    assert [c["clinica"] for c in r["clinicas_com_prontuai"]] == ["Mediar - Belo Horizonte"]
    assert r["clinicas_sem_prontuai"] == []


def test_documento_avulso_nao_da_cadastro_a_quem_nao_tem():
    """Unidade vizinha mandando pela conta de outra não cadastra o credenciado."""
    cred = "COTIA - SP - CAMARGO DANTAS"
    pedidos = {1: pedido("2026-08-01", cred), 2: pedido(None, cred, "2026-09-25")}
    r = ds._cruzar_expedicoes(
        pedidos, {1: 1}, date(2026, 9, 22), {1: "Mediar - Belo Horizonte"},
        cadastros("Mediar - Belo Horizonte"),
    )
    assert r["clinicas_com_prontuai"] == []
    assert [c["credenciado"] for c in r["clinicas_sem_prontuai"]] == [cred]


def test_documento_de_cadastro_inativo_nao_habilita():
    """A prova é o cadastro estar ATIVO, não o documento existir."""
    cred = "BELO HORIZONTE - MG - MEDIAR"
    pedidos = {n: pedido("2026-08-01", cred) for n in (1, 2, 3)}
    pedidos[4] = pedido(None, cred, "2026-09-25")
    r = ds._cruzar_expedicoes(
        pedidos, {1: 1, 2: 1, 3: 1}, date(2026, 9, 22),
        {n: "Mediar - Belo Horizonte" for n in (1, 2, 3)}, cadastros(),  # nenhum ativo
    )
    assert r["clinicas_com_prontuai"] == [] and len(r["clinicas_sem_prontuai"]) == 1


def test_atendido_sem_liberacao_nao_e_realizado(monkeypatch):
    """Realizado é pedido EXPEDIDO, não atendido (1.2).

    O pedido 1 foi atendido e liberado; o 2 foi atendido e ainda não. Só o
    primeiro pode entrar no denominador da adesão e no KPI de expedições — o
    segundo é trabalho em curso.

    Antes de set/2026 os dois contavam. Medido em setembro, isso punha 131
    pedidos a mais no denominador e deixava a adesão 3,1 pp abaixo da real.
    """
    cred = "RECIFE - PE - CLINICA A"
    pedidos = {
        1: pedido("2026-09-01", cred, liberacao="2026-09-03"),
        2: pedido("2026-09-02", cred, liberacao=None),
    }
    saida = ds._cruzar_expedicoes(pedidos, {1: 1, 2: 1}, HOJE.date(), {}, cadastros(cred))

    # Denominador: só o liberado, e datado pelo dia da LIBERAÇÃO.
    assert saida["expedicoes_dia"] == {"2026-09-03": 1}
    assert saida["expedicoes_prontuai_dia"] == {"2026-09-03": 1}

    (linha,) = [c for c in saida["clinicas_com_prontuai"] if c["credenciado"] == cred]
    assert linha["realizados_dia"] == {"2026-09-03": 1}
    assert linha["realizados_prontuai_dia"] == {"2026-09-03": 1}


def test_liberado_conta_no_dia_da_liberacao_nao_do_atendimento(monkeypatch):
    """A virada de mês é o caso que importa: atendido em agosto e liberado em
    setembro é realizado de SETEMBRO. Com a datação antiga caía em agosto."""
    cred = "RECIFE - PE - CLINICA A"
    pedidos = {1: pedido("2026-08-28", cred, liberacao="2026-09-02")}
    saida = ds._cruzar_expedicoes(pedidos, {1: 1}, HOJE.date(), {}, cadastros(cred))

    assert saida["expedicoes_dia"] == {"2026-09-02": 1}
    assert "2026-08-28" not in saida["expedicoes_dia"]


def test_credenciado_habilitado_com_poucos_documentos_e_nome_divergente():
    """Lacuna conhecida da ponte por nome, travada aqui para não passar batida.

    Nome que não casa + menos de `MIN_DOCUMENTOS_CADASTRO` documentos = o
    credenciado cai na lista de inclusão mesmo tendo cadastro ativo. Só sai dessa
    se o BRNET passar a mandar id ou CNPJ, ou se o cadastro for renomeado para
    casar. O log de `_cruzar_expedicoes` é quem denuncia o caso.
    """
    cred = "BELO HORIZONTE - MG - MEDIAR"
    pedidos = {1: pedido("2026-08-01", cred), 2: pedido(None, cred, "2026-09-25")}
    r = ds._cruzar_expedicoes(
        pedidos, {1: 2}, date(2026, 9, 22), {1: "Mediar - Belo Horizonte"},
        cadastros("Mediar - Belo Horizonte"),
    )
    assert r["clinicas_com_prontuai"] == []
    assert [c["credenciado"] for c in r["clinicas_sem_prontuai"]] == [cred]


def test_cadastros_com_o_mesmo_nome_normalizado_se_fundem():
    """Também conhecido: o índice guarda um por chave, o primeiro em ordem."""
    assert ds._indexar_cadastros(["QUALIMETRA", "Qualimetra"]) == {"qualimetra": "QUALIMETRA"}
    # parêntese descartado pode colidir com um cadastro de nome igual sem ele
    assert ds._chave_nome("CISVIVER (CONDIÇÃO ESPECIAL)") == ds._chave_nome("Cisviver")


# ── 2.1: previstos por UF, de cada lado do corte ───────────────────────────


def test_previstos_por_uf_seguem_o_credenciado_nao_o_cadastro():
    """Cadastro que recebe de duas praças não joga tudo na UF de uma delas."""
    a, b = "RECIFE - PE - REDE X", "SALVADOR - BA - REDE X"
    pedidos = {
        1: pedido(None, a, "2026-09-25"), 2: pedido(None, a, "2026-09-25"),
        3: pedido(None, b, "2026-09-26"),
        4: pedido(None, "NATAL - RN - SEM CADASTRO", "2026-09-27"),
    }
    r = ds._cruzar_expedicoes(pedidos, {}, date(2026, 9, 22), {}, cadastros("Rede X"))
    assert r["previstos_uf_dia"]["dentro"] == {"PE": {"2026-09-25": 2}, "BA": {"2026-09-26": 1}}
    assert r["previstos_uf_dia"]["fora"] == {"RN": {"2026-09-27": 1}}
    # a lista por clínica continua agregando as duas praças numa linha só
    assert len(r["clinicas_com_prontuai"]) == 1
    assert r["clinicas_com_prontuai"][0]["pedidos_previstos"] == 3


def test_uf_por_dia_fecha_com_os_previstos_das_listas():
    """Invariante da 2.1: dentro + fora por UF = total de previstos."""
    pedidos = {
        1: pedido(None, "RECIFE - PE - COM", "2026-09-25"),
        2: pedido(None, "NATAL - RN - SEM", "2026-09-26"),
        3: pedido(None, "NATAL - RN - SEM", "2026-09-01"),   # vencido, fora da conta
        4: pedido(None, "NATAL - RN - SEM", "2026-09-28", True),  # liberado, fora da conta
    }
    r = ds._cruzar_expedicoes(pedidos, {}, date(2026, 9, 22), {}, cadastros("COM"))
    soma_uf = sum(
        n for lado in r["previstos_uf_dia"].values() for dias in lado.values() for n in dias.values()
    )
    soma_listas = sum(
        c["pedidos_previstos"]
        for c in r["clinicas_com_prontuai"] + r["clinicas_sem_prontuai"]
    )
    assert soma_uf == soma_listas == 2


def test_credenciado_sem_uf_cai_num_balde_proprio():
    pedidos = {1: ds._Pedido(None, "ROTULO SOLTO", None, None, None, "2026-09-25", False, None)}
    r = ds._cruzar_expedicoes(pedidos, {}, date(2026, 9, 22), {}, cadastros())
    assert r["previstos_uf_dia"]["fora"] == {"—": {"2026-09-25": 1}}
