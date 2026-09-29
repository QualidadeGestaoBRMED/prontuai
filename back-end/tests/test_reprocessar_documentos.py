"""
Testes do `scripts/reprocessar_documentos.py`.

O script grava sobre documentos de produção, então o que precisa de rede de
segurança não é o "caminho feliz" — é tudo aquilo que ele se recusa a fazer:

- não reprocessar documento que falhou ANTES da comparação (no banco de dev são
  596 de 598 com comparativo vazio: paciente não encontrado, CNPJ inválido,
  expedição inexistente). Para esses o reprocessamento não resolve nada e
  sobrescreveria o erro que explica o caso;
- não mexer na decisão humana de quem já foi aprovado/rejeitado na checagem;
- não gravar nada quando a comparação falha de novo, para não apagar o erro
  original;
- não gravar com o índice de similaridade descarregado, quando a comparação
  rodaria sem contexto RAG e ninguém perceberia pelo resultado.

A comparação é mockada como em `test_validacao.py`: `comparar_exames_com_rag`
sempre chama a OpenAI, e sem o mock estes testes virariam chamada de rede paga e
não determinística. O resto — elegibilidade, recálculo de confiança, montagem do
payload e o que chega no `update_document` — roda de verdade, porque é nele que
mora a regressão.
"""
import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import validacao_service

CAMINHO_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "reprocessar_documentos.py"


