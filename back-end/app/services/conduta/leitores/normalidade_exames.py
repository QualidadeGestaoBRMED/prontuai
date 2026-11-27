"""
Normalidade e alteração de exames de laboratório.

Lê no markdown do OCR o resultado de cada parâmetro (glicose, HbA1c, hemoglobina,
plaquetas...) e a faixa de referência impressa pelo laboratório no mesmo laudo. O
resultado é só informativo: não muda status, faltantes, confiança nem
validation_status. A tela da checagem mostra os valores numa coluna da Comparação
Detalhada.

A faixa é a do laudo, por decisão da Saúde na reunião de 28/10/2026: os médicos da
BR MED seguem o que o laboratório considera normal ou alterado, sem cadastrar
faixa e sem contraprova da BR MED. O critério de conduta é outra etapa. Sem faixa
legível, a situação é `sem_referencia`: o valor aparece e nada é classificado.

Roda sobre o markdown local e não chama API: o resultado de exame é dado de
saúde e não sai daqui. Nada deste módulo loga valor nem trecho do documento.

Como a leitura acha o valor (cada regra veio de um erro visto nos laudos reais
da cópia de produção de 23/10/2026):

- procura cada nome do parâmetro e olha o texto logo depois dele, até 160
  caracteres ou até o próximo nome de analito, o que vier antes. Sem o corte, a
  "Hemoglobina" do hemograma herdava o g/dL do CHCM da linha de baixo;
- datas saem antes: "GLICEMIA 15/10/2026" na lista do ASO não é resultado;
- o valor precisa vir com a unidade do parâmetro ("182 mg/dL"), e o número não
  pode ser o fim de uma faixa ("70 a 99 mg/dL") nem vir depois de comparação
  ("maior ou igual a 126 / 200 mg/dL"), que é texto de referência;
- leucócitos e plaquetas aceitam número com separador de milhar ("6.890",
  "148.000") ou seguido de unidade por mm³/µL. Sem isso, o "CRM 1234" e o ano
  "2003" de uma citação viravam plaquetas. Contagem por mL é do exame de urina
  e não vale. "233 mil" vira 233.000, mas "150.600 mil/mm³" fica 150.600: o
  laboratório escreveu "mil" sobrando;
- valor fora do possível para o parâmetro (HbA1c 69 %, creatinina urinária 139
  mg/dL) é leitura errada, não resultado alterado, e é descartado;
- vale a primeira ocorrência com valor. Ocorrência sem valor (o nome na lista
  do ASO, no título do laudo) passa para a próxima.
"""
from __future__ import annotations

import os
import re
import unicodedata
from bisect import bisect_right
from dataclasses import dataclass
from typing import Any, Iterable, NamedTuple, Optional

layout_ocr = None  # só a leitura é usada aqui; a localização no PDF não

# Desliga a leitura sem deploy de código: NORMALIDADE_EXAMES=false.
HABILITADA = os.getenv("NORMALIDADE_EXAMES", "true").strip().lower() not in ("0", "false", "nao", "no")

NORMAL = "normal"
ACIMA = "acima"
ABAIXO = "abaixo"
# Qualitativo fora do normal (VDRL reagente): não tem lado.
ALTERADO = "alterado"
# Parâmetro do exame sem valor legível no PDF.
SEM_RESULTADO = "sem_resultado"
# Valor lido, mas sem faixa do laboratório em que se possa confiar.
SEM_REFERENCIA = "sem_referencia"

JANELA = 160


@dataclass(frozen=True)
class Parametro:
    chave: str
    nome: str
    unidade: str
    # Como o nome aparece no laudo, já normalizado (sem acento, maiúsculo).
    nomes: tuple[str, ...]
    # Onde o mínimo e o máximo impressos podem estar. Não é critério clínico: é a
    # conferência de que o número lido é a faixa deste parâmetro de adulto, e não
    # a de outro analito ou a de recém-nascido que o OCR deixou por perto.
    ref_min: Optional[tuple[float, float]] = None
    ref_max: Optional[tuple[float, float]] = None
    # Regex da unidade aceita logo depois do número, no texto normalizado.
    unidade_rx: str = ""
    # Contagem por mm³: aceita número sem unidade se tiver milhar ou "mil".
    milhar: bool = False
    # Resultado em texto (reagente / não reagente), sem faixa numérica.
    qualitativo: bool = False
    normal_texto: str = ""
    # Palavra logo depois do nome que mostra que é outro analito
    # ("HEMOGLOBINA GLICADA" não é a hemoglobina do hemograma).
    exclui: tuple[str, ...] = ()
    # Palavra logo antes do nome com o mesmo efeito ("CONCENTRACAO HEMOGLOBINA"
    # é o CHCM).
    exclui_antes: tuple[str, ...] = ()
    # Faixa do possível. Fora dela, a leitura pegou outro número.
    plausivel: tuple[float, float] = (0, float("inf"))
    # Só aparece na tela quando foi lido. Cada laboratório imprime um pedaço do
    # hemograma e do painel toxicológico; sem isso o modal se enche de "Não lido".
    opcional: bool = False
    # O laudo imprime a faixa do percentual e a da contagem uma depois da outra
    # ("40 a 75 %  1.440 a 9.000 /mm³"): pula a faixa que não é deste parâmetro em
    # vez de desistir na primeira. Só no diferencial do leucograma.
    faixa_entre_outras: bool = False
    # Qualitativo: quantas palavras podem ficar entre o nome e o resultado. Sem o
    # limite, "MACONHA" numa ficha clínica pegava o "FATOR RH POSITIVO" de baixo.
    alcance: Optional[int] = None
    # A referência é só o limite de baixo (HDL: abaixo de 40 é o alterado).
    piso: bool = False
    # A referência é a tabela por classe, e o normal vai até o fim da última classe
    # antes do limítrofe (LDL: ótimo + desejável).
    teto_da_tabela: bool = False


