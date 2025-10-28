import pytest
from unittest.mock import patch, MagicMock
from app.services import ocr_service
from fastapi import status

# Teste unitário: normal OCR pipeline com mock
@patch("app.services.ocr_service.processar_arquivo_docling", return_value="# HEMOGRAMA\n## GLICOSE")
@patch("app.services.ocr_service.extrair_info_ia", return_value={"cpf": "12345678900", "exames": ["HEMOGRAMA", "GLICOSE"]})
def test_ocr_pipeline_success(mock_ia, mock_docling):
    class DummyFile:
        filename = "teste.pdf"
        def save(self, path):
            with open(path, "w") as f:
                f.write("dummy")
    result = ocr_service.ocr_pipeline(DummyFile(), salvar_markdown=False)
    assert result["cpf"] == "12345678900"
    assert "HEMOGRAMA" in result["exames"]
    assert "GLICOSE" in result["exames"]

# Teste de fallback de CPF via regex
@patch("app.services.ocr_service.processar_arquivo_docling", return_value="Paciente: Fulano CPF: 111.222.333-44\n## HEMOGRAMA")
@patch("app.services.ocr_service.extrair_info_ia", return_value={"cpf": None, "exames": ["HEMOGRAMA"]})
def test_ocr_pipeline_fallback_cpf(mock_ia, mock_docling):
    class DummyFile:
        filename = "teste2.pdf"
        def save(self, path):
            with open(path, "w") as f:
                f.write("dummy")
    result = ocr_service.ocr_pipeline(DummyFile(), salvar_markdown=False)
    assert result["cpf"] == "11122233344"
    assert "HEMOGRAMA" in result["exames"]

# Teste de integração da rota OCR
@patch("app.services.ocr_service.ocr_pipeline", return_value={"cpf": "12345678900", "exames": ["HEMOGRAMA"]})
def test_ocr_route(mock_pipeline, client):
    response = client.post("/v1/ocr", files={"arquivo": ("teste.pdf", b"dummy", "application/pdf")})
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["cpf"] == "12345678900"
    assert "HEMOGRAMA" in data["exames"]
