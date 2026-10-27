"""
Posição das linhas do OCR no PDF — a base do atalho "clicar no exame e ir até
ele no documento".

O que precisa de rede de segurança aqui é o PAREAMENTO: o layout não grava o
texto (ele tem nome e CPF, e já está no `ocr_markdown`), então cada caixa só
encontra a sua linha pela ordem. Se `textract_to_markdown` e `linhas_textract`
discordarem sobre quais linhas existem, a tela destacaria a linha errada — e
isso é pior do que não destacar. Por isso, na dúvida, `alinhar` devolve None.
"""
from app.services import layout_ocr
from app.services.ocr_service import textract_to_markdown
from app.services.workflow_service import _normalizar_busca


def _bb(x, y, w, h):
    return {"Geometry": {"BoundingBox": {"Left": x, "Top": y, "Width": w, "Height": h}}}


def _resposta(*linhas, pagina=None):
    """Resposta do Textract com LINE e WORD. Cada linha: (texto, x, y), palavras
    de largura proporcional ao tamanho, separadas por 0,01."""
    blocos = []
    for n, (texto, x, y) in enumerate(linhas):
        ids, cursor = [], x
        for m, palavra in enumerate(texto.split()):
            largura = 0.01 * len(palavra)
            id_palavra = f"w{n}-{m}"
            ids.append(id_palavra)
            bloco_palavra = {"BlockType": "WORD", "Id": id_palavra, "Text": palavra, **_bb(cursor, y, largura, 0.02)}
            if pagina is not None:
                bloco_palavra["Page"] = pagina
            blocos.append(bloco_palavra)
            cursor += largura + 0.01
        linha = {
            "BlockType": "LINE", "Id": f"l{n}", "Text": texto, **_bb(x, y, cursor - x - 0.01, 0.02),
            "Relationships": [{"Type": "CHILD", "Ids": ids}],
        }
        if pagina is not None:
            linha["Page"] = pagina
        blocos.append(linha)
    return {"Blocks": blocos}


def _documento(*paginas):
    """Markdown e layout como o OCR síncrono por página monta."""
    partes, linhas = [], []
    for numero, resposta in enumerate(paginas, start=1):
        partes.append(textract_to_markdown(resposta, pagina=numero))
        linhas.extend(layout_ocr.linhas_textract(resposta, pagina=numero))
    return "\n\n".join(partes), layout_ocr.montar(linhas)


ASO = _resposta(
    ("ATESTADO DE SAUDE OCUPACIONAL", 0.1, 0.05),
    ("Exames complementares realizados:", 0.1, 0.30),
    ("GLICEMIA DE JEJUM 10/10/2026", 0.1, 0.35),
    ("HEMOGRAMA COMPLETO 10/10/2026", 0.1, 0.40),
)
LAUDO = _resposta(
    ("LABORATORIO SAO LUCAS", 0.1, 0.03),
    ("GLICOSE", 0.1, 0.20),
    ("Resultado: 110 mg/dL", 0.1, 0.22),
    ("Valor de referencia: 70 a 99 mg/dL", 0.1, 0.24),
)


# ── captura ────────────────────────────────────────────────────────────────

def test_captura_uma_entrada_por_linha_em_escala_inteira():
    linhas = layout_ocr.linhas_textract(LAUDO, pagina=2)
    assert len(linhas) == 4
    pagina, x, y, w, h, palavras = linhas[2]
    assert (pagina, x, y, h) == (2, 1000, 2200, 200)
    assert len(palavras) == 3  # "Resultado:", "110", "mg/dL"
    assert palavras[1] == [2100, 300]


def test_pagina_vem_do_bloco_no_assincrono():
    linhas = layout_ocr.linhas_textract(_resposta(("GLICOSE", 0.1, 0.2), pagina=7))
    assert linhas[0][0] == 7


def test_linha_vazia_fica_de_fora_como_no_markdown():
    resposta = _resposta(("GLICOSE", 0.1, 0.2))
    resposta["Blocks"].append({"BlockType": "LINE", "Text": "   ", **_bb(0, 0, 0, 0)})
    assert len(layout_ocr.linhas_textract(resposta)) == 1


def test_sem_linha_nao_monta_layout():
    assert layout_ocr.montar([]) is None


def test_separar_tira_o_layout_do_resultado():
    resultado = {"status": "success", layout_ocr.CHAVE_RESULTADO: {"versao": 1, "linhas": []}}
    assert layout_ocr.separar(resultado) == {"versao": 1, "linhas": []}
    assert layout_ocr.CHAVE_RESULTADO not in resultado
    assert layout_ocr.separar(None) is None


