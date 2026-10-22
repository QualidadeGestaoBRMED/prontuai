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


@pytest.fixture(autouse=True)
def nomes_simples(monkeypatch):
    # O canônico de verdade passa pelo catálogo (validacao_service carrega o
    # índice FAISS no import); aqui basta o nome em caixa alta.
    monkeypatch.setattr(reenvio_service, "_canonico", lambda nome: nome.strip().upper())


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
        cpf="057.002.317-35", content_hash="abc", clinic_id="c1", agora=AGORA,
    )
    assert banco.recebido == {
        "content_hash": "abc",
        "pedido_exame_id": 987,
        "cpf": "05700231735",
        "cnpj_empresa": "12345678000190",
        "clinic_id": "c1",
        "desde": AGORA - timedelta(days=30),
    }


@pytest.mark.parametrize("cpf", ["Não encontrado", "", None, "12345"])
def test_cpf_que_nao_e_cpf_nao_entra_na_regra_de_cpf_empresa(cpf):
    banco = BancoFalso()
    reenvio_service.liberado_anterior(banco, {"cnpj_processado": "12345678000190"}, cpf=cpf, content_hash=None, clinic_id="c1", agora=AGORA)
    assert banco.recebido["cpf"] is None


def test_cnpj_incompleto_nao_entra():
    banco = BancoFalso()
    reenvio_service.liberado_anterior(banco, {"cnpj_processado": "1234"}, cpf="05700231735", content_hash=None, clinic_id="c1", agora=AGORA)
    assert banco.recebido["cnpj_empresa"] is None


def test_devolve_o_liberado_encontrado():
    achado = {"documento_id": "d1", "liberado_em": "2026-10-15T10:00:00", "criterio": "pedido"}
    banco = BancoFalso(devolve=achado)
    assert reenvio_service.liberado_anterior(banco, {}, cpf=None, content_hash="abc", clinic_id="c1", agora=AGORA) == achado


def test_falha_na_consulta_nao_derruba_o_envio():
    banco = BancoFalso(erro=RuntimeError("banco fora"))
    assert reenvio_service.liberado_anterior(banco, {}, cpf=None, content_hash="abc", clinic_id="c1", agora=AGORA) is None


# ── complemento: uma expedição pode ter vários prontuários ───────────────────

def liberado(criterio="pedido", exames=(), faltantes=()):
    return {
        "documento_id": "d1", "liberado_em": "2026-10-15T10:00:00+00:00", "criterio": criterio,
        "exames": list(exames), "faltantes": list(faltantes),
    }


def envio(*exames):
    return {"exames_ocr": list(exames)}


def detectar(anterior, resultado):
    return reenvio_service.liberado_anterior(
        BancoFalso(devolve=anterior), resultado, cpf=None, content_hash="abc", clinic_id="c1", agora=AGORA
    )


def test_mesmos_exames_e_reenvio():
    achado = detectar(liberado(exames=["CLINICO OCUPACIONAL", "AUDIOMETRIA"]), envio("clinico ocupacional"))
    # Exames e faltantes servem só para decidir; não vão para o resultado.
    assert achado == {"documento_id": "d1", "liberado_em": "2026-10-15T10:00:00+00:00", "criterio": "pedido"}


def test_exame_a_mais_nao_basta_para_ser_complemento():
    """O mesmo arquivo reprocessado sai com 2+ exames diferentes em 4 de 9 casos."""
    assert detectar(liberado(exames=["CLINICO OCUPACIONAL"]), envio("CLINICO OCUPACIONAL", "ACUIDADE VISUAL"))


def test_traz_exame_que_faltava_no_liberado_e_complemento():
    anterior = liberado(exames=["CLINICO OCUPACIONAL"], faltantes=["AUDIOMETRIA", "ESPIROMETRIA"])
    assert detectar(anterior, envio("CLINICO OCUPACIONAL", "AUDIOMETRIA")) is None


def test_faltante_que_outro_liberado_ja_trouxe_nao_conta():
    # Dois liberados do mesmo pedido: o segundo cobriu o que faltava no primeiro.
    anterior = liberado(exames=["CLINICO OCUPACIONAL", "AUDIOMETRIA"], faltantes=["AUDIOMETRIA"])
    assert detectar(anterior, envio("CLINICO OCUPACIONAL", "AUDIOMETRIA"))


def test_nenhum_exame_em_comum_e_complemento():
    """Outra parte da expedição — o laudo de laboratório depois do ASO."""
    assert detectar(liberado(exames=["CLINICO OCUPACIONAL", "ECG"]), envio("GLICEMIA DE JEJUM")) is None


def test_mesmo_arquivo_e_reenvio_mesmo_lendo_outros_exames():
    assert detectar(liberado(criterio="arquivo", exames=["CLINICO OCUPACIONAL"]), envio("GLICEMIA DE JEJUM"))


def test_envio_sem_exame_lido_fica_como_reenvio():
    assert detectar(liberado(exames=["CLINICO OCUPACIONAL"]), envio())


def test_exames_vem_do_ocr_quando_o_resultado_nao_tem_a_lista():
    resultado = {"ocr_result": {"exames_extraidos": [{"nome": "GLICEMIA DE JEJUM"}]}}
    assert detectar(liberado(exames=["CLINICO OCUPACIONAL"]), resultado) is None


