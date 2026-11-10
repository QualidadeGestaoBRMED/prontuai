"""Sinais vitais impossíveis na ficha médica BR MED (peso e altura trocados).

Os blocos imitam o markdown do OCR da ficha: rótulos e, depois, os valores na
ordem pulso, peso, altura e IMC.
"""
from app.services import sinais_vitais as sv
from app.services.workflow_service import decisao_da_ia


def bloco(pulso, peso, altura, imc):
    return (
        "Sinais Vitais\nPressão Sistólica (mmHg)\nPressão Diastólica (mmHg)\n"
        "Circunferência Abdominal (cm)\n117\n77\n109\nPulso (bpm)\nPeso (kg)\nAltura (cm)\n\n## IMC\n\n"
        f"{pulso}\n{peso}\n{altura}\n{imc}\nMédica\n"
    )


def test_peso_e_altura_trocados():
    # Novembro/2026: altura 93 cm, peso 156 kg — o IMC calculado confirma a leitura.
    achado = sv.incoerencia(bloco(77, "156,00", 93, "180.37"))
    assert achado == {"peso_kg": 156.0, "altura_cm": 93.0, "imc": 180.37}
    assert "altura 93 cm" in sv.motivo(achado) and "peso 156 kg" in sv.motivo(achado)


def test_ficha_normal_nao_avisa():
    assert sv.incoerencia(bloco(62, "75,00", 178, "23.67")) is None


def test_imc_sem_virgula_lido_pelo_ocr():
    # "2976" é 29,76: a ficha está certa.
    assert sv.incoerencia(bloco(70, "86,00", 170, "2976")) is None


def test_leitura_fora_de_ordem_nao_avisa():
    # O OCR perdeu um valor e a "altura" lida é o IMC: o IMC não confere, então não
    # dá para afirmar nada (era a fonte dos falsos positivos).
    assert sv.incoerencia(bloco(94, "30,35", 172, "86")) is None


def test_sem_bloco_de_sinais_vitais_nao_avisa():
    assert sv.incoerencia("ATESTADO DE SAÚDE OCUPACIONAL Trabalho em Altura (NR 35) Apto") is None
    assert sv.incoerencia("") is None


def test_desligada_nao_avisa(monkeypatch):
    monkeypatch.setattr(sv, "HABILITADA", False)
    assert sv.incoerencia(bloco(77, "156,00", 93, "180.37")) is None


def test_sinais_vitais_impossiveis_mandam_para_a_checagem():
    resultado = {"status": "success", "validation_result": {"exames_faltantes": [], "sinais_vitais": {"altura_cm": 93}}}
    assert decisao_da_ia(resultado) == "pending"
    resultado["validation_result"]["sinais_vitais"] = None
    assert decisao_da_ia(resultado) == "validated"
