"""
Usuários vinculados a uma clínica — `GET /v1/clinics/{id}/users`.

O que precisa de rede de segurança aqui é a **permissão**, não o formato: o
restante da tela de clínicas é `require_management`, e este endpoint é o único
dela que expõe pessoas. Se alguém "uniformizar" as dependências do arquivo, o
MANAGER passa a ver e-mail de usuário sem que nenhum teste de formato perceba.
"""
import asyncio

import pytest
from fastapi import HTTPException

from app.api.v1 import clinics
from app.core.auth import require_admin, require_management
from app.models.user import User, UserRole


def _rota(caminho: str):
    for r in clinics.router.routes:
        if getattr(r, "path", None) == caminho and "GET" in getattr(r, "methods", set()):
            return r
    raise AssertionError(f"rota {caminho} não encontrada")


def _dependencias(rota):
    return {d.call for d in rota.dependant.dependencies if d.call}


# ── permissão ──────────────────────────────────────────────────────────────

def test_rota_exige_admin():
    assert require_admin in _dependencias(_rota("/clinics/{clinic_id}/users"))


def test_rota_nao_aceita_management():
    """MANAGER continua gerenciando clínicas e não enxerga as pessoas delas."""
    assert require_management not in _dependencias(_rota("/clinics/{clinic_id}/users"))


def test_listagem_de_clinicas_segue_em_management():
    """A trava nova não pode ter apertado o resto da tela por tabela."""
    assert require_management in _dependencias(_rota("/clinics"))


# ── comportamento ──────────────────────────────────────────────────────────

ADMIN = User(id="a1", email="admin@grupobrmed.com.br", name="Admin", role=UserRole.ADMIN)


class _FakeDB:
    def __init__(self, clinica=object(), usuarios=()):
        self._clinica = clinica
        self._usuarios = list(usuarios)
        self.chamada = None

    def get_clinic_by_id(self, cid):
        return self._clinica

    def list_users(self, include_inactive=False, clinic_id=None):
        self.chamada = {"include_inactive": include_inactive, "clinic_id": clinic_id}
        return self._usuarios


def _usuario(nome, ativo=True, email=None):
    return User(
        id=f"u-{nome}",
        email=email or f"{nome.lower()}@clinica.com",
        name=nome,
        role=UserRole.SENDER,
        is_active=ativo,
        clinic_id="c1",
    )


def _chamar(db, monkeypatch, clinic_id="c1"):
    monkeypatch.setattr(clinics, "user_db", db)
    return asyncio.run(clinics.list_clinic_users(clinic_id, current_user=ADMIN))


def test_clinica_inexistente_da_404(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        _chamar(_FakeDB(clinica=None), monkeypatch)
    assert exc.value.status_code == 404


def test_pede_inativos_e_recorta_pela_clinica(monkeypatch):
    """Inativo entra: numa investigação, "existe mas está desativado" é resposta."""
    db = _FakeDB(usuarios=[_usuario("Ana")])
    _chamar(db, monkeypatch, clinic_id="c-xyz")
    assert db.chamada == {"include_inactive": True, "clinic_id": "c-xyz"}


def test_campos_devolvidos(monkeypatch):
    saida = _chamar(_FakeDB(usuarios=[_usuario("Ana")]), monkeypatch)
    assert saida == [
        {
            "id": "u-Ana",
            "email": "ana@clinica.com",
            "name": "Ana",
            "role": "SENDER",
            "is_active": True,
        }
    ]


def test_inativos_vao_para_o_fim_e_o_resto_sai_por_nome(monkeypatch):
    db = _FakeDB(usuarios=[_usuario("Zuleica"), _usuario("Bruno", ativo=False), _usuario("Ana")])
    nomes = [u["name"] for u in _chamar(db, monkeypatch)]
    assert nomes == ["Ana", "Zuleica", "Bruno"]


def test_clinica_sem_usuarios_devolve_lista_vazia(monkeypatch):
    """Vazio não é erro — a tela distingue um do outro."""
    assert _chamar(_FakeDB(usuarios=[]), monkeypatch) == []
