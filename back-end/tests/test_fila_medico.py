"""Fila da tela do médico — `GET /v1/documents/paged?queue=medico`.

**Por que existe.** O médico só recebe o que um REVISOR aprovou na Checagem. A
IA também grava "validated" sozinha (sem `reviewed_by`), à espera do revisor:
esse documento não pode chegar ao médico, nem o rejeitado. A data da tela é a
da aprovação (`reviewed_at`), no mesmo intervalo semiaberto da data de envio.

Rodar sem o conftest, que importa main.py e exige DATABASE_URL:

    PYTHONPATH=back-end pytest back-end/tests/test_fila_medico.py -q --noconftest
"""
import asyncio
import types
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models.user import User, UserRole
from tests.test_filtro_data_envio import BancoFalso, carregar


def listar(mod, **extra):
    admin = User(id="u1", email="u1@grupobrmed.com.br", name="u1", role=UserRole.ADMIN, is_active=True)
    return asyncio.run(
        mod.list_documents_paged(
            current_user=admin, queue=mod.DocumentQueue.MEDICO, compact=True, page=1, page_size=10,
            search=None, status_filter=None, sort_by="reviewed_at", sort_dir="desc",
            filter_clinic_id=None, uploaded_from=None, uploaded_to=None,
            previsao_from=None, previsao_to=None, **extra,
        )
    )


def test_fila_e_dia_da_aprovacao_chegam_ao_banco(monkeypatch):
    """A fila vai como texto e o dia local vira instante UTC sem fuso."""
    banco = BancoFalso()
    mod = carregar(monkeypatch, banco)
    brasilia = timezone(timedelta(hours=-3))
    listar(
        mod,
        aprovado_from=datetime(2026, 11, 24, tzinfo=brasilia),
        aprovado_to=datetime(2026, 11, 25, tzinfo=brasilia),
    )
    assert banco.recebido["queue"] == "medico"
    assert banco.recebido["aprovado_from"] == datetime(2026, 11, 24, 3, 0)
    assert banco.recebido["aprovado_to"] == datetime(2026, 11, 25, 3, 0)


def test_sem_data_de_aprovacao_nao_recorta(monkeypatch):
    banco = BancoFalso()
    mod = carregar(monkeypatch, banco)
    listar(mod)
    assert banco.recebido["aprovado_from"] is None
    assert banco.recebido["aprovado_to"] is None


def test_intervalo_de_aprovacao_invertido_da_422(monkeypatch):
    banco = BancoFalso()
    mod = carregar(monkeypatch, banco)
    inicio = datetime(2026, 11, 24, 3, tzinfo=timezone.utc)
    with pytest.raises(HTTPException) as erro:
        listar(mod, aprovado_from=inicio, aprovado_to=inicio)
    assert erro.value.status_code == 422
    assert banco.recebido is None


def _doc(did, status, revisor, aprovado):
    return types.SimpleNamespace(
        id=did, clinic_id="c1", filename="a.pdf", cpf="", uploaded_by_user_email="",
        result_payload={}, validation_status=status, reviewed_by=revisor, reviewed_at=aprovado,
        uploaded_at=datetime(2026, 11, 20), updated_at=datetime(2026, 11, 20),
    )


def test_caminho_em_memoria_so_traz_aprovado_por_revisor(monkeypatch):
    mod = carregar(monkeypatch, BancoFalso())
    docs = [
        _doc("revisor_antigo", "validated", "rev@x", datetime(2026, 11, 23, 12)),
        _doc("revisor_novo", "validated", "rev@x", datetime(2026, 11, 24, 12)),
        _doc("so_ia", "validated", None, None),
        _doc("rejeitado", "rejected", "rev@x", datetime(2026, 11, 24, 13)),
        _doc("pendente", "pending", None, None),
    ]
    pagina = mod._in_memory_paged_documents(
        docs, page=1, page_size=10, queue=mod.DocumentQueue.MEDICO, status_filter=None, search=None,
        sort_by="reviewed_at", sort_dir="desc",
    )
    # Aprovação mais recente no topo.
    assert [d.id for d in pagina["items"]] == ["revisor_novo", "revisor_antigo"]


def test_caminho_em_memoria_recorta_pela_aprovacao(monkeypatch):
    """[de, até): a aprovação às 00:00 do dia seguinte fica de fora."""
    mod = carregar(monkeypatch, BancoFalso())
    docs = [
        _doc("antes", "validated", "rev@x", datetime(2026, 11, 24, 2, 59, 59)),
        _doc("dentro", "validated", "rev@x", datetime(2026, 11, 24, 3, 0)),
        _doc("depois", "validated", "rev@x", datetime(2026, 11, 25, 3, 0)),
    ]
    pagina = mod._in_memory_paged_documents(
        docs, page=1, page_size=10, queue=mod.DocumentQueue.MEDICO, status_filter=None, search=None,
        sort_by="reviewed_at", sort_dir="desc",
        aprovado_from=datetime(2026, 11, 24, 3, 0), aprovado_to=datetime(2026, 11, 25, 3, 0),
    )
    assert [d.id for d in pagina["items"]] == ["dentro"]
