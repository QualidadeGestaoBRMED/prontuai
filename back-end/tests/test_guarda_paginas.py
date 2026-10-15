"""
Marcador de página do OCR e a guarda por contagem de páginas.

O par existe por um motivo medido: nos 16 documentos que a checagem rejeitou por
exame faltante na semana de 05/10, quinze saíram com confiança 100, e seis deles
tinham menos páginas do que seria possível para conter os laudos dos exames
exigidos. A guarda não decide nada — só impede a confiança de afirmar certeza
onde a aritmética já diz que falta documento.

O que precisa de rede de segurança aqui é a **degradação**: documento sem
marcador de página (caminho síncrono do Textract, e tudo que foi processado
antes do marcador existir) não pode ser penalizado por engano. `None` significa
"não dá para contar", nunca "zero páginas".
"""
import pytest

from app.services.ocr_service import textract_to_markdown
from app.services.workflow_service import (
    TETO_CONFIANCA_POUCAS_PAGINAS,
    _exames_sem_laudo,
    _paginas_do_markdown,
    _paginas_insuficientes,
)


def _linha(texto, pagina=None):
    bloco = {"BlockType": "LINE", "Text": texto}
    if pagina is not None:
        bloco["Page"] = pagina
    return bloco


# ── marcador de página ─────────────────────────────────────────────────────

def test_marca_troca_de_pagina():
    md = textract_to_markdown({"Blocks": [
        _linha("Atestado de Saude Ocupacional", 1),
        _linha("texto corrido da primeira pagina", 1),
        _linha("LAUDO DE ESPIROMETRIA", 2),
    ]})
    assert "<!-- pagina 1 -->" in md
    assert "<!-- pagina 2 -->" in md
    assert md.count("<!-- pagina") == 2, "um marcador por página, não por linha"


def test_sem_page_no_bloco_o_markdown_nao_muda():
    """Caminho síncrono do Textract não informa página. O markdown precisa sair
    idêntico ao de antes — qualquer marcador ali seria ruído no prompt."""
    blocos = [_linha("Atestado de Saude Ocupacional"), _linha("texto corrido")]
    assert "<!-- pagina" not in textract_to_markdown({"Blocks": blocos})


def test_marcador_e_comentario_nao_vira_cabecalho():
    """O conversor transforma texto curto em maiúsculas em `## título`. O
    marcador não pode passar por esse caminho e virar conteúdo."""
    md = textract_to_markdown({"Blocks": [_linha("ESPIROMETRIA", 1)]})
    assert "## <!-- pagina" not in md
    assert md.strip().startswith("<!-- pagina 1 -->")


# ── contagem ───────────────────────────────────────────────────────────────

def test_conta_pela_maior_pagina():
    md = "a\n<!-- pagina 1 -->\nb\n<!-- pagina 2 -->\nc\n<!-- pagina 3 -->\nd"
    assert _paginas_do_markdown(md) == 3


def test_sem_marcador_devolve_none():
    assert _paginas_do_markdown("prontuário sem marcador nenhum") is None
    assert _paginas_do_markdown("") is None
    assert _paginas_do_markdown(None) is None


# ── a guarda ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "paginas,exigidos,esperado,caso",
    [
        (2, 11, True, "2bec7a35: ASO e um laudo para onze exames exigidos"),
        (9, 9, True, "31593a9b: nove páginas não cabem ASO, ficha e nove laudos"),
        (5, 4, True, "c29228a9"),
        (18, 13, False, "207deed8: cabe, mesmo que falte laudo por outro motivo"),
        (25, 19, False, "a7f796dd"),
        (13, 10, False, "d32b45d8"),
    ],
)
def test_aritmetica_da_guarda(paginas, exigidos, esperado, caso):
    assert _paginas_insuficientes(paginas, exigidos) is esperado, caso


def test_nao_penaliza_quando_nao_da_para_contar():
    """A degradação mais importante: sem marcador, a guarda não dispara. Tratar
    `None` como zero marcaria todo documento legado como suspeito."""
    assert _paginas_insuficientes(None, 11) is False


def test_nao_dispara_sem_exigencia_do_brnet():
    """Sem exame exigido não há laudo a esperar — e a consulta ao BRNET pode ter
    falhado, o que é outro problema, já visível por outro caminho."""
    assert _paginas_insuficientes(2, 0) is False


