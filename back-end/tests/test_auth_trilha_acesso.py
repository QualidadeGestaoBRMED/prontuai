"""
Trilha das recusas de acesso em requisição autenticada.

`get_current_user` e as guardas `require_*` levantavam 401/403 sem log nenhum.
A tabela até guardava o usuário (o middleware o recupera do Bearer), mas nunca
o motivo — e requisição GET sequer é auditada por padrão. Resultado: as duas
situações que derrubam um usuário inteiro, conta desativada e papel sem
permissão, não deixavam rastro. Estes testes travam o contrato de cada recusa.

Segue o padrão de test_auth_trilha_login.py: user_db falso e reload dos módulos
de auth, para não depender de Postgres. Rode com --noconftest.
"""
import importlib
import sys
import types

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.models.user import User, UserRole


class FakeUserDB:
    def __init__(self):
        self.users_by_email = {}

    def get_user_by_email(self, email):
        return self.users_by_email.get(email)

    def add_user(self, email, role=UserRole.CHECKER, is_active=True, clinic_id=None):
        user = User(
            id=f"user-{email}",
            email=email,
            name="Teste",
            role=role,
            is_active=is_active,
            clinic_id=clinic_id,
        )
        self.users_by_email[email] = user
        return user


class FakeRequest:
    def __init__(self, path="/v1/notifications"):
        self.state = types.SimpleNamespace()
        self.url = types.SimpleNamespace(path=path)

    @property
    def audit(self) -> dict:
        return getattr(self.state, "audit", None) or {}

    @property
    def metadata(self) -> dict:
        return self.audit.get("metadata", {})


def load_core_auth(monkeypatch, fake_db):
    import app.core.config as config

    monkeypatch.setattr(config.settings, "APP_ENV", "test", raising=False)
    monkeypatch.setattr(config.settings, "JWT_SECRET_KEY", "x" * 40, raising=False)
    monkeypatch.setattr(config.settings, "JWT_ISSUER", "prontuai-backend", raising=False)
    monkeypatch.setattr(config.settings, "JWT_AUDIENCE", "prontuai-frontend", raising=False)
    monkeypatch.setattr(config.settings, "JWT_EXPIRATION_HOURS", 1, raising=False)
    monkeypatch.setattr(config.settings, "JWT_MIN_SECRET_LENGTH", 32, raising=False)
    monkeypatch.setattr(config.settings, "DEV_AUTH_BYPASS", False, raising=False)

    fake_database_module = types.ModuleType("app.core.database")
    fake_database_module.user_db = fake_db
    monkeypatch.setitem(sys.modules, "app.core.database", fake_database_module)
    sys.modules.pop("app.core.auth", None)

    import app.core.auth as core_auth

    return importlib.reload(core_auth)


def _credenciais(core_auth, email, role=UserRole.CHECKER, clinic_id=None):
    dados = {"sub": email, "role": role.value, "name": "Teste"}
    if clinic_id:
        dados["clinic_id"] = clinic_id
    token = core_auth.create_access_token(data=dados)
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@pytest.mark.asyncio
async def test_usuario_inativo_deixa_rastro(monkeypatch):
    """Desativar é a revogação que mata o access token na hora — e era muda."""
    fake_db = FakeUserDB()
    core_auth = load_core_auth(monkeypatch, fake_db)
    fake_db.add_user("ana@clinica.com.br", is_active=False)
    req = FakeRequest("/v1/documents")

    with pytest.raises(HTTPException) as exc:
        await core_auth.get_current_user(req, _credenciais(core_auth, "ana@clinica.com.br"))

    assert exc.value.status_code == 403
    assert req.audit["action"] == "auth.access.denied"
    assert req.audit["user_email"] == "ana@clinica.com.br"
    assert req.metadata["motivo"] == "usuario_inativo"
    assert req.metadata["rota"] == "/v1/documents"


@pytest.mark.asyncio
async def test_usuario_removido_do_banco_deixa_rastro(monkeypatch):
    fake_db = FakeUserDB()
    core_auth = load_core_auth(monkeypatch, fake_db)
    req = FakeRequest()

    with pytest.raises(HTTPException) as exc:
        await core_auth.get_current_user(req, _credenciais(core_auth, "fantasma@x.com"))

    assert exc.value.status_code == 401
    assert req.metadata["motivo"] == "usuario_inexistente"
    assert req.audit["user_email"] == "fantasma@x.com"


@pytest.mark.asyncio
async def test_permissao_negada_registra_papel_e_exigencia(monkeypatch):
    fake_db = FakeUserDB()
    core_auth = load_core_auth(monkeypatch, fake_db)
    sender = fake_db.add_user("envio@clinica.com.br", role=UserRole.SENDER)
    req = FakeRequest("/v1/users")

    with pytest.raises(HTTPException) as exc:
        await core_auth.require_admin(req, sender)

    assert exc.value.status_code == 403
    assert req.audit["action"] == "auth.access.denied"
    assert req.audit["user_email"] == "envio@clinica.com.br"
    assert req.metadata["motivo"] == "papel_sem_permissao"
    assert req.metadata["papel"] == "SENDER"
    assert req.metadata["papeis_exigidos"] == ["ADMIN"]
    assert req.metadata["rota"] == "/v1/users"


@pytest.mark.asyncio
async def test_acesso_permitido_nao_polui_a_trilha(monkeypatch):
    fake_db = FakeUserDB()
    core_auth = load_core_auth(monkeypatch, fake_db)
    admin = fake_db.add_user("adm@grupobrmed.com.br", role=UserRole.ADMIN)
    req = FakeRequest()

    assert await core_auth.require_admin(req, admin) is admin
    assert req.audit == {}


@pytest.mark.asyncio
async def test_usuario_ativo_passa_sem_registrar_recusa(monkeypatch):
    fake_db = FakeUserDB()
    core_auth = load_core_auth(monkeypatch, fake_db)
    fake_db.add_user("ana@clinica.com.br")
    req = FakeRequest()

    user = await core_auth.get_current_user(req, _credenciais(core_auth, "ana@clinica.com.br"))

    assert user.email == "ana@clinica.com.br"
    assert req.audit == {}


def test_token_vencido_revela_de_quem_era(monkeypatch):
    """As milhares de linhas de expiração por dia não identificavam ninguém."""
    fake_db = FakeUserDB()
    core_auth = load_core_auth(monkeypatch, fake_db)
    token = core_auth.create_access_token(data={"sub": "ana@clinica.com.br", "role": "CHECKER"})

    assert core_auth._sujeito_nao_verificado(token) == "ana@clinica.com.br"
    # Token corrompido não derruba o caminho de erro.
    assert core_auth._sujeito_nao_verificado("nao-e-um-jwt") is None
