"""Testes do parecer humano sobre o acerto da IA (modal do fim da checagem).

Rodar sem o conftest, que importa main.py e exige DATABASE_URL:

    PYTHONPATH=back-end pytest back-end/tests/test_document_feedback.py -q --noconftest
"""
import asyncio
import importlib
import sys
import types

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from app.models.feedback import (
    CATEGORIAS_DOCUMENTO,
    CATEGORIAS_EXAME,
    DocumentFeedback,
    DocumentFeedbackInput,
)
from app.models.user import User, UserRole


def usuario(uid, role):
    return User(id=uid, email=f"{uid}@grupobrmed.com.br", name=uid, role=role, is_active=True)


def documento(doc_id="doc1", reviewed_by="checador@grupobrmed.com.br"):
    return types.SimpleNamespace(
        id=doc_id, clinic_id="c1", clinic_name="Clínica 1", reviewed_by=reviewed_by
    )


def item(categoria="FALTANTE_INCORRETO", exame="Audiometria", **extra):
    return {"categoria": categoria, "exame": exame, **extra}


def entrada(status="IA_INCORRETA", itens=None, docs=None,
            notes="A audiometria estava no PDF."):
    """Parecer negativo completo; cada teste tira a peça que quer testar."""
    return DocumentFeedbackInput(
        status=status,
        issue_items=[item()] if itens is None else itens,
        document_issues=docs or [],
        notes=notes,
    )


def requisicao(document_id="doc1"):
    """Request de verdade, montado do escopo ASGI — o handler lê method/url/headers."""
    return Request(
        {
            "type": "http",
            "method": "PUT",
            "scheme": "http",
            "server": ("testserver", 80),
            "path": f"/v1/documents/{document_id}/feedback",
            "raw_path": f"/v1/documents/{document_id}/feedback".encode(),
            "query_string": b"",
            "headers": [(b"user-agent", b"pytest")],
            "client": ("127.0.0.1", 1234),
        }
    )


class BancoFalso:
    def __init__(self, documentos=(), feedbacks=None):
        self.documentos = {d.id: d for d in documentos}
        self.feedbacks = feedbacks or {}
        self.gravados = []
        self.auditorias = []
        self.itens_recebidos = []

    def create_audit_log(self, data):
        self.auditorias.append(data)
        return data

    def get_document_by_id(self, did):
        return self.documentos.get(did)

    def get_clinic_by_id(self, cid):
        return types.SimpleNamespace(id=cid, name="Clínica 1")

    def get_document_feedback(self, did):
        return self.feedbacks.get(did)

    def upsert_document_feedback(self, document_id, status, issue_categories, issue_items,
                                 document_issues, notes,
                                 reviewed_by_id=None, reviewed_by_email=None):
        # Guarda os dicts crus: é isso que vai para a coluna JSONB. O
        # DocumentFeedback abaixo reconverte para modelo, então assertar nele
        # testaria o Pydantic, não a fronteira handler → banco.
        self.itens_recebidos = list(issue_items)
        salvo = DocumentFeedback(
            id="fb1",
            document_id=document_id,
            status=status,
            issue_categories=issue_categories,
            issue_items=issue_items,
            document_issues=document_issues,
            notes=notes,
            reviewed_by_id=reviewed_by_id,
            reviewed_by_email=reviewed_by_email,
        )
        self.gravados.append(salvo)
        self.feedbacks[document_id] = salvo
        return salvo


def carregar(monkeypatch, banco):
    # Importar o router carrega `app.api` inteiro, e nesse caminho um cliente da
    # OpenAI é criado na importação e exige a chave. Sem isto o teste só passa em
    # máquina com `.env`. Mesmo truque de test_role_permissions.py.
    monkeypatch.setenv("OPENAI_API_KEY", "chave-de-teste")
    import app.core.config as config
    for chave, valor in {"APP_ENV": "test", "JWT_SECRET_KEY": "x" * 40, "DEV_AUTH_BYPASS": False}.items():
        monkeypatch.setattr(config.settings, chave, valor, raising=False)
    falso = types.ModuleType("app.core.database")
    falso.user_db = banco
    monkeypatch.setitem(sys.modules, "app.core.database", falso)
    for nome in ("app.core.auth", "app.api.v1.feedback"):
        sys.modules.pop(nome, None)
    return importlib.import_module("app.api.v1.feedback")


def salvar(mod, banco, payload, quem=None, doc_id="doc1"):
    return asyncio.run(
        mod.put_document_feedback(
            document_id=doc_id,
            payload=payload,
            request=requisicao(doc_id),
            current_user=quem or usuario("checador", UserRole.CHECKER),
        )
    )


# ── schema ───────────────────────────────────────────────────────────────────