PARAMETROS: dict[str, Parametro] = {p.chave: p for p in (
    Parametro("glicemia", "Glicose em jejum", "mg/dL",
              ("GLICEMIA DE JEJUM", "GLICEMIA EM JEJUM", "GLICOSE DE JEJUM", "GLICOSE EM JEJUM", "GLICEMIA", "GLICOSE"),
              (40, 100), (80, 140), unidade_rx=r"MG\s?/\s?D[L1]", plausivel=(20, 1000),
              exclui=("MEDIA", "ESTIMADA", "POS", "NA URINA", "URINA", "1 HORA", "2 HORAS")),
    Parametro("hba1c", "Hemoglobina glicada (HbA1c)", "%",
              # "HB SA1C - forma estável" (laboratório do RJ) e "Hb Ale" (A1c lido pelo scanner): 27/11.
              ("HEMOGLOBINA GLICADA", "HBA1C", "HB A1C", "HB ALC", "HBALC", "HB SA1C", "SA1C", "HB ALE", "A1C"),
              (3, 5), (5, 7.5), unidade_rx=r"%", plausivel=(3, 20)),
    Parametro("colesterol", "Colesterol total", "mg/dL",
              ("COLESTEROL TOTAL", "COLESTROL TOTAL"),
              (0, 150), (150, 240), unidade_rx=r"MG\s?/\s?D[L1]", plausivel=(50, 1000)),
    Parametro("hdl", "Colesterol HDL", "mg/dL",
              ("COLESTEROL HDL", "HDL COLESTEROL", "HDL-COLESTEROL", "HDL"),
              (35, 55), None, unidade_rx=r"MG\s?/\s?D[L1]", plausivel=(5, 200), piso=True,
              exclui_antes=("NAO", "NAO-")),
    Parametro("ldl", "Colesterol LDL", "mg/dL",
              ("COLESTEROL LDL", "LDL COLESTEROL", "LDL-COLESTEROL", "LDL"),
              None, (99, 160), unidade_rx=r"MG\s?/\s?D[L1]", plausivel=(5, 600), teto_da_tabela=True),
    Parametro("triglic", "Triglicerídeos", "mg/dL",
              ("TRIGLICERIDEOS", "TRIGLICERIDES", "TRIGLICERIDIOS"),
              (0, 100), (100, 200), unidade_rx=r"MG\s?/\s?D[L1]", plausivel=(10, 5000)),
    Parametro("creatinina", "Creatinina", "mg/dL",
              ("CREATININA",),
              (0.3, 1.1), (0.8, 1.7), unidade_rx=r"MG\s?/\s?D[L1]", plausivel=(0.1, 20),
              exclui=("NA URINA", "URINARIA", "CLEARANCE")),
    Parametro("ureia", "Ureia", "mg/dL",
              ("UREIA",),
              (5, 30), (30, 80), unidade_rx=r"MG\s?/\s?D[L1]", plausivel=(2, 400),
              exclui=("NA URINA", "URINARIA")),
    Parametro("tgo", "TGO (AST)", "U/L",
              ("ASPARTATO AMINOTRANSFERASE", "TRANSAMINASE GLUTAMICA OXALACETICA", "TRANSAMINASE OXALACETICA", "TGO", "AST"),
              (0, 20), (20, 70), unidade_rx=r"U\s?/\s?L", plausivel=(1, 5000)),
    Parametro("tgp", "TGP (ALT)", "U/L",
              ("ALANINA AMINOTRANSFERASE", "TRANSAMINASE GLUTAMICA PIRUVICA", "TRANSAMINASE PIRUVICA", "TGP", "ALT"),
              (0, 20), (20, 70), unidade_rx=r"U\s?/\s?L", plausivel=(1, 5000)),
    Parametro("ggt", "Gama GT", "U/L",
              ("GAMA GLUTAMIL TRANSFERASE", "GAMA GLUTAMILTRANSFERASE", "GAMA-GT", "GAMA GT", "GGT"),
              (0, 20), (25, 90), unidade_rx=r"U\s?/\s?L", plausivel=(1, 5000)),
    Parametro("hemoglobina", "Hemoglobina", "g/dL",
              ("HEMOGLOBINA",),
              (10, 15.5), (14, 19), unidade_rx=r"G\s?/\s?DL|G\s?%", plausivel=(3, 25),
              exclui=("GLICADA", "CORPUSCULAR", "VARIANTE", "FETAL", "A1C"), exclui_antes=("CONCENTRACAO", "CONC.")),
    Parametro("leucocitos", "Leucócitos", "/mm³",
              ("LEUCOCITOS", "GLOBULOS BRANCOS"),
              (2500, 6000), (8000, 14000), milhar=True, plausivel=(500, 200000)),
    Parametro("plaquetas", "Plaquetas", "/mm³",
              ("PLAQUETAS",),
              (100000, 200000), (300000, 600000), milhar=True, plausivel=(5000, 2000000)),
    Parametro("vdrl", "VDRL", "",
              ("VDRL",),
              qualitativo=True, normal_texto="Não reagente"),
    # --- Resto do hemograma. Opcionais: só entram na tela quando lidos. ---
    Parametro("eritrocitos", "Eritrócitos", "milhões/mm³",
              ("ERITROCITOS", "HEMACIAS", "GLOBULOS VERMELHOS"),
              (3.5, 5.0), (4.8, 6.6), plausivel=(1, 9), opcional=True,
              # "milhões/mm³", "x10⁶/µL", "T/L". Sem unidade de milhão não vale:
              # é a hemácia do sedimento urinário ("3 /campo", "5.000 /mL").
              unidade_rx=r"MILH\w*|MI\s?/|X\s?10\s?\^?\s?6|10\s?\^?\s?6|T\s?/\s?L\b|M\s?/\s?UL",
              exclui=("NA URINA", "POR CAMPO", "/CAMPO")),
    Parametro("hematocrito", "Hematócrito", "%",
              ("HEMATOCRITO",),
              (33, 46), (43, 56), unidade_rx=r"%", plausivel=(10, 75), opcional=True),
    Parametro("vcm", "VCM", "fL",
              ("VCM", "VOLUME CORPUSCULAR MEDIO"),
              (76, 88), (94, 102), plausivel=(40, 150), opcional=True,
              # "fL" ou "µm³" (o µ cai na normalização e sobra "M3").
              unidade_rx=r"F\s?L\b|U?\s?M\s?3\b|FENTOLITROS?\b"),
    Parametro("hcm", "HCM", "pg",
              ("HCM", "HEMOGLOBINA CORPUSCULAR MEDIA"),
              (23, 29), (31, 35), unidade_rx=r"P\s?G\b|PICOGRAMAS?\b", plausivel=(10, 50), opcional=True,
              exclui_antes=("CONCENTRACAO", "CONCENTRACAO DE", "CONC.", "CONC. DE")),
    Parametro("chcm", "CHCM", "g/dL",
              ("CHCM", "CONCENTRACAO DE HEMOGLOBINA CORPUSCULAR MEDIA", "CONCENTRACAO HEMOGLOBINA CORPUSCULAR MEDIA"),
              (30, 34), (34, 38), unidade_rx=r"G\s?/\s?DL|G\s?%|%", plausivel=(20, 45), opcional=True),
    Parametro("rdw", "RDW", "%",
              ("RDW", "RDW-CV"),
              (10, 13), (14, 17), unidade_rx=r"%", plausivel=(5, 40), opcional=True,
              exclui=("-SD", "SD")),
    *(
        p
        for chave, nome, nomes, exclui, pct, conta in (
            ("bastonetes", "Bastonetes", ("BASTONETES", "BASTOES", "NEUTROFILOS EM BASTAO"), (),
             ((0, 1), (2, 11)), ((0, 100), (300, 1100))),
            ("segmentados", "Segmentados", ("SEGMENTADOS", "NEUTROFILOS SEGMENTADOS"), (),
             ((35, 55), (60, 80)), ((1000, 2600), (5500, 9500))),
            ("neutrofilos", "Neutrófilos", ("NEUTROFILOS",), ("SEGMENTADOS", "BASTONETES", "EM BASTAO"),
             ((35, 55), (60, 80)), ((1000, 2600), (5500, 9500))),
            ("eosinofilos", "Eosinófilos", ("EOSINOFILOS",), (),
             ((0, 2), (4, 8)), ((0, 100), (300, 800))),
            ("basofilos", "Basófilos", ("BASOFILOS",), (),
             ((0, 1), (1, 3)), ((0, 50), (100, 300))),
            ("linfocitos", "Linfócitos", ("LINFOCITOS",), ("ATIPICOS", "REATIVOS"),
             ((15, 30), (40, 55)), ((500, 1600), (2500, 5500))),
            ("monocitos", "Monócitos", ("MONOCITOS",), (),
             ((1, 4), (8, 14)), ((0, 500), (600, 1500))),
        )
        # O diferencial vem em percentual e em contagem, cada um com a sua faixa.
        for p in (
            Parametro(chave, nome, "%", nomes, *pct, unidade_rx=r"%", plausivel=(0, 100),
                      exclui=exclui, opcional=True, faixa_entre_outras=True),
            Parametro(f"{chave}_abs", nome, "/mm³", nomes, *conta, plausivel=(0, 100000),
                      unidade_rx=r"/?\s?MM\s?3|/\s?UL\b|/\s?CMM|CELS?\s?/\s?MM\s?3",
                      exclui=exclui, opcional=True, faixa_entre_outras=True),
        )
    ),
    Parametro("vpm", "VPM", "fL",
              ("VPM", "VOLUME PLAQUETARIO MEDIO", "VOLUME MEDIO PLAQUETARIO"),
              (6, 8.5), (10, 13), unidade_rx=r"F\s?L\b|U?\s?M\s?3\b|FENTOLITROS?\b", plausivel=(4, 20), opcional=True),
    # --- Triagem toxicológica: uma linha por substância, resultado em texto. ---
    *(
        # Até três palavras entre a substância e o resultado: "COCAINA E METABOLITOS
        # POSITIVO", "BENZODIAZEPINICOS BZO NEGATIVO".
        Parametro(chave, nome, "", nomes, qualitativo=True, normal_texto="Negativo", opcional=True, alcance=3)
        for chave, nome, nomes in (
            ("tox_anfetaminas", "Anfetaminas", ("ANFETAMINAS", "ANFETAMINA", "AMPHETAMINES", "AMPHETAMINE")),
            ("tox_metanfetamina", "Metanfetamina", ("METANFETAMINAS", "METANFETAMINA", "METHAMPHETAMINE")),
            ("tox_mdma", "Ecstasy (MDMA)", ("ECSTASY MDMA", "ECSTASY", "MDMA", "METILENODIOXIMETANFETAMINA")),
            ("tox_barbituricos", "Barbitúricos", ("BARBITURICOS", "BARBITURICO")),
            ("tox_benzodiazepinicos", "Benzodiazepínicos", ("BENZODIAZEPINICOS", "BENZODIAZEPINICO", "BENZODIAZEPINAS")),
            ("tox_cocaina", "Cocaína", ("COCAINA", "BENZOILECGONINA")),
            ("tox_maconha", "Maconha (THC)",
             ("MACONHA", "TETRAHIDROCANABINOL", "TETRA-HIDROCANABINOL", "CANABINOIDES", "CANABINOIDE", "CANABINOIS",
              "THC")),
            ("tox_fenciclidina", "Fenciclidina", ("FENCICLIDINA",)),
            ("tox_opiaceos", "Opiáceos", ("OPIACEOS", "OPIACEO", "OPIOIDES")),
            ("tox_morfina", "Morfina", ("MORFINA",)),
            ("tox_metadona", "Metadona", ("METADONA",)),
            ("tox_triciclicos", "Antidepressivos tricíclicos", ("ANTIDEPRESSIVOS TRICICLICOS", "TRICICLICOS")),
        )
    ),
)}

