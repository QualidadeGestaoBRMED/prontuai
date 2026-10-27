"""
Rotas do atalho até o PDF: onde cada exame está (`/localizacoes`) e o texto do
OCR com a posição de cada linha (`/texto`), que a busca do visualizador usa.

As duas leem o layout gravado pelo OCR e o pareiam com o markdown; sem layout,
respondem `disponivel: false` e a tela segue como era.
"""
import importlib
import sys
import types

import pytest
from fastapi import HTTPException

from app.models.user import User, UserRole
from app.services import layout_ocr
from app.services.ocr_service import textract_to_markdown


def _bb(x, y, w, h):
    return {"Geometry": {"BoundingBox": {"Left": x, "Top": y, "Width": w, "Height": h}}}


def _resposta(*linhas):
    """Resposta do Textract: cada linha (texto, y), palavras de 0,01 por letra."""
    blocos = []
    for n, (texto, y) in enumerate(linhas):
        ids, x = [], 0.1
        for m, palavra in enumerate(texto.split()):
            ids.append(f"w{n}-{m}")
            blocos.append({"BlockType": "WORD", "Id": f"w{n}-{m}", "Text": palavra, **_bb(x, y, 0.01 * len(palavra), 0.02)})
            x += 0.01 * len(palavra) + 0.01
        blocos.append({
            "BlockType": "LINE", "Id": f"l{n}", "Text": texto, **_bb(0.1, y, x - 0.11, 0.02),
            "Relationships": [{"Type": "CHILD", "Ids": ids}],
        })
    return {"Blocks": blocos}


ASO = _resposta(("Exames complementares realizados:", 0.30), ("GLICEMIA DE JEJUM 10/10/2026", 0.35))
LAUDO = _resposta(("GLICOSE", 0.20), ("Resultado: 110 mg/dL", 0.22))
MARKDOWN = textract_to_markdown(ASO, pagina=1) + "\n\n" + textract_to_markdown(LAUDO, pagina=2)
LAYOUT = layout_ocr.montar(layout_ocr.linhas_textract(ASO, pagina=1) + layout_ocr.linhas_textract(LAUDO, pagina=2))
PAYLOAD = {
    "tabela_comparacao": [{"exame": "GLICEMIA DE JEJUM", "status": "encontrado"}],
    "analysis_details": {"match_confidence": [{"exame": "GLICEMIA DE JEJUM", "ocr_match": "GLICOSE"}]},
}


class BancoFalso:
    def __init__(self, documento=None, layout=None):
        self.documento = documento
        self.layout = layout

    def get_document_by_id(self, document_id):
        return self.documento

    def get_document_layout(self, document_id):
        return self.layout


def _documento():
    return types.SimpleNamespace(ocr_markdown=MARKDOWN, result_payload=PAYLOAD)


def carregar(monkeypatch, banco):
    # Mesmo truque de test_normalidade_exames.py: importar o router carrega
    # `app.api` inteiro, que cria um cliente da OpenAI e abre o banco na importação.
    monkeypatch.setenv("OPENAI_API_KEY", "chave-de-teste")
    import app.core.config as config
    for chave, valor in {"APP_ENV": "test", "JWT_SECRET_KEY": "x" * 40, "DEV_AUTH_BYPASS": False}.items():
        monkeypatch.setattr(config.settings, chave, valor, raising=False)
    falso = types.ModuleType("app.core.database")
    falso.user_db = banco
    monkeypatch.setitem(sys.modules, "app.core.database", falso)
    for nome in ("app.core.auth", "app.api.v1.localizacao"):
        sys.modules.pop(nome, None)
    return importlib.import_module("app.api.v1.localizacao")


def usuario():
    return User(id="revisora", email="revisora@grupobrmed.com.br", name="Revisora", role=UserRole.CHECKER, is_active=True)


def test_texto_traz_cada_linha_com_a_posicao_e_as_palavras(monkeypatch):
    rota = carregar(monkeypatch, BancoFalso(_documento(), LAYOUT))
    resposta = rota.texto_do_documento("doc-1", current_user=usuario())
    assert resposta.disponivel
    assert [(l.pagina, l.texto) for l in resposta.linhas] == [
        (1, "Exames complementares realizados:"),
        (1, "GLICEMIA DE JEJUM 10/10/2026"),
        (2, "GLICOSE"),
        (2, "Resultado: 110 mg/dL"),
    ]
    resultado = resposta.linhas[3]
    assert (resultado.x, resultado.y) == (0.1, 0.22)
    # "Resultado:", "110", "mg/dL" — a faixa de cada palavra, em fração da página.
    assert resultado.palavras[1] == [0.21, 0.03]


def test_texto_sem_layout_nao_esta_disponivel(monkeypatch):
    rota = carregar(monkeypatch, BancoFalso(_documento(), None))
    resposta = rota.texto_do_documento("doc-1", current_user=usuario())
    assert not resposta.disponivel and resposta.linhas == []


def test_texto_de_documento_inexistente_e_404(monkeypatch):
    rota = carregar(monkeypatch, BancoFalso())
    with pytest.raises(HTTPException) as erro:
        rota.texto_do_documento("doc-1", current_user=usuario())
    assert erro.value.status_code == 404


def test_localizacoes_poe_o_laudo_antes_da_lista_do_aso(monkeypatch):
    rota = carregar(monkeypatch, BancoFalso(_documento(), LAYOUT))
    resposta = rota.localizacoes_do_documento("doc-1", current_user=usuario())
    assert resposta.disponivel
    (exame,) = resposta.exames
    # O nome lido no OCR ("GLICOSE") também vale para achar o laudo.
    assert [o.pagina for o in exame.ocorrencias] == [2, 1]


def test_sender_fica_de_fora(monkeypatch):
    rota = carregar(monkeypatch, BancoFalso())
    assert UserRole.SENDER not in rota._LEITORES
