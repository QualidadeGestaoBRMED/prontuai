"""Ajuste do veredito por exame a partir do conteúdo do laudo.

Os textos imitam o markdown normalizado (maiúsculas, sem acento, sem pontuação)
dos formatos medidos nas semanas de 14/09 a 05/10/2026.
"""
import re
import unicodedata

import pytest

from app.services import laudo_evidencia as le


def norm(texto: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c)).upper()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]+", " ", t)).strip()


def md(texto: str) -> str:
    return f" {norm(texto)} "


def ajusta(itens, texto, **kw):
    comparativo = [{"exame": e, "status": s, "justificativa": ""} for e, s in itens]
    mudancas = le.ajustar_comparativo(comparativo, md(texto), norm, **kw)
    return {i["exame"]: i["status"] for i in comparativo}, mudancas


# --- 1. recuperar pelo conteúdo -------------------------------------------------

def test_lipidograma_em_laudos_separados_por_componente():
    texto = ("Colesterol Total 182 mg/dL Valor de referência < 190 "
             "HDL - Colesterol 48 mg/dL LDL - Colesterol 110 mg/dL "
             "Triglicérides 120 mg/dL")
    status, mud = ajusta([("LIPIDOGRAMA (PERFIL LIPÍDICO)", "faltante")], texto)
    assert status["LIPIDOGRAMA (PERFIL LIPÍDICO)"] == "encontrado"
    assert mud[0]["regra"] == "conteudo_do_laudo"


def test_lipidograma_com_dois_componentes_continua_faltante():
    texto = "Colesterol Total 182 mg/dL HDL - Colesterol 48 mg/dL"
    status, _ = ajusta([("LIPIDOGRAMA (PERFIL LIPÍDICO)", "faltante")], texto)
    assert status["LIPIDOGRAMA (PERFIL LIPÍDICO)"] == "faltante"


def test_triagem_toxicologica_com_um_laudo_por_droga():
    texto = ("Barbitúricos Negativo Benzodiazepínicos Negativo Cocaína Benzoilecgonina Negativo "
             "Canabinóides Negativo Anfetaminas Negativo Opiáceos Negativo")
    status, _ = ajusta([("TRIAGEM TOXICOLÓGICO", "faltante")], texto)
    assert status["TRIAGEM TOXICOLÓGICO"] == "encontrado"


def test_toxicologico_capilar_nao_e_recuperado_por_laudo_de_urina():
    texto = "Cocaína Negativo Canabinóides Negativo Anfetaminas Negativo Opiáceos Negativo"
    status, _ = ajusta([("TOXICOLÓGICO CAPILAR", "faltante")], texto)
    assert status["TOXICOLÓGICO CAPILAR"] == "faltante"


def test_glicemia_de_jejum_como_dosagem_de_glicose():
    status, _ = ajusta([("GLICEMIA DE JEJUM", "faltante")], "RESULTADO DOSAGEM DE GLICOSE 93 mg/dL")
    assert status["GLICEMIA DE JEJUM"] == "encontrado"


def test_glicose_so_na_urina_sem_mg_dl_nao_recupera_glicemia():
    status, _ = ajusta([("GLICEMIA DE JEJUM", "faltante")], "Urina tipo I Glicose ausente Proteína ausente")
    assert status["GLICEMIA DE JEJUM"] == "faltante"


def test_etanol_e_separado_pelo_material():
    texto = "Etanol (Material: Soro, Método: Enzimático) Resultado inferior a 10 mg/dL"
    status, _ = ajusta([("DOSAGEM DE ÁLCOOL ETÍLICO (SANGUE)", "faltante"), ("ETANOL URINÁRIO", "faltante")], texto)
    assert status["DOSAGEM DE ÁLCOOL ETÍLICO (SANGUE)"] == "encontrado"
    assert status["ETANOL URINÁRIO"] == "faltante"


