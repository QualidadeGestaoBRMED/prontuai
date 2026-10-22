"""Testes do status de abordagem das credenciadas sem cadastro ("Quem vale a pena incluir").

Rodar sem o conftest, que importa main.py e exige DATABASE_URL:

    PYTHONPATH=back-end pytest back-end/tests/test_credenciado_abordagem.py -q --noconftest
"""
import importlib
import sys
import types
from datetime import datetime

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from app.models.abordagem import Abordagem, AbordagemInput
from app.models.user import User, UserRole

ROTULO = "RECIFE - PE - QUALIMETRA"


def usuario(uid="gestora", role=UserRole.MANAGER):
    return User(id=uid, email=f"{uid}@grupobrmed.com.br", name=f"Nome {uid}", role=role, is_active=True)


def requisicao():
    return Request(
        {
            "type": "http",
            "method": "PUT",
            "scheme": "http",
            "server": ("testserver", 80),
            "path": "/v1/dashboard/abordagens",
            "raw_path": b"/v1/dashboard/abordagens",
            "query_string": b"",
            "headers": [(b"user-agent", b"pytest")],
            "client": ("127.0.0.1", 1234),
        }
    )


class BancoFalso:
    def __init__(self, abordagens=None):
        self.abordagens = dict(abordagens or {})
        self.gravacoes = []

    def list_credenciado_abordagens(self):
        return list(self.abordagens.values())

    def get_credenciado_abordagem(self, credenciado):
        return self.abordagens.get(credenciado)

    def upsert_credenciado_abordagem(self, credenciado, status, motivo,
                                     atualizado_por_id, atualizado_por_email, atualizado_por_nome):
        self.gravacoes.append(dict(credenciado=credenciado, status=status, motivo=motivo,
                                   atualizado_por_id=atualizado_por_id))
        salvo = Abordagem(
            credenciado=credenciado, status=status, motivo=motivo,
            atualizado_por_email=atualizado_por_email, atualizado_por_nome=atualizado_por_nome,
            atualizado_em=datetime(2026, 10, 22, 18, 0),
        )
        self.abordagens[credenciado] = salvo
        return salvo


def carregar(monkeypatch, banco):
    # Mesmo truque de test_document_feedback.py: importar o router carrega
    # `app.api` inteiro, que cria um cliente da OpenAI e abre o banco na importação.
    monkeypatch.setenv("OPENAI_API_KEY", "chave-de-teste")
    import app.core.config as config
    for chave, valor in {"APP_ENV": "test", "JWT_SECRET_KEY": "x" * 40, "DEV_AUTH_BYPASS": False}.items():
        monkeypatch.setattr(config.settings, chave, valor, raising=False)
    falso = types.ModuleType("app.core.database")
    falso.user_db = banco
    monkeypatch.setitem(sys.modules, "app.core.database", falso)
    for nome in ("app.core.auth", "app.api.v1.dashboard"):
        sys.modules.pop(nome, None)
    return importlib.import_module("app.api.v1.dashboard")


# ── schema ───────────────────────────────────────────────────────────────────

def test_recusa_sem_motivo_e_recusada():
    with pytest.raises(ValidationError, match="motivo da recusa"):
        AbordagemInput(credenciado=ROTULO, status="RECUSOU")


def test_motivo_so_de_espaco_conta_como_vazio():
    with pytest.raises(ValidationError):
        AbordagemInput(credenciado=ROTULO, status="RECUSOU", motivo="   ")


def test_motivo_fora_da_recusa_e_descartado():
    """Motivo antigo não pode ficar grudado depois que a conversa avançou."""
    entrada = AbordagemInput(credenciado=ROTULO, status="EM_CONTATO", motivo="já usa outro sistema")
    assert entrada.motivo is None


def test_status_fora_da_lista_e_recusado():
    with pytest.raises(ValidationError):
        AbordagemInput(credenciado=ROTULO, status="DESISTIU")


def test_credenciado_vazio_e_recusado():
    with pytest.raises(ValidationError):
        AbordagemInput(credenciado="  ", status="EM_CONTATO")


def test_rotulo_perde_espaco_das_pontas():
    assert AbordagemInput(credenciado=f"  {ROTULO} ", status="EM_CONTATO").credenciado == ROTULO


# ── rotas ────────────────────────────────────────────────────────────────────

def test_salvar_grava_status_e_autor(monkeypatch):
    banco = BancoFalso()
    mod = carregar(monkeypatch, banco)
    salvo = mod.salvar_abordagem(
        AbordagemInput(credenciado=ROTULO, status="RECUSOU", motivo="Já usa outro sistema"),
        requisicao(),
        current_user=usuario(),
    )
    assert salvo.status == "RECUSOU"
    assert salvo.motivo == "Já usa outro sistema"
    assert salvo.atualizado_por_email == "gestora@grupobrmed.com.br"
    assert salvo.atualizado_por_nome == "Nome gestora"
    assert banco.gravacoes[-1]["atualizado_por_id"] == "gestora"


def test_trilha_tem_antes_e_depois_mas_nao_o_texto_do_motivo(monkeypatch):
    anterior = Abordagem(credenciado=ROTULO, status="EM_CONTATO", atualizado_em=datetime(2026, 10, 1))
    banco = BancoFalso({ROTULO: anterior})
    mod = carregar(monkeypatch, banco)
    req = requisicao()
    mod.salvar_abordagem(
        AbordagemInput(credenciado=ROTULO, status="RECUSOU", motivo="Falei com a Maria"),
        req,
        current_user=usuario(),
    )
    trilha = req.state.audit
    assert trilha["action"] == "dashboard.abordagem"
    assert trilha["user_email"] == "gestora@grupobrmed.com.br"
    assert trilha["user_role"] == "MANAGER"
    assert trilha["resource_id"] == ROTULO
    assert trilha["metadata"]["status_anterior"] == "EM_CONTATO"
    assert trilha["metadata"]["status"] == "RECUSOU"
    assert trilha["metadata"]["motivo_len"] == len("Falei com a Maria")
    assert "Maria" not in str(trilha)


def test_primeira_marcacao_nao_tem_status_anterior(monkeypatch):
    mod = carregar(monkeypatch, BancoFalso())
    req = requisicao()
    mod.salvar_abordagem(AbordagemInput(credenciado=ROTULO, status="EM_CONTATO"), req, current_user=usuario())
    assert req.state.audit["metadata"]["status_anterior"] is None


def test_listar_devolve_o_que_esta_gravado(monkeypatch):
    gravada = Abordagem(credenciado=ROTULO, status="ACEITOU", atualizado_em=datetime(2026, 10, 2))
    mod = carregar(monkeypatch, BancoFalso({ROTULO: gravada}))
    assert mod.listar_abordagens(current_user=usuario(role=UserRole.VIEWER)) == [gravada]


def _dependencias(mod, metodo):
    rota = next(r for r in mod.router.routes if r.path.endswith("/abordagens") and metodo in r.methods)
    return {d.call.__name__ for d in rota.dependant.dependencies}


def test_so_a_gestao_altera_e_quem_ve_o_dashboard_le(monkeypatch):
    mod = carregar(monkeypatch, BancoFalso())
    assert "require_management" in _dependencias(mod, "PUT")
    assert "require_dashboard" in _dependencias(mod, "GET")
