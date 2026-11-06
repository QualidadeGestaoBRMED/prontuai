"""Carga do vocabulário de nomes (`nomes_conhecidos`): nunca zera o que já
existe, não bloqueia quem pede depois da primeira carga, e tenta de novo cedo
quando a consulta falha.

Rodar sem o conftest (`--noconftest`): a consulta ao banco é trocada aqui.
"""
import threading
import time

import pytest

from app.services import nomes_conhecidos as nc


@pytest.fixture(autouse=True)
def limpo(monkeypatch):
    monkeypatch.setattr(nc, "_vocabulario", None)
    monkeypatch.setattr(nc, "_proxima_carga", 0.0)
    monkeypatch.setattr(nc, "_carga_em_andamento", None)


def _esperar_carga():
    evento = nc._carga_em_andamento
    if evento is not None:
        assert evento.wait(2)


def test_primeira_chamada_espera_a_carga(monkeypatch):
    monkeypatch.setattr(nc, "_consultar", lambda: frozenset({"MARIA", "SILVA"}))
    assert nc.vocabulario() == {"MARIA", "SILVA"}


def test_falha_mantem_o_ultimo_vocabulario_e_tenta_de_novo_cedo(monkeypatch):
    monkeypatch.setattr(nc, "_vocabulario", frozenset({"MARIA"}))

    def falha():
        raise RuntimeError("banco fora")

    monkeypatch.setattr(nc, "_consultar", falha)
    antes = time.monotonic()
    assert nc.vocabulario() == {"MARIA"}
    _esperar_carga()
    assert nc.vocabulario() == {"MARIA"}
    assert nc._proxima_carga - antes <= nc.NOVA_TENTATIVA_SEGUNDOS + 1


def test_vencido_devolve_o_antigo_sem_esperar_a_recarga(monkeypatch):
    monkeypatch.setattr(nc, "_vocabulario", frozenset({"MARIA"}))
    liberar = threading.Event()

    def lenta():
        liberar.wait(2)
        return frozenset({"JOAO"})

    monkeypatch.setattr(nc, "_consultar", lenta)
    assert nc.vocabulario() == {"MARIA"}  # não esperou a consulta lenta
    liberar.set()
    _esperar_carga()
    assert nc.vocabulario() == {"JOAO"}


def test_sem_vocabulario_e_banco_fora_devolve_vazio(monkeypatch):
    def falha():
        raise RuntimeError("banco fora")

    monkeypatch.setattr(nc, "_consultar", falha)
    assert nc.vocabulario() == frozenset()
