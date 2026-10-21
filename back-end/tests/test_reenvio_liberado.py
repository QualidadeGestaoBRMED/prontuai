"""Reenvio de prontuário já liberado (migration 015, app/services/reenvio_service.py).

**Por que existe.** A clínica reenviava um prontuário já aprovado, o reenvio
virava item novo na Checagem e ela entendia que o documento não tinha sido
aprovado. Reconstruído sobre jun a 19/10/2026: 184 reenvios de documento já
aprovado pelo revisor — 74 pelo pedido do BRNET, 101 por CPF + empresa, 9 pelo
arquivo —, dos quais 109 tinham sido aprovados de novo e 72 rejeitados.

O que não pode cair: CPF "Não encontrado" (207 documentos no período) não
casa com outro "Não encontrado" da mesma empresa — era o que inflava a primeira
estimativa por SQL da regra de CPF + empresa.

Rodar sem o conftest, que importa main.py e exige DATABASE_URL:

    PYTHONPATH=back-end pytest back-end/tests/test_reenvio_liberado.py -q --noconftest
"""
import importlib
import sys
import types
from datetime import datetime, timedelta

import pytest

from app.models.document import pedido_exame_id_do_payload
from app.services import reenvio_service


@pytest.mark.parametrize("valor, esperado", [
    (4567890, 4567890),
    ("4567890", 4567890),
    (" 123 ", 123),
    ("C-252873", None),   # 9 documentos com o pedido nesse formato: tratados como sem pedido
    (None, None),
    (0, None),
    (True, None),
])
def test_le_o_pedido_do_brnet(valor, esperado):
    assert pedido_exame_id_do_payload({"brmed_result": {"pedido_exame_id": valor}}) == esperado


def test_payload_sem_pedido():
    assert pedido_exame_id_do_payload(None) is None
    assert pedido_exame_id_do_payload({"brmed_result": "erro"}) is None


class BancoFalso:
    def __init__(self, devolve=None, erro=None):
        self.recebido = None
        self.devolve = devolve
        self.erro = erro

    def buscar_liberado_anterior(self, **kwargs):
        self.recebido = kwargs
        if self.erro:
            raise self.erro
        return self.devolve


AGORA = datetime(2026, 10, 21, 12, 0)


def test_chaves_vao_limpas_para_a_consulta():
    banco = BancoFalso()
    reenvio_service.liberado_anterior(
        banco,
        {"brmed_result": {"pedido_exame_id": "987"}, "cnpj_processado": "12.345.678/0001-90"},
        cpf="057.002.317-35", content_hash="abc", agora=AGORA,
    )
    assert banco.recebido == {
        "content_hash": "abc",
        "pedido_exame_id": 987,
        "cpf": "05700231735",
        "cnpj_empresa": "12345678000190",
        "desde": AGORA - timedelta(days=30),
    }


@pytest.mark.parametrize("cpf", ["Não encontrado", "", None, "12345"])
def test_cpf_que_nao_e_cpf_nao_entra_na_regra_de_cpf_empresa(cpf):
    banco = BancoFalso()
    reenvio_service.liberado_anterior(banco, {"cnpj_processado": "12345678000190"}, cpf=cpf, content_hash=None, agora=AGORA)
    assert banco.recebido["cpf"] is None


def test_cnpj_incompleto_nao_entra():
    banco = BancoFalso()
    reenvio_service.liberado_anterior(banco, {"cnpj_processado": "1234"}, cpf="05700231735", content_hash=None, agora=AGORA)
    assert banco.recebido["cnpj_empresa"] is None


def test_devolve_o_liberado_encontrado():
    achado = {"documento_id": "d1", "liberado_em": "2026-10-15T10:00:00", "criterio": "pedido"}
    banco = BancoFalso(devolve=achado)
    assert reenvio_service.liberado_anterior(banco, {}, cpf=None, content_hash="abc", agora=AGORA) == achado


def test_falha_na_consulta_nao_derruba_o_envio():
    banco = BancoFalso(erro=RuntimeError("banco fora"))
    assert reenvio_service.liberado_anterior(banco, {}, cpf=None, content_hash="abc", agora=AGORA) is None


# ── filas ────────────────────────────────────────────────────────────────────

def carregar(monkeypatch):
    # Mesmo truque de test_filtro_data_envio.py: importar o router carrega
    # `app.api` inteiro, que cria cliente da OpenAI e exige a chave.
    monkeypatch.setenv("OPENAI_API_KEY", "chave-de-teste")
    import app.core.config as config
    for chave, valor in {"APP_ENV": "test", "JWT_SECRET_KEY": "x" * 40, "DEV_AUTH_BYPASS": False}.items():
        monkeypatch.setattr(config.settings, chave, valor, raising=False)
    falso = types.ModuleType("app.core.database")
    falso.user_db = object()
    monkeypatch.setitem(sys.modules, "app.core.database", falso)
    for nome in ("app.core.auth", "app.api.v1.documents"):
        sys.modules.pop(nome, None)
    return importlib.import_module("app.api.v1.documents")


def doc(did, status):
    enviado = datetime(2026, 10, 20, 12, 0)
    return types.SimpleNamespace(
        id=did, clinic_id="c1", filename="a.pdf", cpf="", uploaded_by_user_email="",
        result_payload={}, validation_status=status, reviewed_by=None,
        uploaded_at=enviado, updated_at=enviado,
    )


