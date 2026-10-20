"""Mais de um cargo por usuário (`roles`), migration 012.

**O que trava.** O usuário passou a acumular cargos, e `role` virou o papel
principal, derivado da lista. Duas coisas não podem quebrar sem ninguém ver:

  * PERMISSÃO é por qualquer cargo da lista — o MANAGER + CURATOR entra no
    catálogo, o CHECKER + SENDER envia; e somar cargos não pode somar o que
    nenhum deles dá (CURATOR + SENDER não aprova documento);
  * o PRINCIPAL segue a precedência, porque é ele que vai para
    `audit_logs.user_role` e o dashboard só conta revisão humana de ADMIN,
    CHECKER ou MANAGER. Um CHECKER + CURATOR gravado como CURATOR some da
    acurácia.

E a gestão: MANAGER não esconde um ADMIN no meio de [CHECKER, ADMIN], a
clínica acompanha o cargo SENDER, e cargo que outro já contém (MANAGER +
VIEWER, ADMIN + qualquer um) não é gravado.

Rodar sem o conftest, que importa main.py e exige DATABASE_URL:

    PYTHONPATH=back-end pytest back-end/tests/test_multiplos_cargos.py -q --noconftest
"""
import asyncio
import importlib
import sys
import types

import pytest
from fastapi import HTTPException

from app.models.user import User, UserCreate, UserRole, UserUpdate

A, M, CH, CU, S, V = (UserRole.ADMIN, UserRole.MANAGER, UserRole.CHECKER, UserRole.CURATOR,
                      UserRole.SENDER, UserRole.VIEWER)


def usuario(uid, *papeis, clinic=None, ativo=True):
    return User(id=uid, email=f"{uid}@grupobrmed.com.br", name=uid, roles=list(papeis),
                clinic_id=clinic, is_active=ativo)


class BancoFalso:
    def __init__(self, usuarios=(), clinicas=("c1",)):
        self.usuarios = {u.id: u for u in usuarios}
        self.clinicas = set(clinicas)
        self.criado = None
        self.atualizado = None

    def get_user_by_id(self, uid):
        return self.usuarios.get(uid)

    def get_clinic_by_id(self, cid):
        return types.SimpleNamespace(id=cid, name=f"Clínica {cid}") if cid in self.clinicas else None

    def create_user(self, **kw):
        self.criado = kw
        return User(id="novo", email=kw["email"], name=kw["name"], roles=kw["roles"],
                    clinic_id=kw["clinic_id"])

    def update_user(self, **kw):
        self.atualizado = kw
        alvo = self.usuarios[kw["user_id"]]
        return User(id=alvo.id, email=alvo.email, name=alvo.name,
                    roles=kw["roles"] or alvo.roles, clinic_id=alvo.clinic_id)


def carregar(monkeypatch, banco, modulo):
    # Mesmo truque de test_role_permissions.py: importar um router carrega
    # `app.api` inteiro, que cria cliente da OpenAI e exige a chave.
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


# ── papel principal ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("papeis, principal", [
    ([CU, CH], CH),     # revisão do CHECKER + CURATOR continua contando no dashboard
    ([S, CH], CH),
    ([S, CU], CU),
    ([CU, M], M),
    ([S, A, CH], A),
    ([S], S),           # SENDER só é principal quando está sozinho...
    ([V, S], S),        # ...ou com o Visualizador, que não lê documento: o recorte por clínica fica
    ([CH, V], CH),
    ([V], V),           # VIEWER só é principal quando está sozinho
])
def test_principal_segue_a_precedencia(papeis, principal):
    u = usuario("u", *papeis)
    assert u.role == principal
    assert u.roles[0] == principal


def test_so_role_vira_lista_de_um():
    """Linha anterior à migration, token antigo e o front de antes mandam só `role`."""
    u = User(email="x@grupobrmed.com.br", name="x", role=S)
    assert u.roles == [S]


def test_cargo_repetido_nao_duplica():
    assert usuario("u", CH, CH, S).roles == [CH, S]


# ── guardas de permissão ─────────────────────────────────────────────────────

def _passa(auth, user, permitidos):
    try:
        auth._exigir_papel(None, user, permitidos, "negado")
        return True
    except HTTPException as exc:
        assert exc.status_code == 403
        return False


def test_qualquer_cargo_da_lista_libera(monkeypatch):
    auth = carregar(monkeypatch, BancoFalso(), "app.core.auth")
    # Catálogo é ADMIN ou CURATOR; o principal do MANAGER + CURATOR é MANAGER.
    assert _passa(auth, usuario("u", M, CU), (A, CU))
    # Envio é SENDER, ADMIN ou MANAGER; o principal do CHECKER + SENDER é CHECKER.
    assert _passa(auth, usuario("u", CH, S), (S, A, M))


