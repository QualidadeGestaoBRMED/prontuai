"""Testes do cache dos indicadores do dashboard.

A consulta em si não é testada aqui — ela precisa de um Postgres com o schema
real. O que se testa é a camada que decide QUANDO ir ao banco, porque é ela que
protege o banco de uma varredura por F5.

Rodar sem o conftest, que importa main.py e exige DATABASE_URL:

    PYTHONPATH=back-end pytest back-end/tests/test_dashboard_service.py -q --noconftest
"""
import json
import threading
from datetime import datetime

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


def test_chamadas_simultaneas_consultam_uma_vez_so(monkeypatch):
    """Com o cache frio, N requisições ao mesmo tempo não podem virar N varreduras."""
    chamadas = []
    liberar = threading.Event()

    def lento():
        chamadas.append(1)
        liberar.wait(timeout=5)
        return resposta(len(chamadas))

    monkeypatch.setattr(ds, "_consultar", lento)

    threads = [threading.Thread(target=ds.obter_indicadores) for _ in range(4)]
    for t in threads:
        t.start()
    liberar.set()
    for t in threads:
        t.join(timeout=10)

    assert chamadas == [1]


# ── extração de expedições do BRNET (arquivo no disco, fora do git) ──────────


def test_expedicoes_ausentes_nao_derrubam_o_painel(monkeypatch, tmp_path):
    """Servidor sem a extração: o resto do dashboard continua funcionando."""
    monkeypatch.setattr(ds, "EXPEDICOES_PATH", str(tmp_path / "nao-existe.json"))
    assert ds._carregar_expedicoes() == {}


def test_expedicoes_validas_sao_carregadas(monkeypatch, tmp_path):
    arquivo = tmp_path / "exp.json"
    arquivo.write_text(json.dumps({"2026-08-03": 396, "2026-08-04": 351}))
    monkeypatch.setattr(ds, "EXPEDICOES_PATH", str(arquivo))
    assert ds._carregar_expedicoes() == {"2026-08-03": 396, "2026-08-04": 351}


def test_expedicoes_com_lixo_descarta_so_o_lixo(monkeypatch, tmp_path):
    """O arquivo vem de conversão manual de planilha — entrada torta acontece."""
    arquivo = tmp_path / "exp.json"
    arquivo.write_text(json.dumps({
        "2026-08-03": 396,
        "03/08/2026": 100,     # formato de data errado
        "2026-08-04": "trezentos",  # valor não numérico
        "total": 496,          # linha de totalizador da planilha
    }))
    monkeypatch.setattr(ds, "EXPEDICOES_PATH", str(arquivo))
    assert ds._carregar_expedicoes() == {"2026-08-03": 396}


def test_json_quebrado_nao_levanta(monkeypatch, tmp_path):
    arquivo = tmp_path / "exp.json"
    arquivo.write_text("{isso não é json")
    monkeypatch.setattr(ds, "EXPEDICOES_PATH", str(arquivo))
    assert ds._carregar_expedicoes() == {}
