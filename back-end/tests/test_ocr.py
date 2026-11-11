import io
import logging
from unittest.mock import patch

from fastapi import status
from PyPDF2 import PdfReader, PdfWriter
from PyPDF2.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
)

from app.services import ocr_service


def _pdf_uma_pagina_com_imagem(resources_indireto: bool) -> bytes:
    """PDF de 1 página com um XObject de imagem, com /Resources direto ou indireto."""
    writer = PdfWriter()
    writer.add_blank_page(612, 792)

    imagem = DecodedStreamObject()
    imagem.set_data(b"\xff")
    imagem.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Image"),
            NameObject("/Width"): NumberObject(1),
            NameObject("/Height"): NumberObject(1),
            NameObject("/ColorSpace"): NameObject("/DeviceGray"),
            NameObject("/BitsPerComponent"): NumberObject(8),
        }
    )
    resources = DictionaryObject(
        {
            NameObject("/XObject"): DictionaryObject(
                {NameObject("/I0"): writer._add_object(imagem)}
            )
        }
    )

    page = writer.pages[0]
    page[NameObject("/Resources")] = (
        writer._add_object(resources) if resources_indireto else resources
    )

    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_pagina_tem_imagem_com_resources_direto():
    pdf = PdfReader(io.BytesIO(_pdf_uma_pagina_com_imagem(resources_indireto=False)))
    assert ocr_service._pagina_tem_imagem(pdf.pages[0]) is True


def test_pagina_tem_imagem_com_resources_indireto():
    """
    PDFs gerados por PDFium apontam /Resources por referência indireta. O PyPDF2
    não faz proxy de `in`/`.get()` em IndirectObject, então sem resolver o objeto
    a página era lida como "sem imagem": o scan caía na trilha "digital" e era
    recomprimido pelo Ghostscript com /screen (300 -> 72 dpi), corrompendo o OCR
    de nome e CNPJ.
    """
    pdf = PdfReader(io.BytesIO(_pdf_uma_pagina_com_imagem(resources_indireto=True)))
    assert ocr_service._pagina_tem_imagem(pdf.pages[0]) is True


def test_extrair_cpf_regex():
    # CPF com dígito verificador válido: extrair_cpf_regex valida o checksum.
    markdown = "Paciente: Fulano\nCPF: 104.134.126-10\n"
    assert ocr_service.extrair_cpf_regex(markdown) == "10413412610"


def test_extrair_cnpj_regex():
    # CNPJ com dígito verificador válido: extrair_cnpj_regex valida o checksum.
    markdown = "Empresa XYZ\nCNPJ: 12.345.678/0001-95\n"
    assert ocr_service.extrair_cnpj_regex(markdown) == "12345678000195"


def test_extrair_cnpj_regex_prioriza_voucher():
    """O CNPJ do voucher da BR MED vence o de laudos anexados ao mesmo PDF.

    O voucher origina o agendamento no BR NET, então o CNPJ dele é o cadastro
    que a API externa reconhece. Laudos de terceiros imprimem o CNPJ do
    contratante ou da própria clínica e vêm antes no markdown, então venciam por
    ordem de aparição e a consulta falhava com "Paciente não encontrado".
    """
    markdown = (
        "RESULTADO DE EXAMES\n"
        "Unidade: TERMINAL LOGISTICO DO VALE DO PARAIBA\n"
        "CNPJ: 11.243.246/0001-00\n"
        "CNPJ: 36.182.482/0001-95 / E-mail: atendimento@n1med.com.br\n"
        "\n## VOUCHER\n\n"
        "TERMINAL LOGISTICO DO VALE DO PARAIBA - PORTO VALE - TIPI\n"
        "CNPJ: 03.214.786/0004-80\n"
        "1. Identificacao / Identification:\n"
    )
    assert ocr_service.extrair_cnpj_regex(markdown) == "03214786000480"


