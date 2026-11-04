"""Cargo FILIAL: envia e decide só os próprios documentos, em tela única.

**O que trava.** O atalho de dar CHECKER + SENDER abriria todas as clínicas,
porque a fila e o PATCH da checagem não recortam por clínica. Por isso a filial
é um cargo que se soma ao SENDER, e estas regras não podem quebrar em silêncio:

  * o principal continua SENDER, que é o que mantém o recorte de leitura e deixa
    a decisão fora da revisão humana do dashboard;
  * só decide documento que ela enviou e que ninguém mais decidiu;
  * o SENDER comum continua sem decidir nada;
  * as consultas do dashboard que olham `reviewed_by` ou o parecer excluem a filial.

Rodar sem o conftest, que importa main.py e exige DATABASE_URL:

    PYTHONPATH=back-end pytest back-end/tests/test_cargo_filial.py -q --noconftest
"""
import asyncio
import importlib
import re
import sys
import types
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.models.user import User, UserRole, cargo_que_contem

A, M, CH, S, F, V = (UserRole.ADMIN, UserRole.MANAGER, UserRole.CHECKER, UserRole.SENDER,
                     UserRole.FILIAL, UserRole.VIEWER)


def usuario(uid, *papeis, clinic="c1"):
    return User(id=uid, email=f"{uid}@grupobrmed.com.br", name=uid, roles=list(papeis), clinic_id=clinic)


def documento(enviado_por="filial", reviewed_by=None):
    return types.SimpleNamespace(id="doc1", uploaded_by_user_id=enviado_por, reviewed_by=reviewed_by)


class BancoFalso:
    def __init__(self, documentos=()):
        self.documentos = {d.id: d for d in documentos}

    def get_document_by_id(self, doc_id):
        return self.documentos.get(doc_id)

    def get_clinic_by_id(self, cid):
        return types.SimpleNamespace(id=cid, name=cid)

    def get_document_feedback(self, doc_id):
        return None

    def get_user_by_id(self, uid):
        return None

    def create_audit_log(self, *_a, **_k):
        return None


def carregar(monkeypatch, nome_modulo, banco=None):
    """Importa o módulo com um `app.core.database` falso: o real exige DATABASE_URL."""
    banco = banco or BancoFalso()
    falso = types.ModuleType("app.core.database")
    falso.user_db = banco
    monkeypatch.setitem(sys.modules, "app.core.database", falso)
    for nome in ("app.core.auth", nome_modulo):
        sys.modules.pop(nome, None)
    return importlib.import_module(nome_modulo)


def test_principal_da_filial_continua_sender():
    filial = usuario("filial", F, S)
    assert filial.role == S
    assert filial.roles == [S, F]
    # Com o Visualizador também: VIEWER fica depois, e o recorte não muda.
    assert usuario("filial", V, F, S).role == S


@pytest.mark.parametrize("dono", [A, M, CH])
def test_quem_decide_tudo_ja_contem_a_filial(dono):
    assert cargo_que_contem(F, [dono, F]) == dono


def test_filial_decide_o_que_enviou(monkeypatch):
    auth = carregar(monkeypatch, "app.core.auth")
    auth.garantir_decisao_no_documento(usuario("filial", S, F), documento())


def test_filial_nao_decide_documento_de_outro_usuario(monkeypatch):
    auth = carregar(monkeypatch, "app.core.auth")
    with pytest.raises(HTTPException) as erro:
        auth.garantir_decisao_no_documento(usuario("filial", S, F), documento(enviado_por="outra"))
    assert erro.value.status_code == 403


def test_filial_nao_desfaz_decisao_da_checagem_central(monkeypatch):
    auth = carregar(monkeypatch, "app.core.auth")
    with pytest.raises(HTTPException) as erro:
        auth.garantir_decisao_no_documento(
            usuario("filial", S, F), documento(reviewed_by="checador@grupobrmed.com.br")
        )
    assert erro.value.status_code == 403
    assert "outra pessoa" in erro.value.detail