def test_rx_reconhecido_pela_conclusao_do_laudo():
    texto = ("Laudo Médico – RAIO-X  RAIO X COLUNA LOMBAR AP E PERFIL Conclusões: "
             "corpos vertebrais alinhados, espaços intervertebrais conservados")
    status, _ = ajusta([("RADIOGRAFIA DE COLUNA LOMBO SACRA AP/PERFIL", "faltante")], texto)
    assert status["RADIOGRAFIA DE COLUNA LOMBO SACRA AP/PERFIL"] == "encontrado"


FICHA_ACUIDADE = ("ACUIDADE VISUAL Método de avaliação: Escala optométrica de Snellen "
                  "Com correção ( ) Sem correção (X) Olho direito {od} Olho esquerdo {oe} "
                  "Teste de Ishihara: normal")


def test_acuidade_reconhecida_pelos_valores_de_snellen():
    texto = FICHA_ACUIDADE.format(od="20/25", oe="20/25")
    status, mud = ajusta([("ACUIDADE VISUAL", "faltante")], texto)
    assert status["ACUIDADE VISUAL"] == "encontrado"
    assert mud[0]["regra"] == "conteudo_do_laudo"


def test_ficha_de_acuidade_em_branco_continua_faltante():
    # "Snellen" vem impresso no formulário; sem a fração anotada não é laudo.
    texto = FICHA_ACUIDADE.format(od="", oe="")
    status, _ = ajusta([("ACUIDADE VISUAL", "faltante")], texto)
    assert status["ACUIDADE VISUAL"] == "faltante"


def test_acuidade_com_um_olho_so_continua_faltante():
    texto = FICHA_ACUIDADE.format(od="20/25", oe="")
    status, _ = ajusta([("ACUIDADE VISUAL", "faltante")], texto)
    assert status["ACUIDADE VISUAL"] == "faltante"


def test_senso_cromatico_exige_o_teste_de_cores():
    texto = FICHA_ACUIDADE.format(od="20/20", oe="20/20").replace("Teste de Ishihara: normal", "")
    status, _ = ajusta([("ACUIDADE VISUAL COM SENSO CROMÁTICO", "faltante")], texto)
    assert status["ACUIDADE VISUAL COM SENSO CROMÁTICO"] == "faltante"


def test_recuperar_desligado_nao_mexe():
    status, mud = ajusta([("GLICEMIA DE JEJUM", "faltante")], "DOSAGEM DE GLICOSE 93 mg/dL", recuperar=False)
    assert status["GLICEMIA DE JEJUM"] == "faltante" and not mud


# --- 2. exigir laudo -------------------------------------------------------------

ASO_SO_LISTANDO = ("ATESTADO DE SAÚDE OCUPACIONAL Exames complementares: Audiometria Tonal 21/09/2026 "
                   "Radiografia de Tórax Padrão OIT 21/09/2026 Anti-HBs 21/09/2026 Apto")


def test_exame_so_listado_no_aso_vira_faltante():
    itens = [("AUDIOMETRIA TONAL", "encontrado"), ("RADIOGRAFIA DE TÓRAX - PADRÃO OIT", "encontrado"),
             ("ANTI-HBS", "encontrado")]
    status, mud = ajusta(itens, ASO_SO_LISTANDO)
    assert set(status.values()) == {"faltante"}
    assert {m["tipo"] for m in mud} == {"AUDIOMETRIA", "RX_OIT", "SOROLOGIA"}


def test_exame_com_laudo_continua_encontrado():
    texto = ASO_SO_LISTANDO + (" AUDIOMETRIA TONAL Orelha Direita Orelha Esquerda 0,25 0,5 1 2 kHz "
                               "Folha de leitura radiológica Classificação internacional de pneumoconioses "
                               "Anti-HBs Resultado: Não Reagente")
    itens = [("AUDIOMETRIA TONAL", "encontrado"), ("RADIOGRAFIA DE TÓRAX - PADRÃO OIT", "encontrado"),
             ("ANTI-HBS", "encontrado")]
    status, mud = ajusta(itens, texto)
    assert set(status.values()) == {"encontrado"} and not mud