def test_categoria_fora_da_lista_e_recusada():
    with pytest.raises(ValidationError):
        entrada(itens=[item(categoria="GHE")])


def test_categoria_de_documento_nao_entra_em_issue_items():
    """Elas não têm exame: aceitar aqui geraria item com exame inventado."""
    for codigo in CATEGORIAS_DOCUMENTO:
        with pytest.raises(ValidationError):
            entrada(itens=[item(categoria=codigo)])


def test_categoria_de_exame_nao_entra_em_document_issues():
    """E o contrário também: motivo de exame sem exame é o que queremos impedir."""
    with pytest.raises(ValidationError):
        entrada(docs=["FALTANTE_INCORRETO"])


def test_as_duas_familias_nao_se_cruzam():
    assert not (CATEGORIAS_EXAME & CATEGORIAS_DOCUMENTO)


def test_exame_vazio_e_recusado():
    """Motivo sem exame é o parecer solto que este formato existe para evitar."""
    with pytest.raises(ValidationError):
        entrada(itens=[item(exame="   ")])


def test_exame_perde_espaco_das_pontas():
    assert entrada(itens=[item(exame="  Audiometria  ")]).issue_items[0].exame == "Audiometria"


def test_par_repetido_e_descartado():
    """Mesmo (motivo, exame) duas vezes inflaria a contagem do painel."""
    dados = entrada(itens=[item(), item(), item(exame="AUDIOMETRIA")])
    assert len(dados.issue_items) == 1


def test_mesmo_exame_sob_motivos_diferentes_e_permitido():
    """Um exame pode ter dois problemas de uma vez."""
    dados = entrada(
        itens=[
            item(categoria="FALTANTE_INCORRETO", exame="Audiometria"),
            item(categoria="SINONIMO_NAO_RECONHECIDO", exame="Audiometria"),
        ]
    )
    assert len(dados.issue_items) == 2


def test_problema_de_documento_sozinho_e_parecer_valido(monkeypatch):
    """Nome corrompido é erro real da IA e não tem exame a que amarrar — foi por
    isto que as categorias de documento voltaram."""
    banco = BancoFalso([documento()])
    mod = carregar(monkeypatch, banco)
    salvo = salvar(mod, banco, entrada(
        itens=[], docs=["OCR_NOME"], notes="Nome veio embaralhado no OCR."))
    assert salvo.status == "IA_INCORRETA"
    assert salvo.document_issues == ["OCR_NOME"]
    assert salvo.issue_items == []


def test_categorias_derivadas_juntam_as_duas_familias():
    dados = entrada(
        itens=[item(categoria="EXTRA_INCORRETO", exame="Glicemia")],
        docs=["OCR_NOME", "OCR_CPF"],
    )
    assert dados.categorias() == ["EXTRA_INCORRETO", "OCR_NOME", "OCR_CPF"]


def test_problemas_de_documento_deduplicam():
    assert entrada(docs=["OCR_NOME", "OCR_NOME"]).document_issues == ["OCR_NOME"]


def test_categorias_sao_derivadas_dos_itens():
    dados = entrada(
        itens=[
            item(categoria="EXTRA_INCORRETO", exame="Glicemia"),
            item(categoria="FALTANTE_INCORRETO", exame="Audiometria"),
            item(categoria="EXTRA_INCORRETO", exame="Hemograma"),
        ]
    )
    # Distintas, na ordem em que o revisor marcou.
    assert dados.categorias() == ["EXTRA_INCORRETO", "FALTANTE_INCORRETO"]


def test_notas_so_de_espaco_viram_none():
    assert DocumentFeedbackInput(status="IA_CORRETA", notes="   ").notes is None


def test_status_invalido_e_recusado():
    with pytest.raises(ValidationError):
        DocumentFeedbackInput(status="NAO_AVALIADO")


# ── regra de negócio ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("status", ["IA_CORRETA_COM_AJUSTES", "IA_INCORRETA"])
def test_parecer_negativo_sem_nada_apontado_da_422(monkeypatch, status):
    """Nem exame, nem problema de documento: não há o que medir."""
    banco = BancoFalso([documento()])
    mod = carregar(monkeypatch, banco)
    with pytest.raises(HTTPException) as exc:
        salvar(mod, banco, entrada(status=status, itens=[], docs=[]))
    assert exc.value.status_code == 422
    assert not banco.gravados


@pytest.mark.parametrize("status", ["IA_CORRETA_COM_AJUSTES", "IA_INCORRETA"])
def test_parecer_negativo_sem_descricao_da_422(monkeypatch, status):
    banco = BancoFalso([documento()])
    mod = carregar(monkeypatch, banco)
    with pytest.raises(HTTPException) as exc:
        salvar(mod, banco, entrada(status=status, notes=None))
    assert exc.value.status_code == 422


