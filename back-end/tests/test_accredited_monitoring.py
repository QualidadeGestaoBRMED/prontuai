from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import accredited_monitoring_service as svc


def _item(**overrides):
    item = {
        "pedido_exame_id": 1234567,
        "credenciado": "RECIFE - PE - CLINICA TESTE",
        "empresa": "EMPRESA TESTE - PE (00.000.000/0001-00)",
        "grupo": "GRUPO TESTE",
        "paciente": "PACIENTE TESTE",
        "cpf_passaporte": "00000000000",
        "tipo_pedido_exame": "ADMISSIONAL",
        "data_solicitacao": "01/09/2026 08:15:00",
        "data_confirmacao": "01/09/2026 08:20:00",
        "mes_agendamento": "Set/2026",
        "status_agendamento": "01. AUTOMÁTICO",
        "usuario_agendamento": "credenciado.automatico",
        "confirmacao_automatica": "Sim",
        "tempo_resposta": "36:16",
        "data_atendimento": "02/09/2026",
        "mes_atendimento": "Set/2026",
        "data_cadastro_atendimento": "02/09/2026",
        "usuario_atendimento": "usuario",
        "prazo_liberacao": 3,
        "data_previsao": "05/09/2026",
        "utilizou_o_br_net": "Não",
        "status_expedicao_cliente": "Em dia",
        "status_expedicao_brmed": "Pendente - Exame alterado",
        "data_liberacao": "",
        "usuario_expedicao": "",
        "possui_anexo": "Não",
        "data_inclusao_exame_alterado": "03/09/2026 10:00:00",
        "data_inclusao_exame_não_realizado": "",
        "data_inclusao_particularidade_não_atendida": "",
        "possui_observacao_cliente": "Não",
        "observacoes_cliente": "",
    }
    item.update(overrides)
    return item


def _item_nao_atendido():
    campos_atendimento = (
        "data_atendimento", "mes_atendimento", "data_cadastro_atendimento", "usuario_atendimento",
        "prazo_liberacao", "data_previsao", "utilizou_o_br_net", "status_expedicao_cliente",
        "status_expedicao_brmed", "data_inclusao_exame_alterado",
    )
    return _item(**{campo: "" for campo in campos_atendimento})


def test_mapear_atendimento_tipa_campos():
    r = svc.mapear_atendimento(_item())
    assert r.data_solicitacao == datetime(2026, 9, 1, 8, 15)
    assert r.data_previsao == date(2026, 9, 5)
    assert r.prazo_liberacao == 3
    assert r.tempo_resposta_minutos == 36 * 60 + 16
    assert r.confirmacao_automatica is True
    assert r.utilizou_o_br_net is False
    assert r.data_liberacao is None
    assert r.data_inclusao_exame_alterado == datetime(2026, 9, 3, 10)
    assert r.atendido is True


def test_mapear_atendimento_nao_atendido_vira_none():
    r = svc.mapear_atendimento(_item_nao_atendido())
    assert r.atendido is False
    assert r.prazo_liberacao is None
    assert r.data_previsao is None
    assert r.utilizou_o_br_net is None
    assert r.status_expedicao_brmed is None


def test_repr_nao_expoe_pii():
    texto = repr(svc.mapear_atendimento(_item()))
    assert "PACIENTE TESTE" not in texto
    assert "00000000000" not in texto


@pytest.mark.parametrize(
    "rotulo, esperado",
    [
        ("RECIFE - PE - QUALIMETRA", ("RECIFE", "PE", "QUALIMETRA")),
        ("PIRAPORA – MG – CLINICA HUMANITAS", ("PIRAPORA", "MG", "CLINICA HUMANITAS")),
        ("ITAPEVA - SP- SAME", ("ITAPEVA", "SP", "SAME")),
        ("SÃO LUIS - MA - SELPMED - FILIAL", ("SÃO LUIS", "MA", "SELPMED - FILIAL")),
        ("EMBU-GUAÇU - SP - CLINICA X", ("EMBU-GUAÇU", "SP", "CLINICA X")),
    ],
)
def test_parse_credenciado(rotulo, esperado):
    ref = svc.parse_credenciado(rotulo)
    assert (ref.cidade, ref.uf, ref.nome) == esperado
    assert ref.rotulo == rotulo


def test_parse_credenciado_fora_do_padrao_preserva_rotulo():
    ref = svc.parse_credenciado("CLINICA SEM CIDADE")
    assert ref.rotulo == "CLINICA SEM CIDADE"
    assert ref.uf is None and ref.nome is None


def _mock_client(response):
    client = AsyncMock()
    client.get.return_value = response
    ctx = AsyncMock()
    ctx.__aenter__.return_value = client
    return ctx, client


def _settings_ok(mock_settings):
    mock_settings.PRONTUAI_API_BASE_URL = "https://api.exemplo"
    mock_settings.ACCREDITED_MONITORING_SERVICE_TOKEN = "token"
    mock_settings.ACCREDITED_MONITORING_USERNAME = "usuario"
    mock_settings.ACCREDITED_MONITORING_TIMEOUT_SECONDS = 60


@pytest.mark.asyncio
async def test_consulta_envia_parametros_e_descarta_item_invalido():
    response = MagicMock(status_code=200, content=b"[]")
    response.json.return_value = [_item(), _item(pedido_exame_id=2, tempo_resposta="invalido")]
    ctx, client = _mock_client(response)

    with patch.object(svc, "settings") as mock_settings, patch.object(svc.httpx, "AsyncClient", return_value=ctx):
        _settings_ok(mock_settings)
        registros = await svc.consultar_monitoramento_credenciados(9, 2026)

    assert [r.pedido_exame_id for r in registros] == [1234567]
    _, kwargs = client.get.call_args
    assert client.get.call_args.args[0] == "https://api.exemplo/api/accrediteds/get-accredited-monitoring/"
    assert kwargs["params"] == {"month": 9, "year": 2026}
    assert kwargs["headers"] == {"Service-Token": "token", "Username": "usuario"}


@pytest.mark.asyncio
async def test_erro_400_em_texto_vira_semantic():
    response = MagicMock(status_code=400, content=b"", text="O ano informado é inválido")
    response.json.side_effect = ValueError()
    ctx, _ = _mock_client(response)

    with patch.object(svc, "settings") as mock_settings, patch.object(svc.httpx, "AsyncClient", return_value=ctx):
        _settings_ok(mock_settings)
        with pytest.raises(svc.MonitoramentoCredenciadosError) as exc:
            await svc.consultar_monitoramento_credenciados(9, 1999)

    assert exc.value.error_type == "semantic"
    assert exc.value.http_status == 400
    assert str(exc.value) == "O ano informado é inválido"


@pytest.mark.asyncio
async def test_mes_invalido_nem_chama_api():
    with pytest.raises(svc.MonitoramentoCredenciadosError) as exc:
        await svc.consultar_monitoramento_credenciados(13, 2026)
    assert exc.value.error_type == "semantic"
