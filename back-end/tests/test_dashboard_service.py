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


def pedido(atendimento=None, credenciado="RECIFE - PE - CLINICA A", previsao=None, liberado=False):
    cidade, uf, nome = credenciado.split(" - ", 2)
    return ds._Pedido(atendimento, credenciado, cidade, uf, nome, previsao, liberado)


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
    """Pedido com dois documentos liberados é uma expedição só."""
    pedidos = {1: pedido("2026-09-01"), 2: pedido("2026-09-01"), 3: pedido("2026-09-02"), 4: pedido(None)}
    docs = {1: (2, True), 3: (1, False)}
    r = ds._cruzar_expedicoes(pedidos, docs, date(2026, 9, 22))
    assert r["expedicoes_dia"] == {"2026-09-01": 2, "2026-09-02": 1}
    assert r["expedicoes_prontuai_dia"] == {"2026-09-01": 1}


def test_clinicas_sem_prontuai_usam_o_limite_de_documentos():
    a, b, c = "RECIFE - PE - CLINICA A", "NATAL - RN - CLINICA B", "SALVADOR - BA - CLINICA C"
    pedidos = {
        # A: 3 documentos no histórico -> usa o ProntuAI, fica fora da lista
        1: pedido("2026-08-01", a), 2: pedido("2026-08-02", a), 3: pedido(None, a, "2026-09-25"),
        # B: 2 documentos -> abaixo do limite, entra
        4: pedido("2026-08-01", b), 5: pedido(None, b, "2026-09-30"), 6: pedido(None, b, "2026-09-23"),
        # C: sem documento; previsão passada e pedido já liberado não contam
        7: pedido(None, c, "2026-09-24"), 8: pedido(None, c, "2026-09-01"), 9: pedido(None, c, "2026-09-26", True),
    }
    docs = {1: (2, True), 2: (1, True), 4: (2, True)}
    lista = ds._cruzar_expedicoes(pedidos, docs, date(2026, 9, 22))["clinicas_sem_prontuai"]
    assert [(x["credenciado"], x["pedidos_previstos"], x["proxima_previsao"], x["documentos"]) for x in lista] == [
        (b, 2, "2026-09-23", 2),
        (c, 1, "2026-09-24", 0),
    ]
    assert lista[0]["nome"] == "CLINICA B" and lista[0]["uf"] == "RN"


def test_previsao_de_hoje_ainda_e_futura():
    pedidos = {1: pedido(None, previsao="2026-09-22")}
    assert len(ds._cruzar_expedicoes(pedidos, {}, date(2026, 9, 22))["clinicas_sem_prontuai"]) == 1


def test_brnet_indisponivel_esvazia_tudo_sem_inventar():
    r = ds._cruzar_expedicoes(None, {1: (1, True)}, date(2026, 9, 22))
    assert r == {"expedicoes_dia": {}, "expedicoes_prontuai_dia": {}, "clinicas_sem_prontuai": None}


@pytest.mark.parametrize(
    "primeiro, esperado",
    [(date(2026, 6, 2), "2026-06-01"), (date(2026, 6, 1), "2026-06-01"), (date(2026, 12, 31), "2026-12-01"), (None, None)],
)
def test_primeiro_dia_ligado_e_o_primeiro_do_mes(primeiro, esperado):
    assert ds._primeiro_dia_ligado(primeiro) == esperado
