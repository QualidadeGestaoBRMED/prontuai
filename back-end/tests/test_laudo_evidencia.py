"""Ajuste do veredito por exame a partir do conteúdo do laudo.

Os textos imitam o markdown normalizado (maiúsculas, sem acento, sem pontuação)
dos formatos medidos nas semanas de 14/09 a 05/10/2026.
"""
import re
import unicodedata

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
    # Glicose, transaminases, hemograma, espirometria e RX comum barravam mais
    # documentos certos do que pegavam: ficam fora da exigência.
    itens = [("GLICEMIA DE JEJUM", "encontrado"), ("TGO (AST)", "encontrado"),
             ("HEMOGRAMA COMPLETO COM PLAQUETAS", "encontrado"), ("ESPIROMETRIA", "encontrado"),
             ("RADIOGRAFIA DE COLUNA LOMBO SACRA AP/PERFIL", "encontrado"), ("CLÍNICO OCUPACIONAL", "encontrado")]
    status, mud = ajusta(itens, "ATESTADO DE SAÚDE OCUPACIONAL lista de exames sem laudo")
    assert set(status.values()) == {"encontrado"} and not mud


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
