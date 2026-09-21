"""
Testes da rotação de uso único de refresh tokens e detecção de reuso.

Usa o mesmo padrão de test_auth_security.py: injeta um user_db falso e
recarrega os módulos de auth para não depender de Postgres.
"""
import importlib
import sys
import types
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

from app.models.user import User, UserRole


class FakeRefreshDB:
    """user_db falso com o contrato de sessões de refresh em memória."""

    def __init__(self):
        self.users_by_email = {}
        self.sessions = {}

    # --- usuários ---
    def get_user_by_email(self, email):
        return self.users_by_email.get(email)

    def add_user(self, email, role=UserRole.ADMIN, is_active=True):
        user = User(
            id=f"user-{email}",
            email=email,
            name="Teste",
            role=role,
            is_active=is_active,
            clinic_id=None,
        )
        self.users_by_email[email] = user
        return user

    # --- sessões de refresh ---
    def create_refresh_session(self, jti_hash, user_email, family_id, expires_at):
        self.sessions[jti_hash] = {
            "jti_hash": jti_hash,
            "user_email": user_email,
            "family_id": family_id,
            "expires_at": expires_at,
            "created_at": datetime.utcnow(),
            "revoked_at": None,
            "replaced_by_jti_hash": None,
        }

    def get_refresh_session(self, jti_hash):
        row = self.sessions.get(jti_hash)
        return dict(row) if row else None

    def rotate_refresh_session(self, old_jti_hash, new_jti_hash, user_email, family_id, expires_at):
        row = self.sessions.get(old_jti_hash)
        if row is None or row["revoked_at"] is not None:
            return False
        row["revoked_at"] = datetime.utcnow()
        row["replaced_by_jti_hash"] = new_jti_hash
        self.create_refresh_session(new_jti_hash, user_email, family_id, expires_at)
        return True

    def revoke_refresh_family(self, family_id):
        revoked = 0
        for row in self.sessions.values():
            if row["family_id"] == family_id and row["revoked_at"] is None:
                row["revoked_at"] = datetime.utcnow()
                revoked += 1
        return revoked

    def purge_expired_refresh_sessions(self):
        expired = [k for k, row in self.sessions.items() if row["expires_at"] < datetime.utcnow()]
        for key in expired:
            del self.sessions[key]
        return len(expired)


def load_modules(monkeypatch: pytest.MonkeyPatch, fake_db: FakeRefreshDB):
    import app.core.config as config

    monkeypatch.setattr(config.settings, "APP_ENV", "test", raising=False)
    monkeypatch.setattr(config.settings, "JWT_SECRET_KEY", "x" * 40, raising=False)
    monkeypatch.setattr(config.settings, "JWT_ISSUER", "prontuai-backend", raising=False)
    monkeypatch.setattr(config.settings, "JWT_AUDIENCE", "prontuai-frontend", raising=False)
    monkeypatch.setattr(config.settings, "JWT_EXPIRATION_HOURS", 2, raising=False)
    monkeypatch.setattr(config.settings, "JWT_MIN_SECRET_LENGTH", 32, raising=False)
    monkeypatch.setattr(config.settings, "DEV_AUTH_BYPASS", False, raising=False)

    fake_database_module = types.ModuleType("app.core.database")
    fake_database_module.user_db = fake_db
    monkeypatch.setitem(sys.modules, "app.core.database", fake_database_module)
    sys.modules.pop("app.core.auth", None)
    sys.modules.pop("app.api.v1.auth", None)

    import app.core.auth as core_auth

    core_auth = importlib.reload(core_auth)

    import app.api.v1.auth as api_auth

    api_auth = importlib.reload(api_auth)
    return core_auth, api_auth


def _login(core_auth, fake_db, email="user@test.com"):
    """Simula o pós-login: emite refresh token e registra a sessão."""
    user = fake_db.get_user_by_email(email) or fake_db.add_user(email)
    token_data = {"sub": user.email, "role": user.role.value, "name": user.name}
    token, jti, family_id, expires_at = core_auth.create_refresh_token(data=token_data)
    fake_db.create_refresh_session(
        jti_hash=core_auth.hash_refresh_jti(jti),
        user_email=user.email,
        family_id=family_id,
        expires_at=expires_at,
    )
    return token, family_id


class FakeRequest:
    """Request mínimo: os handlers de auth só escrevem a trilha em `.state`."""

    def __init__(self):
        self.state = types.SimpleNamespace()

    @property
    def audit(self) -> dict:
        return getattr(self.state, "audit", None) or {}

    @property
    def motivo(self):
        return self.audit.get("metadata", {}).get("motivo")


async def _refresh(api_auth, token, request=None):
    return await api_auth.refresh_token(
        api_auth.RefreshRequest(refresh_token=token), request or FakeRequest()
    )