def test_visualizador_ve_o_dashboard_e_nada_de_documento(monkeypatch):
    auth = carregar(monkeypatch, BancoFalso(), "app.core.auth")
    so_visualizador = usuario("u", V)
    assert _passa(auth, so_visualizador, auth.DASHBOARD_ROLES)
    assert not _passa(auth, so_visualizador, auth.DOCUMENT_ROLES)
    assert not _passa(auth, so_visualizador, (A, M))  # não vira gestão


def test_somar_cargos_nao_soma_o_que_nenhum_da(monkeypatch):
    auth = carregar(monkeypatch, BancoFalso(), "app.core.auth")
    # Aprovar/rejeitar é CHECKER, ADMIN ou MANAGER: nem CURATOR nem SENDER.
    assert not _passa(auth, usuario("u", CU, S), (CH, A, M))


# ── gestão de usuários ───────────────────────────────────────────────────────

GESTOR = usuario("gestor", M)
ADMIN = usuario("admin", A)


def criar(users, dados, quem):
    return asyncio.run(users.create_user(user_create=UserCreate(**dados), admin=quem))


def editar(users, uid, dados, quem):
    return asyncio.run(users.update_user(user_id=uid, user_update=UserUpdate(**dados), admin=quem))


def test_gestor_nao_esconde_admin_no_meio_da_lista(monkeypatch):
    users = carregar(monkeypatch, BancoFalso(), "app.api.v1.users")
    with pytest.raises(HTTPException) as exc:
        criar(users, {"email": "n@grupobrmed.com.br", "name": "n", "roles": ["CHECKER", "ADMIN"]}, GESTOR)
    assert exc.value.status_code == 403


def test_gestor_nao_atribui_visualizador(monkeypatch):
    """Decisão de produto: o Visualizador do dashboard é atribuído só pelo ADMIN."""
    users = carregar(monkeypatch, BancoFalso(), "app.api.v1.users")
    with pytest.raises(HTTPException) as exc:
        criar(users, {"email": "n@grupobrmed.com.br", "name": "n", "roles": ["CHECKER", "VIEWER"]}, GESTOR)
    assert exc.value.status_code == 403


def test_gestor_cria_checker_e_sender_juntos(monkeypatch):
    banco = BancoFalso()
    users = carregar(monkeypatch, banco, "app.api.v1.users")
    criar(users, {"email": "n@grupobrmed.com.br", "name": "n", "roles": ["SENDER", "CHECKER"],
                  "clinic_id": "c1"}, GESTOR)
    assert banco.criado["roles"] == [CH, S]
    assert banco.criado["role"] == CH
    assert banco.criado["clinic_id"] == "c1"


def test_gestor_nao_edita_quem_acumula_cargo_fora_do_alcance(monkeypatch):
    """Principal CHECKER, mas com CURATOR junto: está fora do alcance do gestor."""
    users = carregar(monkeypatch, BancoFalso([usuario("alvo", CH, CU)]), "app.api.v1.users")
    with pytest.raises(HTTPException) as exc:
        editar(users, "alvo", {"name": "x"}, GESTOR)
    assert exc.value.status_code == 403


def test_lista_vazia_de_cargos_e_recusada(monkeypatch):
    users = carregar(monkeypatch, BancoFalso([usuario("alvo", CH)]), "app.api.v1.users")
    with pytest.raises(HTTPException) as exc:
        criar(users, {"email": "n@grupobrmed.com.br", "name": "n", "roles": []}, ADMIN)
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        editar(users, "alvo", {"roles": []}, ADMIN)
    assert exc.value.status_code == 400


def test_sender_na_lista_exige_clinica(monkeypatch):
    users = carregar(monkeypatch, BancoFalso([usuario("alvo", CH)]), "app.api.v1.users")
    with pytest.raises(HTTPException) as exc:
        criar(users, {"email": "n@grupobrmed.com.br", "name": "n", "roles": ["CHECKER", "SENDER"]}, ADMIN)
    assert exc.value.status_code == 400
    # Ganhar SENDER na edição também exige a clínica.
    with pytest.raises(HTTPException) as exc:
        editar(users, "alvo", {"roles": ["CHECKER", "SENDER"]}, ADMIN)
    assert exc.value.status_code == 400


def test_sem_sender_a_clinica_nao_e_gravada_na_criacao(monkeypatch):
    banco = BancoFalso()
    users = carregar(monkeypatch, banco, "app.api.v1.users")
    criar(users, {"email": "n@grupobrmed.com.br", "name": "n", "roles": ["CHECKER", "CURATOR"],
                  "clinic_id": "c1"}, ADMIN)
    assert banco.criado["clinic_id"] is None


def test_perder_o_sender_tira_a_clinica(monkeypatch):
    banco = BancoFalso([usuario("alvo", CH, S, clinic="c1")])
    users = carregar(monkeypatch, banco, "app.api.v1.users")
    editar(users, "alvo", {"roles": ["CHECKER"]}, ADMIN)
    assert banco.atualizado["limpar_clinica"] is True