# Ordem do laudo, para o hemograma aparecer na tela como o laboratório imprime.
_HEMOGRAMA = (
    "eritrocitos", "hemoglobina", "hematocrito", "vcm", "hcm", "chcm", "rdw", "leucocitos",
    "bastonetes", "bastonetes_abs", "segmentados", "segmentados_abs", "neutrofilos", "neutrofilos_abs",
    "eosinofilos", "eosinofilos_abs", "basofilos", "basofilos_abs", "linfocitos", "linfocitos_abs",
    "monocitos", "monocitos_abs", "plaquetas", "vpm",
)
_TOXICOLOGICO = tuple(k for k in PARAMETROS if k.startswith("tox_"))

# Nomes que encerram a janela de um parâmetro: o próximo analito do laudo. Inclui
# os próprios parâmetros e os vizinhos que têm número com a mesma unidade (CHCM
# em g/dL, HDL em mg/dL, glicose média estimada da HbA1c).
_FRONTEIRA_EXTRA = (
    "ERITROCITOS", "HEMACIAS", "HEMATOCRITO", "VCM", "HCM", "CHCM", "RDW", "VPM", "PLAQUETOCRITO",
    "NEUTROFILOS", "SEGMENTADOS", "BASTONETES", "LINFOCITOS", "MONOCITOS", "EOSINOFILOS", "BASOFILOS",
    "HDL", "LDL", "VLDL", "NAO HDL", "LIPIDEOS TOTAIS", "GLICEMIA ESTIMADA", "GLICOSE MEDIA", "HB A1A", "HB A1B", "HB ALA", "HB ALB",
    "CONCENTRACAO DE HEMOGLOBINA", "MIELOCITOS", "METAMIELOCITOS", "PROMIELOCITOS", "BLASTOS",
    # Outros analitos que aparecem no mesmo laudo, com mg/dL ou U/L.
    "BILIRRUBINA", "FOSFATASE", "ACIDO URICO", "ACIDO", "SODIO", "POTASSIO", "CALCIO", "MAGNESIO", "FERRO", "FERRITINA",
    "ALBUMINA", "PROTEINAS", "AMILASE", "LIPASE", "CPK", "CREATINOFOSFOQUINASE", "TSH", "T4", "PSA", "INSULINA",
    "CORTISOL", "VITAMINA", "LIPOPROTEINA", "ZINCO", "CHUMBO", "COLINESTERASE", "MICROALBUMINURIA", "HEMACIAS NA URINA",
)

# Exame do BRNET → parâmetros. Casa contra o nome normalizado; a ordem importa
# (hemoglobina glicada antes de hemograma, carboxi-hemoglobina fora de tudo).
_EXAME_PARAMETROS: tuple[tuple[re.Pattern, tuple[str, ...]], ...] = (
    (re.compile(r"CARBOXI"), ()),
    (re.compile(r"\bHEMOGLOBINA GLICADA\b|\bHBA1C\b"), ("hba1c",)),
    (re.compile(r"\bHEMOGRAMA\b"), _HEMOGRAMA),
    (re.compile(r"\bTOXICOLOG"), _TOXICOLOGICO),
    (re.compile(r"\bLIPIDOGRAMA\b|\bPERFIL LIPIDICO\b|\bCOLESTEROL TOTAL E FRACOES\b"),
     ("colesterol", "hdl", "ldl", "triglic")),
    (re.compile(r"(?<!NAO )\bHDL\b"), ("hdl",)),
    (re.compile(r"(?<!V)\bLDL\b"), ("ldl",)),
    (re.compile(r"\bCOLESTEROL TOTAL\b"), ("colesterol",)),
    (re.compile(r"\bTRIGLICER"), ("triglic",)),
    (re.compile(r"\bCURVA\b|\bTOLERANCIA\b"), ()),
    (re.compile(r"\bGLICEMIA\b|\bGLICOSE\b"), ("glicemia",)),
    (re.compile(r"\bCREATININA\b"), ("creatinina",)),
    (re.compile(r"\bUREIA\b"), ("ureia",)),
    (re.compile(r"\bTGO\b|\bASPARTATO\b"), ("tgo",)),
    (re.compile(r"\bTGP\b|\bALANINA\b"), ("tgp",)),
    (re.compile(r"\bGGT\b|\bGAMA\s?-?\s?GT\b|\bGAMA GLUTAMIL"), ("ggt",)),
    (re.compile(r"\bVDRL\b"), ("vdrl",)),
    (re.compile(r"\bPLAQUETAS\b"), ("plaquetas",)),
)

_DATA = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")
# O número não pode ser pedaço de outro token: nem cauda ("MM3" de
# "MILHOES/MM3") nem começo ("52.000" de "CRM 52.0000000-0").
# "3.651,7/mm³": milhar com ponto e decimal com vírgula (contagem absoluta do leucograma; Textract, 24/11).
_NUMERO = r"(?<![A-Z0-9/.,])(\d{1,3}(?:\.\d{3})+,\d+|\d{1,3}(?:\.\d{3})+|\d+(?:[.,]\d+)?)(?![0-9]|[.,][0-9])"
_MILHAR = re.compile(r"\d{1,3}(?:\.\d{3})+")
# Unidade de contagem no sangue. "/ML" (por mililitro) é do sedimento urinário.
_UNIDADE_CONTAGEM = re.compile(r"\s*(?:/?\s?MM\s?3|/\s?MM\b|/\s?UL|/\s?L\b|/\s?CMM)")
# Palavra imediatamente antes do número que o torna texto de referência.
_ANTES_REFERENCIA = {
    "A", "ATE", "DE", "QUE", "E", "MAIOR", "MENOR", "IGUAL", "INFERIOR", "SUPERIOR", "ACIMA", "ABAIXO",
    "ENTRE", "<", ">", "<=", ">=", "-",
    # "ATE" lido pelo OCR ("HOMENS AT6 60,0 U/L"): GGT 60/43 e TGP 41 saíam da referência (auditoria do Breno, 27/11).
    "AT6", "AT", "AID", "ATB", "AT8",
    # "Menor que" lido pelo scanner como "Manor qua" (unicodoc-8558911, 27/11).
    "QUA",
}
# Comparação um pouco antes do número: "estão acima de [...] 800 mg/dL" é nota
# do laboratório, com o OCR embaralhando a ordem das palavras.
_COMPARACAO_PERTO = {"ACIMA", "ABAIXO", "MAIOR", "MENOR", "SUPERIOR", "INFERIOR", "IGUAL", "ATE", "ENTRE", "QUANDO"}
# "DETECTADO" sozinho fica de fora: "NAO FOI DETECTADO O USO" virava positivo.
_QUALITATIVO = re.compile(r"\b(NAO REAGENTE|NAO-REAGENTE|NEGATIVO|REAGENTE|POSITIVO|NAO DETECTADO)\b(\s+\d+/\d+)?")
_TEXTO_QUALITATIVO = {
    "NAO REAGENTE": "Não reagente", "NEGATIVO": "Negativo", "REAGENTE": "Reagente", "POSITIVO": "Positivo",
    "NAO DETECTADO": "Não detectado",
}
_QUALITATIVO_NORMAL = ("Não reagente", "Negativo", "Não detectado")