@pytest.mark.asyncio
async def test_refresh_rotates_token(monkeypatch):
    fake_db = FakeRefreshDB()
    core_auth, api_auth = load_modules(monkeypatch, fake_db)
    token, family_id = _login(core_auth, fake_db)

    sucesso_req = FakeRequest()
    response = await _refresh(api_auth, token, sucesso_req)

    assert sucesso_req.audit["action"] == "auth.refresh.success"
    assert sucesso_req.audit["user_email"] == "user@test.com"
    assert sucesso_req.audit["user_role"] == "ADMIN"
    assert response.access_token
    assert response.refresh_token
    assert response.refresh_token != token
    # Sessão antiga revogada, nova ativa na mesma família
    active = [r for r in fake_db.sessions.values() if r["revoked_at"] is None]
    assert len(active) == 1
    assert active[0]["family_id"] == family_id


@pytest.mark.asyncio
async def test_refresh_reuse_revokes_family(monkeypatch):
    fake_db = FakeRefreshDB()
    core_auth, api_auth = load_modules(monkeypatch, fake_db)
    monkeypatch.setattr(api_auth, "REFRESH_REUSE_GRACE_SECONDS", 0)
    token, family_id = _login(core_auth, fake_db)

    first = await _refresh(api_auth, token)

    # Reuso do token antigo (fora da janela de graça) deve falhar...
    reuse_req = FakeRequest()
    with pytest.raises(HTTPException) as excinfo:
        await _refresh(api_auth, token, reuse_req)
    assert excinfo.value.status_code == 401
    # ...e deixar na trilha o evento mais grave da rota, com de quem era.
    assert reuse_req.audit["action"] == "auth.refresh.reuse_detected"
    assert reuse_req.audit["user_email"] == "user@test.com"
    assert reuse_req.audit["metadata"]["family_id"] == family_id

    # ...e revogar a família inteira, incluindo o token novo.
    with pytest.raises(HTTPException):
        await _refresh(api_auth, first.refresh_token)
    active = [r for r in fake_db.sessions.values() if r["revoked_at"] is None]
    assert active == []


@pytest.mark.asyncio
async def test_refresh_reuse_within_grace_does_not_revoke_family(monkeypatch):
    fake_db = FakeRefreshDB()
    core_auth, api_auth = load_modules(monkeypatch, fake_db)
    monkeypatch.setattr(api_auth, "REFRESH_REUSE_GRACE_SECONDS", 60)
    token, _ = _login(core_auth, fake_db)

    first = await _refresh(api_auth, token)

    # Corrida benigna (duas abas): reuso logo após a rotação nega a
    # requisição mas mantém a família viva.
    grace_req = FakeRequest()
    with pytest.raises(HTTPException) as excinfo:
        await _refresh(api_auth, token, grace_req)
    assert excinfo.value.status_code == 401
    # Corrida não é roubo: a trilha precisa distinguir os dois.
    assert grace_req.audit["action"] == "auth.refresh.denied"
    assert grace_req.motivo == "reuso_em_corrida"

    second = await _refresh(api_auth, first.refresh_token)
    assert second.refresh_token


@pytest.mark.asyncio
async def test_refresh_without_session_row_rejected(monkeypatch):
    fake_db = FakeRefreshDB()
    core_auth, api_auth = load_modules(monkeypatch, fake_db)
    fake_db.add_user("user@test.com")
    token_data = {"sub": "user@test.com", "role": "ADMIN", "name": "Teste"}
    # Token assinado corretamente mas sem sessão persistida (pré-rotação)
    token, _, _, _ = core_auth.create_refresh_token(data=token_data)

    expirada_req = FakeRequest()
    with pytest.raises(HTTPException) as excinfo:
        await _refresh(api_auth, token, expirada_req)
    assert excinfo.value.status_code == 401
    assert expirada_req.motivo == "sessao_expirada"
    assert expirada_req.audit["user_email"] == "user@test.com"


@pytest.mark.asyncio
async def test_refresh_inactive_user_rejected(monkeypatch):
    fake_db = FakeRefreshDB()
    core_auth, api_auth = load_modules(monkeypatch, fake_db)
    fake_db.add_user("user@test.com", is_active=False)
    token, _ = _login(core_auth, fake_db, "user@test.com")

    inativo_req = FakeRequest()
    with pytest.raises(HTTPException) as excinfo:
        await _refresh(api_auth, token, inativo_req)
    assert excinfo.value.status_code == 401
    assert inativo_req.motivo == "usuario_inativo"


@pytest.mark.asyncio
async def test_logout_revokes_family(monkeypatch):
    fake_db = FakeRefreshDB()
    core_auth, api_auth = load_modules(monkeypatch, fake_db)
    token, _ = _login(core_auth, fake_db)

    logout_req = FakeRequest()
    result = await api_auth.logout(api_auth.RefreshRequest(refresh_token=token), logout_req)
    assert result == {"success": True}
    assert logout_req.audit["action"] == "auth.logout.success"
    assert logout_req.audit["user_email"] == "user@test.com"
    assert logout_req.audit["metadata"]["sessoes_revogadas"] == 1

    with pytest.raises(HTTPException):
        await _refresh(api_auth, token)


def test_purge_expired_sessions():
    fake_db = FakeRefreshDB()
    fake_db.create_refresh_session("h1", "a@t.com", "f1", datetime.utcnow() - timedelta(days=1))
    fake_db.create_refresh_session("h2", "a@t.com", "f1", datetime.utcnow() + timedelta(days=1))
    assert fake_db.purge_expired_refresh_sessions() == 1
    assert "h2" in fake_db.sessions
