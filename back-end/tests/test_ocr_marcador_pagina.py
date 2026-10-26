"""Marcador de página e comentário de confiança de leitura no markdown do Textract.

Sem AWS e sem OpenAI: as respostas do Textract são dicts montados à mão e o
cliente da OpenAI é trocado por um falso que só guarda o prompt.

Roda isolado: `PYTHONPATH=back-end pytest back-end/tests/test_ocr_marcador_pagina.py -q --noconftest`.
"""
import io
import json
import re
from types import SimpleNamespace

import pytest
from PyPDF2 import PdfWriter

from app.core import pii_redaction
from app.services import ocr_service

# Cópia literal de `workflow_service._RE_PAGINA_MARKDOWN`. Não importa o módulo
# para o teste não depender de banco; se o de lá mudar, este precisa mudar junto.
RE_PAGINA_WORKFLOW = re.compile(r"<!--\s*pagina\s+(\d+)\s*-->")


def _linha(texto, confianca=99.0, page=None):
    bloco = {"BlockType": "LINE", "Text": texto, "Confidence": confianca}
    if page is not None:
        bloco["Page"] = page
    return bloco


def _palavra(texto, confianca=99.0, page=None):
    bloco = {"BlockType": "WORD", "Text": texto, "Confidence": confianca}
    if page is not None:
        bloco["Page"] = page
    return bloco


def _pagina(page=None):
    bloco = {"BlockType": "PAGE"}
    if page is not None:
        bloco["Page"] = page
    return bloco


def _leituras(markdown):
    return [
        {
            "pagina": int(m.group(1)),
            "confianca": float(m.group(2)),
            "palavras": int(m.group(3)),
            "baixa": float(m.group(4)),
        }
        for m in ocr_service.RE_LEITURA_PAGINA.finditer(markdown)
    ]


def _pdf_em_branco(paginas: int) -> bytes:
    writer = PdfWriter()
    for _ in range(paginas):
        writer.add_blank_page(612, 792)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


# --- textract_to_markdown ----------------------------------------------------


def test_sem_pagina_e_sem_page_mantem_markdown_como_era():
    resposta = {"Blocks": [_linha("Texto comum do laudo"), _palavra("Texto")]}
    markdown = ocr_service.textract_to_markdown(resposta)
    assert "<!--" not in markdown
    assert markdown == "Texto comum do laudo"


def test_pagina_informada_abre_com_marcador_e_leitura():
    resposta = {
        "Blocks": [
            _pagina(),
            _linha("HEMOGRAMA", confianca=90.0),
            _linha("Resultado dentro da referencia", confianca=80.0),
            _palavra("HEMOGRAMA", confianca=95.0),
            _palavra("Resultado", confianca=70.0),
            _palavra("dentro", confianca=79.9),
            _palavra("referencia", confianca=80.0),
        ]
    }
    markdown = ocr_service.textract_to_markdown(resposta, pagina=3)

    assert markdown.lstrip().startswith("<!-- pagina 3 -->")
    assert [int(n) for n in RE_PAGINA_WORKFLOW.findall(markdown)] == [3]
    assert _leituras(markdown) == [
        # média das LINE (90 e 80); 2 de 4 WORD abaixo de 80 (79.9 conta, 80.0 não)
        {"pagina": 3, "confianca": 85.0, "palavras": 4, "baixa": 0.5}
    ]
    assert "<!-- leitura pagina=3 confianca=85.0 palavras=4 baixa=0.50 -->" in markdown
    assert "## HEMOGRAMA" in markdown


def test_pagina_informada_prevalece_sobre_page_do_bloco():
    resposta = {"Blocks": [_linha("texto da pagina", page=1)]}
    markdown = ocr_service.textract_to_markdown(resposta, pagina=2)
    assert RE_PAGINA_WORKFLOW.findall(markdown) == ["2"]


def test_confianca_cai_para_word_quando_line_nao_traz():
    resposta = {
        "Blocks": [
            {"BlockType": "LINE", "Text": "texto sem confianca"},
            _palavra("texto", confianca=60.0),
            _palavra("sem", confianca=100.0),
        ]
    }
    markdown = ocr_service.textract_to_markdown(resposta, pagina=1)
    assert _leituras(markdown) == [
        {"pagina": 1, "confianca": 80.0, "palavras": 2, "baixa": 0.5}
    ]


def test_pagina_vazia_tem_marcador_e_zero_palavras():
    markdown = ocr_service.textract_to_markdown({"Blocks": [_pagina()]}, pagina=4)
    assert RE_PAGINA_WORKFLOW.findall(markdown) == ["4"]
    assert "<!-- leitura pagina=4 confianca=0.0 palavras=0 baixa=0.00 -->" in markdown

    sem_blocos = ocr_service.textract_to_markdown({}, pagina=5)
    assert _leituras(sem_blocos) == [
        {"pagina": 5, "confianca": 0.0, "palavras": 0, "baixa": 0.0}
    ]


