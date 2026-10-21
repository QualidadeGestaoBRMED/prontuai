"""Filtro por previsão de liberação da Checagem — `GET /v1/documents/paged`.

**Por que existe.** A previsão vem do BRNET dentro de `result_payload`, como
texto "dd/mm/aaaa", e a coluna `data_previsao_liberacao` (migration 013) é uma
cópia dela para o filtro não ler JSON a cada consulta. Se a leitura da data
divergir entre a gravação e o filtro em memória, ou se uma ponta do intervalo
deixar de ser inclusa, o "vence hoje" da tela some com os documentos de hoje.

Rodar sem o conftest, que importa main.py e exige DATABASE_URL:

    PYTHONPATH=back-end pytest back-end/tests/test_filtro_previsao_liberacao.py -q --noconftest
"""
import asyncio
import importlib
import sys
import types
from datetime import date, datetime

import pytest
from fastapi import HTTPException

from app.models.document import previsao_liberacao_do_payload
from app.models.user import User, UserRole


def payload(previsao):
    return {"brmed_result": {"data_previsao_liberacao": previsao}}


# ── leitura da data ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("bruto, esperado", [
    ("20/10/2026", date(2026, 10, 20)),
    (" 20/10/2026 ", date(2026, 10, 20)),
    ("2025-07-08", date(2025, 7, 8)),      # os dois documentos de 2025 vieram em ISO
    ("31/02/2026", None),                  # o to_date do Postgres levantaria erro aqui
    ("", None),
    (None, None),
])
def test_le_a_previsao_do_brnet(bruto, esperado):
    assert previsao_liberacao_do_payload(payload(bruto)) == esperado


@pytest.mark.parametrize("resultado", [None, "texto", {}, {"brmed_result": None}, {"brmed_result": "x"}])
def test_payload_sem_previsao_nao_quebra(resultado):
    assert previsao_liberacao_do_payload(resultado) is None


# ── rota ─────────────────────────────────────────────────────────────────────

class BancoFalso:
    def __init__(self):
        self.recebido = None

    def list_documents_paged(self, **kwargs):
        self.recebido = kwargs
        return {"items": [], "page": 1, "page_size": 10, "total_items": 0,
                "total_pages": 1, "has_next": False, "summary_counts": {}}


def carregar(monkeypatch, banco):
    # Mesmo truque de test_filtro_data_envio.py: importar o router carrega
    # `app.api` inteiro, que cria cliente da OpenAI e exige a chave.
    monkeypatch.setenv("OPENAI_API_KEY", "chave-de-teste")
    import app.core.config as config
    for chave, valor in {"APP_ENV": "test", "JWT_SECRET_KEY": "x" * 40, "DEV_AUTH_BYPASS": False}.items():
        monkeypatch.setattr(config.settings, chave, valor, raising=False)
    falso = types.ModuleType("app.core.database")
    falso.user_db = banco
    monkeypatch.setitem(sys.modules, "app.core.database", falso)
    for nome in ("app.core.auth", "app.api.v1.documents"):
        sys.modules.pop(nome, None)
    return importlib.import_module("app.api.v1.documents")


def listar(mod, previsao_from=None, previsao_to=None):
    checador = User(id="u1", email="u1@grupobrmed.com.br", name="u1",
                    role=UserRole.CHECKER, is_active=True)
    return asyncio.run(
        mod.list_documents_paged(
            current_user=checador, queue=None, compact=True, page=1, page_size=10,
            search=None, status_filter=None, sort_by="uploaded_at", sort_dir="desc",
            filter_clinic_id=None, uploaded_from=None, uploaded_to=None,
            previsao_from=previsao_from, previsao_to=previsao_to,
        )
    )


def test_datas_chegam_ao_banco_sem_conversao(monkeypatch):
    """Data de calendário: nada de fuso, ao contrário da data de envio."""
    banco = BancoFalso()
    mod = carregar(monkeypatch, banco)
    listar(mod, previsao_from=date(2026, 10, 20), previsao_to=date(2026, 10, 26))
    assert banco.recebido["previsao_from"] == date(2026, 10, 20)
    assert banco.recebido["previsao_to"] == date(2026, 10, 26)


