"""Kit VIX: documento da VIX Logística ou da Autoport sem o ASO VIXPAR e a Ficha Clínica.

A exigência é da empresa e não vem do BRNET, então a IA aprovava o documento
só com o ASO da BR MED. Os textos imitam o markdown do OCR; os códigos dos
formulários são os reais: FM.COP.MED/002 é a Ficha Clínica e /001, /003 e /004
são o ASO VIXPAR.
"""
import pytest

from app.services.workflow_service import KIT_VIX_FALTANTE, _falta_kit_vix

ASO_BR_MED = "ATESTADO DE SAÚDE OCUPACIONAL Empresa: VIX LOGÍSTICA S/A Função: Motorista Apto"
ASO_AUTOPORT = "ATESTADO DE SAÚDE OCUPACIONAL Empresa: AUTOPORT TRANSPORTE E LOGISTICA LTDA Apto"
ASO_VIXPAR = " VIXPAR ASO Atestado de Saúde Ocupacional FM.COP.MED/004 "
FICHA_VIX = " FICHA CLÍNICA FM.COP.MED/002 Anamnese "

CNPJ_AUTOPORT = "07.677.731/0025-92"
CNPJ_VIX_LOGISTICA = "32681371000172"
CNPJ_VIX_TRANSPORTES = "09452900000100"
CNPJ_LETS = "00873894001449"


def test_vix_logistica_sem_o_kit():
    assert _falta_kit_vix(ASO_BR_MED)


def test_vix_logistica_com_o_kit_completo():
    assert not _falta_kit_vix(ASO_BR_MED + ASO_VIXPAR + FICHA_VIX)


@pytest.mark.parametrize("parte", [ASO_VIXPAR, FICHA_VIX])
def test_kit_pela_metade_continua_faltando(parte):
    # Novembro/2026: o ASO VIXPAR sozinho contava como kit, e faltava a ficha.
    assert _falta_kit_vix(ASO_BR_MED + parte)


def test_autoport_pelo_cnpj_sem_a_ficha():
    assert _falta_kit_vix(ASO_AUTOPORT + ASO_VIXPAR, CNPJ_AUTOPORT)
    assert not _falta_kit_vix(ASO_AUTOPORT + ASO_VIXPAR + FICHA_VIX, CNPJ_AUTOPORT)


def test_autoport_so_no_rodape_de_formulario_nao_dispara():
    # Clínicas usam o questionário da VIX (FM.COP.SMT/114, rodapé "Autoport") para
    # outras empresas: sem o CNPJ do grupo, não é documento da Autoport.
    rodape = "QUESTIONARIO PSICOSSOCIAL FM.COP.SMT/114 REVISAO AUTOPORT LET'S"
    assert not _falta_kit_vix(rodape, "12345678000199")


def test_vix_logistica_pelo_cnpj_mesmo_sem_o_nome():
    assert _falta_kit_vix("ATESTADO DE SAÚDE OCUPACIONAL Apto", CNPJ_VIX_LOGISTICA)


@pytest.mark.parametrize("ficha", ["FM.COP.MED/032", "FM.COP.MID/002"])
def test_codigo_da_ficha_lido_errado_pelo_ocr(ficha):
    assert not _falta_kit_vix(ASO_BR_MED + ASO_VIXPAR + f" FICHA CLÍNICA {ficha} ")


def test_vix_transportes_fica_fora():
    # Tem aprovados sem VIXPAR: a exigência medida é só da VIX Logística e da Autoport.
    assert not _falta_kit_vix(ASO_BR_MED.replace("VIX LOGÍSTICA S/A", "VIX TRANSPORTES DEDICADOS"))
    assert not _falta_kit_vix("ATESTADO DE SAÚDE OCUPACIONAL Apto", CNPJ_VIX_TRANSPORTES)


def test_lets_fica_fora_ate_a_operacao_decidir():
    assert not _falta_kit_vix("ATESTADO DE SAÚDE OCUPACIONAL Empresa LET'S RENT A CAR", CNPJ_LETS)


def test_sem_texto_nao_aponta():
    assert not _falta_kit_vix("")
    assert not _falta_kit_vix("", CNPJ_AUTOPORT)


def test_nome_do_faltante_diz_o_que_falta():
    assert "VIXPAR" in KIT_VIX_FALTANTE and "FICHA" in KIT_VIX_FALTANTE
