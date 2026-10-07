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
