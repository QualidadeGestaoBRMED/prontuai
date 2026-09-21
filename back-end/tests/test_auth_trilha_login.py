"""
Trilha de auditoria das tentativas de login.

Antes, toda tentativa caía na tabela como `post:/v1/auth/google` com
`user_email` nulo: dava para contar recusas, nunca para saber de quem eram, e
os dois 403 (não cadastrado / inativo) eram indistinguíveis. Estes testes
travam o contrato de cada desfecho — a `action`, o email e o motivo.

Segue o padrão de test_refresh_rotation.py: user_db falso e reload dos módulos
de auth, para não depender de Postgres. Rode com --noconftest.
"""
import importlib
import sys
import types

import pytest
from fastapi import HTTPException

from app.models.user import User, UserRole


class FakeUserDB:
    def __init__(self):
        self.users_by_email = {}
        self.sessions = {}

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

    def create_refresh_session(self, jti_hash, user_email, family_id, expires_at):
        self.sessions[jti_hash] = {"user_email": user_email, "family_id": family_id}


class FakeRequest:
    def __init__(self):
        self.state = types.SimpleNamespace()

    @property
    def audit(self) -> dict:
        return getattr(self.state, "audit", None) or {}

    @property
    def motivo(self):
        return self.audit.get("metadata", {}).get("motivo")


def load_api_auth(monkeypatch, fake_db, google_client_id="client-id.apps.googleusercontent.com"):
    import app.core.config as config

    monkeypatch.setattr(config.settings, "APP_ENV", "test", raising=False)
    monkeypatch.setattr(config.settings, "JWT_SECRET_KEY", "x" * 40, raising=False)
    monkeypatch.setattr(config.settings, "JWT_ISSUER", "prontuai-backend", raising=False)
    monkeypatch.setattr(config.settings, "JWT_AUDIENCE", "prontuai-frontend", raising=False)
    monkeypatch.setattr(config.settings, "JWT_EXPIRATION_HOURS", 1, raising=False)
    monkeypatch.setattr(config.settings, "JWT_MIN_SECRET_LENGTH", 32, raising=False)
    monkeypatch.setattr(config.settings, "DEV_AUTH_BYPASS", False, raising=False)
    monkeypatch.setattr(config.settings, "GOOGLE_CLIENT_ID", google_client_id, raising=False)

    fake_database_module = types.ModuleType("app.core.database")
    fake_database_module.user_db = fake_db
    monkeypatch.setitem(sys.modules, "app.core.database", fake_database_module)
    sys.modules.pop("app.core.auth", None)
    sys.modules.pop("app.api.v1.auth", None)

    import app.core.auth as core_auth

    importlib.reload(core_auth)
    import app.api.v1.auth as api_auth

    return importlib.reload(api_auth)


def _google_ok(api_auth, monkeypatch, email, email_verified=True, sub="google-sub-1"):
    """Faz a validação do id_token devolver estas claims."""
    monkeypatch.setattr(
        api_auth.google_id_token,
        "verify_oauth2_token",
        lambda *a, **k: {"email": email, "email_verified": email_verified, "sub": sub},
    )


async def _login(api_auth, request, id_token="tok", email=None):
    return await api_auth.google_auth(
        api_auth.GoogleAuthRequest(id_token=id_token, email=email), request
    )


@pytest.mark.asyncio
async def test_login_bem_sucedido_registra_quem_entrou(monkeypatch):
    fake_db = FakeUserDB()
    api_auth = load_api_auth(monkeypatch, fake_db)
    fake_db.add_user("ana@grupobrmed.com.br", role=UserRole.CHECKER, clinic_id=None)
    _google_ok(api_auth, monkeypatch, "ana@grupobrmed.com.br")

    req = FakeRequest()
    resposta = await _login(api_auth, req)

    assert resposta.access_token
    assert req.audit["action"] == "auth.login.success"
    assert req.audit["user_email"] == "ana@grupobrmed.com.br"
    assert req.audit["user_role"] == "CHECKER"
    assert req.audit["metadata"]["expira_em_horas"] == 1