def test_teto_fica_abaixo_da_faixa_alta():
    """O valor do teto é o ponto da mudança: se alguém subir para 100, a guarda
    passa a não fazer nada e nenhum outro teste percebe."""
    assert TETO_CONFIANCA_POUCAS_PAGINAS < 90


# ── exame sem laudo: sinal em observação ───────────────────────────────────
#
# Estes testes travam o CONTRATO, não a precisão. A regra ainda marca 70% dos
# exames exigidos nos 16 documentos reprocessados, porque "exame exigido" não é
# "exame que gera laudo separado" — o clínico ocupacional é a consulta e nunca
# terá página própria. Enquanto esse metadado não existir, o resultado só é
# gravado. O que não pode mudar sem alguém perceber é que ele NÃO decide nada.

def _md(*paginas):
    """Markdown com marcador por página, como o OCR emite."""
    return "".join(f"\n<!-- pagina {i} -->\n{t}\n" for i, t in enumerate(paginas, 1))


def test_sem_marcador_nao_avalia():
    """Mesma degradação da guarda: documento legado não vira suspeito."""
    assert _exames_sem_laudo("ASO sem marcador de pagina", ["ESPIROMETRIA"]) is None


def test_sem_exigencia_nao_avalia():
    assert _exames_sem_laudo(_md("Exames complementares", "LAUDO"), []) is None


def test_lista_do_aso_sozinha_nao_e_evidencia():
    """O coração do caso: o nome está no documento, mas só na lista impressa no
    ASO. Era exatamente isso que fazia a IA contar o exame como entregue."""
    md = _md("4. Procedimentos Realizados\nExames complementares\n## ESPIROMETRIA 28/09/2026",
             "Ficha Medica - Admissional\nDados do paciente")
    assert _exames_sem_laudo(md, ["ESPIROMETRIA"]) == ["ESPIROMETRIA"]


def test_pagina_de_laudo_conta_como_evidencia():
    md = _md("4. Procedimentos Realizados\nExames complementares\n## ESPIROMETRIA 28/09/2026",
             "LAUDO REALIZADO - ESPIROMETRIA\nConclusao: exame normal\nCRM-SP 151.123")
    assert _exames_sem_laudo(md, ["ESPIROMETRIA"]) == []


def test_laudo_sem_vocabulario_de_resultado_ainda_escapa():
    """Limite conhecido, registrado de propósito.

    `varrer_markdown` exige vocabulário de resultado por perto, e a espirometria
    do `45e08fdd` traz só a tabela em inglês — "FVC 4.05 L FEV1 3.36 L
    Espirometria Normal". A unidade "L" não está no vocabulário, então a página
    de laudo não conta e o exame é marcado sem laudo.

    É parte dos 70% de excesso. Se alguém ampliar o vocabulário e isto passar a
    devolver lista vazia, a mudança é desejada — ajuste o teste.
    """
    md = _md("4. Procedimentos Realizados\nExames complementares\n## ESPIROMETRIA",
             "Analysis Report\nFVC 4.05 L FEV1 3.36 L\nEspirometria Normal")
    assert _exames_sem_laudo(md, ["ESPIROMETRIA"]) == ["ESPIROMETRIA"]


def test_resultado_e_so_informativo():
    """Nenhuma decisão olha para isto. Se alguém ligar na comparação ou na
    confiança sem antes resolver o metadado de laudo, o número de faltantes
    explode — medido: 70% dos exames exigidos."""
    import inspect
    from app.services import workflow_service as ws
    fonte = inspect.getsource(ws._processar_documento_completo_impl)
    assert "_exames_sem_laudo" in fonte, "o detector deve rodar"
    # a única atribuição permitida é no dicionário de detalhes da confiança
    usos = [l.strip() for l in fonte.splitlines() if "sem_laudo" in l]
    assert any('confidence_details["exames_sem_laudo"]' in u for u in usos)
    proibidos = ("exames_faltantes", "status_liberado", "validation_status",
                 "confiabilidade_score =", "exames_comparativo")
    for u in usos:
        assert not any(p in u for p in proibidos), f"o sinal vazou para uma decisão: {u}"
