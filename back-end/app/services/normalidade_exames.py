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
  "148.000") ou seguido de unidade por mm³/µL. Sem isso, o "CRM 1639" e o ano
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

from app.services import layout_ocr

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


PARAMETROS: dict[str, Parametro] = {p.chave: p for p in (
    Parametro("glicemia", "Glicose em jejum", "mg/dL",
              ("GLICEMIA DE JEJUM", "GLICEMIA EM JEJUM", "GLICOSE DE JEJUM", "GLICOSE EM JEJUM", "GLICEMIA", "GLICOSE"),
              (40, 100), (80, 140), unidade_rx=r"MG\s?/\s?DL", plausivel=(20, 1000),
              exclui=("MEDIA", "ESTIMADA", "POS", "NA URINA", "URINA", "1 HORA", "2 HORAS")),
    Parametro("hba1c", "Hemoglobina glicada (HbA1c)", "%",
              ("HEMOGLOBINA GLICADA", "HBA1C", "HB A1C", "HB ALC", "HBALC", "A1C"),
              (3, 5), (5, 7.5), unidade_rx=r"%", plausivel=(3, 20)),
    Parametro("colesterol", "Colesterol total", "mg/dL",
              ("COLESTEROL TOTAL", "COLESTROL TOTAL"),
              (0, 150), (150, 240), unidade_rx=r"MG\s?/\s?DL", plausivel=(50, 1000)),
    Parametro("triglic", "Triglicerídeos", "mg/dL",
              ("TRIGLICERIDEOS", "TRIGLICERIDES", "TRIGLICERIDIOS"),
              (0, 100), (100, 200), unidade_rx=r"MG\s?/\s?DL", plausivel=(10, 5000)),
    Parametro("creatinina", "Creatinina", "mg/dL",
              ("CREATININA",),
              (0.3, 1.1), (0.8, 1.7), unidade_rx=r"MG\s?/\s?DL", plausivel=(0.1, 20),
              exclui=("NA URINA", "URINARIA", "CLEARANCE")),
    Parametro("ureia", "Ureia", "mg/dL",
              ("UREIA",),
              (5, 30), (30, 80), unidade_rx=r"MG\s?/\s?DL", plausivel=(2, 400),
              exclui=("NA URINA", "URINARIA")),
    Parametro("tgo", "TGO (AST)", "U/L",
              ("ASPARTATO AMINOTRANSFERASE", "TRANSAMINASE OXALACETICA", "TGO", "AST"),
              (0, 20), (20, 70), unidade_rx=r"U\s?/\s?L", plausivel=(1, 5000)),
    Parametro("tgp", "TGP (ALT)", "U/L",
              ("ALANINA AMINOTRANSFERASE", "TRANSAMINASE PIRUVICA", "TGP", "ALT"),
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
)}

# Nomes que encerram a janela de um parâmetro: o próximo analito do laudo. Inclui
# os próprios parâmetros e os vizinhos que têm número com a mesma unidade (CHCM
# em g/dL, HDL em mg/dL, glicose média estimada da HbA1c).
_FRONTEIRA_EXTRA = (
    "ERITROCITOS", "HEMACIAS", "HEMATOCRITO", "VCM", "HCM", "CHCM", "RDW", "VPM", "PLAQUETOCRITO",
    "NEUTROFILOS", "SEGMENTADOS", "BASTONETES", "LINFOCITOS", "MONOCITOS", "EOSINOFILOS", "BASOFILOS",
    "HDL", "LDL", "VLDL", "NAO HDL", "LIPIDEOS TOTAIS", "GLICEMIA ESTIMADA", "GLICOSE MEDIA", "HB A1A", "HB A1B", "HB ALA", "HB ALB",
    "CONCENTRACAO DE HEMOGLOBINA",
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
    (re.compile(r"\bHEMOGRAMA\b"), ("hemoglobina", "leucocitos", "plaquetas")),
    (re.compile(r"\bLIPIDOGRAMA\b|\bPERFIL LIPIDICO\b|\bCOLESTEROL TOTAL E FRACOES\b"), ("colesterol", "triglic")),
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
# "MILHOES/MM3") nem começo ("52.012" de "CRM 52.0123237-1").
_NUMERO = r"(?<![A-Z0-9/.,])(\d{1,3}(?:\.\d{3})+|\d+(?:[.,]\d+)?)(?![0-9]|[.,][0-9])"
_MILHAR = re.compile(r"\d{1,3}(?:\.\d{3})+")
# Unidade de contagem no sangue. "/ML" (por mililitro) é do sedimento urinário.
_UNIDADE_CONTAGEM = re.compile(r"\s*(?:/?\s?MM\s?3|/\s?MM\b|/\s?UL|/\s?L\b|/\s?CMM)")
# Palavra imediatamente antes do número que o torna texto de referência.
_ANTES_REFERENCIA = {
    "A", "ATE", "DE", "QUE", "E", "MAIOR", "MENOR", "IGUAL", "INFERIOR", "SUPERIOR", "ACIMA", "ABAIXO",
    "ENTRE", "<", ">", "<=", ">=", "-",
}
# Comparação um pouco antes do número: "estão acima de [...] 800 mg/dL" é nota
# do laboratório, com o OCR embaralhando a ordem das palavras.
_COMPARACAO_PERTO = {"ACIMA", "ABAIXO", "MAIOR", "MENOR", "SUPERIOR", "INFERIOR", "IGUAL", "ATE", "ENTRE", "QUANDO"}
_QUALITATIVO = re.compile(r"\b(NAO REAGENTE|NAO-REAGENTE|NEGATIVO|REAGENTE|POSITIVO)\b(\s+\d+/\d+)?")


def normalizar(texto: str) -> str:
    """Sem acento, maiúsculo, espaço simples. Mantém dígitos, vírgula, ponto, "%",
    "/", "-" e "<>" (fazem parte de valor, unidade e faixa)."""
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().upper()
    texto = texto.replace("³", "3")
    return re.sub(r"[^A-Z0-9,.%/<>\-]+", " ", texto).strip()


def _numero(texto: str) -> float:
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", texto):
        return float(texto.replace(".", ""))
    return float(texto.replace(",", "."))


def _regex_nomes(nomes: Iterable[str]) -> str:
    alts = sorted({n for n in nomes}, key=len, reverse=True)
    return "|".join(re.escape(n).replace(r"\ ", r"\s+") for n in alts)


def _compilar(p: Parametro) -> re.Pattern:
    exclui = "".join(f"(?!\\s*{re.escape(e)})" for e in p.exclui)
    return re.compile(rf"(?<![A-Z0-9\-])(?:{_regex_nomes(p.nomes)})(?![A-Z0-9]){exclui}")


_RX_NOME = {k: _compilar(p) for k, p in PARAMETROS.items()}
_RX_FRONTEIRA = re.compile(
    rf"(?<![A-Z0-9\-])(?:{_regex_nomes([n for p in PARAMETROS.values() for n in p.nomes] + list(_FRONTEIRA_EXTRA))})(?![A-Z0-9])"
)


def _palavra_antes(texto: str, fim: int) -> str:
    m = re.search(r"(\S+)\s*$", texto[:fim])
    return m.group(1).rstrip(":") if m else ""


def _referencia_antes(jan: str, inicio: int) -> bool:
    antes = _palavra_antes(jan, inicio)
    if antes in _ANTES_REFERENCIA or re.fullmatch(r"[\d.,]+", antes):
        return True
    return bool(_COMPARACAO_PERTO.intersection(jan[:inicio].split()[-3:]))


def _valor_numerico(p: Parametro, jan: str) -> Optional[tuple[float, str, int, int]]:
    """(valor, como exibir, início e fim do número na janela)."""
    lo, hi = p.plausivel
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
        valor = _numero(m.group(1))
        return (valor, m.group(1), m.start(1), m.end(1)) if lo <= valor <= hi else None
    return None


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
_RX_SEXO = re.compile(r"\bSEXO\s*(MASCULINO|FEMININO|M|F)\b")
_RX_ADULTO = re.compile(r"\bADULTOS?\b(?:\s+(?:ACIMA|MAIOR(?:ES)?)\s+DE\s+\d+\s+ANOS)?")


def _sexo_do_documento(norm: str) -> Optional[str]:
    """Sexo impresso no laudo. Fica no processo: não vai para log nem para fora."""
    m = _RX_SEXO.search(norm)
    return m.group(1)[0] if m else None


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


def _faixa_do_laudo(p: Parametro, depois: str, sexo: Optional[str]) -> Optional[FaixaLaudo]:
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
    homem, mulher = _RX_HOMEM.search(texto), _RX_MULHER.search(texto)
    if homem or mulher:
        proprio, outro = (homem, mulher) if sexo == "M" else (mulher, homem) if sexo == "F" else (None, None)
        if not proprio:
            return None
        fim = outro.start() if outro and outro.start() > proprio.start() else len(texto)
        texto = texto[proprio.end():fim]
    classe = _RX_OUTRA_CLASSE.search(texto)
    if classe:
        texto = texto[:classe.start()]

    candidatos = [m for m in (_RX_INTERVALO.search(texto), _RX_TETO.search(texto), _RX_PAR.search(texto)) if m]
    if not candidatos:
        return None
    m = min(candidatos, key=lambda c: c.start())
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


def _valor_qualitativo(jan: str) -> Optional[tuple[str, int, int]]:
    """(como exibir, início e fim do resultado na janela)."""
    # Quando a janela tem "RESULTADO", a resposta vem depois dele; antes pode
    # estar a faixa ("Valor de referência: Não reagente").
    pos = jan.find("RESULTADO")
    m = _QUALITATIVO.search(jan, pos if pos >= 0 else 0)
    if not m:
        return None
    titulo = (m.group(2) or "").strip()
    palavra = m.group(1).replace("-", " ")
    texto = {"NAO REAGENTE": "Não reagente", "NEGATIVO": "Negativo", "REAGENTE": "Reagente", "POSITIVO": "Positivo"}[palavra]
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
        trecho = re.sub(r" {2,}", " ", _DATA.sub(" ", normalizar(linha))).strip()
        if not trecho:
            continue
        if partes:
            tamanho += 1  # o espaço que junta as linhas
        inicios.append((tamanho, indice))
        partes.append(trecho)
        tamanho += len(trecho)
    return " ".join(partes), inicios


def _ler(markdown: str) -> tuple[dict[str, Leitura], str, list[tuple[int, int]]]:
    norm, inicios = _texto_normalizado(markdown)
    fronteiras = [m.start() for m in _RX_FRONTEIRA.finditer(norm)]
    sexo = _sexo_do_documento(norm)
    leituras: dict[str, Leitura] = {}
    for chave, p in PARAMETROS.items():
        for m in _RX_NOME[chave].finditer(norm):
            if p.exclui_antes and norm[max(0, m.start() - 20):m.start()].rstrip().endswith(p.exclui_antes):
                continue
            ini = m.end()
            proxima = next((f for f in fronteiras if f >= ini), len(norm))
            jan = norm[ini:min(ini + JANELA, proxima)]
            if p.qualitativo:
                achado = _valor_qualitativo(jan)
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
                leituras[chave] = Leitura(chave, p.nome, p.unidade, valor, texto, m.span(), (ini + a, fim_valor), faixa)
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
        return "não lida no laudo"
    un = f" {p.unidade}" if p.unidade else ""
    if faixa.minimo is not None and faixa.maximo is not None:
        return f"{_fmt(faixa.minimo)} a {_fmt(faixa.maximo)}{un}"
    return f"{'abaixo de' if faixa.teto_exclusivo else 'até'} {_fmt(faixa.maximo)}{un}"


def classificar(leitura: Leitura) -> str:
    p = PARAMETROS[leitura.chave]
    if p.qualitativo:
        return NORMAL if leitura.valor_texto.startswith(("Não reagente", "Negativo")) else ALTERADO
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
        itens.append({"exame": item.get("exame"), "parametros": parametros})
    return itens
