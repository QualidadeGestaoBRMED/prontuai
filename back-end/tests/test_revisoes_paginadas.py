"""Tela de Revisões (`/admin/validacoes`) — `GET /v1/documents/revisoes`.

**Por que existe.** A tela baixava `GET /v1/documents` inteiro (12 mil
documentos) e filtrava no navegador. Aquela consulta não tem ORDER BY: a lista
saía na ordem física das linhas e terminava num documento de 24/09, o que fazia
a tela parecer parada. Agora a página vem do banco, já filtrada e do envio mais
recente para o mais antigo; os filtros (e o que conta como "sem justificativa")
precisam continuar os mesmos da tela.

Rodar sem o conftest, que importa main.py e exige DATABASE_URL:

    PYTHONPATH=back-end pytest back-end/tests/test_revisoes_paginadas.py -q --noconftest
"""
import asyncio
import importlib
import pathlib
import re
import sys
import types
from datetime import datetime

import pytest

from app.models.document import JUSTIFICATIVAS_VAZIAS, analise_do_payload
from app.models.user import User, UserRole


@pytest.mark.parametrize("payload, esperado", [
    ({"validation_result": {"analysis": "Todos os exames enviados"}}, "Todos os exames enviados"),
    ({"validation_result": {"analysis": "  "}, "decisao_final": "Rejeitado"}, "Rejeitado"),
    ({"analysis": "Antigo"}, "Antigo"),
    ({"validation_result": None}, None),
    (None, None),
])
def test_mensagem_da_ia_vem_de_onde_o_payload_a_pos(payload, esperado):
    assert analise_do_payload(payload) == esperado


def test_justificativas_vazias_batem_com_as_da_tela():
    """O filtro "Somente com justificativas" saiu do navegador para o banco:
    a lista do que não conta como justificativa tem de ser a mesma dos dois lados."""
    arquivo = pathlib.Path(__file__).resolve().parents[2] / "front-end" / "app" / "admin" / "validacoes" / "page.tsx"
    if not arquivo.exists():  # pragma: no cover - back-end publicado sozinho
        pytest.skip("front-end não está neste checkout")
    funcao = arquivo.read_text(encoding="utf-8").split("function normalizeReason")[1]
    bloco = funcao.split("new Set([")[1].split("])")[0]
    assert set(re.findall(r'"([^"]+)"', bloco)) == set(JUSTIFICATIVAS_VAZIAS)


class BancoFalso:
    def __init__(self):
        self.recebido = None

    def list_revisoes_paged(self, **kwargs):
        self.recebido = kwargs
        return {
            "items": [{
                "id": "d1", "filename": "a.pdf", "cpf": "05700231735", "validation_status": "validated",
                "uploaded_at": datetime(2026, 10, 19, 20, 57), "reviewed_by": None, "reviewed_at": None,
                "confidence_score": 91.0, "analysis": "ok", "approval_reason": None, "rejection_reason": None,
            }],
            "page": 2, "page_size": 20, "total_items": 21, "total_pages": 2, "has_next": False,
        }


def carregar(monkeypatch, banco):
    # Mesmo truque de test_filtro_data_envio.py: importar o router carrega
    # `app.api` inteiro, que cria cliente da OpenAI e exige a chave.
    monkeypatch.setenv("OPENAI_API_KEY", "chave-de-teste")
    import app.core.config as config
    for chave, valor in {"APP_ENV": "test", "JWT_SECRET_KEY": "x" * 40, "DEV_AUTH_BYPASS": False}.items():
        monkeypatch.setattr(config.settings, chave, valor, raising=False)
    falso = types.ModuleType("app.core.database")
    falso.user_db = banco
    monkeypatch.setitem(sys.modules, "app.core.database", falso)
    for nome in ("app.core.auth", "app.api.v1.documents"):
        sys.modules.pop(nome, None)
    return importlib.import_module("app.api.v1.documents")


def test_rota_repassa_os_filtros_e_devolve_a_pagina(monkeypatch):
    banco = BancoFalso()
    mod = carregar(monkeypatch, banco)
    admin = User(id="a", email="a@grupobrmed.com.br", name="a", role=UserRole.ADMIN, is_active=True)
    resposta = asyncio.run(mod.list_revisoes(
        current_user=admin, page=2, page_size=20, cpf="057.002", revisor="maria",
        status_filter="pending", texto="liberação", so_com_justificativa=True,
    ))
    assert banco.recebido == {
        "page": 2, "page_size": 20, "cpf": "057.002", "revisor": "maria",
        "status": "pending", "texto": "liberação", "so_com_justificativa": True,
    }
    assert resposta.total_items == 21
    assert resposta.items[0].analysis == "ok"


def test_rota_e_so_de_admin(monkeypatch):
    """A tela é ADMIN-only (`RequireRole`); a rota tem de ser também."""
    import inspect

    mod = carregar(monkeypatch, BancoFalso())
    assinatura = inspect.signature(mod.list_revisoes)
    assert assinatura.parameters["current_user"].default.dependency is sys.modules["app.core.auth"].require_admin
