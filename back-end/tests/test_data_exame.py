"""Aviso de exame de laboratório coletado muito antes do ASO.

Os textos imitam o markdown do OCR; nomes são fictícios.

Medido por replay nos 6.441 documentos com tabela de exames enviados de 14/09 a
03/11/2026 (cópia de produção de 03/11), com limite de 180 dias: avisa em 5
documentos, todos com diferença de 317 a 371 dias para o ASO, 4 deles da mesma
clínica. Com 90 dias entram mais 2. Nenhum caso entre 103 e 316 dias.

Rodar sem o conftest, que importa main.py e exige DATABASE_URL:
  PYTHONPATH=back-end back-end/.venv/bin/python -m pytest \
      back-end/tests/test_data_exame.py -q --noconftest
"""
from datetime import date

from app.services import data_exame as de
from app.services import evidencia_laboratorio as ev

HOJE = date(2026, 10, 28)

ASO = """<!-- pagina 1 -->
# ATESTADO DE SAÚDE OCUPACIONAL
Paciente: FULANO DE TAL FICTICIO
Data de nascimento: 05/05/1976
## Procedimentos realizados
## CREATININA 12/11/2025
## HEMOGRAMA 12/11/2025
Goiânia, 21/10/2026
"""


def laudo(pagina: int, exame: str, coleta: str, unidade: str = "mg/dL") -> str:
    return f"""<!-- pagina {pagina} -->
Paciente: FULANO DE TAL FICTICIO  Nascimento: 05/05/1976
Atendimento: {coleta}  Data da coleta: {coleta}
{exame} 0,9 {unidade}
Valores de referência
"""


def anotado(markdown: str, *exames: str, limite: int = 180) -> list[dict]:
    itens = [{"exame": e, "status": "encontrado"} for e in exames]
    ev.anotar_comparativo(itens, markdown)
    de.anotar_comparativo(itens, markdown, hoje=HOJE, limite_dias=limite)
    return itens


def test_coleta_do_ano_anterior_ganha_aviso_com_a_diferenca_para_o_aso():
    item = anotado(ASO + laudo(2, "CREATININA", "12/11/2025"), "CREATININA")[0]
    assert item["data_antiga"] == {
        "data_exame": "12/11/2025",
        "data_referencia": "21/10/2026",
        "referencia": "aso",
        "dias": 343,
    }


def test_coleta_recente_nao_avisa():
    assert "data_antiga" not in anotado(ASO + laudo(2, "CREATININA", "20/10/2026"), "CREATININA")[0]


def test_o_limite_vale_a_partir_do_dia_exato():
    # 21/10/2026 menos 180 dias = 24/04/2026
    md = ASO + laudo(2, "CREATININA", "24/04/2026")
    assert anotado(md, "CREATININA")[0]["data_antiga"]["dias"] == 180
    assert "data_antiga" not in anotado(md, "CREATININA", limite=181)[0]


def test_com_laudo_novo_e_antigo_do_mesmo_exame_vale_o_novo():
    md = ASO + laudo(2, "CREATININA", "12/11/2025") + laudo(3, "CREATININA", "20/10/2026")
    assert "data_antiga" not in anotado(md, "CREATININA")[0]


def test_cada_exame_e_julgado_pela_coleta_do_proprio_laudo():
    md = ASO + laudo(2, "CREATININA", "12/11/2025") + laudo(3, "UREIA", "20/10/2026")
    creatinina, ureia = anotado(md, "CREATININA", "UREIA")
    assert creatinina["data_antiga"]["dias"] == 343
    assert "data_antiga" not in ureia


def test_exame_so_na_lista_nao_avisa_mesmo_com_data_antiga_no_aso():
    assert "data_antiga" not in anotado(ASO, "CREATININA")[0]


def test_nascimento_depois_do_rotulo_nao_vira_coleta():
    texto = "Coleta  Data de nascimento: 05/05/1976\nDATA DA COLETA 20/10/2026"
    assert de.coletas(texto, HOJE) == [date(2026, 10, 20)]


def test_data_de_coleta_futura_ou_velha_demais_e_ignorada():
    assert de.coletas("Coleta: 21/10/2028", HOJE) == []
    assert de.coletas("Coleta: 12/11/2015", HOJE) == []


def test_historico_de_resultados_sem_rotulo_de_coleta_nao_conta():
    md = ASO + laudo(2, "CREATININA", "20/10/2026") + "Histórico: 12/11/2023 1,0  01/02/2021 0,8\n"
    assert "data_antiga" not in anotado(md, "CREATININA")[0]


def test_data_do_aso_e_a_mais_recente_sem_nascimento():
    assert de.data_do_aso(ASO, HOJE) == date(2026, 10, 21)


def test_sem_aso_a_referencia_e_o_dia_do_processamento():
    item = anotado(laudo(1, "CREATININA", "12/11/2025"), "CREATININA")[0]
    assert item["data_antiga"]["referencia"] == "processamento"
    assert item["data_antiga"]["dias"] == 350


def test_aviso_nao_muda_o_status_do_exame():
    item = anotado(ASO + laudo(2, "CREATININA", "12/11/2025"), "CREATININA")[0]
    assert item["status"] == "encontrado"
    assert item["evidencia"] == "com_resultado"


def test_faltante_e_extra_nao_ganham_aviso():
    md = ASO + laudo(2, "CREATININA", "12/11/2025")
    itens = [{"exame": "CREATININA", "status": "faltante", "evidencia": "com_resultado"}]
    assert de.anotar_comparativo(itens, md, hoje=HOJE) == []
    assert "data_antiga" not in itens[0]