# ── pareamento com o markdown ──────────────────────────────────────────────

def test_pareia_cada_linha_do_markdown_com_a_sua_caixa():
    markdown, layout = _documento(ASO, LAUDO)
    linhas = layout_ocr.alinhar(markdown, layout)
    assert [l.texto for l in linhas][-3:] == ["GLICOSE", "Resultado: 110 mg/dL", "Valor de referencia: 70 a 99 mg/dL"]
    assert linhas[0].cabecalho and not linhas[1].cabecalho
    assert [l.pagina for l in linhas] == [1, 1, 1, 1, 2, 2, 2, 2]


def test_marcador_de_pagina_do_assincrono_nao_conta_como_linha():
    resposta = _resposta(("GLICOSE", 0.1, 0.2), ("Resultado: 110 mg/dL", 0.1, 0.22), pagina=3)
    markdown = textract_to_markdown(resposta)
    assert "<!--" in markdown
    linhas = layout_ocr.alinhar(markdown, layout_ocr.montar(layout_ocr.linhas_textract(resposta)))
    assert [l.texto for l in linhas] == ["GLICOSE", "Resultado: 110 mg/dL"]


def test_contagem_diferente_nao_pareia():
    markdown, layout = _documento(ASO, LAUDO)
    assert layout_ocr.alinhar(markdown + "\nlinha a mais", layout) is None


def test_sem_layout_ou_versao_desconhecida_nao_pareia():
    markdown, layout = _documento(LAUDO)
    assert layout_ocr.alinhar(markdown, None) is None
    assert layout_ocr.alinhar(markdown, {**layout, "versao": 99}) is None
    assert layout_ocr.alinhar("", layout) is None


# ── caixa de um trecho da linha ────────────────────────────────────────────

def test_caixa_do_trecho_usa_as_palavras():
    markdown, layout = _documento(LAUDO)
    linha = layout_ocr.alinhar(markdown, layout)[2]  # "Resultado: 110 mg/dL"
    inicio = linha.texto.index("110")
    x, y, w, h = layout_ocr.caixa_do_trecho(linha, inicio, len(linha.texto))
    # "110" começa em 0,1 + 0,10 + 0,01 e "mg/dL" termina em 0,21 + 0,03 + 0,01 + 0,05.
    assert (x, x + w) == (2100, 3000)
    assert (y, h) == (linha.caixa[1], linha.caixa[3])


def test_caixa_do_trecho_sem_palavras_estima_pela_proporcao():
    linha = layout_ocr.LinhaPosicionada("ABCD EFGH", 1, (1000, 500, 900, 100), palavras=[])
    x, _, w, _ = layout_ocr.caixa_do_trecho(linha, 5, 9)
    assert (x, w) == (1500, 400)


# ── onde o exame aparece ───────────────────────────────────────────────────

def _localizar(markdown, layout, *termos):
    linhas = layout_ocr.alinhar(markdown, layout)
    return layout_ocr.localizar_termos(
        linhas,
        layout_ocr.normalizar_linhas(linhas, _normalizar_busca),
        {_normalizar_busca(t) for t in termos},
        layout_ocr.paginas_da_lista_aso(linhas),
    )


def test_laudo_vem_antes_da_lista_do_aso():
    markdown, layout = _documento(ASO, LAUDO)
    ocorrencias = _localizar(markdown, layout, "GLICEMIA DE JEJUM", "GLICOSE")
    assert [o["pagina"] for o in ocorrencias] == [2, 1]
    caixa = ocorrencias[0]["caixas"][0]
    assert caixa["y"] == 0.2 and caixa["x"] == 0.1


def test_exame_so_na_lista_do_aso_ainda_e_localizado():
    markdown, layout = _documento(ASO, LAUDO)
    assert [o["pagina"] for o in _localizar(markdown, layout, "HEMOGRAMA COMPLETO")] == [1]


def test_termo_casa_so_palavra_inteira_e_termo_curto_e_ignorado():
    markdown, layout = _documento(_resposta(("GLICOSE MEDIA ESTIMADA", 0.1, 0.1), ("RX", 0.1, 0.2)))
    assert _localizar(markdown, layout, "GLICO") == []
    assert _localizar(markdown, layout, "RX") == []


def test_limita_as_ocorrencias():
    markdown, layout = _documento(_resposta(*[("GLICOSE", 0.1, 0.05 * i) for i in range(1, 9)]))
    assert len(_localizar(markdown, layout, "GLICOSE")) == layout_ocr.MAX_OCORRENCIAS