def test_tipos_fora_da_regra_nao_sao_exigidos():
    # Transaminases, hemograma, espirometria e RX comum barravam mais documentos
    # certos do que pegavam: ficam fora da exigência.
    itens = [("TGO (AST)", "encontrado"), ("HEMOGRAMA COMPLETO COM PLAQUETAS", "encontrado"),
             ("ESPIROMETRIA", "encontrado"), ("RADIOGRAFIA DE COLUNA LOMBO SACRA AP/PERFIL", "encontrado")]
    status, mud = ajusta(itens, "ATESTADO DE SAÚDE OCUPACIONAL lista de exames sem laudo")
    assert set(status.values()) == {"encontrado"} and not mud


def test_clinico_sem_ficha_vira_faltante():
    status, mud = ajusta([("CLÍNICO OCUPACIONAL", "encontrado")], ASO_SO_LISTANDO + " CLÍNICO OCUPACIONAL")
    assert status["CLÍNICO OCUPACIONAL"] == "faltante"
    assert mud[0]["tipo"] == "CLINICO"


@pytest.mark.parametrize("laudo", [
    "FICHA MÉDICA OCUPACIONAL",
    "Ficha clínica do colaborador",
    "PRONTUÁRIO MÉDICO",
    "Anamnese: sem queixas. Exame físico: sem alterações",
    "Pressão arterial 120x80 ... ANAMNESE ocupacional",
])
def test_clinico_com_ficha_ou_anamnese_com_exame_fisico_continua(laudo):
    status, mud = ajusta([("CLÍNICO OCUPACIONAL", "encontrado")], f"{ASO_SO_LISTANDO} {laudo}")
    assert status["CLÍNICO OCUPACIONAL"] == "encontrado" and not mud


def test_anamnese_sozinha_nao_prova_o_clinico():
    # "Anamnese" também está na audiometria e no psicossocial.
    status, _ = ajusta([("CLÍNICO OCUPACIONAL", "encontrado")], f"{ASO_SO_LISTANDO} Anamnese ocupacional")
    assert status["CLÍNICO OCUPACIONAL"] == "faltante"


def test_glicemia_exige_o_nome_e_mg_dl_no_documento():
    item = [("GLICEMIA DE JEJUM", "encontrado")]
    assert ajusta(item, "Procedimentos realizados GLICEMIA DE JEJUM 12/10/2026")[0]["GLICEMIA DE JEJUM"] == "faltante"
    assert ajusta(item, "GLICOSE 93 mg/dL")[0]["GLICEMIA DE JEJUM"] == "encontrado"
    # As duas palavras não precisam estar juntas: o OCR separa a tabela do laudo.
    assert ajusta(item, "GLICEMIA DE JEJUM Método enzimático ... Creatinina 0,9 mg/dL")[0]["GLICEMIA DE JEJUM"] == "encontrado"


def test_ergometrico_so_na_lista_vira_faltante_e_com_laudo_continua():
    lista = "EXAMES COMPLEMENTARES TESTE ERGOMÉTRICO 12/10/2026 CONCLUSÃO CONCLUSION apto"
    item = [("TESTE ERGOMÉTRICO", "encontrado")]
    status, mud = ajusta(item, lista)
    assert status["TESTE ERGOMÉTRICO"] == "faltante" and mud[0]["tipo"] == "ERGOMETRICO"
    assert ajusta(item, f"{lista} LAUDO DE TESTE ERGOMÉTRICO protocolo de Bruce")[0]["TESTE ERGOMÉTRICO"] == "encontrado"