def test_extrair_cnpj_regex_sem_voucher_mantem_ordem_de_aparicao():
    markdown = "Unidade: EMPRESA X\nCNPJ: 12.345.678/0001-95\n"
    assert ocr_service.extrair_cnpj_regex(markdown) == "12345678000195"


def test_extrair_cnpj_do_voucher_ignora_cnpj_fora_do_cabecalho():
    """Só o CNPJ entre o cabeçalho "VOUCHER" e a seção 1 é o da empresa."""
    markdown = (
        "## VOUCHER\n"
        "EMPRESA X\n"
        "1. Identificacao / Identification:\n"
        "CNPJ: 03.214.786/0004-80\n"
    )
    assert ocr_service._extrair_cnpj_do_voucher(markdown) is None


def test_extrair_cnpj_regex_prioriza_aso_sobre_audiograma_da_clinica():
    """Kit juntado com o audiograma da clínica antes do ASO.

    O cabeçalho do audiograma traz o CNPJ da clínica e o do "Empregador"; o da
    consulta é o da empresa do ASO. Pegar o primeiro rótulo dava "Paciente não
    encontrado" (kit de 09/11/2026, audiograma REFORGE + ASO BR MED).
    """
    markdown = (
        "<!-- pagina 1 -->\n"
        "Audiograma\n"
        "## CLINICA PARCEIRA\n"
        "CEP: 13170-675 - CNPJ: 11.243.246/0001-00\n"
        "## AUDIOGRAMA PERIÓDICO (SEQUENCIAL)\n"
        "Empregador:\n"
        "OUTRA EMPRESA LTDA\n"
        "## CNPJ:\n"
        "36.182.482/0001-95\n"
        "<!-- pagina 2 -->\n"
        "Atestado de Saúde Ocupacional\n"
        "\n"
        "## BR MED\n"
        "\n"
        "Medical Health Certificate\n"
        "EMPRESA DO PEDIDO LTDA\n"
        "\n"
        "## CNPJ: 03.214.786/0004-80\n"
        "\n"
        "1. Identificação / Identification:\n"
    )
    assert ocr_service.extrair_cnpj_regex(markdown) == "03214786000480"


def test_extrair_cnpj_regex_aso_vence_voucher():
    markdown = (
        "## VOUCHER\n"
        "EMPRESA X\n"
        "CNPJ: 12.345.678/0001-95\n"
        "1. Identificacao / Identification:\n"
        "Atestado de Saúde Ocupacional\n"
        "Medical Health Certificate\n"
        "EMPRESA DO PEDIDO LTDA\n"
        "CNPJ: 03.214.786/0004-80\n"
        "1. Identificação / Identification:\n"
    )
    assert ocr_service.extrair_cnpj_regex(markdown) == "03214786000480"


def test_extrair_cnpj_do_aso_valor_na_linha_de_baixo():
    """Formulário de ASO da VIX: rótulo sozinho e o valor na linha seguinte."""
    markdown = (
        "ASO Atestado de Saúde Ocupacional\n"
        "Razão Social:\n"
        "## EMPRESA DO PEDIDO LTDA\n"
        "## CNPJ :\n"
        "03.214.786/0004-80\n"
        "Responsável PCMSO\n"
    )
    assert ocr_service._extrair_cnpj_do_aso(markdown) == "03214786000480"


def test_extrair_cnpj_do_aso_ignora_recibo_e_cnpj_apos_identificacao():
    """O recibo cita o ASO no meio da frase e não abre janela; o CNPJ depois da
    seção 1 não é o da empresa."""
    markdown = (
        "Recebi a Segunda via deste ASO (Atestado de Saúde Ocupacional) e todas as informações\n"
        "<!-- pagina 2 -->\n"
        "LABORATORIO X\n"
        "CNPJ: 11.243.246/0001-00\n"
        "Atestado de Saúde Ocupacional\n"
        "EMPRESA DO PEDIDO LTDA\n"
        "1. Identificação / Identification:\n"
        "CNPJ: 03.214.786/0004-80\n"
    )
    assert ocr_service._extrair_cnpj_do_aso(markdown) is None


