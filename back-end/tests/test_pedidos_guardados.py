"""Pedidos guardados para testes em staging (STC-981)."""
import asyncio
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import testes_staging
from app.core.auth import require_admin
from app.core.config import settings
from app.services import brmed_service, pedidos_guardados

CPF = "12345678909"
CNPJ = "12345678000190"
SEM_EXPEDICAO = {
    "erro": "Expedição em aberto não encontrada para o paciente informado.",
    "error_type": "semantic",
    "source": "prontuai_api",
    "http_status": 404,
}
PEDIDO = {
    "nome": "PACIENTE TESTE",
    "exames": ["GLICEMIA DE JEJUM"],
    "source": "prontuai_api",
    "cpf_processado": CPF,
    "pedido_exame_id": "P-1",
}


class Banco:
    """Faz o papel das tabelas, com contagem de acessos."""

    def __init__(self):
        self.ligada = False
        self.linhas = {}
        self.acessos = 0

    def chave(self):
        self.acessos += 1
        return self.ligada

    def gravar(self, identificador, cnpj, resposta):
        self.acessos += 1
        self.linhas[(identificador, cnpj)] = resposta

    def buscar(self, identificador, cnpj):
        self.acessos += 1
        return self.linhas.get((identificador, cnpj))


@pytest.fixture
def banco(monkeypatch):
    novo = Banco()
    monkeypatch.setattr(pedidos_guardados, "chave_ligada", novo.chave)
    monkeypatch.setattr(pedidos_guardados, "_gravar", novo.gravar)
    monkeypatch.setattr(pedidos_guardados, "_buscar", novo.buscar)
    return novo


@pytest.fixture
def staging(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "staging")


def _consultar(monkeypatch, resposta_da_api):
    async def api(**_):
        return dict(resposta_da_api)

    monkeypatch.setattr(brmed_service, "consultar_exames_prontuai_api", api)
    return asyncio.run(brmed_service.consultar_exames_prontuai(cpf=CPF, cnpj=CNPJ))


# ---------------------------------------------------------------------------
# Trava de ambiente
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ambiente", ["production", "prod", "local", "test", "development", "STAGING", ""])
def test_so_existe_em_staging(monkeypatch, ambiente):
    monkeypatch.setattr(settings, "APP_ENV", ambiente)
    assert pedidos_guardados.disponivel() is False


def test_config_assume_producao_sem_app_env():
    """A trava depende disto: sem a variável, o ambiente não é staging."""
    import importlib.util
    import pathlib
    import re

    fonte = pathlib.Path(importlib.util.find_spec("app.core.config").origin).read_text(encoding="utf-8")
    assert re.search(r'APP_ENV = os\.getenv\("APP_ENV", os\.getenv\("ENVIRONMENT", "production"\)\)', fonte)


@pytest.mark.parametrize("ambiente", ["production", "local"])
def test_fora_de_staging_nem_a_chave_e_consultada(monkeypatch, banco, ambiente):
    monkeypatch.setattr(settings, "APP_ENV", ambiente)
    banco.ligada = True
    banco.linhas[(CPF, CNPJ)] = PEDIDO

    assert _consultar(monkeypatch, SEM_EXPEDICAO) == SEM_EXPEDICAO
    assert _consultar(monkeypatch, PEDIDO) == PEDIDO
    assert banco.acessos == 0


def test_fora_de_staging_nao_toca_no_banco(monkeypatch):
    """Sem criar tabela e sem ler a chave, mesmo chamando direto."""
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(pedidos_guardados, "_tabelas_prontas", False)
    for chamada in (
        pedidos_guardados.chave_ligada,
        pedidos_guardados.resumo,
        lambda: pedidos_guardados.definir_chave(True, "x"),
        lambda: pedidos_guardados._buscar(CPF, CNPJ),
        lambda: pedidos_guardados._gravar(CPF, CNPJ, PEDIDO),
    ):
        with pytest.raises(RuntimeError):
            chamada()
    assert pedidos_guardados._tabelas_prontas is False


# ---------------------------------------------------------------------------
# Chave do painel
# ---------------------------------------------------------------------------


def test_desligada_nao_guarda_nem_usa(monkeypatch, banco, staging):
    banco.linhas[(CPF, CNPJ)] = PEDIDO
    assert _consultar(monkeypatch, SEM_EXPEDICAO) == SEM_EXPEDICAO

    banco.linhas.clear()
    assert _consultar(monkeypatch, PEDIDO) == PEDIDO
    assert banco.linhas == {}


def test_consulta_bem_sucedida_guarda_e_devolve_a_resposta_da_api(monkeypatch, banco, staging):
    banco.ligada = True
    assert _consultar(monkeypatch, PEDIDO) == PEDIDO
    assert banco.linhas[(CPF, CNPJ)] == PEDIDO


def test_pedido_sem_exames_nao_e_guardado(monkeypatch, banco, staging):
    banco.ligada = True
    vazio = {**PEDIDO, "exames": []}
    assert _consultar(monkeypatch, vazio) == vazio
    assert banco.linhas == {}


def test_sem_expedicao_usa_o_pedido_guardado_e_marca_a_origem(monkeypatch, banco, staging):
    banco.ligada = True
    banco.linhas[(CPF, CNPJ)] = PEDIDO
    resultado = _consultar(monkeypatch, SEM_EXPEDICAO)
    assert "erro" not in resultado
    assert resultado["exames"] == PEDIDO["exames"]
    assert resultado["source"] == pedidos_guardados.FONTE