def _carregar_script():
    """`scripts/` não é pacote — carrega pelo caminho, como faria o operador."""
    spec = importlib.util.spec_from_file_location("reprocessar_documentos", CAMINHO_SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


script = _carregar_script()

MARKDOWN = """
# ASO
NOME DO PACIENTE: PACIENTE DE TESTE
HEMOGRAMA COMPLETO - 01/09/2026
GLICOSE - 01/09/2026
"""

ERRO_COMPARACAO = "Erro ao comparar exames (fallback): Event loop is closed"


def _documento(**sobrescreve):
    """Documento no estado exato que o bug deixava: comparativo vazio, erro da
    comparação, e `exams_ocr`/`exams_brnet` intactos — é o que torna o
    reprocessamento possível sem o PDF."""
    payload = {
        "cpf_processado": "12345678900",
        "patient_name": "PACIENTE DE TESTE",
        "exames_ocr": ["hemograma completo", "glicose"],
        "exames_brnet": ["HEMOGRAMA COMPLETO", "GLICOSE"],
        "tabela_comparacao": [],
        "erro": ERRO_COMPARACAO,
        "status": "error",
        "confidence_score": 34,
        "analysis_details": {"quality": {"score": 85}},
    }
    payload.update(sobrescreve.pop("payload", {}))
    base = dict(
        id="doc-1",
        result_payload=payload,
        exams_ocr=["hemograma completo", "glicose"],
        exams_brnet=["HEMOGRAMA COMPLETO", "GLICOSE"],
        cpf="12345678900",
        ocr_markdown=MARKDOWN,
        reviewed_by=None,
    )
    base.update(sobrescreve)
    return SimpleNamespace(**base)


@pytest.fixture
def banco(monkeypatch):
    """Substitui o repositório: nada vai para o Postgres, e o teste inspeciona o
    que o script TENTOU gravar."""
    estado = {"documento": _documento(), "updates": [], "auditorias": []}

    monkeypatch.setattr(
        script.user_db, "get_document_by_id",
        lambda document_id: estado["documento"] if estado["documento"] else None,
    )
    monkeypatch.setattr(
        script.user_db, "update_document",
        lambda **campos: estado["updates"].append(campos),
    )
    monkeypatch.setattr(
        script.user_db, "create_audit_log",
        lambda entrada: estado["auditorias"].append(entrada),
    )
    return estado


@pytest.fixture
def comparacao_ok(monkeypatch):
    """Comparação que encontra os dois exames."""
    async def falso(exames_ocr, exames_brnet):
        return [
            {"exame": "HEMOGRAMA COMPLETO", "status": "encontrado", "justificativa": "-"},
            {"exame": "GLICOSE", "status": "encontrado", "justificativa": "-"},
        ]

    monkeypatch.setattr(validacao_service, "comparar_exames_com_rag", falso)


@pytest.fixture(autouse=True)
def auditoria_em_tmp(monkeypatch, tmp_path):
    """`validar_exames` chama `salvar_auditoria`, que grava um JSON com o CPF no
    nome relativo ao cwd. Em `tmp_path` o teste não acumula CPF no disco."""
    monkeypatch.chdir(tmp_path)


def _rodar(
    document_id="doc-1",
    aplicar=True,
    incluir_revisados=False,
    etapa=script.ETAPA_COMPARACAO,
    padroes=None,
):
    if padroes is None:
        padroes = script.ETAPAS[etapa]["padroes"]
    return asyncio.run(
        script._reprocessar(document_id, aplicar, incluir_revisados, etapa, padroes)
    )


# ── o que ele se recusa a fazer ─────────────────────────────────────────────

@pytest.mark.parametrize(
    "erro",
    [
        "Paciente não encontrado para o CNPJ, CPF ou Passaporte informados.",
        "cnpj é obrigatório e deve ter 14 dígitos",
        "Expedição em aberto não encontrada para o paciente informado.",
        None,
    ],
)
def test_ignora_falha_anterior_a_comparacao(banco, comparacao_ok, erro):
    """Os 596 do dev: falharam antes de existir exame obrigatório. Reprocessar a
    comparação não resolve, e gravar apagaria o erro que explica o caso."""
    banco["documento"] = _documento(payload={"erro": erro})

    resultado = _rodar()

    assert resultado["situacao"] == "inelegivel"
    assert banco["updates"] == []


def test_ignora_documento_sem_exames_brnet(banco, comparacao_ok):
    """Sem exigência do BRNET não há o que comparar, mesmo com o erro certo."""
    banco["documento"] = _documento(exams_brnet=[], payload={"exames_brnet": []})

    resultado = _rodar()

    assert resultado["situacao"] == "inelegivel"
    assert "BRNET" in resultado["detalhe"]
    assert banco["updates"] == []


def test_documento_revisado_fica_de_fora_por_padrao(banco, comparacao_ok):
    banco["documento"] = _documento(reviewed_by="revisor@grupobrmed.com.br")

    resultado = _rodar()

    assert resultado["situacao"] == "revisado_ignorado"
    assert banco["updates"] == []


def test_revisor_apenas_no_payload_tambem_conta_como_revisado(banco, comparacao_ok):
    """Em parte da base o revisor só está no `result_payload`; olhar a coluna
    `reviewed_by` sozinha deixaria o script mexer numa decisão humana."""
    banco["documento"] = _documento(payload={"reviewed_by": "revisor@grupobrmed.com.br"})

    assert _rodar()["situacao"] == "revisado_ignorado"


def test_revisado_incluido_preserva_a_decisao(banco, comparacao_ok):
    """Com `--incluir-revisados` o comparativo entra e a decisão não se mexe.

    Duas coisas garantem isso, e ambas são verificadas aqui: `validation_status`
    não vai no update (então o `validated`/`rejected` da checagem permanece), e
    `reviewed_by` também não — `update_document` só toca a coluna quando recebe o
    campo ou quando o encontra no payload, logo omitir os dois deixa a coluna
    intacta.
    """
    banco["documento"] = _documento(reviewed_by="revisor@grupobrmed.com.br")

    resultado = _rodar(incluir_revisados=True)

    assert resultado["situacao"] == "ok"
    (campos,) = banco["updates"]
    assert "validation_status" not in campos
    assert "reviewed_by" not in campos
    assert campos["result_payload"]["tabela_comparacao"]


def test_revisor_no_payload_sobrevive_a_remontagem(banco, comparacao_ok):
    """Quando o revisor está no payload, ele tem de continuar lá depois do
    reprocessamento: `update_document` relê `reviewed_by` de dentro do payload,
    então perdê-lo na remontagem desfaria a decisão humana no banco."""
    banco["documento"] = _documento(payload={"reviewed_by": "revisor@grupobrmed.com.br"})

    resultado = _rodar(incluir_revisados=True)

    assert resultado["situacao"] == "ok"
    (campos,) = banco["updates"]
    assert campos["result_payload"]["reviewed_by"] == "revisor@grupobrmed.com.br"
    assert "validation_status" not in campos


def test_nao_grava_quando_a_comparacao_falha_de_novo(banco, monkeypatch):
    """Sobrescrever com um erro novo só apagaria o rastro do original."""
    async def falha(exames_ocr, exames_brnet):
        return {"erro": "Erro ao comparar exames (fallback): Connection error."}

    monkeypatch.setattr(validacao_service, "comparar_exames_com_rag", falha)

    resultado = _rodar()

    assert resultado["situacao"] == "falhou_de_novo"
    assert banco["updates"] == []
    assert banco["auditorias"] == []


def test_dry_run_nao_grava(banco, comparacao_ok):
    resultado = _rodar(aplicar=False)

    assert resultado["situacao"] == "ok_dry_run"
    assert banco["updates"] == []
    assert banco["auditorias"] == []


def test_preflight_barra_sem_indice_de_similaridade(monkeypatch):
    """Com o índice descarregado a comparação roda sem contexto RAG e o resultado
    não denuncia isso — é o pior desfecho num reprocessamento."""
    monkeypatch.setattr(validacao_service, "exam_similarity_index", None)
    assert script._preflight_indice(permitir_sem_indice=False) is not None

    monkeypatch.setattr(validacao_service, "exam_similarity_index", object())
    assert script._preflight_indice(permitir_sem_indice=False) is None


# ── o que ele grava quando pode ────────────────────────────────────────────

def test_payload_reconstruido_preenche_a_comparacao(banco, comparacao_ok):
    resultado = _rodar()

    assert resultado["situacao"] == "ok"
    (campos,) = banco["updates"]
    payload = campos["result_payload"]

    assert len(payload["tabela_comparacao"]) == 2
    assert payload["erro"] is None
    assert payload["status"] == "success"
    assert payload["validation_result"]["exames_faltantes"] == []
    assert campos["validation_status"] == "pending"
    # Rastro para excluir estes documentos da medição de acurácia do período.
    assert payload["reprocessado_por"].endswith("reprocessar_documentos.py")
    assert payload["reprocessado_motivo"] == ERRO_COMPARACAO


def test_confianca_sai_do_chao(banco, comparacao_ok):
    """Era 34 porque a cobertura de obrigatórios foi calculada sobre comparativo
    vazio (cobertura 0). Com os dois exames encontrados, cobertura 1."""
    resultado = _rodar()

    assert resultado["confianca_antes"] == 34
    (campos,) = banco["updates"]
    assert campos["mandatory_coverage"] == 1.0
    assert campos["confidence_score"] > 34
    assert campos["result_payload"]["confidence_details"]["mandatory_found"] == 2


def test_dados_alheios_a_falha_sobrevivem(banco, comparacao_ok):
    """O payload novo parte do antigo: nome, CPF e o que veio do BRNET não têm
    relação com a falha e não podem se perder no reprocessamento."""
    _rodar()

    payload = banco["updates"][0]["result_payload"]
    assert payload["patient_name"] == "PACIENTE DE TESTE"
    assert payload["cpf_processado"] == "12345678900"
    assert payload["exames_brnet"] == ["HEMOGRAMA COMPLETO", "GLICOSE"]


def test_faltante_de_verdade_continua_faltante(banco, monkeypatch):
    """Reprocessar não é liberar: exame exigido que não veio segue faltante, e o
    documento segue não liberado."""
    async def falso(exames_ocr, exames_brnet):
        return [
            {"exame": "HEMOGRAMA COMPLETO", "status": "encontrado", "justificativa": "-"},
            {"exame": "TSH", "status": "faltante", "justificativa": "nao veio"},
        ]

    monkeypatch.setattr(validacao_service, "comparar_exames_com_rag", falso)
    banco["documento"] = _documento(
        exams_brnet=["HEMOGRAMA COMPLETO", "TSH"],
        payload={"exames_brnet": ["HEMOGRAMA COMPLETO", "TSH"]},
    )

    resultado = _rodar()

    assert resultado["liberado"] is False
    assert resultado["faltantes"] == 1
    payload = banco["updates"][0]["result_payload"]
    assert payload["validation_result"]["exames_faltantes"] == ["TSH"]


def test_auditoria_registra_o_reprocessamento(banco, comparacao_ok):
    """A trilha tem de dizer o que mudou e que o erro original existiu — sem CPF
    nem nome do paciente."""
    _rodar()

    (entrada,) = banco["auditorias"]
    assert entrada.action == "documents.reprocessado"
    assert entrada.resource_id == "doc-1"
    # A etapa entra na trilha: sem ela não se sabe de onde o dado novo veio.
    assert entrada.metadata["etapa"] == script.ETAPA_COMPARACAO
    assert entrada.metadata["erro_original"] == ERRO_COMPARACAO
    assert entrada.metadata["exames_encontrados"] == 2
    assert entrada.metadata["decisao_humana_preservada"] is False
    serializado = json.dumps(entrada.metadata, ensure_ascii=False)
    assert "12345678900" not in serializado
    assert "PACIENTE DE TESTE" not in serializado


def test_documento_inexistente(banco, comparacao_ok):
    banco["documento"] = None
    assert _rodar()["situacao"] == "nao_encontrado"


def test_identificador_mascarado_no_relatorio(banco, comparacao_ok):
    """O relatório vai para o terminal e para arquivo; CPF cru não pode sair."""
    resultado = _rodar()
    assert "12345678900" not in resultado["paciente"]


# ── generalização por etapa e por erro ─────────────────────────────────────

def test_like_reproduz_o_padrao_do_postgres():
    """O mesmo padrão tem de casar no SQL e em Python; se divergirem, `--doc`
    aceitaria documento que a varredura recusa (ou o contrário)."""
    assert script._like("Erro ao comparar exames (fallback):%", ERRO_COMPARACAO)
    assert script._like("formato_de_resposta_invalido", "formato_de_resposta_invalido")
    assert not script._like("formato_de_resposta_invalido", "formato_de_resposta_invalido_x")
    assert not script._like("Paciente não encontrado%", ERRO_COMPARACAO)
    # Parênteses do erro real não podem ser lidos como grupo de regex.
    assert script._like("%(fallback)%", ERRO_COMPARACAO)


def test_erro_de_ocr_nao_e_reprocessavel(banco, comparacao_ok):
    """O PDF não sobrevive (12 arquivos para 4861 documentos no dev), então falha
    de leitura só se resolve com reenvio. O script tem de dizer isso, não tentar."""
    banco["documento"] = _documento(payload={"erro": "Erro no OCR: falha ao ler o PDF"})

    resultado = _rodar()

    assert resultado["situacao"] == "inelegivel"
    assert "reenvio" in resultado["detalhe"]
    assert banco["updates"] == []


def test_identificador_ausente_nao_e_reprocessavel(banco, comparacao_ok):
    """A extração de CPF é regex determinística: reprocessar devolve o mesmo
    resultado, então prometer conserto seria falso."""
    banco["documento"] = _documento(
        payload={"erro": "Não foi possível extrair um CPF válido ou consultar exames"}
    )

    resultado = _rodar(etapa=script.ETAPA_BRNET)

    assert resultado["situacao"] == "inelegivel"
    assert "regex determinística" in resultado["detalhe"]


def test_erro_personalizado_por_padrao(banco, comparacao_ok):
    """`--erro` é o que torna o script útil num erro novo, sem alterar código."""
    banco["documento"] = _documento(payload={"erro": "Timeout na comparação após 60s"})

    assert _rodar()["situacao"] == "inelegivel"
    assert _rodar(padroes=["Timeout%"])["situacao"] == "ok"


def test_sem_markdown_nao_reprocessa(banco, comparacao_ok):
    banco["documento"] = _documento(ocr_markdown=None)

    resultado = _rodar()

    assert resultado["situacao"] == "inelegivel"
    assert "ocr_markdown" in resultado["detalhe"]


def test_comparacao_orienta_a_etapa_brnet_quando_falta_exigencia(banco, comparacao_ok):
    """Mensagem útil em vez de recusa seca: é o caso de quem escolheu a etapa
    errada."""
    banco["documento"] = _documento(exams_brnet=[], payload={"exames_brnet": []})

    resultado = _rodar()

    assert resultado["situacao"] == "inelegivel"
    assert "--etapa brnet" in resultado["detalhe"]


# ── etapa brnet ────────────────────────────────────────────────────────────

@pytest.fixture
def brnet_ok(monkeypatch):
    """Consulta externa que agora encontra o paciente e devolve a exigência."""
    async def falso(cpf=None, passaporte=None, cnpj=None):
        return {
            "exames": ["HEMOGRAMA COMPLETO", "GLICOSE"],
            "nome": "PACIENTE DE TESTE",
            "cpf_processado": "12345678900",
            "source": "prontuai_api",
            "pedido_exame_id": 4321,
            "tipo_identificador_consulta": "cpf",
            "identificador_consulta": "12345678900",
        }

    monkeypatch.setattr(script.brmed_service, "consultar_exames_prontuai", falso)


def _documento_sem_brnet():
    return _documento(
        exams_brnet=[],
        payload={
            "erro": "Paciente não encontrado para o CNPJ, CPF ou Passaporte informados.",
            "exames_brnet": [],
            "tabela_comparacao": [],
        },
    )


def test_brnet_reconsulta_e_conclui(banco, brnet_ok, comparacao_ok):
    """O caso transitório: o paciente foi cadastrado depois do envio."""
    banco["documento"] = _documento_sem_brnet()

    resultado = _rodar(etapa=script.ETAPA_BRNET)

    assert resultado["situacao"] == "ok"
    assert resultado["n_brnet"] == 2
    (campos,) = banco["updates"]
    payload = campos["result_payload"]
    assert payload["exames_brnet"] == ["HEMOGRAMA COMPLETO", "GLICOSE"]
    assert payload["brmed_result"]["pedido_exame_id"] == 4321
    assert payload["erro"] is None
    # As colunas que espelham a exigência acompanham, senão a tela divergiria.
    assert campos["exams_brnet"] == ["HEMOGRAMA COMPLETO", "GLICOSE"]


def test_brnet_falhando_de_novo_nao_grava(banco, comparacao_ok, monkeypatch):
    async def falha(cpf=None, passaporte=None, cnpj=None):
        return {"erro": "Paciente não encontrado para o CNPJ, CPF ou Passaporte informados."}

    monkeypatch.setattr(script.brmed_service, "consultar_exames_prontuai", falha)
    banco["documento"] = _documento_sem_brnet()

    resultado = _rodar(etapa=script.ETAPA_BRNET)

    assert resultado["situacao"] == "falhou_de_novo"
    assert banco["updates"] == []


def test_brnet_sem_exames_nao_grava(banco, comparacao_ok, monkeypatch):
    """Consulta responde sem exigência nenhuma: gravar deixaria o documento
    'liberado' por ausência de regra, pior que o erro atual."""
    async def vazio(cpf=None, passaporte=None, cnpj=None):
        return {"exames": [], "nome": "PACIENTE DE TESTE"}

    monkeypatch.setattr(script.brmed_service, "consultar_exames_prontuai", vazio)
    banco["documento"] = _documento_sem_brnet()

    resultado = _rodar(etapa=script.ETAPA_BRNET)

    assert resultado["situacao"] == "falhou_de_novo"
    assert "sem exames obrigatórios" in resultado["detalhe"]
    assert banco["updates"] == []


def test_brnet_exige_identificador(banco, brnet_ok, comparacao_ok):
    doc = _documento_sem_brnet()
    doc.cpf = None
    doc.result_payload = {**doc.result_payload, "cpf_processado": "Não encontrado"}
    banco["documento"] = doc

    resultado = _rodar(etapa=script.ETAPA_BRNET)

    assert resultado["situacao"] == "inelegivel"
    assert "identificador" in resultado["detalhe"] or "CPF" in resultado["detalhe"]


def test_brnet_preserva_decisao_humana(banco, brnet_ok, comparacao_ok):
    doc = _documento_sem_brnet()
    doc.reviewed_by = "revisor@grupobrmed.com.br"
    banco["documento"] = doc

    resultado = _rodar(etapa=script.ETAPA_BRNET, incluir_revisados=True)

    assert resultado["situacao"] == "ok"
    (campos,) = banco["updates"]
    assert "validation_status" not in campos
    assert "reviewed_by" not in campos


def test_nenhuma_etapa_altera_autoria(banco, brnet_ok, comparacao_ok):
    """Vale para as duas etapas: nada que identifique origem ou envio vai no
    update. Se alguém acrescentar um campo desses, este teste quebra."""
    proibidos = {
        "uploaded_by_user_id", "uploaded_by_user_email", "clinic_id",
        "filename", "uploaded_at", "content_hash", "file_path",
    }

    _rodar()
    banco["documento"] = _documento_sem_brnet()
    _rodar(etapa=script.ETAPA_BRNET)

    assert len(banco["updates"]) == 2
    for campos in banco["updates"]:
        assert proibidos.isdisjoint(campos)


def test_catalogo_de_etapas_e_coerente():
    """Cada etapa declara descrição e padrões, e nenhum padrão da etapa cai na
    lista de erros sem conserto — seria uma promessa que o script não cumpre."""
    for nome, cfg in script.ETAPAS.items():
        assert cfg["descricao"]
        assert cfg["padroes"]
        for padrao in cfg["padroes"]:
            assert script._motivo_sem_conserto(padrao.replace("%", "")) is None, (nome, padrao)
