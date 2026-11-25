"""Fila da conduta na aprovação da Checagem: no máximo N documentos chamando o ml-exams ao mesmo tempo, documento
repetido não entra duas vezes, falha não para a fila e a abertura espera o documento que ainda está nela."""
import asyncio
import threading
import time
from types import SimpleNamespace

import pytest

from app.services.conduta import fila_aprovacao as fa


@pytest.fixture
def ambiente(monkeypatch):
    estado = {"ativos": 0, "pico": 0, "feitos": [], "lento": 0.05}
    trava = threading.Lock()

    def documento(document_id):
        return None if document_id == "sumiu" else SimpleNamespace(id=document_id)

    def sugerir(document):
        with trava:
            estado["ativos"] += 1
            estado["pico"] = max(estado["pico"], estado["ativos"])
        try:
            time.sleep(estado["lento"])
            if document.id == "ruim":
                raise ValueError("leitura quebrou")
            estado["feitos"].append(document.id)
            return {"conduta_sugerida": {"situacao_aso": "LIBERADO"}, "sugestao_id": 1}
        finally:
            with trava:
                estado["ativos"] -= 1

    monkeypatch.setattr(fa.user_db, "get_document_by_id", documento, raising=False)
    monkeypatch.setattr(fa, "sugerir_para_documento", sugerir)
    return estado


async def _rodar(fila, ids):
    fila.iniciar()
    for i in ids:
        fila.enfileirar(i)
    await asyncio.wait_for(fila._fila.join(), 5)


def test_no_maximo_tres_ao_mesmo_tempo(ambiente):
    async def caso():
        fila = fa.FilaConduta(paralelo=3)
        await _rodar(fila, [f"d{i}" for i in range(10)])
        await fila.parar()

    asyncio.run(caso())
    assert ambiente["pico"] == 3
    assert sorted(ambiente["feitos"]) == sorted(f"d{i}" for i in range(10))


def test_documento_repetido_e_falha_nao_param_a_fila(ambiente):
    async def caso():
        fila = fa.FilaConduta(paralelo=3)
        fila.iniciar()
        assert fila.enfileirar("a") is True
        assert fila.enfileirar("a") is False
        for i in ("ruim", "sumiu", "b"):
            fila.enfileirar(i)
        await asyncio.wait_for(fila._fila.join(), 5)
        assert fila._pendentes == {}
        # Depois de sair da fila, uma nova aprovação do mesmo documento entra de novo.
        assert fila.enfileirar("a") is True
        await asyncio.wait_for(fila._fila.join(), 5)
        await fila.parar()

    asyncio.run(caso())
    assert ambiente["feitos"] == ["a", "b", "a"]


def test_fila_desligada_nao_enfileira():
    assert fa.FilaConduta().enfileirar("x") is False


def test_abertura_espera_o_documento_da_fila(ambiente):
    ambiente["lento"] = 0.3

    async def caso():
        fila = fa.FilaConduta(paralelo=1)
        fila.iniciar()
        fila.enfileirar("a")
        await fila.aguardar("a", timeout=5)
        assert ambiente["feitos"] == ["a"]
        inicio = time.monotonic()
        await fila.aguardar("nunca-entrou", timeout=5)
        assert time.monotonic() - inicio < 0.05
        await fila.parar()

    asyncio.run(caso())


def test_abertura_nao_espera_alem_do_limite(ambiente):
    ambiente["lento"] = 1.0

    async def caso():
        fila = fa.FilaConduta(paralelo=1)
        fila.iniciar()
        fila.enfileirar("a")
        inicio = time.monotonic()
        await fila.aguardar("a", timeout=0.1)
        assert time.monotonic() - inicio < 0.5
        await fila.parar()

    asyncio.run(caso())
