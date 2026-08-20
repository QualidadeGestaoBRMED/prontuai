import io
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
