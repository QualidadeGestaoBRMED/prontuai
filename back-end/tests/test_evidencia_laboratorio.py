"""Selo "só na lista do ASO" para exame de laboratório dado como encontrado.

Os textos imitam o markdown do OCR; nomes e CPFs são fictícios.

Rodar sem o conftest, que importa main.py e exige DATABASE_URL:
  PYTHONPATH=back-end back-end/.venv/bin/python -m pytest \
      back-end/tests/test_evidencia_laboratorio.py -q --noconftest
"""
import asyncio

import pytest

from app.services import evidencia_laboratorio as ev

LISTA_ASO = """# ATESTADO DE SAÚDE OCUPACIONAL
Paciente: FULANO DE TAL FICTICIO
## Procedimentos realizados
## URÉIA 15/10/2026
## CLÍNICO OCUPACIONAL 15/10/2026
"""

# A janela de resultado atravessa linhas: o laudo precisa estar a mais de 250
# caracteres da lista para a ocorrência da lista não herdar o resultado.
SEPARACAO = "Texto corrido do atestado, sem exame nenhum.\n" * 8

LAUDO_UREIA = SEPARACAO + """
## LAUDO LABORATORIAL
UREIA
Material: soro   Método: enzimático
32 mg/dL    Valores de referência: 15 a 45 mg/dL
"""


def test_ureia_so_na_lista_do_aso():
    evidencia, linha = ev.avaliar(LISTA_ASO, "URÉIA")
    assert evidencia == ev.SO_LISTA
    assert linha == "## URÉIA 15/10/2026"


def test_ureia_com_laudo_tem_resultado():
    evidencia, linha = ev.avaliar(LISTA_ASO + LAUDO_UREIA, "URÉIA")
    assert evidencia == ev.COM_RESULTADO
    # A linha de origem é a da ocorrência que tem resultado, não a da lista.
    assert linha == "UREIA"


def test_data_nao_conta_como_valor():
    # "15/10" seguido de "MIL" ou de número solto não pode virar resultado.
    md = "## URÉIA 15/10/2026 15/10 mil\n## CREATININA 01/09\n"
    assert ev.avaliar(md, "URÉIA")[0] == ev.SO_LISTA
    assert ev.avaliar(md, "CREATININA")[0] == ev.SO_LISTA


def test_glicemia_achada_como_glicose():
    md = "## GLICEMIA DE JEJUM 15/10/2026\n\nGLICOSE\nRESULTADO 93 MG/DL\n"
    assert ev.avaliar(md, "GLICEMIA DE JEJUM")[0] == ev.COM_RESULTADO


def test_hemograma_pela_hemoglobina():
    md = "## HEMOGRAMA COMPLETO 15/10/2026\n" + SEPARACAO + "HEMOGRAMA COMPLETO\nHemoglobina 14,2 g/dL\n"
    assert ev.avaliar(md, "HEMOGRAMA COMPLETO")[0] == ev.COM_RESULTADO


def test_hemograma_so_na_lista():
    assert ev.avaliar("## HEMOGRAMA COMPLETO 15/10/2026\n", "HEMOGRAMA COMPLETO")[0] == ev.SO_LISTA


# Os três abaixo eram selo à toa em documentos aprovados (conferido no texto em
# 26/10/2026): o laboratório imprime outro nome, ou o resultado vem em "%".
def test_ggt_pelo_nome_do_laboratorio():
    md = "## GGT (GAMA-GT) 16/10/2026\n" + SEPARACAO + "GAMA GLUTAMIL TRANSFERASE\nRESULTADO 31,0 U/L\n"
    assert ev.avaliar(md, "GGT (GAMA-GT)")[0] == ev.COM_RESULTADO


def test_triglicerides_com_a_grafia_do_laudo():
    md = "## TRIGLICERÍDEOS 14/10/2026\n" + SEPARACAO + "TRIGLICERIDES\n56 mg/dL\n"
    assert ev.avaliar(md, "TRIGLICERÍDEOS")[0] == ev.COM_RESULTADO


