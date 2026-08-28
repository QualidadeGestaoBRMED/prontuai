"""Testes da sanitização da cronometragem de revisão.

Rodar sem o conftest, que importa main.py e exige DATABASE_URL:

    PYTHONPATH=back-end pytest back-end/tests/test_review_timing.py -q --noconftest
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.document import ReviewTiming
from app.services.review_timing import (
    MAX_WALL_MS,
    TOLERANCIA_ATIVO_MS,
    sanitizar_review_timing,
)

AGORA = datetime(2026, 8, 28, 12, 0, 0)


def timing(**kwargs) -> ReviewTiming:
    base = {
        "started_at": AGORA - timedelta(minutes=5),
        "active_ms": 120_000,
        "wall_ms": 300_000,
        "open_count": 2,
    }
    base.update(kwargs)
    return ReviewTiming(**base)


def test_sem_cronometragem_devolve_none():
    assert sanitizar_review_timing(None, "doc-1", agora=AGORA) is None


def test_caminho_feliz():
    resultado = sanitizar_review_timing(timing(), "doc-1", agora=AGORA)
    assert resultado == {
        "started_at": AGORA - timedelta(minutes=5),
        "active_ms": 120_000,
        "wall_ms": 300_000,
        "open_count": 2,
    }


def test_started_at_com_fuso_vira_utc_naive():
    # O cliente manda ISO com Z; a coluna é TIMESTAMP sem fuso.
    com_fuso = datetime(2026, 8, 28, 11, 55, 0, tzinfo=timezone(timedelta(hours=-3)))
    resultado = sanitizar_review_timing(timing(started_at=com_fuso), "doc-1", agora=AGORA)
    assert resultado is not None
    assert resultado["started_at"] == datetime(2026, 8, 28, 14, 55, 0)
    assert resultado["started_at"].tzinfo is None


def test_parede_acima_do_teto_descarta_tudo():
    assert sanitizar_review_timing(
        timing(active_ms=10, wall_ms=MAX_WALL_MS + 1), "doc-1", agora=AGORA
    ) is None


def test_ativo_maior_que_parede_descarta_tudo():
    assert sanitizar_review_timing(
        timing(active_ms=300_000 + TOLERANCIA_ATIVO_MS + 1, wall_ms=300_000),
        "doc-1",
        agora=AGORA,
    ) is None


def test_ativo_dentro_da_tolerancia_e_truncado():
    resultado = sanitizar_review_timing(
        timing(active_ms=300_000 + TOLERANCIA_ATIVO_MS, wall_ms=300_000), "doc-1", agora=AGORA
    )
    assert resultado is not None
    assert resultado["active_ms"] == 300_000


@pytest.mark.parametrize("campo", ["active_ms", "wall_ms"])
def test_duracao_negativa_descarta_tudo(campo):
    assert sanitizar_review_timing(timing(**{campo: -1}), "doc-1", agora=AGORA) is None


@pytest.mark.parametrize("campo", ["active_ms", "wall_ms"])
def test_duracao_ausente_descarta_tudo(campo):
    assert sanitizar_review_timing(timing(**{campo: None}), "doc-1", agora=AGORA) is None


@pytest.mark.parametrize(
    "started_at",
    [AGORA + timedelta(hours=25), AGORA - timedelta(days=91)],
    ids=["futuro", "antigo"],
)
def test_started_at_fora_de_faixa_derruba_so_ele(started_at):
    # As durações são monotônicas e não dependem do relógio de parede, então
    # sobrevivem ao skew.
    resultado = sanitizar_review_timing(timing(started_at=started_at), "doc-1", agora=AGORA)
    assert resultado is not None
    assert resultado["started_at"] is None
    assert resultado["active_ms"] == 120_000
    assert resultado["wall_ms"] == 300_000


def test_started_at_ausente_nao_impede_a_medicao():
    resultado = sanitizar_review_timing(timing(started_at=None), "doc-1", agora=AGORA)
    assert resultado is not None
    assert resultado["started_at"] is None


@pytest.mark.parametrize(
    "recebido,esperado",
    [(None, 1), (0, 1), (-3, 1), (2, 2), (9999, 255)],
)
def test_open_count_e_limitado_ao_smallint(recebido, esperado):
    resultado = sanitizar_review_timing(timing(open_count=recebido), "doc-1", agora=AGORA)
    assert resultado is not None
    assert resultado["open_count"] == esperado


def test_revisao_instantanea_e_valida():
    # Decidir direto pela comparação, sem abrir o PDF, é revisão legítima.
    resultado = sanitizar_review_timing(
        timing(active_ms=0, wall_ms=0, open_count=1), "doc-1", agora=AGORA
    )
    assert resultado == {"started_at": AGORA - timedelta(minutes=5), "active_ms": 0, "wall_ms": 0, "open_count": 1}


# --------------------------------------------------------------------------
# Guarda de decisão no handler: a cronometragem só pode ser gravada quando o
# PATCH é uma transição de status de verdade. Sem isto, um retry de rede ou um
# duplo clique somaria a mesma revisão duas vezes.
# --------------------------------------------------------------------------
import asyncio
import sys
import types

from fastapi import BackgroundTasks

from app.models.document import DocumentUpdate
from app.models.user import User, UserRole


class FakeDocumentDB:
    """Só o suficiente para o handler rodar sem banco."""

    def __init__(self, validation_status="pending", reviewed_by=None):
        self.documento = types.SimpleNamespace(
            id="doc-1",
            validation_status=validation_status,
            reviewed_by=reviewed_by,
            result_payload={},
            clinic_id="clinic-1",
            clinic_name="Clínica Teste",
        )
        self.kwargs = None

    def get_document_by_id(self, document_id):
        return self.documento

    def get_clinic_by_id(self, clinic_id):
        return types.SimpleNamespace(name="Clínica Teste")

    def update_document(self, **kwargs):
        self.kwargs = kwargs
        return self.documento


def carregar_documents(monkeypatch, fake_db):
    fake_database_module = types.ModuleType("app.core.database")
    fake_database_module.user_db = fake_db
    monkeypatch.setitem(sys.modules, "app.core.database", fake_database_module)
    sys.modules.pop("app.api.v1.documents", None)
    import app.api.v1.documents as documents

    return documents


def patch_documento(monkeypatch, fake_db, payload: DocumentUpdate):
    documents = carregar_documents(monkeypatch, fake_db)
    usuario = User(
        id="user-1",
        email="checker@grupobrmed.com.br",
        name="Checker",
        role=UserRole.CHECKER,
        is_active=True,
        clinic_id=None,
    )
    asyncio.run(
        documents.update_document(
            document_id="doc-1",
            payload=payload,
            background_tasks=BackgroundTasks(),
            current_user=usuario,
        )
    )
    return fake_db.kwargs


TIMING_VALIDO = {
    "started_at": "2026-08-28T11:55:00Z",
    "active_ms": 120_000,
    "wall_ms": 300_000,
    "open_count": 1,
}


def test_decisao_grava_a_cronometragem(monkeypatch):
    fake_db = FakeDocumentDB(validation_status="pending")
    kwargs = patch_documento(
        monkeypatch,
        fake_db,
        DocumentUpdate(validation_status="validated", review_timing=TIMING_VALIDO),
    )
    assert kwargs["review_timing"]["active_ms"] == 120_000
    assert kwargs["review_timing"]["wall_ms"] == 300_000


def test_ia_aprovou_e_humano_confirma_grava(monkeypatch):
    # A fila da checagem inclui documentos que a IA já marcou "validated"
    # aguardando confirmação humana: o status não muda, mas é revisão de gente.
    fake_db = FakeDocumentDB(validation_status="validated", reviewed_by=None)
    kwargs = patch_documento(
        monkeypatch,
        fake_db,
        DocumentUpdate(validation_status="validated", review_timing=TIMING_VALIDO),
    )
    assert kwargs["review_timing"]["active_ms"] == 120_000


def test_ia_rejeitou_e_humano_confirma_a_rejeicao_grava(monkeypatch):
    fake_db = FakeDocumentDB(validation_status="rejected", reviewed_by=None)
    kwargs = patch_documento(
        monkeypatch,
        fake_db,
        DocumentUpdate(validation_status="rejected", review_timing=TIMING_VALIDO),
    )
    assert kwargs["review_timing"]["active_ms"] == 120_000


def test_patch_repetido_apos_a_decisao_nao_grava(monkeypatch):
    # Retry de rede / duplo clique: mesmo status E revisor já gravado.
    fake_db = FakeDocumentDB(
        validation_status="validated", reviewed_by="checker@grupobrmed.com.br"
    )
    kwargs = patch_documento(
        monkeypatch,
        fake_db,
        DocumentUpdate(validation_status="validated", review_timing=TIMING_VALIDO),
    )
    assert kwargs["review_timing"] is None


def test_segunda_revisao_que_muda_a_decisao_grava(monkeypatch):
    # Revisor volta atrás depois: é trabalho novo, soma.
    fake_db = FakeDocumentDB(
        validation_status="validated", reviewed_by="checker@grupobrmed.com.br"
    )
    kwargs = patch_documento(
        monkeypatch,
        fake_db,
        DocumentUpdate(validation_status="rejected", review_timing=TIMING_VALIDO),
    )
    assert kwargs["review_timing"]["active_ms"] == 120_000


def test_patch_sem_decisao_nao_grava(monkeypatch):
    fake_db = FakeDocumentDB(validation_status="pending")
    kwargs = patch_documento(
        monkeypatch,
        fake_db,
        DocumentUpdate(ocr_markdown="texto", review_timing=TIMING_VALIDO),
    )
    assert kwargs["review_timing"] is None


def test_cronometragem_impossivel_nao_bloqueia_a_decisao(monkeypatch):
    fake_db = FakeDocumentDB(validation_status="pending")
    kwargs = patch_documento(
        monkeypatch,
        fake_db,
        DocumentUpdate(
            validation_status="rejected",
            review_timing={**TIMING_VALIDO, "wall_ms": MAX_WALL_MS + 1},
        ),
    )
    assert kwargs["validation_status"] == "rejected"
    assert kwargs["review_timing"] is None