@pytest.mark.parametrize("status_ia, motivo, motivo_gravado", [
    ("rejected", "Expedição em aberto não encontrada", "Expedição em aberto não encontrada"),
    ("validated", "qualquer", None),
    ("pending", None, None),
])
def test_marcar_guarda_a_decisao_da_ia(status_ia, motivo, motivo_gravado):
    resultado = {}
    reenvio_service.marcar(resultado, {"documento_id": "d1"}, status_ia=status_ia, motivo_ia=motivo)
    assert resultado["reenvio"] == {"documento_id": "d1", "status_ia": status_ia, "motivo_ia": motivo_gravado}


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
        self.busca = None

    def buscar_liberado_anterior(self, **kwargs):
        self.busca = kwargs
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
    assert jobs.concluido["reenvio"] == {**achado, "status_ia": "validated", "motivo_ia": None}
    assert jobs.falhou is None
    # A clínica do envio entra na busca: pedido e CPF + empresa só casam com ela.
    assert banco.busca["clinic_id"] == "c1"


def test_reenvio_com_expedicao_fechada_nao_vira_rejeicao(monkeypatch, tmp_path):
    """O BRNET recusa ("expedição em aberto não encontrada") porque o pedido já fechou."""
    resultado = {"status": "error", "erro": "Expedição em aberto não encontrada para o paciente informado.",
                 "cpf_processado": "05700231735", "cnpj_processado": "12345678000190"}
    achado = {"documento_id": "original", "liberado_em": "2026-10-15T13:00:00+00:00", "criterio": "cpf_empresa"}
    banco, jobs = processar(monkeypatch, tmp_path, achado, resultado)
    assert banco.criado["validation_status"] == "reenvio"
    assert banco.criado["rejection_reason"] is None
    # Se for complemento, o documento volta a ser a rejeição que a IA tinha dado.
    assert jobs.concluido["reenvio"]["status_ia"] == "rejected"
    assert jobs.concluido["reenvio"]["motivo_ia"] == resultado["erro"]


def test_envio_novo_segue_como_sempre(monkeypatch, tmp_path):
    banco, jobs = processar(monkeypatch, tmp_path, None, RESULTADO_APROVADO)
    assert banco.criado["validation_status"] == "validated"
    assert banco.criado["reenvio_de"] is None
    assert "reenvio" not in jobs.concluido


# ── "É um complemento": devolver o reenvio à Checagem ────────────────────────

class BancoDoComplemento:
    def __init__(self, documento):
        self.documento = documento
        self.desfeito_por = None

    def get_document_by_id(self, did):
        return self.documento if self.documento and self.documento.id == did else None

    def desfazer_reenvio(self, did, *, por):
        self.desfeito_por = por
        return types.SimpleNamespace(id=did, validation_status="rejected")


def usuario(*papeis, clinic_id="c1"):
    return types.SimpleNamespace(
        email="quem@clinica.com", clinic_id=clinic_id, tem_papel=lambda *pedidos: bool(set(papeis) & set(pedidos))
    )


def complemento(monkeypatch, documento, user):
    import asyncio
    mod = carregar(monkeypatch)
    banco = BancoDoComplemento(documento)
    monkeypatch.setattr(mod, "user_db", banco)
    request = types.SimpleNamespace(state=types.SimpleNamespace())
    resposta = asyncio.run(mod.marcar_como_complemento("doc-1", request, current_user=user))
    return banco, request, resposta


def documento(status="reenvio", clinic_id="c1"):
    return types.SimpleNamespace(id="doc-1", clinic_id=clinic_id, validation_status=status, reenvio_de="original")


def test_clinica_devolve_o_proprio_reenvio(monkeypatch):
    from app.models.user import UserRole
    banco, request, resposta = complemento(monkeypatch, documento(), usuario(UserRole.SENDER))
    assert banco.desfeito_por == "quem@clinica.com"
    assert resposta.validation_status == "rejected"
    assert request.state.audit["action"] == "documents.reenvio.complemento"
    assert request.state.audit["metadata"]["reenvio_de"] == "original"


def test_clinica_nao_mexe_em_documento_de_outra(monkeypatch):
    from fastapi import HTTPException
    from app.models.user import UserRole
    with pytest.raises(HTTPException) as erro:
        complemento(monkeypatch, documento(clinic_id="outra"), usuario(UserRole.SENDER))
    assert erro.value.status_code == 403


def test_revisor_devolve_reenvio_de_qualquer_clinica(monkeypatch):
    from app.models.user import UserRole
    banco, _, _ = complemento(monkeypatch, documento(clinic_id="outra"), usuario(UserRole.CHECKER, clinic_id=None))
    assert banco.desfeito_por == "quem@clinica.com"


def test_so_reenvio_pode_virar_complemento(monkeypatch):
    from fastapi import HTTPException
    from app.models.user import UserRole
    with pytest.raises(HTTPException) as erro:
        complemento(monkeypatch, documento(status="validated"), usuario(UserRole.ADMIN))
    assert erro.value.status_code == 409