def test_uma_ponta_so_e_aceita(monkeypatch):
    """"Atrasados" é só o fim: tudo com previsão até ontem."""
    banco = BancoFalso()
    mod = carregar(monkeypatch, banco)
    listar(mod, previsao_to=date(2026, 10, 19))
    assert banco.recebido["previsao_from"] is None
    assert banco.recebido["previsao_to"] == date(2026, 10, 19)


def test_mesmo_dia_nas_duas_pontas_vale(monkeypatch):
    banco = BancoFalso()
    mod = carregar(monkeypatch, banco)
    listar(mod, previsao_from=date(2026, 10, 20), previsao_to=date(2026, 10, 20))
    assert banco.recebido["previsao_to"] == date(2026, 10, 20)


def test_intervalo_invertido_da_422(monkeypatch):
    banco = BancoFalso()
    mod = carregar(monkeypatch, banco)
    with pytest.raises(HTTPException) as erro:
        listar(mod, previsao_from=date(2026, 10, 21), previsao_to=date(2026, 10, 20))
    assert erro.value.status_code == 422
    assert banco.recebido is None


# ── caminho em memória ───────────────────────────────────────────────────────

def doc(did, previsao):
    enviado = datetime(2026, 10, 1, 12, 0)
    return types.SimpleNamespace(
        id=did, clinic_id="c1", filename="a.pdf", cpf="", uploaded_by_user_email="",
        result_payload=payload(previsao), validation_status="pending", reviewed_by=None,
        uploaded_at=enviado, updated_at=enviado,
    )


DOCS = [
    doc("ontem", "19/10/2026"),
    doc("hoje", "20/10/2026"),
    doc("amanha", "21/10/2026"),
    doc("sem_previsao", None),
    doc("invalida", "31/02/2026"),
]


def paginar(mod, **filtros):
    return mod._in_memory_paged_documents(
        DOCS, page=1, page_size=10, queue=None, status_filter=None, search=None,
        sort_by="uploaded_at", sort_dir="asc", **filtros,
    )


def test_caminho_em_memoria_inclui_as_duas_pontas(monkeypatch):
    mod = carregar(monkeypatch, BancoFalso())
    pagina = paginar(mod, previsao_from=date(2026, 10, 20), previsao_to=date(2026, 10, 21))
    assert {d.id for d in pagina["items"]} == {"hoje", "amanha"}
    # Os cards de contagem saem do mesmo recorte.
    assert pagina["summary_counts"]["total"] == 2


def test_caminho_em_memoria_so_com_o_fim_deixa_de_fora_quem_nao_tem_previsao(monkeypatch):
    mod = carregar(monkeypatch, BancoFalso())
    pagina = paginar(mod, previsao_to=date(2026, 10, 19))
    assert {d.id for d in pagina["items"]} == {"ontem"}


def test_sem_filtro_de_previsao_ninguem_sai(monkeypatch):
    mod = carregar(monkeypatch, BancoFalso())
    assert paginar(mod)["summary_counts"]["total"] == len(DOCS)


# ── ordenação pela previsão ──────────────────────────────────────────────────

def test_ordem_pela_previsao_desempata_pelo_envio_mais_recente(monkeypatch):
    """Atrasado primeiro; no mesmo dia, o enviado por último; sem previsão no fim.

    O desempate não é cosmético: com centenas de documentos no mesmo dia, a
    paginação por OFFSET sem ele repete ou pula linhas.
    """
    mod = carregar(monkeypatch, BancoFalso())

    def enviado(did, previsao, hora):
        d = doc(did, previsao)
        d.uploaded_at = d.updated_at = datetime(2026, 10, 19, hora, 0)
        return d

    docs = [
        enviado("dia21_cedo", "21/10/2026", 8),
        enviado("sem_previsao", None, 23),
        enviado("dia20", "20/10/2026", 9),
        enviado("dia21_tarde", "21/10/2026", 17),
        enviado("atrasado", "15/10/2026", 10),
    ]
    pagina = mod._in_memory_paged_documents(
        docs, page=1, page_size=10, queue=None, status_filter=None, search=None,
        sort_by="previsao", sort_dir="asc",
    )
    assert [d.id for d in pagina["items"]] == [
        "atrasado", "dia20", "dia21_tarde", "dia21_cedo", "sem_previsao",
    ]