def test_hemoglobina_glicada_em_percentual():
    md = "## HEMOGLOBINA GLICADA 15/10/2026\n" + SEPARACAO + "HbA1c 5,6%\n"
    assert ev.avaliar(md, "HEMOGLOBINA GLICADA")[0] == ev.COM_RESULTADO
    assert ev.avaliar("## HEMOGLOBINA GLICADA 15/10/2026\n", "HEMOGLOBINA GLICADA")[0] == ev.SO_LISTA


def test_exame_que_nao_aparece_nao_e_avaliado():
    assert ev.avaliar(LISTA_ASO, "TSH") == (None, None)


def test_parte_entre_parenteses_e_sinonimo_do_catalogo():
    md = "TGO\n25 U/L\n"
    assert ev.avaliar(md, "TRANSAMINASE OXALACÉTICA (TGO)")[0] == ev.COM_RESULTADO
    termos = ev.termos_do_exame("ÁCIDO ÚRICO", ["URICEMIA"])
    assert ev.avaliar("URICEMIA 4,1 mg/dL\n", "ÁCIDO ÚRICO", termos)[0] == ev.COM_RESULTADO


def test_quem_e_laboratorio():
    assert ev.eh_laboratorio("URÉIA")
    assert ev.eh_laboratorio("GAMA GT")
    assert ev.eh_laboratorio("HEMOGRAMA COMPLETO")
    assert not ev.eh_laboratorio("AUDIOMETRIA TONAL")
    assert not ev.eh_laboratorio("ELETROCARDIOGRAMA")
    assert not ev.eh_laboratorio("CLÍNICO OCUPACIONAL")


@pytest.mark.parametrize("cpf", ["123.456.789-09", "12345678909"])
def test_cpf_mascarado_na_linha_de_origem(cpf):
    md = f"Paciente FULANO FICTICIO CPF {cpf} UREIA 15/10/2026\n"
    evidencia, linha = ev.avaliar(md, "URÉIA")
    assert evidencia == ev.SO_LISTA
    assert cpf not in linha and "***.***.***-**" in linha


def test_linha_de_origem_truncada():
    md = "UREIA " + "X" * 400 + "\n"
    assert len(ev.avaliar(md, "URÉIA")[1]) == ev.LIMITE_LINHA_ORIGEM


def test_anotar_comparativo():
    comparativo = [
        {"exame": "URÉIA", "status": "encontrado"},
        {"exame": "CREATININA", "status": "encontrado"},
        {"exame": "CLÍNICO OCUPACIONAL", "status": "encontrado"},
        {"exame": "AUDIOMETRIA", "status": "encontrado"},
        {"exame": "TSH", "status": "faltante"},
    ]
    md = LISTA_ASO + SEPARACAO + "CREATININA 0,9 mg/dL\n"
    so_lista = ev.anotar_comparativo(comparativo, md)
    assert so_lista == ["URÉIA"]
    ureia, creatinina, clinico, audiometria, tsh = comparativo
    assert ureia["evidencia"] == "so_lista" and ureia["linha_origem"] == "## URÉIA 15/10/2026"
    assert creatinina["evidencia"] == "com_resultado"
    # Não laboratório: só a linha de origem, sem evidência.
    assert clinico["linha_origem"] == "## CLÍNICO OCUPACIONAL 15/10/2026" and "evidencia" not in clinico
    assert "linha_origem" not in audiometria and "evidencia" not in audiometria
    assert tsh == {"exame": "TSH", "status": "faltante"}
    assert [i["status"] for i in comparativo] == ["encontrado"] * 4 + ["faltante"]