def test_extrair_cnpj_regex_loga_a_fonte(caplog):
    """O campo fonte= permite validar no log se o CNPJ veio do voucher."""
    voucher = (
        "CNPJ: 11.243.246/0001-00\n"
        "\n## VOUCHER\n\n"
        "EMPRESA X\n"
        "CNPJ: 03.214.786/0004-80\n"
        "1. Identificacao / Identification:\n"
    )
    with caplog.at_level(logging.INFO, logger="app.services.ocr_service"):
        assert ocr_service.extrair_cnpj_regex(voucher) == "03214786000480"
    assert "fonte=voucher" in caplog.text
    # O CNPJ nunca vai em claro para o log.
    assert "03214786000480" not in caplog.text

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="app.services.ocr_service"):
        assert ocr_service.extrair_cnpj_regex("EMPRESA X\nCNPJ: 12.345.678/0001-95\n") == "12345678000195"
    assert "fonte=documento_rotulo" in caplog.text

    caplog.clear()
    aso = "Atestado de Saúde Ocupacional\nEMPRESA X\nCNPJ: 03.214.786/0004-80\n"
    with caplog.at_level(logging.INFO, logger="app.services.ocr_service"):
        assert ocr_service.extrair_cnpj_regex(aso) == "03214786000480"
    assert "fonte=aso" in caplog.text


def test_extrair_passaporte_regex():
    markdown = "Dados do paciente\nPassaporte: ab123456\n"
    assert ocr_service.extrair_passaporte_regex(markdown) == "AB123456"


def test_extrair_cpf_regex_rotulo_combinado_cpf_passport():
    """Voucher/ASO da BR MED imprimem um campo único "CPF / Passport".

    O rótulo tem 13 caracteres entre "CPF" e o número, acima da tolerância de
    10 do passo por rótulo, então sem tratamento próprio o CPF só era achado
    pelo fallback por linha - que falha quando o OCR funde as colunas.
    """
    markdown = "Nome / Name: PATRICIA\nCPF / Passport: 10413412610\n"
    assert ocr_service.extrair_cpf_regex(markdown) == "10413412610"

    fundido = "CPF / Passport: 10413412610 Identidade / ID Number: 16041755\n"
    assert ocr_service.extrair_cpf_regex(fundido) == "10413412610"


def test_extrair_passaporte_regex_ignora_cpf_em_rotulo_combinado():
    """CPF válido no campo "CPF / Passport" não é passaporte.

    Tratá-lo como passaporte fazia a consulta externa sair por ?passport= e o
    paciente nunca era encontrado ("Paciente não encontrado para o CNPJ, CPF ou
    Passaporte informados"), porque o desempate descartava o CPF correto.
    """
    markdown = "Nome / Name: PATRICIA\nCPF / Passport: 10413412610\n"
    assert ocr_service.extrair_passaporte_regex(markdown) is None


def test_extrair_passaporte_regex_aceita_passaporte_em_rotulo_combinado():
    """Estrangeiro: o mesmo campo traz um passaporte de verdade."""
    markdown = "Nome / Name: JOHN SMITH\nCPF / Passport: ab123456\n"
    assert ocr_service.extrair_passaporte_regex(markdown) == "AB123456"
    assert ocr_service.extrair_cpf_regex(markdown) is None


@patch(
    "app.services.ocr_service.ocr_pipeline",
    return_value={
        "cpf": "12345678900",
        "passaporte": "AB123456",
        "cnpj": "12345678000190",
        "exames": ["HEMOGRAMA"],
    },
)
def test_ocr_route(mock_pipeline, client):
    response = client.post("/v1/ocr", files={"arquivo": ("teste.pdf", b"dummy", "application/pdf")})
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["cpf"] == "12345678900"
    assert data["passaporte"] == "AB123456"
    assert data["cnpj"] == "12345678000190"
    assert "HEMOGRAMA" in data["exames"]