def normalizar(texto: str) -> str:
    """Sem acento, maiúsculo, espaço simples. Mantém dígitos, vírgula, ponto, "%",
    "/", "-" e "<>" (fazem parte de valor, unidade e faixa)."""
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().upper()
    texto = texto.replace("³", "3")
    return re.sub(r"[^A-Z0-9,.%/<>\-]+", " ", texto).strip()


def _numero(texto: str) -> float:
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+,\d+", texto):
        return float(texto.replace(".", "").replace(",", "."))
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", texto):
        return float(texto.replace(".", ""))
    return float(texto.replace(",", "."))


def _regex_nomes(nomes: Iterable[str]) -> str:
    alts = sorted({n for n in nomes}, key=len, reverse=True)
    return "|".join(re.escape(n).replace(r"\ ", r"\s+") for n in alts)


# Nome colado em letra, número ou hífen de palavra ("NAO-HDL", "HDL-COLESTEROL") não vale. Hífen solto, de marcador de
# lista, vale: "-COLESTEROL TOTAL.:174 MG/DL" e "COLESTEROL -HDL 42,0" ficavam sem leitura (auditoria do LDL, 27/11).
_ANTES_DO_NOME = r"(?<![A-Z0-9])(?<![A-Z0-9]-)"


def _compilar(p: Parametro) -> re.Pattern:
    exclui = "".join(f"(?!\\s*{re.escape(e)})" for e in p.exclui)
    return re.compile(rf"{_ANTES_DO_NOME}(?:{_regex_nomes(p.nomes)})(?![A-Z0-9]){exclui}")


_RX_NOME = {k: _compilar(p) for k, p in PARAMETROS.items()}
_RX_FRONTEIRA = re.compile(
    rf"{_ANTES_DO_NOME}(?:{_regex_nomes([n for p in PARAMETROS.values() for n in p.nomes] + list(_FRONTEIRA_EXTRA))})(?![A-Z0-9])"
)


def _palavra_antes(texto: str, fim: int) -> str:
    m = re.search(r"(\S+)\s*$", texto[:fim])
    return m.group(1).rstrip(":") if m else ""


def _referencia_antes(jan: str, inicio: int) -> bool:
    antes = _palavra_antes(jan, inicio)
    # Ícone do laudo lido como "0" entre o nome e o resultado ("CREATININA ○ 1,11 MG/DL 0,70 A 1,30"): o zero solto
    # logo depois do nome não é início de faixa (auditoria de exames sem dado, 27/11).
    if antes == "0" and len(jan[:inicio].split()) == 1:
        return False
    # Número antes ("100 - 200") é faixa; pontuação sozinha não é número: "COLESTEROL TOTAL. 260 mg/dl" (Labore, que
    # imprime o nome seguido de pontilhado) perdia colesterol, HDL e triglicerídeos (unicodoc-8513620, 27/11).
    if antes in _ANTES_REFERENCIA or (re.fullmatch(r"[\d.,]+", antes) and re.search(r"\d", antes)):
        return True
    # Pontuação solta logo depois de um número é decimal quebrado pelo OCR: "HB A1C . 4 , 7 %" não é 7.
    if antes and re.fullmatch(r"[.,]+", antes):
        anteriores = jan[:inicio].split()[-2:-1]
        if anteriores and re.fullmatch(r"[\d.,]*\d[\d.,]*", anteriores[0]):
            return True
    return bool(_COMPARACAO_PERTO.intersection(jan[:inicio].split()[-3:]))


def _valor_numerico(p: Parametro, jan: str) -> Optional[tuple[float, str, int, int]]:
    """(valor, como exibir, início e fim do número na janela)."""
    lo, hi = p.plausivel
    # HbA1c com um decimal logo depois do nome e o "%" lido como 8 ("HB A1C 4,9 8" e "HB A1C 4,98" no laudo
    # DB Diagnósticos, que imprime "4,9 %"): conferido no PDF em 27/11 (8048992, 8197264, 8688305).
    if p.chave == "hba1c":
        # Também sem o "%": "HB A1C 5,4 NORMAL MENOR QUE 5,7%" (o resultado vem colado no nome e a referência depois).
        m = re.match(r"\s*[:.]?\s*(\d{1,2},\d)(?:\s?8(?![\d.,%])|(?=\s+(?:NORMAL|NOTMAL|VALOR|VR\b|V\.R|VIDE)))", jan)
        if m and lo <= _numero(m.group(1)) <= hi:
            return _numero(m.group(1)), m.group(1), m.start(1), m.end(1)
    if p.milhar:
        m = re.search(rf"{_NUMERO}(\s*(?:MIL\b|X\s?10\s?\^?\s?3|X\s?10E3))?", jan)
        if not m or _referencia_antes(jan, m.start()):
            return None
        texto = m.group(1)
        valor = _numero(texto)
        depois = jan[m.end(1):]
        # "/ML" é urina; "2.000 A 7.000" é a faixa do neutrófilo numa tabela
        # embaralhada, não a contagem.
        if re.match(r"\s*/\s?ML\b", depois) or re.match(r"\s*(?:A|ATE|-)\s*\d", depois):
            return None
        if m.group(2) and not _MILHAR.fullmatch(texto) and valor < 1000:
            valor *= 1000
            texto = _fmt(valor)
        elif not (_MILHAR.fullmatch(texto) or _UNIDADE_CONTAGEM.match(depois)):
            return None
        return (valor, texto, m.start(1), m.end(1)) if lo <= valor <= hi else None
    for m in re.finditer(rf"{_NUMERO}\s*(?:{p.unidade_rx})", jan):
        if _referencia_antes(jan, m.start()):
            continue
        # Número que abre uma faixa ("PRE-DIABETES 5,7% A 6,4%") é a referência, não o resultado: com o resultado
        # ilegível, a HbA1c ficava 5,7 em 432 documentos (auditoria do Breno, 27/11).
        # Só faixa com a unidade dos dois lados: "35 U/L ATE 40 U/L" é resultado seguido da referência, e
        # "188 MG/DL A 2 ANOS" é a tabela por idade que vem depois.
        if re.match(rf"\s*A\s+\d+(?:[.,]\d+)?\s*(?:{p.unidade_rx})", jan[m.end():]):
            continue
        valor = _numero(m.group(1))
        return (valor, m.group(1), m.start(1), m.end(1)) if lo <= valor <= hi else None
    return _valor_pela_faixa(p, jan)


# O RapidOCR perde ou troca a unidade ao lado do valor ("CHCM.. 33,3 / 31,5 a 35,5 %", "HCM 28,6 bd 27,0 a 32,0 pg"):
# na comparação com o Textract (23/11, 197 documentos de produção) 82 documentos perdiam algum valor por isso. A unidade
# vem então da faixa de referência logo depois do número, que precisa estar no lugar certo para o parâmetro.
_RX_FAIXA_COM_UNIDADE = r"\s*(?:\S{{1,4}}\s+)?{num}\s*(?:A|ATE|-)\s*{num}\s*(?:{uni})"