# Formatos das divergências de novembro/2026 conferidas no PDF: o exame só aparece
# na lista "Procedimentos realizados" do ASO ou no voucher BR MED.
LISTA_ASO = ("ATESTADO DE SAÚDE OCUPACIONAL Procedimentos realizados / Exames complementares: "
             "AVALIAÇÃO PSICOLÓGICA 05/11/2026 AVALIAÇÃO ODONTOLÓGICA 05/11/2026 "
             "ELETROENCEFALOGRAMA 05/11/2026 Conclusão / Conclusion: Paciente é considerado apto")
VOUCHER = ("04 Exames AVALIAÇÃO PSICOLÓGICA AVALIAÇÃO ODONTOLÓGICA ELETROENCEFALOGRAMA "
           "Todos os exames listados são obrigatórios")
TRES = [("AVALIAÇÃO PSICOLÓGICA", "encontrado"), ("AVALIAÇÃO ODONTOLÓGICA", "encontrado"),
        ("ELETROENCEFALOGRAMA", "encontrado")]


@pytest.mark.parametrize("lista", [LISTA_ASO, VOUCHER])
def test_psicologica_odontologica_e_eeg_so_listados_viram_faltantes(lista):
    status, mud = ajusta(TRES, lista)
    assert set(status.values()) == {"faltante"}
    assert {m["tipo"] for m in mud} == {"PSICOLOGICA", "ODONTOLOGICA", "EEG"}


@pytest.mark.parametrize("exame,laudo", [
    ("AVALIAÇÃO PSICOLÓGICA", "PARECER PSICOLÓGICO Conclusão: apto. Psicóloga CRP 06/12345"),
    # Laudo que só traz a bateria de testes, sem a palavra "psicológica".
    ("AVALIAÇÃO PSICOLÓGICA", "Instrumentos utilizados: Palográfico, Beta III, CTA AC e entrevista"),
    ("AVALIAÇÃO PSICOLÓGICA", "Teste de atenção concentrada: médio superior"),
    ("AVALIAÇÃO ODONTOLÓGICA", "Odontograma sem alterações. Cirurgião-dentista CRO 1234"),
    # Protegy: o título é o único sinal no texto.
    ("AVALIAÇÃO ODONTOLÓGICA", "## ATESTADO DE SAÚDE BUCAL Assoalho bucal sem alterações"),
    ("ELETROENCEFALOGRAMA", "Laudo de eletroencefalograma: atividade de base organizada"),
    ("ELETROENCEFALOGRAMA", "Fotoestimulação intermitente e hiperpneia sem alterações"),
])
def test_psicologica_odontologica_e_eeg_com_laudo_continuam(exame, laudo):
    status, mud = ajusta([(exame, "encontrado")], f"{LISTA_ASO} {laudo}")
    assert status[exame] == "encontrado" and not mud


def test_psicossocial_nao_e_exigido_como_psicologica():
    # A anamnese psicossocial de altura não tem marca estável: fica sem exigência.
    assert le.tipo_do_exame(norm("PSICOSSOCIAL")) is None
    status, mud = ajusta([("PSICOSSOCIAL", "encontrado")], "Procedimentos realizados PSICOSSOCIAL 26/10/2026")
    assert status["PSICOSSOCIAL"] == "encontrado" and not mud


def test_eeg_e_classificado_antes_do_ecg():
    assert le.tipo_do_exame(norm("ELETROENCEFALOGRAMA")) == "EEG"
    assert le.tipo_do_exame(norm("ELETROCARDIOGRAMA")) == "ECG"


