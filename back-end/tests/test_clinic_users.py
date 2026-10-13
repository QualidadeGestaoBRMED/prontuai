"""
Usuários vinculados a uma clínica — `GET /v1/clinics/{id}/users`.

O que precisa de rede de segurança aqui é a **permissão**, não o formato: o
restante da tela de clínicas é `require_management`, e este endpoint é o único
dela que expõe pessoas. Se alguém "uniformizar" as dependências do arquivo, o
MANAGER passa a ver e-mail de usuário sem que nenhum teste de formato perceba.
"""
import asyncio
from datetime import datetime

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
    def __init__(self, clinica=object(), usuarios=(), atividade=None, ultimo_envio=None):
        self._clinica = clinica
        self._usuarios = list(usuarios)
        self._atividade = atividade or {}
        self._ultimo_envio = ultimo_envio
        self.chamada = None
        self.atividade_pedida = None

    def get_clinic_by_id(self, cid):
        return self._clinica

    def list_users(self, include_inactive=False, clinic_id=None):
        self.chamada = {"include_inactive": include_inactive, "clinic_id": clinic_id}
        return self._usuarios

    def get_users_activity(self, user_ids, user_emails):
        self.atividade_pedida = {"user_ids": list(user_ids), "user_emails": list(user_emails)}
        return {
            uid: self._atividade.get(
                uid, {"last_upload_at": None, "last_login_at": None}
            )
            for uid in user_ids
        }

    def get_clinic_last_upload(self, clinic_id):
        return self._ultimo_envio


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
    db = _FakeDB(
        usuarios=[_usuario("Ana")],
        atividade={
            "u-Ana": {
                "last_upload_at": datetime(2026, 10, 1, 15, 34),
                "last_login_at": datetime(2026, 10, 1, 13, 14),
            }
        },
        ultimo_envio=datetime(2026, 10, 2, 9, 0),
    )
    saida = _chamar(db, monkeypatch)
    assert saida == {
        "ultimo_envio_clinica": "2026-10-02T09:00:00",
        "usuarios": [
            {
                "id": "u-Ana",
                "email": "ana@clinica.com",
                "name": "Ana",
                "role": "SENDER",
                "is_active": True,
                "last_upload_at": "2026-10-01T15:34:00",
                "last_login_at": "2026-10-01T13:14:00",
            }
        ],
    }


def test_usuario_sem_atividade_vem_com_nulo(monkeypatch):
    """Nunca enviou / nunca logou é `null`, não ausência do campo.

    A tela distingue os dois: `null` vira "nunca", que é a resposta que o
    ADMIN está procurando quando abre a clínica.
    """
    saida = _chamar(_FakeDB(usuarios=[_usuario("Ana")]), monkeypatch)
    assert saida["ultimo_envio_clinica"] is None
    assert saida["usuarios"][0]["last_upload_at"] is None
    assert saida["usuarios"][0]["last_login_at"] is None


def test_atividade_pedida_de_uma_vez_para_a_lista_inteira(monkeypatch):
    """Uma consulta agregada para todos, nunca uma por usuário.

    Se alguém trocar isto por um laço, uma clínica com dezenas de SENDER passa
    a abrir devagar — e nenhum teste de formato perceberia.
    """
    db = _FakeDB(usuarios=[_usuario("Zuleica"), _usuario("Ana")])
    _chamar(db, monkeypatch)
    assert db.atividade_pedida == {
        # Já na ordem de exibição, para o zip com os e-mails bater.
        "user_ids": ["u-Ana", "u-Zuleica"],
        "user_emails": ["ana@clinica.com", "zuleica@clinica.com"],
    }


def test_inativos_vao_para_o_fim_e_o_resto_sai_por_nome(monkeypatch):
    db = _FakeDB(usuarios=[_usuario("Zuleica"), _usuario("Bruno", ativo=False), _usuario("Ana")])
    nomes = [u["name"] for u in _chamar(db, monkeypatch)["usuarios"]]
    assert nomes == ["Ana", "Zuleica", "Bruno"]


def test_clinica_sem_usuarios_devolve_lista_vazia(monkeypatch):
    """Vazio não é erro — a tela distingue um do outro."""
    saida = _chamar(_FakeDB(usuarios=[]), monkeypatch)
    assert saida["usuarios"] == []
