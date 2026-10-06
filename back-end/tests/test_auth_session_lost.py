"""
Trilha das sessões que morrem no cliente.

Quando o cookie do NextAuth vence, a rota `/api/auth/refresh-token` do front
responde 401 sem chamar o back-end: o usuário lê "Sessão expirada" e não sobra
registro de quem foi deslogado nem por quê. Era o único desfecho de
autenticação invisível. `/auth/session-lost` fecha esse buraco — e, como é uma
rota anônima, estes testes travam também o que ela se recusa a aceitar.

Segue o padrão de test_auth_trilha_login.py: user_db falso e reload dos módulos
de auth, para não depender de Postgres. Rode com --noconftest.
"""
import datetime
import importlib
import sys
import types

import pytest


class FakeRequest:
    def __init__(self):
        self.state = types.SimpleNamespace()

    @property
    def audit(self) -> dict:
        return getattr(self.state, "audit", None) or {}

    @property
    def metadata(self) -> dict:
        return self.audit.get("metadata", {})


def load_api_auth(monkeypatch):
    import app.core.config as config

    monkeypatch.setattr(config.settings, "APP_ENV", "test", raising=False)
    monkeypatch.setattr(config.settings, "JWT_SECRET_KEY", "x" * 40, raising=False)
    monkeypatch.setattr(config.settings, "JWT_MIN_SECRET_LENGTH", 32, raising=False)

    fake_database_module = types.ModuleType("app.core.database")
    fake_database_module.user_db = object()
    monkeypatch.setitem(sys.modules, "app.core.database", fake_database_module)
    sys.modules.pop("app.core.auth", None)
    sys.modules.pop("app.api.v1.auth", None)

    import app.core.auth as core_auth

    importlib.reload(core_auth)
    import app.api.v1.auth as api_auth

    return importlib.reload(api_auth)


async def _avisar(api_auth, request, **campos):
    return await api_auth.session_lost(api_auth.SessionLostRequest(**campos), request)


@pytest.mark.asyncio
async def test_registra_quem_perdeu_a_sessao_e_por_que(monkeypatch):
    api_auth = load_api_auth(monkeypatch)
    req = FakeRequest()

    await _avisar(
        api_auth,
        req,
        motivo="cookie_ausente",
        email="ana@clinica.com.br",
        url="/v1/notifications",
    )

    assert req.audit["action"] == "auth.session.lost"
    assert req.audit["user_email"] == "ana@clinica.com.br"
    assert req.metadata["motivo"] == "cookie_ausente"
    assert req.metadata["url"] == "/v1/notifications"
    # O email veio de um cliente anônimo: entra para investigar, não para confiar.
    assert req.metadata["email_verificado"] is False


@pytest.mark.asyncio
async def test_cookie_ausente_e_cookie_sem_refresh_sao_causas_distintas(monkeypatch):
    """A distinção é o que prova (ou refuta) que o maxAge do cookie é o culpado."""
    api_auth = load_api_auth(monkeypatch)

    for motivo in ("cookie_ausente", "cookie_sem_refresh"):
        req = FakeRequest()
        await _avisar(api_auth, req, motivo=motivo)
        assert req.metadata["motivo"] == motivo


@pytest.mark.asyncio
async def test_motivo_desconhecido_nao_vira_texto_livre_na_trilha(monkeypatch):
    api_auth = load_api_auth(monkeypatch)
    req = FakeRequest()

    await _avisar(api_auth, req, motivo="<script>qualquer coisa</script>")

    assert req.metadata["motivo"] == "desconhecido"


@pytest.mark.asyncio
async def test_motivo_ausente_tambem_cai_em_desconhecido(monkeypatch):
    api_auth = load_api_auth(monkeypatch)
    req = FakeRequest()

    await _avisar(api_auth, req)

    assert req.audit["action"] == "auth.session.lost"
    assert req.metadata["motivo"] == "desconhecido"


@pytest.mark.asyncio
async def test_email_sem_forma_de_email_nao_entra_na_trilha(monkeypatch):
    """`user_email` é indexado junto com os verificados; lixo não entra lá."""
    api_auth = load_api_auth(monkeypatch)

    for valor in ("semarroba", "@dominio.com", "a@b", "x y@z.com", ""):
        req = FakeRequest()
        await _avisar(api_auth, req, motivo="cookie_ausente", email=valor)
        assert "user_email" not in req.audit, valor
        # O registro sobrevive mesmo sem o email: o motivo ainda é a informação.
        assert req.metadata["motivo"] == "cookie_ausente"


@pytest.mark.asyncio
async def test_duracao_da_sessao_e_calculada_no_servidor(monkeypatch):
    api_auth = load_api_auth(monkeypatch)
    req = FakeRequest()
    uma_hora_atras = int(datetime.datetime.utcnow().timestamp()) - 3600

    await _avisar(
        api_auth, req, motivo="cookie_ausente", sessao_iniciada_em=uma_hora_atras
    )

    assert abs(req.metadata["duracao_da_sessao_s"] - 3600) <= 5


@pytest.mark.asyncio
async def test_duracao_implausivel_do_cliente_e_descartada(monkeypatch):
    """Relógio do cliente errado não vira sessão de meses (nem negativa)."""
    api_auth = load_api_auth(monkeypatch)
    agora = int(datetime.datetime.utcnow().timestamp())

    for inicio in (agora + 86400, agora - (60 * 60 * 24 * 365)):
        req = FakeRequest()
        await _avisar(
            api_auth, req, motivo="cookie_ausente", sessao_iniciada_em=inicio
        )
        assert "duracao_da_sessao_s" not in req.metadata
