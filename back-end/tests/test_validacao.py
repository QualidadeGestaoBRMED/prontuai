import pytest
from app.services import validacao_service
from fastapi import status

# Teste unitário: fuzzy matching e comparação

def test_fuzzy_match():
    lista = ["HEMOGRAMA COMPLETO", "GLICOSE"]
    assert validacao_service.fuzzy_match("hemograma completo", lista)
    assert not validacao_service.fuzzy_match("TSH", lista)

def test_comparar_listas_exames():
    obrigatorios = ["HEMOGRAMA COMPLETO", "GLICOSE"]
    enviados = ["hemograma completo", "glicose"]
    result = validacao_service.comparar_listas_exames(obrigatorios, enviados)
    assert result["status_liberado"]
    assert result["exames_faltantes"] == []
    enviados = ["hemograma completo"]
    result = validacao_service.comparar_listas_exames(obrigatorios, enviados)
    assert not result["status_liberado"]
    assert "GLICOSE" in result["exames_faltantes"]

# Teste de integração da rota de validação

def test_validacao_route(client):
    payload = {
        "cpf": "12345678900",
        "exames_obrigatorios": ["HEMOGRAMA COMPLETO", "GLICOSE"],
        "exames_enviados": ["hemograma completo", "glicose"]
    }
    response = client.post("/v1/validacao", json=payload)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status_liberado"]
    assert data["exames_faltantes"] == []