def test_admin_com_clinica_nao_perde_a_clinica_ao_ser_editado(monkeypatch):
    """O envio usa a clínica do próprio usuário: há ADMIN que envia por uma."""
    banco = BancoFalso([usuario("alvo", A, clinic="c1")])
    users = carregar(monkeypatch, banco, "app.api.v1.users")
    editar(users, "alvo", {"name": "novo nome"}, ADMIN)
    assert banco.atualizado["limpar_clinica"] is False
    assert banco.atualizado["clinic_id"] is None  # None = não mexe


def test_continuar_sender_mantem_a_clinica_atual(monkeypatch):
    banco = BancoFalso([usuario("alvo", S, clinic="c1")])
    users = carregar(monkeypatch, banco, "app.api.v1.users")
    editar(users, "alvo", {"roles": ["SENDER", "CHECKER"]}, ADMIN)
    assert banco.atualizado["clinic_id"] == "c1"
    assert banco.atualizado["limpar_clinica"] is False


# ── cargo contido em outro ───────────────────────────────────────────────────

@pytest.mark.parametrize("papeis", [
    ["MANAGER", "VIEWER"],      # o caso que existia em produção (2 gestores, out/2026)
    ["MANAGER", "CHECKER"],
    ["MANAGER", "SENDER"],      # decisão de produto: entra mesmo prendendo a uma clínica
    ["ADMIN", "MANAGER"],
    ["ADMIN", "CURATOR"],
    ["CHECKER", "ADMIN"],       # a ordem em que chega não importa
])
def test_cargo_contido_em_outro_e_recusado(monkeypatch, papeis):
    users = carregar(monkeypatch, BancoFalso([usuario("alvo", CH)]), "app.api.v1.users")
    with pytest.raises(HTTPException) as exc:
        criar(users, {"email": "n@grupobrmed.com.br", "name": "n", "roles": papeis,
                      "clinic_id": "c1"}, ADMIN)
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        editar(users, "alvo", {"roles": papeis, "clinic_id": "c1"}, ADMIN)
    assert exc.value.status_code == 400


@pytest.mark.parametrize("papeis", [
    ["CHECKER", "SENDER"],
    ["CHECKER", "CURATOR"],
    ["MANAGER", "CURATOR"],     # o catálogo não é do gestor: o CURATOR acrescenta
    ["CURATOR", "VIEWER"],
    ["CHECKER", "VIEWER"],
])
def test_cargos_que_nao_se_contem_continuam_juntos(monkeypatch, papeis):
    banco = BancoFalso()
    users = carregar(monkeypatch, banco, "app.api.v1.users")
    criar(users, {"email": "n@grupobrmed.com.br", "name": "n", "roles": papeis, "clinic_id": "c1"}, ADMIN)
    assert set(banco.criado["roles"]) == {UserRole(p) for p in papeis}


def test_gestor_com_admin_na_lista_ainda_e_falta_de_permissao(monkeypatch):
    """A escalada responde 403 antes de a sobreposição responder 400."""
    users = carregar(monkeypatch, BancoFalso(), "app.api.v1.users")
    with pytest.raises(HTTPException) as exc:
        criar(users, {"email": "n@grupobrmed.com.br", "name": "n", "roles": ["ADMIN", "CHECKER"]}, GESTOR)
    assert exc.value.status_code == 403


def test_quem_ja_tem_a_sobreposicao_e_editado_sem_mexer_nos_cargos(monkeypatch):
    """A regra vale para o que se grava: ativar ou renomear não exige limpar antes."""
    banco = BancoFalso([usuario("alvo", M, V)])
    users = carregar(monkeypatch, banco, "app.api.v1.users")
    editar(users, "alvo", {"name": "novo nome"}, ADMIN)
    assert banco.atualizado["roles"] is None
    # E a limpeza, que é o que a tela manda ao salvar, passa.
    editar(users, "alvo", {"roles": ["MANAGER"]}, ADMIN)
    assert banco.atualizado["roles"] == [M]


# ── jobs ─────────────────────────────────────────────────────────────────────

def test_jobs_somam_os_recortes_de_cada_cargo(monkeypatch):
    jobs = carregar(monkeypatch, BancoFalso(), "app.api.v1_jobs")
    quem = usuario("eu", CH, S, clinic="c1")
    proprio_de_outra_clinica = {"metadata": {"uploaded_by_user_id": "eu", "clinic_id": "c2"}}
    alheio_da_minha_clinica = {"metadata": {"uploaded_by_user_id": "outro", "clinic_id": "c1"}}
    alheio_de_outra_clinica = {"metadata": {"uploaded_by_user_id": "outro", "clinic_id": "c2"}}
    assert jobs._can_access_job(quem, proprio_de_outra_clinica)      # pelo SENDER
    assert jobs._can_access_job(quem, alheio_da_minha_clinica)       # pelo CHECKER
    assert not jobs._can_access_job(quem, alheio_de_outra_clinica)