# Listas que o `sem_listas` passou a reconhecer em 10/11/2026 (casos 21, 51 e 55
# das divergências de novembro): sem elas, o nome na lista contava como laudo.
@pytest.mark.parametrize("lista", [
    # e-mail de agendamento "Exames agendados", até a quebra de página
    "TEM O AGENDAMENTO DE UM PERIODICO EXAMES AGENDADOS ACUIDADE VISUAL AVALIAÇÃO ODONTOLÓGICA "
    "AVALIAÇÃO PSICOLÓGICA ELETROENCEFALOGRAMA PAGINA 17 LEITURA PAGINA 17 CONFIANCA 96",
    # certificado médico marítimo, até "This is to certify"
    "ADDITIONAL EXAMS EXAMES COMPLEMENTARES AVALIAÇÃO ODONTOLÓGICA DENTAL ASSESSMENT "
    "AVALIAÇÃO PSICOLÓGICA PSYCHOLOGICAL ASSESSMENT ELETROENCEFALOGRAMA "
    "THIS IS TO CERTIFY THAT THE SEAFARER IS FIT FOR SERVICE",
    # tela de atendimento do portal impressa no PDF, até a ficha médica
    "OLÁ EXCELLENCE VOCÊ ESTÁ LOGADO EM RIO DE JANEIRO ATENDIMENTO ADMISSIONAL EXAMES ACUIDADE VISUAL "
    "AVALIAÇÃO PSICOLÓGICA AVALIAÇÃO ODONTOLÓGICA ELETROENCEFALOGRAMA FICHA MÉDICA ANAMNESE",
])
def test_listas_de_agendamento_certificado_e_tela_nao_contam_como_laudo(lista):
    status, mud = ajusta(TRES, lista)
    assert set(status.values()) == {"faltante"}
    assert {m["tipo"] for m in mud} == {"PSICOLOGICA", "ODONTOLOGICA", "EEG"}


def test_tela_de_atendimento_nao_apaga_a_ficha_medica():
    # O bloco termina antes da ficha: o título dela continua no texto.
    tela = "VOCÊ ESTÁ LOGADO EM CENTRO EXAMES CLINICO OCUPACIONAL FICHA MÉDICA ANAMNESE"
    assert "FICHA MEDICA" in le.sem_listas(md(tela))


def test_ggt_julgado_pelo_resultado_perto_do_nome():
    # A normalização do motor reescreve "GAMA-GT" e "GAMA GLUTAMIL TRANSFERASE" como GGT.
    item = [("GGT", "encontrado")]
    assert ajusta(item, "Procedimentos realizados GGT 12/10/2026")[0]["GGT"] == "faltante"
    assert ajusta(item, "GGT 25 U/L valores de referência")[0]["GGT"] == "encontrado"
    # Sem o nome no texto a regra não opina, como o selo de laboratório.
    assert ajusta(item, "Texto sem o exame")[0]["GGT"] == "encontrado"


def test_rx_oit_classificado_antes_do_rx_comum():
    assert le.tipo_do_exame(norm("RADIOGRAFIA DE TÓRAX - PADRÃO OIT")) == "RX_OIT"
    assert le.tipo_do_exame(norm("RADIOGRAFIA DE TÓRAX PA")) == "RX"


def test_exigir_desligado_nao_mexe():
    status, mud = ajusta([("AUDIOMETRIA TONAL", "encontrado")], ASO_SO_LISTANDO, exigir_laudo=False)
    assert status["AUDIOMETRIA TONAL"] == "encontrado" and not mud


def test_markdown_vazio_nao_mexe_em_nada():
    comparativo = [{"exame": "AUDIOMETRIA TONAL", "status": "encontrado"}]
    assert le.ajustar_comparativo(comparativo, "  ", norm) == []
    assert comparativo[0]["status"] == "encontrado"


# --- ajustes de 20/10/2026 -------------------------------------------------------

def test_rx_oit_reconhece_a_ficha_da_cmtl():
    # A ficha da CMTL não traz "leitura radiológica" nem "qualidade técnica".
    texto = ("Radiografia do Tórax padrão OIT (Organização Internacional do Trabalho) "
             "Qualidade da radiografia 1 2 3 4 Parênquima Pequenas opacidades Profusão 0/0 "
             "Grandes opacidades 0 Espessamento pleural não")
    status, mud = ajusta([("RADIOGRAFIA DE TÓRAX - PADRÃO OIT", "encontrado")], texto)
    assert status["RADIOGRAFIA DE TÓRAX - PADRÃO OIT"] == "encontrado" and not mud


