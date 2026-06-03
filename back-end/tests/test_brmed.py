from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status

from app.services import brmed_service



def test_select_latest_pedido_by_date():
    pedidos = [
        {"pedido_exame_id": "C-1", "data_previsao_liberacao": "01/03/2026"},
        {"pedido_exame_id": "C-2", "data_previsao_liberacao": "10/03/2026"},
        {"pedido_exame_id": "C-3", "data_previsao_liberacao": "05/03/2026"},
    ]
    selected = brmed_service._select_latest_pedido(pedidos)
    assert selected["pedido_exame_id"] == "C-2"


def test_select_latest_pedido_without_valid_date_uses_last():
    pedidos = [
        {"pedido_exame_id": "C-1", "data_previsao_liberacao": "invalid"},
        {"pedido_exame_id": "C-2", "data_previsao_liberacao": None},
        {"pedido_exame_id": "C-3"},
    ]
    selected = brmed_service._select_latest_pedido(pedidos)
    assert selected["pedido_exame_id"] == "C-3"


def test_select_latest_pedido_with_same_date_uses_last_in_order():
    pedidos = [
        {"pedido_exame_id": "C-1", "data_previsao_liberacao": "31/03/2026"},
        {"pedido_exame_id": "C-2", "data_previsao_liberacao": "31/03/2026"},
    ]
    selected = brmed_service._select_latest_pedido(pedidos)
    assert selected["pedido_exame_id"] == "C-2"


@pytest.mark.asyncio
async def test_prontuai_api_validation_rejects_cpf_and_passport_together():
    result = await brmed_service.consultar_exames_prontuai_api(
        cpf="12345678901",
        passaporte="AB123456",
        cnpj="12345678000190",
    )
    assert result["error_type"] == "semantic"
    assert result["http_status"] == 400


@pytest.mark.asyncio
async def test_prontuai_api_success_maps_latest_pedido():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": 123,
        "nome": "PACIENTE TESTE",
        "pedidos_exames": [
            {
                "pedido_exame_id": "C-OLD",
                "data_previsao_liberacao": "01/03/2026",
                "tipo_pedido_exame": "PERIODICO",
                "exames": [{"nome": "GLICOSE"}],
            },
            {
                "pedido_exame_id": "C-NEW",
                "data_previsao_liberacao": "15/03/2026",
                "tipo_pedido_exame": "ADMISSIONAL",
                "exames": [{"nome": "HEMOGRAMA"}, {"nome": "AUDIOMETRIA"}],
            },
        ],
    }

    with (
        patch.object(brmed_service.settings, "PRONTUAI_SERVICE_TOKEN", "token"),
        patch.object(brmed_service.settings, "PRONTUAI_CLIENT_NAME", "client"),
        patch("app.services.brmed_service.httpx.AsyncClient") as mock_client_cls,
    ):
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await brmed_service.consultar_exames_prontuai_api(
            cpf="12345678901",
            cnpj="12345678000190",
        )

    assert "erro" not in result
    assert result["source"] == "prontuai_api"
    assert result["pedido_exame_id"] == "C-NEW"
    assert result["exames"] == ["HEMOGRAMA", "AUDIOMETRIA"]


@patch("app.services.brmed_service.consultar_exames_prontuai", return_value={"nome": "FULANO", "exames": ["HEMOGRAMA"], "source": "prontuai_api"})
def test_consultar_brmed_route_uses_prontuai_api(mock_prontuai, client):
    response = client.post("/v1/consultar-brmed", json={"cpf": "12345678900", "cnpj": "12345678000190"})
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["nome"] == "FULANO"
    assert "HEMOGRAMA" in data["exames"]
    mock_prontuai.assert_called_once_with(cpf="12345678900", passaporte=None, cnpj="12345678000190")
