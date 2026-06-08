import asyncio
import importlib
import sys
import types

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.models.user import User, UserRole


class FakeUserDB:
    def __init__(self, users_by_email=None):
        self.users_by_email = users_by_email or {}
        self.created_user = None

    def get_user_by_email(self, email: str):
        return self.users_by_email.get(email)

    def get_all_clinics(self):
        return []

    def create_clinic(self, name: str):
        return types.SimpleNamespace(id="clinic-dev")

    def create_user(self, email: str, name: str, role: UserRole, clinic_id=None):
        self.created_user = User(
            id="user-dev",
            email=email,
            name=name,
            role=role,
            is_active=True,
            clinic_id=clinic_id,
        )
        self.users_by_email[email] = self.created_user
        return self.created_user


def load_auth_module(monkeypatch: pytest.MonkeyPatch, fake_db: FakeUserDB):
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

    import app.core.auth as auth

    return importlib.reload(auth)


def test_create_and_decode_access_token_round_trip(monkeypatch: pytest.MonkeyPatch):
    auth = load_auth_module(monkeypatch, FakeUserDB())

    token = auth.create_access_token(
        {
            "sub": "admin@grupobrmed.com.br",
            "role": "ADMIN",
            "name": "Admin",
            "clinic_id": None,
        }
    )

    decoded = auth.decode_token(token)

    assert decoded.email == "admin@grupobrmed.com.br"
    assert decoded.role == UserRole.ADMIN
    assert decoded.name == "Admin"
    assert decoded.clinic_id is None


def test_decode_token_rejects_upload_scope_on_regular_routes(monkeypatch: pytest.MonkeyPatch):
    auth = load_auth_module(monkeypatch, FakeUserDB())
    user = User(
        id="sender-1",
        email="sender@grupobrmed.com.br",
        name="Sender",
        role=UserRole.SENDER,
        clinic_id="clinic-1",
    )

    token = auth.create_upload_token(user)

    with pytest.raises(HTTPException) as exc_info:
        auth.decode_token(token)

    assert exc_info.value.status_code == 401
    assert "upload" in exc_info.value.detail.lower()


def test_assert_auth_security_configuration_rejects_weak_secret_in_production(
    monkeypatch: pytest.MonkeyPatch,
):
    auth = load_auth_module(monkeypatch, FakeUserDB())

    monkeypatch.setattr(auth.settings, "APP_ENV", "production", raising=False)
    monkeypatch.setattr(auth.settings, "JWT_SECRET_KEY", "short", raising=False)
    monkeypatch.setattr(auth.settings, "DEV_AUTH_BYPASS", False, raising=False)

    with pytest.raises(RuntimeError) as exc_info:
        auth.assert_auth_security_configuration()

    assert "JWT_SECRET_KEY insegura" in str(exc_info.value)


def test_assert_auth_security_configuration_rejects_dev_bypass_in_production(
    monkeypatch: pytest.MonkeyPatch,
):
    auth = load_auth_module(monkeypatch, FakeUserDB())

    monkeypatch.setattr(auth.settings, "APP_ENV", "production", raising=False)
    monkeypatch.setattr(auth.settings, "JWT_SECRET_KEY", "x" * 40, raising=False)
    monkeypatch.setattr(auth.settings, "DEV_AUTH_BYPASS", True, raising=False)

    with pytest.raises(RuntimeError) as exc_info:
        auth.assert_auth_security_configuration()

    assert "DEV_AUTH_BYPASS" in str(exc_info.value)


def test_get_current_user_supports_dev_bypass_only_in_non_production(
    monkeypatch: pytest.MonkeyPatch,
):
    fake_db = FakeUserDB()
    auth = load_auth_module(monkeypatch, fake_db)

    monkeypatch.setattr(auth.settings, "DEV_AUTH_BYPASS", True, raising=False)
    monkeypatch.setenv("DEV_AUTH_EMAIL", "dev@grupobrmed.com.br")
    monkeypatch.setenv("DEV_AUTH_NAME", "Dev User")
    monkeypatch.setenv("DEV_AUTH_ROLE", "ADMIN")

    user = asyncio.run(auth.get_current_user(credentials=None))

    assert user.email == "dev@grupobrmed.com.br"
    assert user.role == UserRole.ADMIN
    assert fake_db.created_user is not None


def test_require_admin_rejects_non_admin(monkeypatch: pytest.MonkeyPatch):
    auth = load_auth_module(monkeypatch, FakeUserDB())
    checker = User(
        id="checker-1",
        email="checker@grupobrmed.com.br",
        name="Checker",
        role=UserRole.CHECKER,
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(auth.require_admin(checker))

    assert exc_info.value.status_code == 403
    assert "administradores" in exc_info.value.detail.lower()


def test_upload_endpoint_rejects_regular_access_token(monkeypatch: pytest.MonkeyPatch):
    sender = User(
        id="sender-1",
        email="sender@grupobrmed.com.br",
        name="Sender",
        role=UserRole.SENDER,
        clinic_id="clinic-1",
    )
    auth = load_auth_module(monkeypatch, FakeUserDB({sender.email: sender}))
    token = auth.create_access_token(
        {
            "sub": sender.email,
            "role": sender.role.value,
            "name": sender.name,
            "clinic_id": sender.clinic_id,
        }
    )

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(auth.get_current_upload_user(credentials=credentials))

    assert exc_info.value.status_code == 401
    assert "upload direto" in exc_info.value.detail.lower()


def test_upload_endpoint_accepts_scoped_upload_token(monkeypatch: pytest.MonkeyPatch):
    sender = User(
        id="sender-1",
        email="sender@grupobrmed.com.br",
        name="Sender",
        role=UserRole.SENDER,
        clinic_id="clinic-1",
    )
    auth = load_auth_module(monkeypatch, FakeUserDB({sender.email: sender}))
    token = auth.create_upload_token(sender)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    user = asyncio.run(auth.get_current_upload_user(credentials=credentials))

    assert user.email == sender.email
    assert user.role == UserRole.SENDER


def test_require_checker_rejects_sender_for_validation_updates(monkeypatch: pytest.MonkeyPatch):
    auth = load_auth_module(monkeypatch, FakeUserDB())
    sender = User(
        id="sender-1",
        email="sender@grupobrmed.com.br",
        name="Sender",
        role=UserRole.SENDER,
        clinic_id="clinic-1",
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(auth.require_checker(sender))

    assert exc_info.value.status_code == 403
    assert "checadores" in exc_info.value.detail.lower()
