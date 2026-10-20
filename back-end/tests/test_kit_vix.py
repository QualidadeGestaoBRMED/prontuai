"""Kit VIX: documento da VIX Logística sem o ASO VIXPAR e a ficha clínica.

A exigência é da empresa e não vem do BRNET, então a IA aprovava o documento
só com o ASO da BR MED. Os textos imitam o markdown do OCR.
"""
from app.services.workflow_service import KIT_VIX_FALTANTE, _falta_kit_vix

ASO_BR_MED = "ATESTADO DE SAÚDE OCUPACIONAL Empresa: VIX LOGÍSTICA S/A Função: Motorista Apto"


def test_vix_logistica_sem_o_kit():
    assert _falta_kit_vix(ASO_BR_MED)


def test_vix_logistica_com_aso_vixpar():
    assert not _falta_kit_vix(ASO_BR_MED + " ASO VIXPAR Atestado de Saúde Ocupacional")


def test_vix_logistica_com_a_ficha_clinica():
    assert not _falta_kit_vix(ASO_BR_MED + " FM.COP.012 Ficha Clínica Ocupacional")


def test_vix_transportes_fica_fora():
    # Tem aprovados sem VIXPAR: a exigência medida é só da VIX Logística.
    assert not _falta_kit_vix(ASO_BR_MED.replace("VIX LOGÍSTICA S/A", "VIX TRANSPORTES DEDICADOS"))


def test_sem_texto_nao_aponta():
    assert not _falta_kit_vix("")


def test_nome_do_faltante_diz_o_que_falta():
    assert "VIXPAR" in KIT_VIX_FALTANTE and "FICHA" in KIT_VIX_FALTANTE
