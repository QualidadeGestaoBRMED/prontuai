"""
Envio do mesmo arquivo pelo mesmo usuário (duplicidade "hard", UPLOAD_DEDUP_HARD).

Caso de 11/11/2026: a clínica reenviou, idênticos, dois prontuários que o
revisor tinha rejeitado. O upload devolvia o resultado antigo da IA e não
criava documento: a tela da clínica mostrava "Aguardando Revisão" e a operação
só achava o envio rejeitado.

Agora o original rejeitado pelo revisor não segura o envio — ele é processado
como documento novo. Nos outros casos o envio continua sem documento novo, mas
o resultado sai marcado como reenvio, para a tela mostrar a situação real.
"""
import asyncio
import importlib
import io
import sys
import types
from datetime import datetime

from starlette.datastructures import Headers, UploadFile

from app.models.user import UserRole

PAYLOAD_DA_IA = {"status": "success", "decisao_final": "Faltam exames obrigatórios: ANTI-HBS"}


def documento(validation_status, reviewed_by=None, reviewed_at=None):
    return types.SimpleNamespace(
        id="original",
        filename="prontuario.pdf",
        validation_status=validation_status,
        reviewed_by=reviewed_by,
        reviewed_at=reviewed_at,
        uploaded_at=datetime(2026, 11, 5, 17, 47),
        result_payload=dict(PAYLOAD_DA_IA),
    )


class Banco:
    def __init__(self, existente):
        self.existente = existente

    def get_document_by_hash(self, **kwargs):
        return self.existente

    def get_recent_document_by_hash(self, **kwargs):
        return None

    def get_clinic_by_id(self, cid):
        return None


class Jobs:
    def __init__(self):
        self.criados = []
        self.concluidos = {}

    async def create_job(self, job_type, metadata):
        self.criados.append(metadata)
        return f"job-{len(self.criados)}"

    async def complete_job(self, job_id, resultado):
        self.concluidos[job_id] = resultado


class ThreadFalsa:
    iniciadas = []

    def __init__(self, target=None, kwargs=None, **_):
        self.kwargs = kwargs or {}
        self.name = "thread-falsa"

    def start(self):
        ThreadFalsa.iniciadas.append(self.kwargs)


def enviar(monkeypatch, existente):
    monkeypatch.setenv("OPENAI_API_KEY", "chave-de-teste")
    monkeypatch.setenv("UPLOAD_DEDUP_HARD", "true")
    monkeypatch.setenv("UPLOAD_DEDUP_WINDOW_SECONDS", "120")
    import app.core.config as config
    for chave, valor in {"APP_ENV": "test", "JWT_SECRET_KEY": "x" * 40, "DEV_AUTH_BYPASS": False}.items():
        monkeypatch.setattr(config.settings, chave, valor, raising=False)
    banco = Banco(existente)
    falso = types.ModuleType("app.core.database")
    falso.user_db = banco
    monkeypatch.setitem(sys.modules, "app.core.database", falso)
    for nome in ("app.core.auth", "app.api.v1_brmed"):
        sys.modules.pop(nome, None)
    mod = importlib.import_module("app.api.v1_brmed")
    jobs = Jobs()
    monkeypatch.setattr(mod, "job_manager", jobs)
    monkeypatch.setattr(mod, "user_db", banco)
    monkeypatch.setattr(mod, "_store_upload_file", lambda *a, **k: None)
    ThreadFalsa.iniciadas = []
    monkeypatch.setattr(mod.threading, "Thread", ThreadFalsa)

    arquivo = UploadFile(
        file=io.BytesIO(b"%PDF-1.4 mesmo arquivo"),
        filename="prontuario.pdf",
        headers=Headers({"content-type": "application/pdf"}),
    )
    usuario = types.SimpleNamespace(id="u1", email="clinica@x.com", role=UserRole.SENDER, clinic_id="c1")
    resposta = asyncio.run(mod.processar_documento_async_api(arquivo=arquivo, exames_obrigatorios="[]", current_user=usuario))
    return mod, resposta, jobs


def test_mesmo_arquivo_de_rejeitado_pelo_revisor_vira_envio_novo(monkeypatch):
    original = documento("rejected", reviewed_by="revisor@grupobrmed.com.br", reviewed_at=datetime(2026, 11, 10, 12, 45))
    _, resposta, jobs = enviar(monkeypatch, original)

    assert resposta["status"] != "duplicate"
    # Nada reaproveitado: o job vai para o processamento, como um envio novo.
    assert jobs.concluidos == {}
    assert len(ThreadFalsa.iniciadas) == 1
    assert "duplicate_of" not in jobs.criados[0]


def test_mesmo_arquivo_em_revisao_continua_sem_documento_novo_e_marcado(monkeypatch):
    # Rejeitado só pela IA ainda espera o revisor: continua em revisão.
    original = documento("rejected")
    _, resposta, jobs = enviar(monkeypatch, original)

    assert resposta["status"] == "duplicate"
    assert resposta["message"] == "Este arquivo já foi enviado em 05/11/2026 e ainda aguarda revisão. Nenhum envio novo foi criado."
    assert ThreadFalsa.iniciadas == []
    resultado = jobs.concluidos[resposta["job_id"]]
    assert resultado["document_id"] == "original"
    assert resultado["reenvio"] == {
        "documento_id": "original",
        "liberado_em": None,
        "enviado_em": "2026-11-05T17:47:00+00:00",
        "criterio": "arquivo",
        "situacao": "em_revisao",
    }
    # O payload do original não é alterado.
    assert "reenvio" not in original.result_payload


def test_mesmo_arquivo_liberado_mostra_ja_revisado(monkeypatch):
    original = documento("validated", reviewed_by="revisor@grupobrmed.com.br", reviewed_at=datetime(2026, 11, 6, 9, 30))
    _, resposta, jobs = enviar(monkeypatch, original)

    assert resposta["status"] == "duplicate"
    assert resposta["message"] == "Este arquivo já foi enviado em 05/11/2026 e já foi revisado. Nenhum envio novo foi criado."
    reenvio = jobs.concluidos[resposta["job_id"]]["reenvio"]
    assert reenvio["situacao"] == "liberado"
    assert reenvio["liberado_em"] == "2026-11-06T09:30:00+00:00"


def test_arquivo_novo_segue_como_sempre(monkeypatch):
    _, resposta, jobs = enviar(monkeypatch, None)

    assert resposta["status"] != "duplicate"
    assert len(ThreadFalsa.iniciadas) == 1
    assert jobs.concluidos == {}