def test_sinonimo_do_catalogo_acha_o_laudo():
    md = ASO + laudo(2, "CREATININA SERICA", "12/11/2025")
    itens = [{"exame": "FUNCAO RENAL", "status": "encontrado", "evidencia": "com_resultado"}]
    de.anotar_comparativo(itens, md, lambda _c: {"CREATININA SERICA"}, hoje=HOJE)
    assert itens[0]["data_antiga"]["dias"] == 343


def test_workflow_rejeita_coleta_antiga_sem_mudar_faltantes_nem_confianca(monkeypatch):
    import asyncio
    from datetime import timedelta

    from app.services import workflow_service as ws

    hoje = date.today()
    fmt = lambda d: d.strftime("%d/%m/%Y")  # noqa: E731
    aso = f"""<!-- pagina 1 -->
# ATESTADO DE SAÚDE OCUPACIONAL
Local e data: {fmt(hoje)}
"""
    brnet = ["CREATININA"]

    def processar(coleta: date, rejeita: bool = True) -> dict:
        markdown = aso + laudo(2, "CREATININA", fmt(coleta))

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
        monkeypatch.setattr(ws.monitoramento_checagem, "HABILITADO", False)
        monkeypatch.setattr(ws.evidencia_laboratorio, "HABILITADA", True)
        monkeypatch.setattr(ws.data_exame, "HABILITADA", True)
        monkeypatch.setattr(ws.data_exame, "REJEITA", rejeita)

        class Arquivo:
            filename = "ficticio.pdf"
            content_type = "application/pdf"

        return asyncio.run(ws._processar_documento_completo_impl(Arquivo(), []))

    antigo = processar(hoje - timedelta(days=300))
    recente = processar(hoje - timedelta(days=3))
    so_aviso = processar(hoje - timedelta(days=300), rejeita=False)

    item = antigo["tabela_comparacao"][0]
    assert item["status"] == "encontrado"
    assert item["data_antiga"]["dias"] == 300
    assert item["data_antiga"]["referencia"] == "aso"
    assert antigo["confidence_details"]["exames_data_antiga"] == ["CREATININA"]
    assert antigo["validation_result"]["exames_faltantes"] == []
    # Rejeitado pela IA: vai à Checagem, sem exame faltante, com o motivo na análise.
    assert antigo["validation_result"]["data_antiga"] is True
    assert ws.decisao_da_ia(antigo) == "pending"
    assert "CREATININA (300 dias)" in antigo["validation_result"]["analysis"]
    assert antigo["status"] == recente["status"] == "success"
    assert antigo["confidence_details"]["score"] == recente["confidence_details"]["score"]
    assert ws.decisao_da_ia(recente) == "validated"
    assert recente["validation_result"]["data_antiga"] is False

    # DATA_EXAME_REJEITA=false volta a só avisar.
    assert so_aviso["tabela_comparacao"][0]["data_antiga"]["dias"] == 300
    assert so_aviso["validation_result"]["data_antiga"] is False
    assert ws.decisao_da_ia(so_aviso) == "validated"
    assert so_aviso["decisao_final"] == recente["decisao_final"]

    assert "data_antiga" not in recente["tabela_comparacao"][0]
    assert "exames_data_antiga" not in recente["confidence_details"]


# ---------------------------------------------------------------------------
# Rejeição pela IA (STC-991): coleta 180 dias ou mais antes do ASO.
# ---------------------------------------------------------------------------

def test_motivo_da_rejeicao_traz_exame_e_dias_sem_data_do_paciente():
    itens = anotado(ASO + laudo(2, "CREATININA", "12/11/2025"), "CREATININA")
    assert de.motivo_rejeicao(itens) == "Exame coletado 180 dias ou mais antes do ASO: CREATININA (343 dias)."


def test_motivo_sem_data_do_aso_usa_a_analise():
    itens = [{"exame": "CREATININA", "data_antiga": {"dias": 200, "referencia": de.REFERENCIA_PROCESSAMENTO}}]
    assert de.motivo_rejeicao(itens).endswith("antes da análise do documento: CREATININA (200 dias).")


def test_sem_exame_antigo_nao_ha_motivo():
    itens = anotado(ASO.replace("12/11/2025", "15/10/2026") + laudo(2, "CREATININA", "15/10/2026"), "CREATININA")
    assert de.motivo_rejeicao(itens) == ""


def test_rejeicao_entra_na_mensagem_e_tira_a_liberacao():
    from app.services import workflow_service as ws

    validacao = {"status_liberado": True, "mensagem": "Todos os exames obrigatórios encontrados."}
    ws._rejeitar_com_motivo(validacao, "Exame coletado 180 dias ou mais antes do ASO: CREATININA (343 dias).")
    assert validacao == {"status_liberado": False, "mensagem": "Exame coletado 180 dias ou mais antes do ASO: CREATININA (343 dias)."}
    # Com faltante, o motivo vem depois da frase que já existia.
    validacao = {"status_liberado": False, "mensagem": "Falta: AUDIOMETRIA."}
    ws._rejeitar_com_motivo(validacao, "Exame coletado 180 dias ou mais antes do ASO: CREATININA (343 dias).")
    assert validacao["mensagem"] == "Falta: AUDIOMETRIA. Exame coletado 180 dias ou mais antes do ASO: CREATININA (343 dias)."