def test_so_lista_troca_a_justificativa_e_guarda_a_da_comparacao():
    frase = "'URÉIA' foi encontrado na lista de exames recebidos."
    comparativo = [{"exame": "URÉIA", "status": "encontrado", "justificativa": frase}]
    ev.anotar_comparativo(comparativo, LISTA_ASO)
    ureia = comparativo[0]
    assert ureia["justificativa"] == ev.JUSTIFICATIVA_SO_LISTA
    assert ureia["justificativa_comparacao"] == frase
    # Anotar de novo não perde a frase original.
    ev.anotar_comparativo(comparativo, LISTA_ASO)
    assert ureia["justificativa_comparacao"] == frase


def test_com_resultado_mantem_a_justificativa():
    frase = "'CREATININA' foi encontrado na lista de exames recebidos."
    comparativo = [{"exame": "CREATININA", "status": "encontrado", "justificativa": frase}]
    ev.anotar_comparativo(comparativo, SEPARACAO + "CREATININA 0,9 mg/dL\n")
    assert comparativo[0]["justificativa"] == frase
    assert "justificativa_comparacao" not in comparativo[0]


# ---------------------------------------------------------------------------
# Integração no workflow: grava o selo, limita a confiança, não muda status.
# ---------------------------------------------------------------------------


def test_workflow_grava_selo_sem_mudar_status(monkeypatch):
    from app.services import workflow_service as ws

    markdown = LISTA_ASO
    brnet = ["URÉIA", "CLÍNICO OCUPACIONAL"]

    async def ocr_falso(arquivo, progress_hook=None):
        return {"cpf": "52998224725", "exames": brnet, "markdown_content": markdown, "patient_name": None}

    async def brmed_falso(cpf=None, passaporte=None, cnpj=None):
        return {"cpf_processado": cpf, "exames": brnet, "nome": "FULANO FICTICIO", "source": "teste"}

    async def validar_falso(cpf, exames_obrigatorios, exames_enviados, exames_brnet, run_id=None):
        return {
            "status_liberado": True,
            "mensagem": "Todos os exames obrigatórios foram enviados. Liberação concedida.",
            "exames_faltantes": [],
            "exames_presentes": list(brnet),
            "exames_comparativo": [{"exame": e, "status": "encontrado"} for e in brnet],
        }

    monkeypatch.setattr(ws.ocr_service, "ocr_pipeline", ocr_falso)
    monkeypatch.setattr(ws.brmed_service, "consultar_exames_prontuai", brmed_falso)
    monkeypatch.setattr(ws.validacao_service, "validar_exames", validar_falso)
    monkeypatch.setattr(ws, "_filtrar_exames_ocr", lambda enviados, brnet_, md: enviados)
    monkeypatch.setattr(ws.exam_catalog_source, "sinonimos_de", lambda chave: set())
    monkeypatch.setattr(ws.settings, "LAUDO_RECUPERAR_POR_CONTEUDO", False)
    monkeypatch.setattr(ws.settings, "LAUDO_EXIGIR_EVIDENCIA", False)
    monkeypatch.setattr(ws.evidencia_laboratorio, "HABILITADA", True)

    class Arquivo:
        filename = "ficticio.pdf"
        content_type = "application/pdf"

    resultado = asyncio.run(ws._processar_documento_completo_impl(Arquivo(), []))

    tabela = resultado["tabela_comparacao"]
    assert [i["status"] for i in tabela] == ["encontrado", "encontrado"]
    assert tabela[0]["evidencia"] == "so_lista"
    assert tabela[0]["linha_origem"] == "## URÉIA 15/10/2026"
    assert "evidencia" not in tabela[1] and tabela[1]["linha_origem"]
    detalhes = resultado["confidence_details"]
    assert detalhes["exames_so_lista"] == ["URÉIA"]
    assert detalhes["score"] <= ws.TETO_CONFIANCA_SO_LISTA
    assert resultado["status"] == "success"
    assert resultado["validation_result"]["exames_faltantes"] == []
    assert resultado["decisao_final"].startswith("Todos os exames")
