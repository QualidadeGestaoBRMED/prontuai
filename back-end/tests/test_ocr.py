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
    markdown = "Paciente: Fulano\nCPF: 111.222.333-44\n"
    assert ocr_service.extrair_cpf_regex(markdown) == "11122233344"


def test_extrair_cnpj_regex():
    markdown = "Empresa XYZ\nCNPJ: 12.345.678/0001-90\n"
    assert ocr_service.extrair_cnpj_regex(markdown) == "12345678000190"


def test_extrair_passaporte_regex():
    markdown = "Dados do paciente\nPassaporte: ab123456\n"
    assert ocr_service.extrair_passaporte_regex(markdown) == "AB123456"


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
