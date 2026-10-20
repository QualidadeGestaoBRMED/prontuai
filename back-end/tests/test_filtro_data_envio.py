"""Filtro por data de envio da Checagem — `GET /v1/documents/paged`.

**Por que existe.** A tela manda o dia escolhido pelo revisor já convertido em
instante, com o fuso do browser (`2026-10-15T03:00:00.000Z` é a meia-noite de
15/10 em Brasília), e o banco guarda `uploaded_at` em UTC sem fuso. Se a
conversão se perder, o recorte desliza três horas: o que foi enviado às 22h do
dia 14 aparece no dia 15, e a contagem dos cards deixa de bater com a lista.

Rodar sem o conftest, que importa main.py e exige DATABASE_URL:

    PYTHONPATH=back-end pytest back-end/tests/test_filtro_data_envio.py -q --noconftest
"""
import asyncio
import importlib
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models.user import User, UserRole


class BancoFalso:
    """Guarda o que o handler repassou e devolve uma página vazia."""

    def __init__(self):
        self.recebido = None

    def list_documents_paged(self, **kwargs):
        self.recebido = kwargs
        return {"items": [], "page": 1, "page_size": 10, "total_items": 0,
                "total_pages": 1, "has_next": False, "summary_counts": {}}


def carregar(monkeypatch, banco):
    # Mesmo truque de test_document_feedback.py: importar o router carrega
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


def listar(mod, uploaded_from=None, uploaded_to=None):
    checador = User(id="u1", email="u1@grupobrmed.com.br", name="u1",
                    role=UserRole.CHECKER, is_active=True)
    return asyncio.run(
        mod.list_documents_paged(
            current_user=checador, queue=None, compact=True, page=1, page_size=10,
            search=None, status_filter=None, sort_by="uploaded_at", sort_dir="desc",
            filter_clinic_id=None, uploaded_from=uploaded_from, uploaded_to=uploaded_to,
            previsao_from=None, previsao_to=None,
        )
    )


def test_dia_local_chega_ao_banco_em_utc_sem_fuso(monkeypatch):
    """Meia-noite de Brasília vira 03:00 UTC, no formato de `uploaded_at`."""
    banco = BancoFalso()
    mod = carregar(monkeypatch, banco)
    brasilia = timezone(timedelta(hours=-3))
    listar(
        mod,
        uploaded_from=datetime(2026, 10, 15, tzinfo=brasilia),
        uploaded_to=datetime(2026, 10, 16, tzinfo=brasilia),
    )
    assert banco.recebido["uploaded_from"] == datetime(2026, 10, 15, 3, 0)
    assert banco.recebido["uploaded_to"] == datetime(2026, 10, 16, 3, 0)
    assert banco.recebido["uploaded_from"].tzinfo is None


def test_sem_filtro_nao_recorta(monkeypatch):
    banco = BancoFalso()
    mod = carregar(monkeypatch, banco)
    listar(mod)
    assert banco.recebido["uploaded_from"] is None
    assert banco.recebido["uploaded_to"] is None


@pytest.mark.parametrize("fim_dias", [0, -1])
def test_intervalo_vazio_ou_invertido_da_422(monkeypatch, fim_dias):
    """Melhor recusar que devolver lista vazia sem dizer por quê."""
    banco = BancoFalso()
    mod = carregar(monkeypatch, banco)
    inicio = datetime(2026, 10, 15, 3, tzinfo=timezone.utc)
    with pytest.raises(HTTPException) as erro:
        listar(mod, uploaded_from=inicio, uploaded_to=inicio + timedelta(days=fim_dias))
    assert erro.value.status_code == 422
    assert banco.recebido is None


def test_caminho_em_memoria_usa_intervalo_semiaberto(monkeypatch):
    """[de, até): o instante final é o começo do dia seguinte e fica de fora."""
    mod = carregar(monkeypatch, BancoFalso())

    def doc(did, enviado):
        return types.SimpleNamespace(
            id=did, clinic_id="c1", filename="a.pdf", cpf="", uploaded_by_user_email="",
            result_payload={}, validation_status="pending", reviewed_by=None,
            uploaded_at=enviado, updated_at=enviado,
        )

    docs = [
        doc("antes", datetime(2026, 10, 15, 2, 59, 59)),      # 23:59:59 do dia 14 em Brasília
        doc("inicio", datetime(2026, 10, 15, 3, 0)),           # 00:00 do dia 15
        doc("fim_do_dia", datetime(2026, 10, 16, 2, 59, 59)),  # 23:59:59 do dia 15
        doc("depois", datetime(2026, 10, 16, 3, 0)),           # 00:00 do dia 16
        # Gravado com fuso: o caminho em memória também aceita.
        doc("com_fuso", datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)),
    ]
    pagina = mod._in_memory_paged_documents(
        docs, page=1, page_size=10, queue=None, status_filter=None, search=None,
        sort_by="uploaded_at", sort_dir="asc",
        uploaded_from=datetime(2026, 10, 15, 3, 0), uploaded_to=datetime(2026, 10, 16, 3, 0),
    )
    assert {d.id for d in pagina["items"]} == {"inicio", "fim_do_dia", "com_fuso"}
    # Os cards de contagem saem do mesmo recorte.
    assert pagina["summary_counts"]["total"] == 3