def test_filial_pode_voltar_a_propria_decisao(monkeypatch):
    auth = carregar(monkeypatch, "app.core.auth")
    auth.garantir_decisao_no_documento(
        usuario("filial", S, F), documento(reviewed_by="filial@grupobrmed.com.br")
    )


def test_sender_comum_continua_sem_decidir(monkeypatch):
    auth = carregar(monkeypatch, "app.core.auth")
    sender = usuario("sender", S)
    with pytest.raises(HTTPException) as erro:
        asyncio.run(auth.require_decisor(None, sender))
    assert erro.value.status_code == 403
    # Nem o próprio envio: decidir é do cargo, não de quem enviou.
    with pytest.raises(HTTPException):
        auth.garantir_decisao_no_documento(sender, documento(enviado_por="sender"))


@pytest.mark.parametrize("papel", [A, M, CH])
def test_checagem_central_decide_qualquer_documento(monkeypatch, papel):
    auth = carregar(monkeypatch, "app.core.auth")
    auth.garantir_decisao_no_documento(
        usuario("revisor", papel, clinic=None), documento(enviado_por="outra", reviewed_by="x@y.com")
    )


@pytest.mark.parametrize(
    "papeis, aceita",
    [([S, F], True), ([S, F, V], True), ([F], False), ([F, V], False), ([S], True), ([CH], True)],
)
def test_filial_exige_enviador(monkeypatch, papeis, aceita):
    users = carregar(monkeypatch, "app.api.v1.users")
    if aceita:
        users._exigir_enviador_na_filial(papeis)
        return
    with pytest.raises(HTTPException) as erro:
        users._exigir_enviador_na_filial(papeis)
    assert erro.value.status_code == 400


def test_gestor_nao_atribui_filial(monkeypatch):
    users = carregar(monkeypatch, "app.api.v1.users")
    with pytest.raises(HTTPException) as erro:
        users._assert_manager_cannot_touch_admin(usuario("gestor", M, clinic=None), [S, F])
    assert erro.value.status_code == 403


def test_localizacao_da_filial_so_no_que_enviou(monkeypatch):
    localizacao = carregar(monkeypatch, "app.api.v1.localizacao")
    filial = usuario("filial", S, F)
    localizacao._garantir_leitura(filial, documento())
    with pytest.raises(HTTPException) as erro:
        localizacao._garantir_leitura(filial, documento(enviado_por="outra"))
    assert erro.value.status_code == 403
    # O checador segue lendo qualquer um.
    localizacao._garantir_leitura(usuario("checador", CH, clinic=None), documento(enviado_por="outra"))


def test_normalidade_da_filial_so_no_que_enviou(monkeypatch):
    normalidade = carregar(monkeypatch, "app.api.v1.normalidade", BancoFalso([documento(enviado_por="outra")]))
    monkeypatch.setattr(normalidade.ne, "HABILITADA", True)
    with pytest.raises(HTTPException) as erro:
        normalidade.normalidade_do_documento("doc1", usuario("filial", S, F))
    assert erro.value.status_code == 403
    # As faixas de referência continuam fora do alcance dela.
    assert F not in normalidade._LEITORES and F in normalidade._LEITORES_DO_DOCUMENTO


class BancoDoPatch(BancoFalso):
    def __init__(self, doc):
        super().__init__([doc])
        self.gravado = None

    def update_document(self, **kwargs):
        self.gravado = kwargs
        return self.documentos[kwargs["document_id"]]


def patch_como_filial(monkeypatch, doc, payload):
    from fastapi import BackgroundTasks

    from app.models.document import DocumentUpdate

    banco = BancoDoPatch(doc)
    documents = carregar(monkeypatch, "app.api.v1.documents", banco)
    tarefas = BackgroundTasks()
    asyncio.run(
        documents.update_document(
            document_id=doc.id,
            payload=DocumentUpdate(**payload),
            background_tasks=tarefas,
            current_user=usuario("filial", S, F),
        )
    )
    return banco, tarefas


