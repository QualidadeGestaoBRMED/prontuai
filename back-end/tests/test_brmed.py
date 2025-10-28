import pytest
from unittest.mock import patch
from app.services import brmed_service
from fastapi import status

# Teste unitário: parsing de exames

def test_extract_nome_e_exames():
    texto = (
        "Nome / Name: FULANO DE TAL\n"
        "4. Exames\n"
        "HEMOGRAMA COMPLETO\tGLICOSE\n"
        "ELETROCARDIOGRAMA\n"
    )
    result = brmed_service.extract_nome_e_exames(texto)
    assert result["nome"] == "FULANO DE TAL"
    assert "HEMOGRAMA COMPLETO" in result["exames"]
    assert "GLICOSE" in result["exames"]
    assert "ELETROCARDIOGRAMA" in result["exames"]

# Teste de integração da rota BRMED
@patch("app.services.brmed_service.consultar_exames_brmed", return_value={"nome": "FULANO", "exames": ["HEMOGRAMA"]})
def test_brmed_route(mock_brmed, client):
    response = client.post("/v1/brmed/exames-obrigatorios", params={"cpf": "12345678900"})
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["nome"] == "FULANO"
    assert "HEMOGRAMA" in data["exames"]
