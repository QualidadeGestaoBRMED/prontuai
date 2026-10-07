"""Varredura determinística do markdown pelos sinônimos do catálogo.

Roda sem banco: o cache de sinônimos é preenchido direto, como o
`_carregar` faria a partir de `exam_parents`/`exam_variations`.
"""
import pytest

from app.services import exam_catalog_source as ecs

TGO = "TGO AST"
GRUPO_TGO = {"TGO AST", "TGO", "TRANSAMINASE OXALACETICA TGO"}


@pytest.fixture(autouse=True)
def catalogo_tgo():
    termos, sinonimos = ecs._termos, ecs._sinonimos
    ecs._termos = set(GRUPO_TGO)
    ecs._sinonimos = {t: set(GRUPO_TGO) for t in GRUPO_TGO}
    yield
    ecs._termos, ecs._sinonimos = termos, sinonimos


def test_acha_o_laudo_mesmo_quando_o_nome_aparece_antes_na_lista_de_pedidos():
    # Caso real da semana de 28/09/2026: o nome vem primeiro na lista de exames
    # pedidos, sem resultado por perto, e só depois no laudo com "23 U L".
    markdown = (
        " EXAMES SOLICITADOS HEMOGRAMA TRANSAMINASE OXALACETICA TGO BILIRRUBINAS"
        + " CREATININA FOSFATASE ALCALINA" * 6
        + " PAGINA 2 TRANSAMINASE OXALACETICA TGO 23 U L MATERIAL SORO "
    )
    achados = ecs.varrer_markdown(markdown, [TGO], exigir_valor=True)
    assert achados[TGO][0] == "TRANSAMINASE OXALACETICA TGO"
    assert achados[TGO][1] is True


def test_nome_so_na_lista_de_pedidos_continua_descartado():
    markdown = (
        " EXAMES SOLICITADOS HEMOGRAMA TRANSAMINASE OXALACETICA TGO BILIRRUBINAS"
        + " CREATININA FOSFATASE ALCALINA" * 6
        + " "
    )
    assert ecs.varrer_markdown(markdown, [TGO], exigir_valor=True) == {}