def _valor_pela_faixa(p: Parametro, jan: str) -> Optional[tuple[float, str, int, int]]:
    lo, hi = p.plausivel
    m = next((x for x in re.finditer(_NUMERO, jan) if not _referencia_antes(jan, x.start())), None)
    if not m:
        return None
    faixa = re.match(_RX_FAIXA_COM_UNIDADE.format(num=_NUM_REF, uni=p.unidade_rx), jan[m.end():m.end() + 70])
    if not faixa:
        return None
    a, b = _numero(faixa.group(1)), _numero(faixa.group(2))
    valor = _numero(m.group(1))
    # O número tem de ser da ordem da faixa: "basófilos 35 / 0 a 2 %" é o valor de outra linha da tabela embaralhada.
    if not (a < b and _no_lugar_certo(p, a, b) and lo <= valor <= hi and a / 2 <= valor <= b * 2):
        return None
    return valor, m.group(1), m.start(1), m.end(1)


class FaixaLaudo(NamedTuple):
    minimo: Optional[float]
    maximo: Optional[float]
    # "Inferior a 190": o próprio 190 já está fora.
    teto_exclusivo: bool = False


_NUM_REF = r"(\d{1,3}(?:\.\d{3})+|\d+(?:[.,]\d+)?)"
_UNIDADE_REF = r"(?:\s*(?:MG\s?/\s?DL|G\s?/\s?DL|U\s?/\s?L|%|/?\s?MM\s?3|/\s?UL|MIL(?:\s?/\s?MM\s?3)?))?"
_SEM_IDADE = r"(?!\s*(?:ANO|ANOS|MES|MESES|DIA|DIAS)\b)"
_RX_INTERVALO = re.compile(rf"(?<![A-Z\d.,/]){_NUM_REF}{_UNIDADE_REF}\s*(?:A|ATE|-)\s*{_NUM_REF}(?![\d]){_SEM_IDADE}")
# Tabela em que o OCR comeu o conector: "60,0 99,0 MG/DL".
_RX_PAR = re.compile(rf"(?<![A-Z\d.,/]){_NUM_REF}\s+{_NUM_REF}(?![\d.,/]){_SEM_IDADE}")
_RX_TETO = re.compile(
    rf"(INFERIOR OU IGUAL A|MENOR OU IGUAL A|<\s?=|ATE)\s*{_NUM_REF}{_SEM_IDADE}"
    rf"|(INFERIOR A|MENOR QUE|MENOR DE|<)\s*{_NUM_REF}{_SEM_IDADE}"
)
# Daqui em diante são as outras classes da tabela, não a de quem está normal.
_RX_OUTRA_CLASSE = re.compile(
    r"\b(?:PRE.?DIABET\w*|DIABET\w*|LIMITROFE|ALTO|ELEVADO|RISCO|TOLERANCIA|DIAGNOSTICO|META|CONTROLE|ANTERIOR|ANTERIORES|PACIENTES?|DM1|DM2|DATA HORA|RESULTADO)\b"
)
_RX_NAO_ADULTO = re.compile(
    r"\b(?:CRIANCAS?|ADOLESCENTES?|RECEM|NEONATOS?|PREMATUROS?|CORDAO|LACTENTES?|INFANTIL)\b"
    r"|\b\d+\s*(?:ANO|ANOS|MES|MESES|DIA|DIAS)\b|\b\d+[AM]\d+[MD]"
)
_RX_HOMEM = re.compile(r"\b(?:HOMEM|HOMENS|MASCULINO)\b")
_RX_MULHER = re.compile(r"\b(?:MULHER|MULHERES|FEMININO)\b")
# "Sexo: M", "Gênero / Genre: Masculino". "Para pacientes DO sexo feminino, anotar DUM" (ficha) não é o sexo.
_RX_SEXO = re.compile(r"(?<!PACIENTES DO )(?<!PACIENTE DO )\b(?:SEXO|GENERO(?:\s*/\s*GENRE)?|GENRE|GENDER)\s*[:/]?\s*(MASCULINO|FEMININO|MALE|FEMALE|M|F)\b")
_RX_ADULTO = re.compile(r"\bADULTOS?\b(?:\s+(?:ACIMA|MAIOR(?:ES)?)\s+DE\s+\d+\s+ANOS)?")
# Faixa etária de adulto escrita pela idade: "Superior a 19 anos", "Acima de 18
# anos", ">= 20 anos", "20 anos ou mais".
_RX_IDADE_ADULTA = re.compile(
    r"\b(?:SUPERIOR|ACIMA|MAIOR(?:ES)?|A PARTIR)\s+(?:A|DE|QUE)\s+(?:1[89]|20)\s+ANOS\b"
    r"|(?:>\s?=?)\s*(?:1[89]|20)\s+ANOS\b"
    r"|\b(?:1[89]|20)\s+ANOS\s+(?:OU MAIS|OU MAIOR|EM DIANTE)\b"
)
_RX_TABELA_DE_RISCO = re.compile(r"\b(?:RISCO|INTERMEDIARIO|META|METAS|CATEGORIA)\b")
_RX_COM_JEJUM = re.compile(r"\bCOM JEJUM\b")
_RX_SEM_JEJUM = re.compile(r"\bSEM JEJUM\b")
# Limite de baixo do HDL. Os dois sentidos dizem o mesmo número: "menor que 40" é
# o baixo, "maior que 40" é o desejável.
_RX_PISO = re.compile(
    rf"(MAIOR OU IGUAL A|MAIOR QUE|MAIOR DE|SUPERIOR A|ACIMA DE|>\s?=|>|MENOR QUE|MENOR DE|INFERIOR A|<\s?=|<)"
    rf"\s*{_NUM_REF}{_SEM_IDADE}"
)


def _sexo_do_documento(norm: str) -> Optional[str]:
    """Sexo impresso no laudo. Fica no processo: não vai para log nem para fora."""
    m = _RX_SEXO.search(norm)
    if not m:
        return None
    return {"MALE": "M", "FEMALE": "F"}.get(m.group(1), m.group(1)[0])


def _no_lugar_certo(p: Parametro, minimo: Optional[float], maximo: Optional[float]) -> bool:
    if minimo is not None and not (p.ref_min and p.ref_min[0] <= minimo <= p.ref_min[1]):
        return False
    return maximo is None or bool(p.ref_max and p.ref_max[0] <= maximo <= p.ref_max[1])


def _intervalo(p: Parametro, m: re.Match) -> Optional[FaixaLaudo]:
    a, b = _numero(m.group(1)), _numero(m.group(2))
    # "150 A 400" ao lado de "MIL/MM3" é 150.000 a 400.000.
    for escala in (1, 1000) if p.milhar else (1,):
        if a < b and _no_lugar_certo(p, a * escala, b * escala):
            return FaixaLaudo(a * escala, b * escala)
    return None


# Milhar que o OCR gravou com espaço no lugar do ponto: "3 500 A 10.500". Só nas
# contagens (`milhar`), sem zero à esquerda, sem letra colada antes (o "3" de
# "MM3 150 A 450" não é milhar) e com o grupo de três dígitos fechado.
# A conferência de `ref_min`/`ref_max` continua barrando o que não for faixa.
_RX_MILHAR_COM_ESPACO = re.compile(r"(?<![A-Z\d.,/])([1-9]\d{0,2}) (\d{3})(?![\d.,])")


def _faixa_no_texto(p: Parametro, depois: str, sexo: Optional[str]) -> Optional[FaixaLaudo]:
    """
    A faixa de adulto impressa logo depois do resultado, ou None. Errar aqui marca
    como alterado quem está normal, então toda dúvida vira None: faixa por idade
    sem adulto, coluna de homem e mulher sem saber o sexo, dois intervalos sem
    rótulo, número fora do lugar deste parâmetro.
    """
    texto = depois[:170]
    adulto = _RX_ADULTO.search(texto)
    if adulto:
        texto = texto[adulto.end():]
    faixa = _faixa_recortada(p, texto, sexo, adulto is not None)
    if faixa is not None:
        return faixa
    # Tabela por idade sem a palavra "adulto": "0 a 2 anos ... 2 a 19 anos ...
    # Superior a 19 anos: Com jejum: Inferior a 190". Fica longe do valor, por isso
    # a busca vai mais adiante; e só roda quando a leitura acima não achou nada.
    etaria = _RX_IDADE_ADULTA.search(depois[:600])
    if not etaria:
        return None
    texto = depois[etaria.end():etaria.end() + 170]
    # Com e sem jejum lado a lado: vale a de jejum, como é colhido o kit do ASO.
    jejum = _RX_COM_JEJUM.search(texto)
    if jejum:
        sem = _RX_SEM_JEJUM.search(texto, jejum.end())
        texto = texto[jejum.end():sem.start() if sem else len(texto)]
    return _faixa_recortada(p, texto, sexo, True)


