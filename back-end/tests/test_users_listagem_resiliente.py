"""Uma linha inconsistente não pode derrubar a listagem de usuários.

O staging tinha `GET /v1/users` em 500 por causa de um registro só. A tela de
administração ficava vazia e, como é ela que confirma a criação, parecia que
criar usuário estava quebrado — o POST respondia 201 o tempo todo.

Rodar sem o conftest, que importa main.py e exige DATABASE_URL:

    PYTHONPATH=back-end pytest back-end/tests/test_users_listagem_resiliente.py -q --noconftest
"""
from types import SimpleNamespace

import pytest

from app.core.database_postgres import PostgresUserDatabase
from app.models.user import User


def linha(id, email="ok@grupobrmed.com.br", name="Alguém", role="CHECKER",
          created_at=SimpleNamespace(isoformat=lambda: "2026-01-01T00:00:00"), **kw):
    return SimpleNamespace(
        id=id, email=email, name=name, role=role, is_active=True, clinic_id=None,
        created_at=created_at, updated_at=created_at, **kw
    )


class _Query:
    def __init__(self, linhas): self._linhas = linhas
    def filter(self, *a, **k): return self
    def all(self): return self._linhas


def _db_com(linhas, monkeypatch):
    db = PostgresUserDatabase.__new__(PostgresUserDatabase)
    sessao = SimpleNamespace(query=lambda *a, **k: _Query(linhas), close=lambda: None)
    monkeypatch.setattr(PostgresUserDatabase, "_get_session", lambda self: sessao)
    return db


def test_role_desconhecido_nao_derruba_a_lista(monkeypatch, caplog):
    """O enum do Postgres nasceu do create_all e nunca foi migrado."""
    db = _db_com([
        linha("bom-1"),
        linha("ruim", role="PAPEL_QUE_NAO_EXISTE"),
        linha("bom-2", email="outro@grupobrmed.com.br"),
    ], monkeypatch)
    usuarios = db.list_users()
    assert [u.id for u in usuarios] == ["bom-1", "bom-2"]
    assert "ruim" in caplog.text


def test_timestamp_nulo_nao_derruba_a_lista(monkeypatch):
    db = _db_com([linha("sem-data", created_at=None), linha("bom")], monkeypatch)
    usuarios = db.list_users()
    assert {u.id for u in usuarios} == {"sem-data", "bom"}
    assert next(u for u in usuarios if u.id == "sem-data").created_at is None


def test_email_invalido_sai_da_lista_e_vai_para_o_log(monkeypatch, caplog):
    db = _db_com([linha("bom"), linha("sem-arroba", email="nao-e-email")], monkeypatch)
    assert [u.id for u in db.list_users()] == ["bom"]
    assert "sem-arroba" in caplog.text
    # o log não pode vazar PII: só id e motivo
    assert "nao-e-email" not in caplog.text


def test_lista_boa_continua_intacta(monkeypatch):
    db = _db_com([linha("a"), linha("b", email="b@grupobrmed.com.br")], monkeypatch)
    usuarios = db.list_users()
    assert len(usuarios) == 2 and all(isinstance(u, User) for u in usuarios)
