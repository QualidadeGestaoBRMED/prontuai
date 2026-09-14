"""Regressões de autorização entre papéis, achadas na varredura de set/2026.

Cada teste reproduz um abuso que funcionava contra o back-end real antes da
correção. Rodar sem o conftest (que importa main.py e exige DATABASE_URL):

    PYTHONPATH=back-end pytest back-end/tests/test_role_permissions.py -q --noconftest
"""
import asyncio
import importlib
import sys
import types

import pytest
from fastapi import HTTPException

from app.models.notification import NotificationCreate
from app.models.user import User, UserRole, UserUpdate


def usuario(uid, role, ativo=True, clinic=None):
    return User(id=uid, email=f"{uid}@grupobrmed.com.br", name=uid, role=role,
                is_active=ativo, clinic_id=clinic)


class BancoFalso:
    def __init__(self, usuarios=(), documentos=()):
        self.usuarios = {u.id: u for u in usuarios}
        self.documentos = {d.id: d for d in documentos}
        self.criadas = []

    def get_user_by_id(self, uid):
        return self.usuarios.get(uid)

    def get_document_by_id(self, did):
        return self.documentos.get(did)

    def create_notification(self, n: NotificationCreate):
        self.criadas.append(n)
        return types.SimpleNamespace(id=f"n{len(self.criadas)}", **n.model_dump())


def carregar(monkeypatch, banco, modulo):
    # Importar um router carrega o pacote `app.api` inteiro, e nesse caminho um
    # cliente da OpenAI é criado na importação e exige a chave. Sem isto o teste
    # só passa em máquina com `.env` — num CI (ou worktree limpo) quebra.
    monkeypatch.setenv("OPENAI_API_KEY", "chave-de-teste")
    import app.core.config as config
    for chave, valor in {"APP_ENV": "test", "JWT_SECRET_KEY": "x" * 40, "DEV_AUTH_BYPASS": False}.items():
        monkeypatch.setattr(config.settings, chave, valor, raising=False)
    falso = types.ModuleType("app.core.database")
    falso.user_db = banco
    monkeypatch.setitem(sys.modules, "app.core.database", falso)
    for nome in ("app.core.auth", modulo):
        sys.modules.pop(nome, None)
    return importlib.import_module(modulo)


# ── MANAGER editando usuários ────────────────────────────────────────────────

MANAGER = usuario("gestor", UserRole.MANAGER)


@pytest.mark.parametrize("papel_alvo", [UserRole.ADMIN, UserRole.MANAGER, UserRole.CURATOR])
def test_manager_nao_edita_papeis_fora_de_checker_e_sender(monkeypatch, papel_alvo):
    """Antes: MANAGER rebaixava outro MANAGER (ou um CURATOR) para SENDER."""
    users = carregar(monkeypatch, BancoFalso([usuario("alvo", papel_alvo)]), "app.api.v1.users")
    with pytest.raises(HTTPException) as exc:
        users._assert_manager_can_edit(MANAGER, "alvo", UserUpdate(role=UserRole.SENDER))
    assert exc.value.status_code == 403


@pytest.mark.parametrize("ativo_hoje, pedido", [(True, False), (False, True)])
def test_manager_nao_ativa_nem_desativa(monkeypatch, ativo_hoje, pedido):
    """Antes: o PATCH de is_active contornava o DELETE (só ADMIN) e reativava demitidos."""
    users = carregar(monkeypatch, BancoFalso([usuario("alvo", UserRole.SENDER, ativo_hoje)]), "app.api.v1.users")
    with pytest.raises(HTTPException) as exc:
        users._assert_manager_can_edit(MANAGER, "alvo", UserUpdate(is_active=pedido))
    assert exc.value.status_code == 403


def test_manager_edita_sender_com_is_active_inalterado(monkeypatch):
    """O modal da tela sempre manda is_active junto; o valor atual precisa passar."""
    users = carregar(monkeypatch, BancoFalso([usuario("alvo", UserRole.SENDER, True)]), "app.api.v1.users")
    users._assert_manager_can_edit(MANAGER, "alvo", UserUpdate(name="Novo", role=UserRole.CHECKER, is_active=True))


def test_manager_editando_usuario_inexistente_da_404(monkeypatch):
    users = carregar(monkeypatch, BancoFalso(), "app.api.v1.users")
    with pytest.raises(HTTPException) as exc:
        users._assert_manager_can_edit(MANAGER, "fantasma", UserUpdate(name="x"))
    assert exc.value.status_code == 404


# ── notificações ─────────────────────────────────────────────────────────────

DOC = types.SimpleNamespace(id="doc1", clinic_id="c1", uploaded_by_user_id="autor",
                           uploaded_by_user_email="autor@grupobrmed.com.br")


def criar(notif, payload, quem):
    return asyncio.run(notif.create_notification(payload=payload, current_user=quem))


@pytest.mark.parametrize("papel", [UserRole.CURATOR, UserRole.CHECKER, UserRole.ADMIN])
def test_destinatario_nunca_vem_do_payload(monkeypatch, papel):
    """Antes: qualquer papel (até o CURATOR, que é só leitura) mirava qualquer usuário."""
    banco = BancoFalso()
    notif = carregar(monkeypatch, banco, "app.api.v1_notifications")
    quem = usuario("quem", papel)
    criar(notif, NotificationCreate(user_id="vitima", user_email="vitima@x", type="warning",
                                    title="documento rejeitado", message="reenvie aqui"), quem)
    assert banco.criadas[-1].user_id == "quem"


def test_checker_avisa_autor_pelo_documento(monkeypatch):
    """O fluxo legítimo da Checagem continua: aprovado/rejeitado chega ao autor."""
    banco = BancoFalso(documentos=[DOC])
    notif = carregar(monkeypatch, banco, "app.api.v1_notifications")
    criar(notif, NotificationCreate(document_id="doc1", type="document_approved", title="t", message="m"),
          usuario("checador", UserRole.CHECKER))
    assert banco.criadas[-1].user_id == "autor"


@pytest.mark.parametrize("papel", [UserRole.CURATOR])
def test_somente_leitura_nao_avisa_autor_pelo_documento(monkeypatch, papel):
    banco = BancoFalso(documentos=[DOC])
    notif = carregar(monkeypatch, banco, "app.api.v1_notifications")
    criar(notif, NotificationCreate(document_id="doc1", type="info", title="t", message="m"),
          usuario("leitor", papel))
    assert banco.criadas[-1].user_id == "leitor"


@pytest.mark.parametrize("link", ["//evil.com", "/\\evil.com", "https://evil.com", "javascript:alert(1)"])
def test_link_externo_em_notificacao_e_recusado(monkeypatch, link):
    banco = BancoFalso()
    notif = carregar(monkeypatch, banco, "app.api.v1_notifications")
    with pytest.raises(HTTPException) as exc:
        criar(notif, NotificationCreate(type="info", title="t", message="m", action_url=link),
              usuario("checador", UserRole.CHECKER))
    assert exc.value.status_code == 422
    assert banco.criadas == []