@pytest.mark.asyncio
async def test_login_de_quem_nao_esta_cadastrado(monkeypatch):
    fake_db = FakeUserDB()
    api_auth = load_api_auth(monkeypatch, fake_db)
    _google_ok(api_auth, monkeypatch, "estranho@outra.com")

    req = FakeRequest()
    with pytest.raises(HTTPException) as exc:
        await _login(api_auth, req)

    assert exc.value.status_code == 403
    assert req.audit["action"] == "auth.login.denied"
    assert req.motivo == "usuario_nao_cadastrado"
    # O email veio do id_token validado pelo Google, então vale como verdade.
    assert req.audit["user_email"] == "estranho@outra.com"
    assert "email_verificado" not in req.audit["metadata"]


@pytest.mark.asyncio
async def test_login_de_usuario_inativo_e_distinguivel_do_nao_cadastrado(monkeypatch):
    fake_db = FakeUserDB()
    api_auth = load_api_auth(monkeypatch, fake_db)
    fake_db.add_user("saiu@grupobrmed.com.br", role=UserRole.SENDER, is_active=False)
    _google_ok(api_auth, monkeypatch, "saiu@grupobrmed.com.br")

    req = FakeRequest()
    with pytest.raises(HTTPException) as exc:
        await _login(api_auth, req)

    assert exc.value.status_code == 403
    # Mesmo status HTTP do teste acima; o motivo é o que separa os dois.
    assert req.motivo == "usuario_inativo"
    assert req.audit["user_email"] == "saiu@grupobrmed.com.br"
    assert req.audit["user_role"] == "SENDER"


@pytest.mark.asyncio
async def test_id_token_invalido_marca_email_como_nao_verificado(monkeypatch):
    fake_db = FakeUserDB()
    api_auth = load_api_auth(monkeypatch, fake_db)

    def explode(*a, **k):
        raise ValueError("assinatura inválida")

    monkeypatch.setattr(api_auth.google_id_token, "verify_oauth2_token", explode)

    req = FakeRequest()
    with pytest.raises(HTTPException) as exc:
        await _login(api_auth, req, email="falsario@outra.com")

    assert exc.value.status_code == 401
    assert req.motivo == "google_token_invalido"
    # Ninguém confirmou esse endereço: ele entra na trilha marcado.
    assert req.audit["user_email"] == "falsario@outra.com"
    assert req.audit["metadata"]["email_verificado"] is False
    assert req.audit["metadata"]["erro"] == "ValueError"


@pytest.mark.asyncio
async def test_email_nao_confirmado_pelo_google_e_recusado(monkeypatch):
    fake_db = FakeUserDB()
    api_auth = load_api_auth(monkeypatch, fake_db)
    fake_db.add_user("ana@grupobrmed.com.br")
    _google_ok(api_auth, monkeypatch, "ana@grupobrmed.com.br", email_verified=False)

    req = FakeRequest()
    with pytest.raises(HTTPException) as exc:
        await _login(api_auth, req)

    assert exc.value.status_code == 401
    assert req.motivo == "google_claims_incompletas"
    assert req.audit["metadata"]["email_confirmado_pelo_google"] is False


@pytest.mark.asyncio
async def test_divergencia_entre_email_do_cliente_e_do_token_fica_registrada(monkeypatch):
    fake_db = FakeUserDB()
    api_auth = load_api_auth(monkeypatch, fake_db)
    fake_db.add_user("ana@grupobrmed.com.br")
    _google_ok(api_auth, monkeypatch, "ana@grupobrmed.com.br")

    req = FakeRequest()
    # Cliente afirma um email, o id_token prova outro: o login segue pelo do
    # token, mas a divergência é sinal de sondagem e precisa aparecer.
    await _login(api_auth, req, email="outro@grupobrmed.com.br")

    assert req.audit["action"] == "auth.login.success"
    assert req.audit["user_email"] == "ana@grupobrmed.com.br"
    assert req.audit["metadata"]["divergencia_de_email"] is True


@pytest.mark.asyncio
async def test_google_client_id_ausente_e_erro_de_servidor_nao_recusa_de_acesso(monkeypatch):
    fake_db = FakeUserDB()
    api_auth = load_api_auth(monkeypatch, fake_db, google_client_id=None)

    req = FakeRequest()
    with pytest.raises(HTTPException) as exc:
        await _login(api_auth, req, email="ana@grupobrmed.com.br")

    assert exc.value.status_code == 500
    assert req.audit["action"] == "auth.login.error"
    assert req.motivo == "google_client_id_ausente"