def test_parecer_de_acerto_com_problema_da_422(monkeypatch):
    """'A IA acertou' com exame apontado junto é contradição, não observação."""
    banco = BancoFalso([documento()])
    mod = carregar(monkeypatch, banco)
    with pytest.raises(HTTPException) as exc:
        salvar(mod, banco, DocumentFeedbackInput(status="IA_CORRETA", issue_items=[item()]))
    assert exc.value.status_code == 422


def test_acerto_com_problema_de_documento_junto_tambem_da_422(monkeypatch):
    banco = BancoFalso([documento()])
    mod = carregar(monkeypatch, banco)
    with pytest.raises(HTTPException) as exc:
        salvar(mod, banco, DocumentFeedbackInput(
            status="IA_CORRETA", document_issues=["OCR_NOME"]))
    assert exc.value.status_code == 422


def test_caminho_feliz_grava_itens_e_autor(monkeypatch):
    banco = BancoFalso([documento()])
    mod = carregar(monkeypatch, banco)
    salvo = salvar(
        mod, banco,
        entrada(itens=[
            item(exame="Audiometria", veredito_ia="faltante"),
            item(categoria="EXTRA_INCORRETO", exame="Glicemia", veredito_ia="extra_no_ocr"),
        ]),
    )
    assert salvo.status == "IA_INCORRETA"
    assert salvo.reviewed_by_email == "checador@grupobrmed.com.br"
    assert [i["exame"] for i in banco.itens_recebidos] == ["Audiometria", "Glicemia"]
    assert banco.gravados[-1].issue_categories == ["FALTANTE_INCORRETO", "EXTRA_INCORRETO"]


def test_veredito_da_ia_fica_junto_do_item(monkeypatch):
    """O result_payload pode ser reprocessado; sem isto não dá para saber o que a
    IA dizia quando o revisor discordou."""
    banco = BancoFalso([documento()])
    mod = carregar(monkeypatch, banco)
    salvar(mod, banco, entrada(itens=[item(exame="Audiometria", veredito_ia="faltante")]))
    assert banco.itens_recebidos[0]["veredito_ia"] == "faltante"


def test_exame_digitado_fica_marcado_como_fora_da_lista(monkeypatch):
    """Texto livre não casa com o catálogo: estes itens precisam de curadoria."""
    banco = BancoFalso([documento()])
    mod = carregar(monkeypatch, banco)
    salvar(mod, banco, entrada(itens=[
        item(categoria="EXAME_NAO_RECONHECIDO", exame="Raio-X de tórax", fora_da_lista=True),
    ]))
    gravado = banco.itens_recebidos[0]
    assert gravado["fora_da_lista"] is True
    assert gravado["veredito_ia"] is None


def test_acerto_simples_dispensa_detalhes(monkeypatch):
    banco = BancoFalso([documento()])
    mod = carregar(monkeypatch, banco)
    salvo = salvar(mod, banco, DocumentFeedbackInput(status="IA_CORRETA"))
    assert salvo.issue_categories == []
    assert salvo.issue_items == []
    assert salvo.notes is None


def test_reavaliar_substitui_em_vez_de_acumular(monkeypatch):
    """PUT é idempotente: um parecer por documento, o segundo reescreve o primeiro.

    A UI não alcança isso hoje (o modal só abre na decisão, e um documento
    decidido não volta para a fila), mas o contrato do endpoint é este — e é o
    que impede um retry de rede de gerar duas linhas."""
    banco = BancoFalso([documento()])
    mod = carregar(monkeypatch, banco)
    salvar(mod, banco, entrada())
    salvar(mod, banco, DocumentFeedbackInput(status="IA_CORRETA"))
    assert banco.feedbacks["doc1"].status == "IA_CORRETA"
    assert banco.feedbacks["doc1"].issue_items == []


def test_documento_inexistente_da_404(monkeypatch):
    banco = BancoFalso()
    mod = carregar(monkeypatch, banco)
    with pytest.raises(HTTPException) as exc:
        salvar(mod, banco, DocumentFeedbackInput(status="IA_CORRETA"), doc_id="fantasma")
    assert exc.value.status_code == 404


def test_documento_sem_decisao_humana_da_409(monkeypatch):
    """O parecer compara a IA com a conclusão do revisor; sem decisão não há par."""
    banco = BancoFalso([documento(reviewed_by=None)])
    mod = carregar(monkeypatch, banco)
    with pytest.raises(HTTPException) as exc:
        salvar(mod, banco, DocumentFeedbackInput(status="IA_CORRETA"))
    assert exc.value.status_code == 409


def test_get_de_documento_nunca_avaliado_devolve_none(monkeypatch):
    banco = BancoFalso([documento()])
    mod = carregar(monkeypatch, banco)
    resultado = asyncio.run(
        mod.get_document_feedback(
            document_id="doc1", current_user=usuario("checador", UserRole.CHECKER)
        )
    )
    assert resultado is None