def documento_do_patch(**campos):
    return types.SimpleNamespace(
        **{
            "id": "doc1", "uploaded_by_user_id": "filial", "reviewed_by": None,
            "validation_status": "pending", "result_payload": {}, "clinic_id": "c1",
            "clinic_name": "Clínica 1", **campos,
        }
    )


def test_aprovacao_da_filial_grava_o_revisor_real_e_agenda_o_drive(monkeypatch):
    """Sem o revisor na coluna o dashboard não a separa; sem o Drive o documento não chega ao destino."""
    banco, tarefas = patch_como_filial(
        monkeypatch,
        documento_do_patch(),
        {"validation_status": "validated", "result_payload": {"reviewed_by": "forjado@x.com"}},
    )
    assert banco.gravado["reviewed_by"] == "filial@grupobrmed.com.br"
    assert banco.gravado["reviewed_at"] is not None
    assert [t.func.__name__ for t in tarefas.tasks] == ["upload_document_to_drive"]


def test_rejeicao_da_filial_tambem_grava_o_revisor(monkeypatch):
    banco, _ = patch_como_filial(monkeypatch, documento_do_patch(), {"validation_status": "rejected"})
    assert banco.gravado["validation_status"] == "rejected"
    assert banco.gravado["reviewed_by"] == "filial@grupobrmed.com.br"


@pytest.mark.parametrize(
    "campos, payload",
    [
        ({"uploaded_by_user_id": "outra"}, {"validation_status": "validated"}),
        ({"reviewed_by": "checador@grupobrmed.com.br"}, {"validation_status": "validated"}),
        ({}, {"exams_found": ["Audiometria"]}),
        ({}, {"validation_status": "pending"}),
    ],
)
def test_patch_da_filial_recusado_nao_grava_nada(monkeypatch, campos, payload):
    from app.models.document import DocumentUpdate

    banco = BancoDoPatch(documento_do_patch(**campos))
    documents = carregar(monkeypatch, "app.api.v1.documents", banco)
    from fastapi import BackgroundTasks

    with pytest.raises(HTTPException) as erro:
        asyncio.run(
            documents.update_document(
                document_id="doc1",
                payload=DocumentUpdate(**payload),
                background_tasks=BackgroundTasks(),
                current_user=usuario("filial", S, F),
            )
        )
    assert erro.value.status_code == 403
    assert banco.gravado is None


def test_dashboard_exclui_a_filial_das_consultas_de_revisao():
    """Lê o fonte: `dashboard_service` puxa dependências pesadas e a regra é o SQL."""
    fonte = (Path(__file__).parent.parent / "app/services/dashboard_service.py").read_text(encoding="utf-8")
    for constante, junta in (
        ("_SQL_PRAZOS", "u.email = d.reviewed_by"),
        ("_SQL_PARECERES_EXAMES", "u.id = f.reviewed_by_id"),
        ("_SQL_DECISOES_DESDE_O_MODAL", "u.email = d.reviewed_by"),
    ):
        sql = re.search(rf'^{constante} = r?"""(.*?)"""', fonte, re.S | re.M).group(1)
        assert f"NOT EXISTS (SELECT 1 FROM users u WHERE {junta} AND 'FILIAL' = ANY(u.roles))" in sql


def test_revisao_humana_do_dashboard_ignora_o_principal_da_filial():
    """A filial fica de fora porque a auditoria grava SENDER. Se a lista mudar, ela entra."""
    sql = (Path(__file__).parent.parent / "app/services/sql/dashboard_indicadores.sql").read_text(encoding="utf-8")
    assert "al.user_role IN ('ADMIN', 'CHECKER', 'MANAGER')" in sql
