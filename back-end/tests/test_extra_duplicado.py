"""Exame que aparece duas vezes no documento não vira "extra".

**Por que existe.** O documento traz o mesmo exame com dois nomes — o pai e
uma variação do catálogo, ou duas variações ("AUDIOMETRIA TONAL" e "AUDIOMETRIA
TONAL OCUPACIONAL"). Um casa com o pedido do BRNET e sai "encontrado"; o outro
sobrava como "extra_no_ocr", porque `_match_exame_local` devolve só o primeiro
nome que casa. De 12/09 a 19/10 eram 352 dos 2.316 extras, em 255 documentos
(caso relatado: 83688e42, aprovado, com a duplicata como extra).

O limite que não pode cair: nome que é ele mesmo um exame que o BRNET pede
(pai ativo do catálogo) é OUTRO exame, mesmo que um sinônimo antigo do disco o
junte a este. GLICOSE e GLICEMIA DE JEJUM são pedidos separadamente.

Rodar sem o conftest, que importa main.py e exige DATABASE_URL:

    PYTHONPATH=back-end pytest back-end/tests/test_extra_duplicado.py -q --noconftest
"""
import asyncio

import pytest

from app.services import exam_catalog_source as ecs
from app.services import validacao_service

# Catálogo do teste: dois pais com variações e GLICOSE como pai próprio.
GRUPOS = {
    "AUDIOMETRIA TONAL": {"AUDIOMETRIA TONAL", "AUDIOMETRIA TONAL OCUPACIONAL", "AUDIOMETRIA TONAL LIMIAR"},
    "HEMOGRAMA COMPLETO COM PLAQUETAS": {"HEMOGRAMA COMPLETO COM PLAQUETAS", "HEMOGRAMA", "HEMOGRAMA COMPLETO"},
    "GLICEMIA DE JEJUM": {"GLICEMIA DE JEJUM", "GLICOSE EM JEJUM"},
    "GLICOSE": {"GLICOSE"},
}


@pytest.fixture
def catalogo(monkeypatch, tmp_path):
    sinonimos = {}
    for grupo in GRUPOS.values():
        for termo in grupo:
            sinonimos.setdefault(termo, set()).update(grupo)
    monkeypatch.setattr(ecs, "_termos", set(sinonimos))
    monkeypatch.setattr(ecs, "_sinonimos", sinonimos)
    monkeypatch.setattr(ecs, "_pais_ativos", set(GRUPOS))
    # O disco ainda junta GLICOSE com GLICEMIA DE JEJUM — é esse o caso que a
    # regra precisa resistir.
    monkeypatch.setattr(validacao_service, "EXAM_SYNONYM_MAP_DISCO", {
        "GLICEMIA DE JEJUM": {"GLICEMIA DE JEJUM", "GLICOSE"},
        "GLICOSE": {"GLICEMIA DE JEJUM", "GLICOSE"},
    })
    # A auditoria grava o CPF no nome do arquivo: fora do cwd de quem roda.
    monkeypatch.chdir(tmp_path)


def validar(monkeypatch, brnet, enviados, resposta_da_ia):
    async def falso(exames_ocr, exames_brnet):
        return resposta_da_ia

    monkeypatch.setattr(validacao_service, "comparar_exames_com_rag", falso)
    resultado = asyncio.run(validacao_service.validar_exames("00000000000", brnet, enviados, brnet))
    return {i["exame"]: i["status"] for i in resultado["exames_comparativo"]}


def test_variacao_repetida_nao_vira_extra(monkeypatch, catalogo):
    """O caso relatado: o pai casa, a variação ao lado sobrava como extra."""
    tabela = validar(
        monkeypatch,
        brnet=["AUDIOMETRIA TONAL"],
        enviados=["AUDIOMETRIA TONAL", "AUDIOMETRIA TONAL OCUPACIONAL"],
        resposta_da_ia=[
            {"exame": "AUDIOMETRIA TONAL", "status": "encontrado", "justificativa": "-"},
            {"exame": "AUDIOMETRIA TONAL OCUPACIONAL", "status": "extra_no_ocr", "justificativa": "-"},
        ],
    )
    assert tabela == {"AUDIOMETRIA TONAL": "encontrado"}