def test_assincrono_um_marcador_por_pagina_sem_duplicar():
    resposta = {
        "Blocks": [
            _pagina(1),
            _linha("ATESTADO DE SAUDE OCUPACIONAL", confianca=98.0, page=1),
            _linha("Exames complementares", confianca=96.0, page=1),
            _palavra("ATESTADO", confianca=98.0, page=1),
            _palavra("Exames", confianca=50.0, page=1),
            _pagina(2),  # página escaneada sem nada legível
            _pagina(3),
            _linha("AUDIOMETRIA", confianca=88.0, page=3),
            _palavra("AUDIOMETRIA", confianca=88.0, page=3),
        ]
    }
    markdown = ocr_service.textract_to_markdown(resposta)

    assert [int(n) for n in RE_PAGINA_WORKFLOW.findall(markdown)] == [1, 2, 3]
    assert markdown.count("<!-- pagina 1 -->") == 1
    assert _leituras(markdown) == [
        {"pagina": 1, "confianca": 97.0, "palavras": 2, "baixa": 0.5},
        {"pagina": 2, "confianca": 0.0, "palavras": 0, "baixa": 0.0},
        {"pagina": 3, "confianca": 88.0, "palavras": 1, "baixa": 0.0},
    ]
    # O texto de cada página fica depois do próprio marcador.
    partes = RE_PAGINA_WORKFLOW.split(markdown)
    assert "ATESTADO" in partes[2] and "AUDIOMETRIA" not in partes[2]
    assert "AUDIOMETRIA" in partes[6]


def test_assincrono_sem_bloco_page_ainda_marca_pela_line():
    resposta = {
        "Blocks": [
            _linha("primeira", page=1),
            _linha("segunda", page=2),
            _linha("ainda segunda", page=2),
        ]
    }
    markdown = ocr_service.textract_to_markdown(resposta)
    assert RE_PAGINA_WORKFLOW.findall(markdown) == ["1", "2"]


def test_comentario_de_leitura_nao_casa_o_regex_de_pagina():
    linha = "<!-- leitura pagina=3 confianca=91.4 palavras=812 baixa=0.12 -->"
    assert RE_PAGINA_WORKFLOW.findall(linha) == []
    assert ocr_service.RE_LEITURA_PAGINA.search(linha)


# --- laço síncrono por página -------------------------------------------------


def test_sincrono_por_pagina_grava_marcadores_na_ordem(tmp_path, monkeypatch):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(_pdf_em_branco(2))

    respostas = iter(
        [
            {"Blocks": [_pagina(), _linha("ASO", 99.0), _palavra("ASO", 99.0)]},
            {"Blocks": [_pagina(), _linha("ESPIROMETRIA", 70.0), _palavra("ESPIROMETRIA", 70.0)]},
        ]
    )
    contextos = []

    def _detect_falso(document_bytes, context):
        contextos.append(context)
        return next(respostas)

    monkeypatch.setattr(ocr_service, "_detect_document_text_with_retry", _detect_falso)
    monkeypatch.setattr(ocr_service, "reparar_pdf_para_textract", lambda caminho: caminho)
    monkeypatch.setattr(ocr_service, "otimizar_pdf_para_textract", lambda caminho: caminho)
    monkeypatch.setattr(ocr_service.settings, "TEXTRACT_SYNC_PAGE_DELAY_SECONDS", 0)

    markdown = ocr_service.processar_pdf_textract_sincrono_por_pagina(str(pdf))

    assert len(contextos) == 2
    assert [int(n) for n in RE_PAGINA_WORKFLOW.findall(markdown)] == [1, 2]
    assert markdown.index("<!-- pagina 1 -->") < markdown.index("ASO")
    assert markdown.index("ASO") < markdown.index("<!-- pagina 2 -->")
    assert markdown.index("<!-- pagina 2 -->") < markdown.index("ESPIROMETRIA")
    assert _leituras(markdown) == [
        {"pagina": 1, "confianca": 99.0, "palavras": 1, "baixa": 0.0},
        {"pagina": 2, "confianca": 70.0, "palavras": 1, "baixa": 1.0},
    ]


# --- saída para a OpenAI ------------------------------------------------------


def test_comentarios_do_ocr_nao_vao_para_a_openai(monkeypatch):
    enviados = []

    def _create(**kwargs):
        enviados.append(kwargs["messages"][1]["content"])
        conteudo = json.dumps({"exames": ["AUDIOMETRIA"]})
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=conteudo))]
        )

    cliente_falso = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=_create))
    )
    monkeypatch.setattr(ocr_service, "client", cliente_falso)

    resposta = {
        "Blocks": [
            _linha("AUDIOMETRIA", 88.0, page=1),
            _palavra("AUDIOMETRIA", 88.0, page=1),
            _linha("Resultado normal", 91.0, page=2),
        ]
    }
    markdown = ocr_service.textract_to_markdown(resposta)
    assert "<!-- pagina 1 -->" in markdown

    resultado = ocr_service.extrair_exames_ia(markdown)

    assert resultado["exames"] == ["AUDIOMETRIA"]
    assert len(enviados) == 1
    assert "<!--" not in enviados[0]
    assert "leitura" not in enviados[0]
    assert "AUDIOMETRIA" in enviados[0]
    assert "Resultado normal" in enviados[0]


@pytest.mark.parametrize(
    "comentario",
    [
        "<!-- pagina 12 -->",
        "<!-- leitura pagina=12 confianca=91.4 palavras=81234 baixa=0.12 -->",
        "<!-- leitura pagina=1 confianca=0.0 palavras=0 baixa=0.00 -->",
    ],
)
def test_comentarios_passam_intactos_pela_redacao_de_pii(comentario):
    # Rede de segurança: mesmo que um dia os comentários voltem para o prompt,
    # a redação não os mutila e a conferência de PII não os confunde com
    # telefone/CEP/CPF (o que bloquearia o envio inteiro).
    texto = f"\n{comentario}\n## HEMOGRAMA\n"
    redigido = pii_redaction.redigir_para_llm(texto, preservar_datas=True)
    assert comentario in redigido
    pii_redaction.verificar_payload(redigido)