# ── auditoria ────────────────────────────────────────────────────────────────

def test_auditoria_carrega_os_exames_mas_nunca_o_texto_do_revisor(monkeypatch):
    """Nome de exame não é PII e é o que dá valor à trilha; `notes` pode ter
    nome/CPF de paciente, então entra só o tamanho."""
    banco = BancoFalso([documento()])
    mod = carregar(monkeypatch, banco)
    segredo = "Paciente Fulano de Tal, CPF 123.456.789-09, faltou audiometria"
    salvar(mod, banco, entrada(
        itens=[item(exame="Audiometria", veredito_ia="faltante")], notes=segredo))
    registro = banco.auditorias[-1]
    assert registro.action == "documents.feedback"
    assert registro.metadata["issue_items"][0]["exame"] == "Audiometria"
    assert registro.metadata["notes_len"] == len(segredo)
    assert "Fulano" not in repr(registro.metadata)
    assert "123.456.789" not in repr(registro.metadata)


def test_auditoria_registra_antes_e_depois_da_reavaliacao(monkeypatch):
    """A tabela guarda só a resposta corrente; quem reescreveu o quê sai daqui."""
    banco = BancoFalso([documento()])
    mod = carregar(monkeypatch, banco)
    salvar(mod, banco, entrada())
    salvar(mod, banco, DocumentFeedbackInput(status="IA_CORRETA"))

    primeira, segunda = banco.auditorias
    assert primeira.metadata["reavaliacao"] is False
    assert primeira.metadata["status_anterior"] is None
    assert segunda.metadata["reavaliacao"] is True
    assert segunda.metadata["status_anterior"] == "IA_INCORRETA"
    assert segunda.metadata["categorias_anteriores"] == ["FALTANTE_INCORRETO"]
    assert segunda.metadata["status"] == "IA_CORRETA"


def test_recusa_nao_gera_auditoria_de_parecer(monkeypatch):
    """422 não escreveu nada; uma linha 'documents.feedback' aqui seria mentira."""
    banco = BancoFalso([documento()])
    mod = carregar(monkeypatch, banco)
    with pytest.raises(HTTPException):
        salvar(mod, banco, entrada(itens=[], docs=[]))
    assert banco.auditorias == []


def test_falha_da_telemetria_nao_derruba_o_parecer(monkeypatch):
    """A clínica é buscada só para rotular a métrica; se o banco engasgar ali, o
    parecer já está commitado e um 500 faria o revisor responder tudo de novo."""
    banco = BancoFalso([documento()])

    def explode(_cid):
        raise RuntimeError("clinics fora do ar")

    banco.get_clinic_by_id = explode
    mod = carregar(monkeypatch, banco)
    salvo = salvar(mod, banco, DocumentFeedbackInput(status="IA_CORRETA"))
    assert salvo.status == "IA_CORRETA"
    # A trilha continua sendo escrita: só a métrica se perdeu.
    assert banco.auditorias[-1].action == "documents.feedback"


def test_falha_da_auditoria_nao_derruba_o_parecer(monkeypatch):
    """O parecer já está commitado quando a trilha é escrita: perder a trilha
    não pode virar 500 e fazer o revisor achar que não salvou."""
    banco = BancoFalso([documento()])

    def explode(_data):
        raise RuntimeError("banco de auditoria fora do ar")

    banco.create_audit_log = explode
    mod = carregar(monkeypatch, banco)
    salvo = salvar(mod, banco, DocumentFeedbackInput(status="IA_CORRETA"))
    assert salvo.status == "IA_CORRETA"


# ── contrato com o front ─────────────────────────────────────────────────────

def test_categorias_do_back_batem_com_as_do_front():
    """`front-end/types/feedback.ts` é a outra metade desta lista; mudar uma só
    deixa o revisor marcando chip que a API recusa (ou escondendo categoria válida)."""
    import pathlib
    import re

    arquivo = (
        pathlib.Path(__file__).resolve().parents[2]
        / "front-end" / "types" / "feedback.ts"
    )
    if not arquivo.exists():  # pragma: no cover - back-end publicado sozinho
        pytest.skip("front-end não está neste checkout")
    texto = arquivo.read_text(encoding="utf-8")
    de_exame = texto.split("CATEGORIAS_EXAME")[1].split("CATEGORIAS_DOCUMENTO")[0]
    de_documento = texto.split("CATEGORIAS_DOCUMENTO")[1]
    achar = lambda bloco: set(re.findall(r'valor:\s*"([A-Z_]+)"', bloco))
    assert achar(de_exame) == set(CATEGORIAS_EXAME)
    assert achar(de_documento) == set(CATEGORIAS_DOCUMENTO)