def test_duas_variacoes_do_mesmo_pai_nao_viram_extra(monkeypatch, catalogo):
    """Nenhum dos dois nomes é o do pedido: casa um, e o outro também é o mesmo exame."""
    tabela = validar(
        monkeypatch,
        brnet=["HEMOGRAMA COMPLETO COM PLAQUETAS"],
        enviados=["HEMOGRAMA", "HEMOGRAMA COMPLETO"],
        resposta_da_ia=[
            {"exame": "HEMOGRAMA COMPLETO COM PLAQUETAS", "status": "encontrado", "justificativa": "-"},
            {"exame": "HEMOGRAMA COMPLETO", "status": "extra_no_ocr", "justificativa": "-"},
        ],
    )
    assert tabela == {"HEMOGRAMA COMPLETO COM PLAQUETAS": "encontrado"}


def test_outro_exame_do_brnet_continua_extra_mesmo_com_sinonimo_antigo(monkeypatch, catalogo):
    """GLICOSE é pai próprio no catálogo: o sinônimo do disco não a esconde."""
    tabela = validar(
        monkeypatch,
        brnet=["GLICEMIA DE JEJUM"],
        enviados=["GLICEMIA DE JEJUM", "GLICOSE"],
        resposta_da_ia=[
            {"exame": "GLICEMIA DE JEJUM", "status": "encontrado", "justificativa": "-"},
            {"exame": "GLICOSE", "status": "extra_no_ocr", "justificativa": "-"},
        ],
    )
    assert tabela == {"GLICEMIA DE JEJUM": "encontrado", "GLICOSE": "extra_no_ocr"}


def test_extra_de_verdade_continua_extra(monkeypatch, catalogo):
    tabela = validar(
        monkeypatch,
        brnet=["AUDIOMETRIA TONAL"],
        enviados=["AUDIOMETRIA TONAL", "TSH"],
        resposta_da_ia=[
            {"exame": "AUDIOMETRIA TONAL", "status": "encontrado", "justificativa": "-"},
            {"exame": "TSH", "status": "extra_no_ocr", "justificativa": "-"},
        ],
    )
    assert tabela == {"AUDIOMETRIA TONAL": "encontrado", "TSH": "extra_no_ocr"}


def test_pedido_equivalente_nao_usa_aproximacao_por_palavras(catalogo):
    """"AUDIOMETRIA VOCAL" divide palavra com "AUDIOMETRIA TONAL", mas não é sinônimo."""
    lista = [("AUDIOMETRIA TONAL", "AUDIOMETRIA TONAL")]
    assert validacao_service._pedido_equivalente("AUDIOMETRIA VOCAL", lista) is None
    assert validacao_service._pedido_equivalente("Audiometria Tonal Limiar", lista) == "AUDIOMETRIA TONAL"


def test_extra_repetido_com_outro_nome_aparece_uma_vez(monkeypatch, catalogo):
    """Exame que ninguém pediu, lido duas vezes: um extra, não dois."""
    tabela = validar(
        monkeypatch,
        brnet=["TSH"],
        enviados=["TSH", "AUDIOMETRIA TONAL", "AUDIOMETRIA TONAL OCUPACIONAL"],
        resposta_da_ia=[
            {"exame": "TSH", "status": "encontrado", "justificativa": "-"},
            {"exame": "AUDIOMETRIA TONAL", "status": "extra_no_ocr", "justificativa": "-"},
            {"exame": "AUDIOMETRIA TONAL OCUPACIONAL", "status": "extra_no_ocr", "justificativa": "-"},
        ],
    )
    assert tabela == {"TSH": "encontrado", "AUDIOMETRIA TONAL": "extra_no_ocr"}


def test_dois_exames_do_brnet_nao_pedidos_continuam_dois_extras(monkeypatch, catalogo):
    """GLICOSE e GLICEMIA DE JEJUM, nenhum pedido: são dois exames, dois extras."""
    tabela = validar(
        monkeypatch,
        brnet=["TSH"],
        enviados=["TSH", "GLICEMIA DE JEJUM", "GLICOSE"],
        resposta_da_ia=[
            {"exame": "TSH", "status": "encontrado", "justificativa": "-"},
            {"exame": "GLICEMIA DE JEJUM", "status": "extra_no_ocr", "justificativa": "-"},
            {"exame": "GLICOSE", "status": "extra_no_ocr", "justificativa": "-"},
        ],
    )
    assert tabela == {"TSH": "encontrado", "GLICEMIA DE JEJUM": "extra_no_ocr", "GLICOSE": "extra_no_ocr"}