_RX_FAIXA_ETARIA_NO_SEXO = re.compile(r"\b\d{1,2} A \d{1,2} ANOS")
_RX_ADULTO_NO_SEXO = re.compile(r"(?:>=?|ACIMA DE|SUPERIOR A|MAIOR(?:ES)? (?:DE|QUE)|A PARTIR DE) ?(?:1[89]|2[01]) ANOS|ADULTOS?")


def _faixa_recortada(p: Parametro, texto: str, sexo: Optional[str], adulto: bool) -> Optional[FaixaLaudo]:
    homem, mulher = _RX_HOMEM.search(texto), _RX_MULHER.search(texto)
    if homem or mulher:
        proprio, outro = (homem, mulher) if sexo == "M" else (mulher, homem) if sexo == "F" else (None, None)
        if not proprio:
            return None
        fim = outro.start() if outro and outro.start() > proprio.start() else len(texto)
        texto = texto[proprio.end():fim]
        # Faixas por idade dentro do sexo ("MASCULINO 15 a 16 anos 0,65-1,04 / 17 a 19 anos 0,69-1,10 / > 19 anos
        # 0,70-1,30"): vale a de adulto. Sem faixa de adulto, None. Antes pegava a primeira (15–16 anos) e marcava
        # creatinina de adulto como acima (lista do Breno, 23/11).
        if _RX_FAIXA_ETARIA_NO_SEXO.search(texto):
            adulta = _RX_ADULTO_NO_SEXO.search(texto)
            if not adulta:
                return None
            texto = texto[adulta.end():]
    # Meta por risco cardiovascular ("< 130 Baixo, < 100 Intermediário"): o alvo
    # depende do paciente, não há um normal do laboratório.
    if p.teto_da_tabela and _RX_TABELA_DE_RISCO.search(texto):
        return None
    classe = _RX_OUTRA_CLASSE.search(texto)
    if classe:
        texto = texto[:classe.start()]
    if p.piso:
        return _piso(p, texto, adulto)
    if p.teto_da_tabela:
        return _teto_da_tabela(p, texto, adulto)

    rxs = (_RX_INTERVALO, _RX_TETO, _RX_PAR)
    if p.faixa_entre_outras:
        candidatos = sorted((m for rx in rxs for m in rx.finditer(texto)), key=lambda c: c.start())
    else:
        # Só a primeira faixa do texto: se não for deste parâmetro, desiste.
        primeiras = [m for m in (rx.search(texto) for rx in rxs) if m]
        candidatos = [min(primeiras, key=lambda c: c.start())] if primeiras else []
    for m in candidatos:
        faixa = _faixa_do_candidato(p, texto, m, adulto)
        if faixa is not None:
            return faixa
    return None


def _piso(p: Parametro, texto: str, adulto: bool) -> Optional[FaixaLaudo]:
    """
    HDL: o laudo diz onde começa o baixo ("Baixo: menor que 40", "Desejável: maior
    que 40"). Vale o primeiro limite no lugar do mínimo deste parâmetro; "maior ou
    igual a 60" é a classe de cima e fica fora pelo `ref_min`.
    """
    for m in _RX_PISO.finditer(texto):
        if not adulto and _RX_NAO_ADULTO.search(texto[:m.start()]):
            return None
        minimo = _numero(m.group(2))
        if p.ref_min and p.ref_min[0] <= minimo <= p.ref_min[1]:
            return FaixaLaudo(minimo, None)
    return None


def _teto_da_tabela(p: Parametro, texto: str, adulto: bool) -> Optional[FaixaLaudo]:
    """
    LDL: tabela por classe ("Ótimo: menor que 100 / Desejável: de 100 a 129 /
    Limítrofe: ..."). `_RX_OUTRA_CLASSE` já cortou do limítrofe em diante; o maior
    teto que sobrou é o fim do que o laboratório considera bom. A tabela por risco
    cardiovascular ("Baixo risco: < 130 / Alto risco: < 70") depende do paciente e
    é cortada antes de achar número.
    """
    melhor: Optional[FaixaLaudo] = None
    for rx in (_RX_INTERVALO, _RX_TETO):
        for m in rx.finditer(texto):
            if not adulto and _RX_NAO_ADULTO.search(texto[:m.start()]):
                return None
            if m.re is _RX_TETO:
                exclusivo = m.group(3) is not None
                faixa = FaixaLaudo(None, _numero(m.group(4) if exclusivo else m.group(2)), exclusivo)
            else:
                faixa = FaixaLaudo(None, _numero(m.group(2)))
            if _no_lugar_certo(p, None, faixa.maximo) and (melhor is None or faixa.maximo > melhor.maximo):
                melhor = faixa
    return melhor


def _faixa_do_candidato(p: Parametro, texto: str, m: re.Match, adulto: bool) -> Optional[FaixaLaudo]:
    if not adulto and _RX_NAO_ADULTO.search(texto[:m.start()]):
        return None
    if m.re is _RX_TETO:
        exclusivo = m.group(3) is not None
        maximo = _numero(m.group(4) if exclusivo else m.group(2))
        return FaixaLaudo(None, maximo, exclusivo) if _no_lugar_certo(p, None, maximo) else None
    faixa = _intervalo(p, m)
    if faixa is None:
        return None
    # "13,0 A 17,5 12,0 A 16,0": duas colunas sem rótulo, uma de cada sexo.
    resto = texto[m.end():m.end() + 25]
    for rx in (_RX_INTERVALO, _RX_PAR):
        vizinho = rx.search(resto)
        if vizinho and (segunda := _intervalo(p, vizinho)) and segunda != faixa:
            return None
    return faixa


_RX_ZERO_LIDO_COMO_O = re.compile(r"(?<![A-Z0-9.,/])O(?=\s+(?:A|ATE)\s+\d)")


def _faixa_do_laudo(p: Parametro, depois: str, sexo: Optional[str]) -> Optional[FaixaLaudo]:
    """
    A faixa do laudo. O milhar com espaço só entra quando a leitura normal não achou
    nada: assim ele não muda faixa que já era lida ("150 450" sem conector é um par,
    e juntar viraria 150.450).
    """
    # O OCR lê o zero do começo da faixa como a letra O: "o a 240 /mm³".
    depois = _RX_ZERO_LIDO_COMO_O.sub("0", depois)
    faixa = _faixa_no_texto(p, depois, sexo)
    if faixa is None and p.milhar:
        corrigido = _RX_MILHAR_COM_ESPACO.sub(r"\1.\2", depois[:170])
        if corrigido != depois[:170]:
            faixa = _faixa_no_texto(p, corrigido, sexo)
    return faixa


def _valor_qualitativo(jan: str, alcance: Optional[int] = None) -> Optional[tuple[str, int, int]]:
    """(como exibir, início e fim do resultado na janela)."""
    # Quando a janela tem "RESULTADO", a resposta vem depois dele; antes pode
    # estar a faixa ("Valor de referência: Não reagente").
    pos = jan.find("RESULTADO")
    m = _QUALITATIVO.search(jan, pos if pos >= 0 else 0)
    if not m:
        return None
    if alcance is not None and len(jan[:m.start()].split()) > alcance:
        return None
    titulo = (m.group(2) or "").strip()
    texto = _TEXTO_QUALITATIVO[m.group(1).replace("-", " ")]
    return f"{texto} {titulo}".strip(), m.start(), m.end()


