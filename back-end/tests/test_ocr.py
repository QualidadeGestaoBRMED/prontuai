from unittest.mock import patch

from fastapi import status

from app.services import ocr_service


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
