"""
Normalidade e alteração de exames de laboratório.

Lê no markdown do OCR o resultado de cada parâmetro (glicose, HbA1c, hemoglobina,
plaquetas...) e compara com a faixa de referência. O resultado é só informativo:
não muda status, faltantes, confiança nem validation_status. A tela da checagem
mostra os valores numa coluna da Comparação Detalhada.

A faixa NÃO é a impressa no laudo: cada laboratório imprime a sua, e o OCR
embaralha a tabela. Vale a faixa cadastrada aqui (padrão no código, ajuste na
tabela `faixas_normalidade`), igual para todos os documentos.

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
from dataclasses import dataclass
from typing import Any, Iterable, Optional

# Desliga a leitura sem deploy de código: NORMALIDADE_EXAMES=false.
HABILITADA = os.getenv("NORMALIDADE_EXAMES", "true").strip().lower() not in ("0", "false", "nao", "no")

NORMAL = "normal"
ACIMA = "acima"
ABAIXO = "abaixo"
# Qualitativo fora do normal (VDRL reagente): não tem lado.
ALTERADO = "alterado"
# Parâmetro do exame sem valor legível no PDF.
SEM_RESULTADO = "sem_resultado"

JANELA = 160


@dataclass(frozen=True)
class Parametro:
    chave: str
    nome: str
    unidade: str
    # Como o nome aparece no laudo, já normalizado (sem acento, maiúsculo).
    nomes: tuple[str, ...]
    padrao_min: Optional[float] = None
    padrao_max: Optional[float] = None
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


# Faixas padrão de adulto. Ponto de partida para a staging: quem decide o
# critério ocupacional ajusta na tela de Normalidade, sem deploy.
PARAMETROS: dict[str, Parametro] = {p.chave: p for p in (
    Parametro("glicemia", "Glicose em jejum", "mg/dL",
              ("GLICEMIA DE JEJUM", "GLICEMIA EM JEJUM", "GLICOSE DE JEJUM", "GLICOSE EM JEJUM", "GLICEMIA", "GLICOSE"),
              70, 99, unidade_rx=r"MG\s?/\s?DL", plausivel=(20, 1000),
              exclui=("MEDIA", "ESTIMADA", "POS", "NA URINA", "URINA", "1 HORA", "2 HORAS")),
    Parametro("hba1c", "Hemoglobina glicada (HbA1c)", "%",
              ("HEMOGLOBINA GLICADA", "HBA1C", "HB A1C", "HB ALC", "HBALC", "A1C"),
              None, 5.6, unidade_rx=r"%", plausivel=(3, 20)),
    Parametro("colesterol", "Colesterol total", "mg/dL",
              ("COLESTEROL TOTAL", "COLESTROL TOTAL"),
              None, 189, unidade_rx=r"MG\s?/\s?DL", plausivel=(50, 1000)),
    Parametro("triglic", "Triglicerídeos", "mg/dL",
              ("TRIGLICERIDEOS", "TRIGLICERIDES", "TRIGLICERIDIOS"),
              None, 149, unidade_rx=r"MG\s?/\s?DL", plausivel=(10, 5000)),
    Parametro("creatinina", "Creatinina", "mg/dL",
              ("CREATININA",),
              0.7, 1.3, unidade_rx=r"MG\s?/\s?DL", plausivel=(0.1, 20),
              exclui=("NA URINA", "URINARIA", "CLEARANCE")),
    Parametro("ureia", "Ureia", "mg/dL",
              ("UREIA",),
              15, 45, unidade_rx=r"MG\s?/\s?DL", plausivel=(2, 400),
              exclui=("NA URINA", "URINARIA")),
    Parametro("tgo", "TGO (AST)", "U/L",
              ("ASPARTATO AMINOTRANSFERASE", "TRANSAMINASE OXALACETICA", "TGO", "AST"),
              None, 40, unidade_rx=r"U\s?/\s?L", plausivel=(1, 5000)),
    Parametro("tgp", "TGP (ALT)", "U/L",
              ("ALANINA AMINOTRANSFERASE", "TRANSAMINASE PIRUVICA", "TGP", "ALT"),
              None, 41, unidade_rx=r"U\s?/\s?L", plausivel=(1, 5000)),
    Parametro("ggt", "Gama GT", "U/L",
              ("GAMA GLUTAMIL TRANSFERASE", "GAMA GLUTAMILTRANSFERASE", "GAMA-GT", "GAMA GT", "GGT"),
              None, 60, unidade_rx=r"U\s?/\s?L", plausivel=(1, 5000)),
    Parametro("hemoglobina", "Hemoglobina", "g/dL",
              ("HEMOGLOBINA",),
              12, 17.5, unidade_rx=r"G\s?/\s?DL|G\s?%", plausivel=(3, 25),
              exclui=("GLICADA", "CORPUSCULAR", "VARIANTE", "FETAL", "A1C"), exclui_antes=("CONCENTRACAO", "CONC.")),
    Parametro("leucocitos", "Leucócitos", "/mm³",
              ("LEUCOCITOS", "GLOBULOS BRANCOS"),
              4000, 11000, milhar=True, plausivel=(500, 200000)),
    Parametro("plaquetas", "Plaquetas", "/mm³",
              ("PLAQUETAS",),
              150000, 450000, milhar=True, plausivel=(5000, 2000000)),
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


def _valor_numerico(p: Parametro, jan: str) -> Optional[tuple[float, str]]:
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
        return (valor, texto) if lo <= valor <= hi else None
    for m in re.finditer(rf"{_NUMERO}\s*(?:{p.unidade_rx})", jan):
        if _referencia_antes(jan, m.start()):
            continue
        valor = _numero(m.group(1))
        return (valor, m.group(1)) if lo <= valor <= hi else None
    return None


def _valor_qualitativo(jan: str) -> Optional[str]:
    # Quando a janela tem "RESULTADO", a resposta vem depois dele; antes pode
    # estar a faixa ("Valor de referência: Não reagente").
    pos = jan.find("RESULTADO")
    m = _QUALITATIVO.search(jan, pos if pos >= 0 else 0)
    if not m:
        return None
    titulo = (m.group(2) or "").strip()
    palavra = m.group(1).replace("-", " ")
    texto = {"NAO REAGENTE": "Não reagente", "NEGATIVO": "Negativo", "REAGENTE": "Reagente", "POSITIVO": "Positivo"}[palavra]
    return f"{texto} {titulo}".strip()


@dataclass
class Leitura:
    chave: str
    nome: str
    unidade: str
    valor: Optional[float]
    valor_texto: str


def ler_valores(markdown: str) -> dict[str, Leitura]:
    """O primeiro resultado legível de cada parâmetro no documento."""
    norm = re.sub(r" {2,}", " ", _DATA.sub(" ", normalizar(markdown)))
    fronteiras = [m.start() for m in _RX_FRONTEIRA.finditer(norm)]
    leituras: dict[str, Leitura] = {}
    for chave, p in PARAMETROS.items():
        for m in _RX_NOME[chave].finditer(norm):
            if p.exclui_antes and norm[max(0, m.start() - 20):m.start()].rstrip().endswith(p.exclui_antes):
                continue
            ini = m.end()
            proxima = next((f for f in fronteiras if f >= ini), len(norm))
            jan = norm[ini:min(ini + JANELA, proxima)]
            if p.qualitativo:
                texto = _valor_qualitativo(jan)
                if texto:
                    leituras[chave] = Leitura(chave, p.nome, p.unidade, None, texto)
                    break
                continue
            achado = _valor_numerico(p, jan)
            if achado:
                leituras[chave] = Leitura(chave, p.nome, p.unidade, achado[0], achado[1])
                break
    return leituras


# ---------------------------------------------------------------------------
# Faixas e classificação
# ---------------------------------------------------------------------------

def faixas_efetivas(ajustes: Optional[dict[str, dict[str, Any]]] = None) -> dict[str, tuple[Optional[float], Optional[float]]]:
    """Faixa de cada parâmetro numérico: o ajuste gravado, senão o padrão."""
    ajustes = ajustes or {}
    out = {}
    for k, p in PARAMETROS.items():
        if p.qualitativo:
            continue
        a = ajustes.get(k)
        out[k] = (a["minimo"], a["maximo"]) if a else (p.padrao_min, p.padrao_max)
    return out


def _fmt(n: Optional[float]) -> str:
    if n is None:
        return ""
    if n >= 1000:
        return f"{n:,.0f}".replace(",", ".")
    return (f"{n:.2f}".rstrip("0").rstrip(".")).replace(".", ",")


def texto_faixa(chave: str, faixa: tuple[Optional[float], Optional[float]] | None) -> str:
    p = PARAMETROS[chave]
    if p.qualitativo:
        return p.normal_texto
    mn, mx = faixa or (None, None)
    un = f" {p.unidade}" if p.unidade else ""
    if mn is not None and mx is not None:
        return f"{_fmt(mn)} a {_fmt(mx)}{un}"
    if mx is not None:
        return f"até {_fmt(mx)}{un}"
    if mn is not None:
        return f"a partir de {_fmt(mn)}{un}"
    return "sem faixa"


def classificar(leitura: Leitura, faixa: tuple[Optional[float], Optional[float]] | None) -> str:
    p = PARAMETROS[leitura.chave]
    if p.qualitativo:
        return NORMAL if leitura.valor_texto.startswith(("Não reagente", "Negativo")) else ALTERADO
    mn, mx = faixa or (None, None)
    if mx is not None and leitura.valor > mx:
        return ACIMA
    if mn is not None and leitura.valor < mn:
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
    ajustes: Optional[dict[str, dict[str, Any]]] = None,
) -> list[dict[str, Any]]:
    """
    Para cada exame da Comparação Detalhada que tem parâmetro numérico, o valor
    lido de cada parâmetro e a situação. Exame faltante fica de fora: não há laudo
    para ler. A ordem é a da tabela.
    """
    leituras = ler_valores(markdown or "")
    faixas = faixas_efetivas(ajustes)
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
            faixa = faixas.get(k)
            lida = leituras.get(k)
            parametros.append({
                "chave": k,
                "nome": p.nome,
                "unidade": p.unidade,
                "valor": lida.valor if lida else None,
                "valor_texto": lida.valor_texto if lida else None,
                "referencia": texto_faixa(k, faixa),
                "situacao": classificar(lida, faixa) if lida else SEM_RESULTADO,
            })
        itens.append({"exame": item.get("exame"), "parametros": parametros})
    return itens