def test_acuidade_em_tabela_de_oftalmologista():
    texto = ("1. AV PARA LONGE OLHO DIREITO OLHO ESQUERDO S/C 20/50 20/40 C/C 20/20 20/20 "
             "2. SENSO CROMÁTICO normal 5. OFTALMOSCOPIA")
    status, mud = ajusta([("ACUIDADE VISUAL", "faltante")], texto)
    assert status["ACUIDADE VISUAL"] == "encontrado"
    assert mud[0]["regra"] == "conteudo_do_laudo"


def test_acuidade_em_tabela_sem_fracao_continua_faltante():
    texto = "AV PARA LONGE OLHO DIREITO OLHO ESQUERDO S/C C/C PARA PERTO"
    status, _ = ajusta([("ACUIDADE VISUAL", "faltante")], texto)
    assert status["ACUIDADE VISUAL"] == "faltante"


ASO_LISTA_SOROLOGIA = ("4. Procedimentos Realizados / Performed Procedures: Exames complementares "
                       "HBSAG 06/10/2026 ANTI-HBs 06/10/2026 ANTI-HCV 06/10/2026 "
                       "Conclusão / Conclusion Apto")


def test_resultado_de_outra_sorologia_nao_prova_o_analito_so_listado():
    # O "NÃO REAGENTE" do HBsAg provava o anti-HCV, que só estava no ASO.
    texto = ASO_LISTA_SOROLOGIA + " HEPATITE B HBsAg Resultado: Não Reagente Valor de referência"
    itens = [("HBSAG", "encontrado"), ("ANTI-HCV", "encontrado")]
    status, mud = ajusta(itens, texto)
    assert status == {"HBSAG": "encontrado", "ANTI-HCV": "faltante"}
    assert mud[0]["tipo"] == "SOROLOGIA"


def test_sorologia_com_laudo_perto_do_analito_continua_encontrada():
    texto = (ASO_LISTA_SOROLOGIA + " HEPATITE B HBsAg Resultado: Não Reagente "
             "ANTI-HCV Leitura 0,05 Resultado: Não Reagente Índice inferior a 0,89")
    status, mud = ajusta([("ANTI-HCV", "encontrado")], texto)
    assert status["ANTI-HCV"] == "encontrado" and not mud


def test_sorologia_aceita_as_grafias_dos_laudos():
    # Colunas trocadas pelo OCR ("HBS ANTI"), hepatite C sem a sigla e "ANT HBS".
    casos = [
        ("ANTI-HBS", "HBS ANTI HEPATITE B Material soro Resultado 2,0 UI/L Não reagente"),
        ("ANTI-HCV", "HEPATITE C ANTICORPO Leitura 0,05 Resultado Não reagente"),
        ("ANTI-HBS", "ANT HBS Resultado 341 mUI/mL Reagente"),
    ]
    for exame, texto in casos:
        status, mud = ajusta([(exame, "encontrado")], texto)
        assert status[exame] == "encontrado" and not mud, texto


def test_anti_hva_do_brnet_e_sorologia():
    # O BRNET grafa "ANTI-HVA IGG"; antes o exame nem era classificado.
    assert le.tipo_do_exame(norm("ANTI-HVA IGG")) == "SOROLOGIA"
    texto = ASO_LISTA_SOROLOGIA.replace("ANTI-HCV", "ANTI-HVA IGG") + " HERPES SIMPLES I IGG Não reagente"
    status, _ = ajusta([("ANTI-HVA IGG", "encontrado")], texto)
    assert status["ANTI-HVA IGG"] == "faltante"


def test_lista_sem_fechamento_fica_no_texto():
    # Sem a conclusão do ASO o bloco não sai: é o lado seguro.
    texto = md("Exames complementares ANTI-HCV 06/10/2026 Apto")
    assert "ANTI HCV" in le.sem_listas(texto)
    assert "ANTI HCV" not in le.sem_listas(md(ASO_LISTA_SOROLOGIA))