def test_sem_expedicao_e_sem_pedido_guardado_mantem_o_erro(monkeypatch, banco, staging):
    banco.ligada = True
    assert _consultar(monkeypatch, SEM_EXPEDICAO) == SEM_EXPEDICAO


def test_pedido_de_outro_cnpj_nao_serve(monkeypatch, banco, staging):
    banco.ligada = True
    banco.linhas[(CPF, "99999999000199")] = PEDIDO
    assert _consultar(monkeypatch, SEM_EXPEDICAO) == SEM_EXPEDICAO


@pytest.mark.parametrize(
    "erro",
    [
        {"erro": "Falha de comunicação com API externa: timeout", "error_type": "technical", "http_status": None},
        {"erro": "Erro interno", "error_type": "technical", "http_status": 500},
        {"erro": "Paciente não encontrado", "error_type": "semantic", "http_status": 404},
        {"erro": "cnpj é obrigatório", "error_type": "semantic", "http_status": 400},
    ],
)
def test_outros_erros_nao_usam_o_pedido_guardado(monkeypatch, banco, staging, erro):
    banco.ligada = True
    banco.linhas[(CPF, CNPJ)] = PEDIDO
    assert _consultar(monkeypatch, erro) == erro
    assert banco.acessos == 0


def test_falha_no_banco_nao_muda_a_resposta_da_api(monkeypatch, staging, caplog):
    def falha(*_):
        raise RuntimeError(f"erro com o CPF {CPF}")

    monkeypatch.setattr(pedidos_guardados, "chave_ligada", lambda: True)
    monkeypatch.setattr(pedidos_guardados, "_gravar", falha)
    monkeypatch.setattr(pedidos_guardados, "_buscar", falha)
    with caplog.at_level(logging.INFO):
        assert _consultar(monkeypatch, PEDIDO) == PEDIDO
        assert _consultar(monkeypatch, SEM_EXPEDICAO) == SEM_EXPEDICAO
    assert CPF not in caplog.text


def test_falha_ao_ler_a_chave_mantem_a_resposta_da_api(monkeypatch, staging):
    def falha():
        raise RuntimeError("banco fora")

    monkeypatch.setattr(pedidos_guardados, "chave_ligada", falha)
    assert _consultar(monkeypatch, SEM_EXPEDICAO) == SEM_EXPEDICAO


def test_log_nao_traz_dados_do_paciente(monkeypatch, banco, staging, caplog):
    banco.ligada = True
    banco.linhas[(CPF, CNPJ)] = PEDIDO
    with caplog.at_level(logging.INFO):
        _consultar(monkeypatch, SEM_EXPEDICAO)
    assert "usando o pedido guardado" in caplog.text
    assert CPF not in caplog.text
    assert PEDIDO["nome"] not in caplog.text


# ---------------------------------------------------------------------------
# Rotas do painel
# ---------------------------------------------------------------------------

ROTA = "/v1/testes-staging/pedidos-guardados"
RESUMO = {"ligada": False, "total_pedidos": 0}


@pytest.fixture
def app():
    aplicacao = FastAPI()
    aplicacao.include_router(testes_staging.router, prefix="/v1")
    return aplicacao


@pytest.mark.parametrize("ambiente", ["production", "local"])
def test_rotas_respondem_404_fora_de_staging_mesmo_para_admin(monkeypatch, app, ambiente):
    monkeypatch.setattr(settings, "APP_ENV", ambiente)
    usadas = []
    monkeypatch.setattr(pedidos_guardados, "resumo", lambda: usadas.append("resumo") or RESUMO)
    monkeypatch.setattr(pedidos_guardados, "definir_chave", lambda *a: usadas.append("definir"))
    cliente = TestClient(app)

    # Sem login: o 404 vem antes da autenticação.
    assert cliente.get(ROTA).status_code == 404
    assert cliente.put(ROTA, json={"ligada": True}).status_code == 404

    app.dependency_overrides[require_admin] = lambda: type("U", (), {"email": "admin@teste"})()
    assert cliente.get(ROTA).status_code == 404
    assert cliente.put(ROTA, json={"ligada": True}).status_code == 404
    assert usadas == []


def test_em_staging_exige_login(monkeypatch, app, staging):
    cliente = TestClient(app)
    assert cliente.get(ROTA).status_code in (401, 403)
    assert cliente.put(ROTA, json={"ligada": True}).status_code in (401, 403)


def test_admin_liga_e_desliga_em_staging(monkeypatch, app, staging):
    estado = {"ligada": False}
    atores = []

    def definir(ligada, ator):
        estado["ligada"] = ligada
        atores.append(ator)

    monkeypatch.setattr(pedidos_guardados, "definir_chave", definir)
    monkeypatch.setattr(pedidos_guardados, "resumo", lambda: {**RESUMO, "ligada": estado["ligada"]})
    app.dependency_overrides[require_admin] = lambda: type("U", (), {"email": "admin@teste"})()
    cliente = TestClient(app)

    assert cliente.get(ROTA).json()["ligada"] is False
    assert cliente.put(ROTA, json={"ligada": True}).json()["ligada"] is True
    assert cliente.put(ROTA, json={"ligada": False}).json()["ligada"] is False
    assert atores == ["admin@teste", "admin@teste"]
