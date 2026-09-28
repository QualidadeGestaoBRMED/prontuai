"""
Testes do casamento de exames e da rota de validação.

Os dois testes unitários antigos (`fuzzy_match` e `comparar_listas_exames`)
apontavam para funções que nunca existiram nesta história do repositório —
nasceram quebrados e ficaram anos assim. Foram reescritos contra o que de fato
faz esse trabalho hoje: `_match_exame_local`, o casamento determinístico que
roda ANTES de qualquer embedding ou LLM e resolve a maioria dos casos sozinho.

Cada asserção abaixo foi medida no serviço real, não deduzida do código.
"""
from fastapi import status

from app.services import validacao_service


# ── casamento determinístico (o que substituiu o antigo fuzzy_match) ────────

def test_match_ignora_caixa():
    ocr = ["hemograma completo", "glicose"]
    assert validacao_service._match_exame_local("HEMOGRAMA COMPLETO", ocr) == "hemograma completo"
    assert validacao_service._match_exame_local("GLICOSE", ocr) == "glicose"


def test_match_devolve_none_quando_o_exame_nao_veio():
    """Faltante de verdade: é o que vira `exames_faltantes` na comparação."""
    assert validacao_service._match_exame_local("TSH", ["hemograma completo", "glicose"]) is None


def test_match_reconhece_raio_x_como_radiografia():
    """`_normalizar_exame` reescreve RAIO X/RX; sem isso o mesmo exame contava
    como faltante só por causa de como o laudo o escreveu."""
    assert (
        validacao_service._match_exame_local("RAIO X DE TORAX", ["radiografia de torax"])
        == "radiografia de torax"
    )


def test_match_reconhece_gama_gt_como_ggt():
    assert (
        validacao_service._match_exame_local("GAMA GLUTAMIL TRANSFERASE", ["GGT"]) == "GGT"
    )


def test_match_aceita_nome_do_ocr_mais_especifico():
    """O OCR costuma trazer o nome completo do laudo; o BRNET pede o curto."""
    assert (
        validacao_service._match_exame_local("HEMOGRAMA", ["HEMOGRAMA COMPLETO COM PLAQUETAS"])
        == "HEMOGRAMA COMPLETO COM PLAQUETAS"
    )


def test_audiometria_casa_por_marcador():
    """Audiometria tem tratamento próprio: o laudo raramente repete o nome que
    o BRNET pede."""
    assert (
        validacao_service._match_exame_local("AUDIOMETRIA TONAL", ["audiometria ocupacional"])
        == "audiometria ocupacional"
    )


def test_normalizacao_remove_acento_e_pontuacao():
    assert validacao_service._normalizar_exame("Raio-X  de Tórax") == "RADIOGRAFIA DE TORAX"
    assert validacao_service._normalizar_exame("Gama GT") == "GGT"


# ── rota ───────────────────────────────────────────────────────────────────

PAYLOAD = {
    "cpf": "12345678900",
    "exames_obrigatorios": ["HEMOGRAMA COMPLETO", "GLICOSE"],
    "exames_enviados": ["hemograma completo", "glicose"],
}


def _sem_llm(monkeypatch, tmp_path, comparacao):
    """Troca a ida à OpenAI por uma resposta fixa e manda a auditoria para um
    diretório temporário.

    `comparar_exames_com_rag` SEMPRE chama a OpenAI — não há caminho local nela.
    Sem este mock a rota só passaria com chave de verdade, e o teste viraria
    chamada de rede paga e não determinística. O resto do pipeline continua
    real: é nele que mora a regressão.

    A auditoria sai do `cwd` e grava o CPF no nome do arquivo; em `tmp_path` o
    teste não acumula CPF no disco de quem roda.
    """
    async def falso(exames_ocr, exames_brnet):
        return comparacao

    monkeypatch.setattr(validacao_service, "comparar_exames_com_rag", falso)
    monkeypatch.chdir(tmp_path)


def test_validacao_route(client, monkeypatch, tmp_path):
    """Regressão: `validar_exames` virou assíncrona e ganhou `exames_brnet`, e a
    rota continuou chamando com 3 argumentos e sem await — respondia 500."""
    _sem_llm(monkeypatch, tmp_path, [
        {"exame": "HEMOGRAMA COMPLETO", "status": "encontrado", "justificativa": "-"},
        {"exame": "GLICOSE", "status": "encontrado", "justificativa": "-"},
    ])

    response = client.post("/v1/validacao", json=PAYLOAD)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status_liberado"]
    assert data["exames_faltantes"] == []


def test_validacao_route_corrige_faltante_errado_da_ia(client, monkeypatch, tmp_path):
    """A rede de segurança determinística: a IA disse que a glicose faltou, mas
    ela está na lista enviada. `_match_exame_local` conserta antes de responder."""
    _sem_llm(monkeypatch, tmp_path, [
        {"exame": "HEMOGRAMA COMPLETO", "status": "encontrado", "justificativa": "-"},
        {"exame": "GLICOSE", "status": "faltante", "justificativa": "nao encontrei"},
    ])

    response = client.post("/v1/validacao", json=PAYLOAD)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status_liberado"]
    assert data["exames_faltantes"] == []


def test_validacao_route_reporta_faltante_de_verdade(client, monkeypatch, tmp_path):
    """Exame que o BRNET exige e não veio: tem de sair em `exames_faltantes`."""
    _sem_llm(monkeypatch, tmp_path, [
        {"exame": "HEMOGRAMA COMPLETO", "status": "encontrado", "justificativa": "-"},
        {"exame": "TSH", "status": "faltante", "justificativa": "nao veio"},
    ])

    response = client.post(
        "/v1/validacao",
        json={**PAYLOAD, "exames_obrigatorios": ["HEMOGRAMA COMPLETO", "TSH"]},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert not data["status_liberado"]
    assert "TSH" in data["exames_faltantes"]