DOCS = [doc("liberado", "validated"), doc("pendente", "pending"), doc("rejeitado", "rejected"),
        doc("reenvio", "reenvio")]


@pytest.mark.parametrize("fila, esperados", [
    ("checagem", {"liberado", "pendente", "rejeitado"}),
    ("pendentes", {"pendente", "rejeitado"}),
    ("historico", {"liberado", "pendente", "rejeitado", "reenvio"}),
])
def test_reenvio_so_aparece_no_historico(monkeypatch, fila, esperados):
    mod = carregar(monkeypatch)
    pagina = mod._in_memory_paged_documents(
        DOCS, page=1, page_size=10, queue=mod.DocumentQueue(fila), status_filter=None, search=None,
        sort_by="uploaded_at", sort_dir="desc",
    )
    assert {d.id for d in pagina["items"]} == esperados


# ── ponta a ponta no processamento em segundo plano ──────────────────────────

class JobsFalsos:
    def __init__(self):
        self.concluido = None
        self.falhou = None

    async def start_job(self, job_id):
        pass

    async def create_progress_callback(self, job_id):
        async def progresso(*args, **kwargs):
            pass
        return progresso

    async def complete_job(self, job_id, resultado):
        self.concluido = resultado

    async def fail_job(self, job_id, erro):
        self.falhou = erro


class BancoDoJob:
    def __init__(self, liberado):
        self.liberado = liberado
        self.criado = None

    def buscar_liberado_anterior(self, **kwargs):
        return self.liberado

    def create_document(self, **kwargs):
        self.criado = kwargs
        return types.SimpleNamespace(id="novo-doc")

    def get_user_by_id(self, uid):
        return None

    def create_audit_log(self, entrada):
        pass

    def get_clinic_by_id(self, cid):
        return None


def processar(monkeypatch, tmp_path, liberado, resultado):
    monkeypatch.setenv("OPENAI_API_KEY", "chave-de-teste")
    import app.core.config as config
    for chave, valor in {"APP_ENV": "test", "JWT_SECRET_KEY": "x" * 40, "DEV_AUTH_BYPASS": False}.items():
        monkeypatch.setattr(config.settings, chave, valor, raising=False)
    banco = BancoDoJob(liberado)
    falso = types.ModuleType("app.core.database")
    falso.user_db = banco
    monkeypatch.setitem(sys.modules, "app.core.database", falso)
    for nome in ("app.core.auth", "app.api.v1_brmed"):
        sys.modules.pop(nome, None)
    mod = importlib.import_module("app.api.v1_brmed")
    jobs = JobsFalsos()
    monkeypatch.setattr(mod, "job_manager", jobs)
    monkeypatch.setattr(mod, "user_db", banco)

    async def processar_pdf(*args, **kwargs):
        return dict(resultado)

    monkeypatch.setattr(mod.workflow_service, "processar_documento_completo", processar_pdf)
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4 teste")
    import asyncio
    asyncio.run(mod.process_document_background(
        job_id="job-1", file_path=str(pdf), stored_path=None, filename="a.pdf", exames_obrigatorios=[],
        uploaded_by_user_id="u1", clinic_id="c1", clinic_cnpj=None, uploaded_by_user_email="u1@x.com",
        content_hash="abc",
    ))
    return banco, jobs


RESULTADO_APROVADO = {
    "status": "success",
    "cpf_processado": "05700231735",
    "brmed_result": {"pedido_exame_id": 987},
    "validation_result": {"exames_faltantes": []},
}


def test_reenvio_de_liberado_sai_como_reenvio_e_o_job_leva_o_aviso(monkeypatch, tmp_path):
    achado = {"documento_id": "original", "liberado_em": "2026-10-15T13:00:00+00:00", "criterio": "pedido"}
    banco, jobs = processar(monkeypatch, tmp_path, achado, RESULTADO_APROVADO)
    assert banco.criado["validation_status"] == "reenvio"
    assert banco.criado["reenvio_de"] == "original"
    assert jobs.concluido["reenvio"] == achado
    assert jobs.falhou is None


def test_reenvio_com_expedicao_fechada_nao_vira_rejeicao(monkeypatch, tmp_path):
    """O BRNET recusa ("expedição em aberto não encontrada") porque o pedido já fechou."""
    resultado = {"status": "error", "erro": "Expedição em aberto não encontrada para o paciente informado.",
                 "cpf_processado": "05700231735", "cnpj_processado": "12345678000190"}
    achado = {"documento_id": "original", "liberado_em": "2026-10-15T13:00:00+00:00", "criterio": "cpf_empresa"}
    banco, jobs = processar(monkeypatch, tmp_path, achado, resultado)
    assert banco.criado["validation_status"] == "reenvio"
    assert banco.criado["rejection_reason"] is None


def test_envio_novo_segue_como_sempre(monkeypatch, tmp_path):
    banco, jobs = processar(monkeypatch, tmp_path, None, RESULTADO_APROVADO)
    assert banco.criado["validation_status"] == "validated"
    assert banco.criado["reenvio_de"] is None
    assert "reenvio" not in jobs.concluido