@dataclass
class Leitura:
    chave: str
    nome: str
    unidade: str
    valor: Optional[float]
    valor_texto: str
    # Onde o nome do parâmetro e o valor estão no texto normalizado, para achar
    # o trecho no PDF (`localizar_leitura`). Fim exclusivo.
    nome_em: tuple[int, int] = (0, 0)
    valor_em: tuple[int, int] = (0, 0)
    faixa: Optional[FaixaLaudo] = None


_SIGLA_PONTUADA = re.compile(r"(?<![A-Z0-9.])(?:[A-Z]\.){2,}[A-Z]?\.?(?![A-Z0-9])")


def _texto_normalizado(markdown: str) -> tuple[str, list[tuple[int, int]]]:
    """
    O markdown normalizado numa linha só, como a leitura procura, e onde cada
    linha do markdown começa nele: [(início no texto, índice da linha)].

    Normaliza linha a linha e junta com espaço. Dá o mesmo texto que normalizar
    o markdown inteiro de uma vez — conferido nos 3.000 documentos mais recentes
    da cópia de produção de 23/10/2026, sem nenhuma diferença —, mas sabendo de
    que linha veio cada posição. É o que liga a leitura à caixa da linha no PDF.
    """
    partes: list[str] = []
    inicios: list[tuple[int, int]] = []
    tamanho = 0
    for indice, linha in enumerate((markdown or "").split("\n")):
        # Rótulo com pontilhado ("HEMOGLOBINA..... 13,2", "V.C.M...... 94,4"): sem isto o valor não é lido
        # (619 documentos do Unicodoc, laboratório Qualimetra; 23/11).
        trecho = re.sub(r" {2,}", " ", re.sub(r"(?:\s*\.){2,}\s*:?", " ", _DATA.sub(" ", normalizar(linha)))).strip()
        # Sigla com ponto entre as letras ("V.C.M.", "R.D.W.", "C.H.C.M."): o Textract escreve assim em alguns
        # laboratórios e o nome não casava (24/11).
        trecho = _SIGLA_PONTUADA.sub(lambda m: m.group(0).replace(".", ""), trecho)
        if not trecho:
            continue
        if partes:
            tamanho += 1  # o espaço que junta as linhas
        inicios.append((tamanho, indice))
        partes.append(trecho)
        tamanho += len(trecho)
    return " ".join(partes), inicios


_DIFERENCIAL = {f"{n}{s}" for n in ("bastonetes", "segmentados", "neutrofilos", "eosinofilos", "basofilos", "linfocitos",
                                     "monocitos") for s in ("", "_abs")}


def _ler(markdown: str) -> tuple[dict[str, Leitura], str, list[tuple[int, int]]]:
    norm, inicios = _texto_normalizado(markdown)
    nomes_em = [m.span() for m in _RX_FRONTEIRA.finditer(norm)]
    fronteiras = [a for a, _ in nomes_em]

    def em_pilha_de_rotulos(inicio: int) -> bool:
        """Nome logo depois de 2+ outros nomes de exame sem número no meio ("EOSINOFILOS / BASOFILOS / LINFOCITOS /
        MONOCITOS" e só depois os valores, fora de ordem): o OCR separou rótulos e valores em colunas e o número
        que vem depois não é deste exame. Laudo do Unicodoc, 23/11: 628 monócitos = 0% e monócitos absolutos com o
        total de leucócitos. Fora da conta do ProntuAI até ser levado para lá (ver normalidade_correcoes.diff)."""
        seguidos, fim, vistos = 0, inicio, set()
        for a, b in reversed([s for s in nomes_em if s[1] <= inicio]):
            meio = norm[b:fim]
            if len(meio.strip(" :/-#")) > 3 or re.search(r"\d", meio):
                break
            fim = a
            if norm[a:b] in vistos:
                continue
            vistos.add(norm[a:b])
            seguidos += 1
            if seguidos >= 2:
                return True
        return False
    sexo = _sexo_do_documento(norm)
    leituras: dict[str, Leitura] = {}
    for chave, p in PARAMETROS.items():
        for m in _RX_NOME[chave].finditer(norm):
            if p.exclui_antes and norm[max(0, m.start() - 20):m.start()].rstrip().endswith(p.exclui_antes):
                continue
            # Só no leucograma diferencial: na série vermelha ("ERITROCITOS HEMOGLOBINA HEMATOCRITO 5,30 15,6 45,7 %")
            # os valores vêm na ordem e a unidade acerta a leitura (conferido em 23/11).
            # Na pilha, só vale o percentual colado no nome ("EOSINOFILOS BASOFILOS LINFOCITOS 26,4 % MONOCITOS 6,1 %").
            if chave in _DIFERENCIAL and em_pilha_de_rotulos(m.start()) and not (
                    not chave.endswith("_abs") and re.match(r"\s*[:\-]?\s*\d+(?:[.,]\d+)?\s*%", norm[m.end():])):
                continue
            ini = m.end()
            proxima = next((f for f in fronteiras if f >= ini), len(norm))
            jan = norm[ini:min(ini + JANELA, proxima)]
            # Contagem em milhar com outro rótulo colado ("PLAQUETAS VPM 152.000/MM3 13,2"): o número em milhar é
            # inconfundível, então a janela passa por cima do rótulo vizinho sem número (24/11).
            if p.milhar and not re.search(r"\d", jan) and not p.qualitativo:
                jan = norm[ini:ini + JANELA]
            if p.qualitativo:
                achado = _valor_qualitativo(jan, p.alcance)
                if achado:
                    texto, a, b = achado
                    leituras[chave] = Leitura(chave, p.nome, p.unidade, None, texto, m.span(), (ini + a, ini + b))
                    break
                continue
            achado = _valor_numerico(p, jan)
            if achado:
                valor, texto, a, b = achado
                fim_valor = ini + b
                seguinte = next((f for f in fronteiras if f >= fim_valor), len(norm))
                faixa = _faixa_do_laudo(p, norm[fim_valor:seguinte], sexo)
                if faixa is None:
                    # O mesmo analito de novo logo depois do valor não encerra a
                    # faixa: "89 mg/dL  Glicemia em jejum: Normal 70 a 99 mg/dL".
                    # Só quando a leitura normal não achou nada, para não trocar
                    # faixa já lida pela nota que vem depois ("... em adultos").
                    estendida = next(
                        (f for f in fronteiras if f >= fim_valor and not _RX_NOME[chave].match(norm, f)), len(norm)
                    )
                    if estendida != seguinte:
                        faixa = _faixa_do_laudo(p, norm[fim_valor:estendida], sexo)
                leitura = Leitura(chave, p.nome, p.unidade, valor, texto, m.span(), (ini + a, fim_valor), faixa)
                # Fica a primeira ocorrência COM faixa. A primeira com valor pode ser o laudo médico citando o
                # exame ("observa-se creatinina 1,4 mg/dL"), sem faixa, antes do laudo do laboratório.
                if chave not in leituras:
                    leituras[chave] = leitura
                elif leituras[chave].faixa is None and faixa is not None:
                    leituras[chave] = leitura
                if faixa is not None:
                    break
    return leituras, norm, inicios


def ler_valores(markdown: str) -> dict[str, Leitura]:
    """O primeiro resultado legível de cada parâmetro no documento."""
    return _ler(markdown)[0]


# ---------------------------------------------------------------------------
# Onde a leitura está no PDF
# ---------------------------------------------------------------------------

def _pedacos(texto: str) -> list[tuple[str, int, int]]:
    """As palavras de uma linha original já normalizadas, cada uma com o trecho
    (início, fim) de onde veio no texto original."""
    pedacos = []
    for m in re.finditer(r"\S+", texto):
        for parte in normalizar(m.group()).split():
            pedacos.append((parte.rstrip(".,:;"), m.start(), m.end()))
    return pedacos


def _casa(pedaco: str, alvo: str, primeiro: bool) -> bool:
    """O pedaço é o alvo. O primeiro do trecho aceita a unidade colada ("96MG/DL"),
    nunca outro número ("960") nem data ("22/10/2026")."""
    pedaco, alvo = pedaco.rstrip(".,:;"), alvo.rstrip(".,:;")
    if not alvo:
        return False
    if pedaco == alvo:
        return True
    return primeiro and pedaco.startswith(alvo) and (pedaco[len(alvo)].isalpha() or pedaco[len(alvo)] == "%")


def _trecho_na_linha(
    linha: layout_ocr.LinhaPosicionada, alvo: list[str], antes: str
) -> Optional[tuple[int, int]]:
    """
    Onde a sequência `alvo` (palavras normalizadas) está no texto original da
    linha. Se aparece mais de uma vez, vale a mesma ocorrência que a leitura
    usou: `antes` é o texto normalizado da linha até a posição lida, e conta
    quantas vezes o alvo já tinha aparecido.
    """
    if not alvo:
        return None
    pedacos = _pedacos(linha.texto)
    n = len(alvo)
    achados = [
        i for i in range(len(pedacos) - n + 1)
        if all(_casa(pedacos[i + j][0], alvo[j], j == 0) for j in range(n))
    ]
    if not achados:
        return None
    anteriores = sum(1 for t in antes.split() if _casa(t, alvo[0], True))
    i = achados[min(anteriores, len(achados) - 1)]
    return pedacos[i][1], pedacos[i + n - 1][2]


def _unidade_depois(p: Parametro, linha: layout_ocr.LinhaPosicionada, fim: int) -> int:
    """Estende o trecho do valor até a unidade, quando ela vem logo depois
    ("96" + "mg/dL"), para o destaque mostrar o resultado inteiro."""
    m = re.match(r"\s+(\S+)", linha.texto[fim:])
    if not m:
        return fim
    seguinte = normalizar(m.group(1))
    # Contagem: "/mm³", "céls/mm³", "mil/mm³", "mil".
    unidade = r"\S*/\S+|MIL|MM3" if p.milhar else p.unidade_rx
    if unidade and re.fullmatch(rf"(?:{unidade})[.,;]?", seguinte):
        return fim + m.end()
    return fim


def localizar_leitura(
    leitura: Leitura,
    norm: str,
    inicios: list[tuple[int, int]],
    linhas: dict[int, layout_ocr.LinhaPosicionada],
) -> Optional[dict[str, Any]]:
    """
    Página e caixas da leitura no PDF: o valor (com a unidade) e o nome do
    parâmetro, quando estão na mesma página. Sem caixa para a linha do valor
    (documento sem layout), None.
    """
    posicoes = [a for a, _ in inicios]

    def caixa(span: tuple[int, int], com_unidade: bool):
        k = bisect_right(posicoes, span[0]) - 1
        if k < 0:
            return None
        inicio_linha, indice = inicios[k]
        linha = linhas.get(indice)
        if linha is None:
            return None
        trecho = _trecho_na_linha(linha, norm[span[0]:span[1]].split(), norm[inicio_linha:span[0]])
        if trecho is None:
            # Não achou as palavras na linha original: destaca a linha inteira.
            return linha, linha.caixa
        a, b = trecho
        if com_unidade:
            b = _unidade_depois(PARAMETROS[leitura.chave], linha, b)
        return linha, layout_ocr.caixa_do_trecho(linha, a, b)

    valor = caixa(leitura.valor_em, True)
    if valor is None:
        return None
    linha_valor, caixa_valor = valor
    caixas = [layout_ocr.caixa_json(caixa_valor)]
    nome = caixa(leitura.nome_em, False)
    if nome is not None and nome[0].pagina == linha_valor.pagina and nome[1] != caixa_valor:
        caixas.append(layout_ocr.caixa_json(nome[1]))
    return {"pagina": linha_valor.pagina, "caixas": caixas}


# ---------------------------------------------------------------------------
# Classificação
# ---------------------------------------------------------------------------

def _fmt(n: Optional[float]) -> str:
    if n is None:
        return ""
    if n >= 1000:
        return f"{n:,.0f}".replace(",", ".")
    return (f"{n:.2f}".rstrip("0").rstrip(".")).replace(".", ",")


def texto_faixa(chave: str, faixa: Optional[FaixaLaudo]) -> str:
    p = PARAMETROS[chave]
    if p.qualitativo:
        return p.normal_texto
    if faixa is None:
        return "faixa não identificada no laudo"
    un = f" {p.unidade}" if p.unidade else ""
    if faixa.minimo is not None and faixa.maximo is not None:
        return f"{_fmt(faixa.minimo)} a {_fmt(faixa.maximo)}{un}"
    if faixa.maximo is None:
        return f"a partir de {_fmt(faixa.minimo)}{un}"
    return f"{'abaixo de' if faixa.teto_exclusivo else 'até'} {_fmt(faixa.maximo)}{un}"


def classificar(leitura: Leitura) -> str:
    p = PARAMETROS[leitura.chave]
    if p.qualitativo:
        return NORMAL if leitura.valor_texto.startswith(_QUALITATIVO_NORMAL) else ALTERADO
    faixa = leitura.faixa
    if faixa is None:
        return SEM_REFERENCIA
    if faixa.maximo is not None and (leitura.valor > faixa.maximo or (faixa.teto_exclusivo and leitura.valor == faixa.maximo)):
        return ACIMA
    if faixa.minimo is not None and leitura.valor < faixa.minimo:
        return ABAIXO
    return NORMAL


def parametros_do_exame(exame: str) -> tuple[str, ...]:
    """Parâmetros que o exame do BRNET traz. Vazio = exame sem valor numérico
    (clínico, audiometria, raio-X) ou fora da lista."""
    nome = normalizar(exame).replace("-", " ")
    for rx, chaves in _EXAME_PARAMETROS:
        if rx.search(nome):
            return chaves
    return ()


def avaliar_documento(
    markdown: str,
    tabela_comparacao: Iterable[dict[str, Any]],
    linhas: Optional[list[layout_ocr.LinhaPosicionada]] = None,
) -> list[dict[str, Any]]:
    """
    Para cada exame da Comparação Detalhada que tem parâmetro numérico, o valor
    lido de cada parâmetro e a situação. Exame faltante fica de fora: não há laudo
    para ler. A ordem é a da tabela.

    Com `linhas` (o layout do OCR já pareado com o markdown, ver `layout_ocr`),
    cada valor lido leva também `localizacao`: a página e as caixas do valor e
    do nome do parâmetro, para a checagem levar até ele no PDF.
    """
    leituras, norm, inicios = _ler(markdown or "")
    por_indice = {l.linha_markdown: l for l in linhas or []}
    itens = []
    for item in tabela_comparacao or []:
        if not isinstance(item, dict) or item.get("status") not in ("encontrado", "parcialmente_encontrado"):
            continue
        chaves = parametros_do_exame(item.get("exame") or "")
        if not chaves:
            continue
        parametros = []
        for k in chaves:
            p = PARAMETROS[k]
            lida = leituras.get(k)
            if lida is None and p.opcional:
                continue
            parametros.append({
                "chave": k,
                "nome": p.nome,
                "unidade": p.unidade,
                "valor": lida.valor if lida else None,
                "valor_texto": lida.valor_texto if lida else None,
                "referencia": texto_faixa(k, lida.faixa if lida else None),
                "situacao": classificar(lida) if lida else SEM_RESULTADO,
                "localizacao": localizar_leitura(lida, norm, inicios, por_indice) if lida and por_indice else None,
            })
        if not parametros:
            # Exame só de opcionais (toxicológico) sem nada lido: uma linha avisando,
            # para não parecer exame sem resultado a ler ("Não se aplica").
            p = PARAMETROS[chaves[0]]
            parametros.append({
                "chave": f"{chaves[0]}_sem_leitura", "nome": "Resultado", "unidade": "", "valor": None,
                "valor_texto": None, "referencia": p.normal_texto, "situacao": SEM_RESULTADO, "localizacao": None,
            })
        itens.append({"exame": item.get("exame"), "parametros": parametros})
    return itens
