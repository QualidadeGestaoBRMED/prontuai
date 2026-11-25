"""
Achados do EXAME FÍSICO da ficha médica, lidos do texto de OCR (sem LLM, sem rede). Pedido do Breno (23/11): fonte de
encaminhamento sem exame complementar (angiologia, dermatologia, ortopedia, clínica).

    ler(texto_entrada) -> {"exame_fisico": "normal" | "alterado" | None, "exame_fisico_achados": "varizes|sopro" | ""}

None = não há seção "Exame físico" no texto.
- Janela: da linha "EXAME FÍSICO" até "Sinais vitais", "Observações", outra página ou 25 linhas.
- A ficha da BR MED é um modelo de frases normais, todas negadas ("Membros inferiores sem alterações anatômicas. Não
  foram observados edemas..."); o achado aparece quando a frase foge do modelo. Cada frase (até ponto/ponto e vírgula)
  é lida por sistema; termo depois de SEM / NÃO FORAM OBSERVADOS / AUSÊNCIA / NEGATIVO na mesma frase não conta.
- "Cicatriz umbilical centrada" é do modelo do abdome, não lesão de pele.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", t).strip().lstrip("#*>| ").strip()


_INICIO = re.compile(r"^EXAME FISICO\b")
_FIM = re.compile(r"^(?:SINAIS VITAIS|OBSERVAC|PRESSAO SISTOLICA|<!--|CONCLUS|ASSINATURA|RESULTADO|APTO\b|INAPTO\b|DADOS DO)")
# Conduta escrita no meio do exame ("Sugiro consulta com nutricionista", "Encaminho ao angiologista", "Oriento"): é o
# RÓTULO e não pode virar feature — o texto da seção é cortado antes dela.
_CONDUTA = re.compile(r"SUGIR\w*|SUGEST\w* (?:DE )?(?:CONSULTA|AVALIACAO|ACOMPANHAMENTO)|ENCAMINH\w*|ORIENT\w*|RECOMEND\w*|SOLICIT\w*"
                      r"|PROCURAR|CONDUTA|AVALIACAO COM|ACOMPANHAMENTO COM|REAVALIA")
JANELA = 25

# Termos que NÃO estão no modelo de frases normais: contam se não negados.
_FORTES = {k: re.compile(v) for k, v in {
    "varizes_edema": r"VARIZ|VARICOS|TELANGIECT|EMPASTAMENTO|MICROVARIZ",
    "pele": r"MANCHA|DERMAT(?!OSCOP)|MICOSE|VITILIGO|PSORIASE|ULCERA|\bNEVOS?\b|QUELOIDE|\bACNE\b|ERITEMA",
    "cardiovascular": r"ARRITMI|BULHAS? (?:HIPO|ARRITM|IRREGULAR)|TAQUICARD|BRADICARD|EXTRASSIST|SOPRO (?:SISTOLICO|DIASTOLICO|\+|EM FOCO)",
    "respiratorio": r"\bSIBIL|ESTERTOR|CREPITA\w* (?:PULMONAR|INSPIRAT|EM BASES?|BIBASAL|FINAS|GROSSAS)|\bRONCOS?\b|MV (?:DIMINUIDO|REDUZIDO)|MURMURIO (?:VESICULAR )?DIMINUIDO",
    "abdome": r"\bHERNIA\b|HEPATOMEGAL|ESPLENOMEG|DOLOROS|DOR A PALPACAO|VISCEROMEGAL|DIASTASE",
    "osteoarticular": r"\bDOR\b|ESCOLIOSE|AMPUTA|ARTROSE|CREPITA\w* (?:A |NA |AO |EM )?(?:EXTENS|FLEX|MOVIMENT|ARTICUL|JOELHO|OMBRO|PALPA)|ATROFIA|HIPERCIFOSE|HIPERLORDOSE",
    "cervical": r"NODULO|BOCIO|TIREOIDE AUMENTAD|LINFONOD|ADENOMEGAL",
    "neurologico": r"ROMBERG (?:POSITIVO|ALTERADO)|\bTREMOR|NISTAGMO|PARESIA|PARESTESIA",
    "estado_geral": r"DESCORAD|DESIDRATAD|REGULAR ESTADO|MAU ESTADO|\bOBES[OA]\b|OBESIDADE",
}.items()}
# Termos do PRÓPRIO modelo ("não foram identificados lesões, tumorações ou cicatrizes", "ausência de sopros", "massas ou
# abaulamentos", "edemas", "deformidades ou limitação"): o OCR embaralha a negação ("NAO FOIEM", "AUSDNCIA", "5EM") e
# reordena as linhas. Só contam com marca positiva na mesma frase.
_FRACOS = {k: re.compile(v) for k, v in {
    "varizes_edema": r"EDEMA|INSUFICIENCIA VENOSA",
    "pele": r"LESA?O|LESOES|TUMORAC|(?<!UMBILICAL )CICATRIZ(?! UMBILICAL)",
    "cardiovascular": r"SOPRO",
    "abdome": r"ABAULAMENTO",
    "osteoarticular": r"DEFORMIDADE|LIMITACAO",
    "cervical": r"(?<!A )MASSAS?\b(?! MUSCULAR)",
}.items()}
_POSITIVO = re.compile(r"\bAPRESENTA\w*|PRESENCA DE|OBSERVA-SE|NOTA-SE|IDENTIFICAD[OA] (?!LES)|\bCOM (?!AUSENCIA)|PRESENTES?\b|EVIDENCIA-SE")


_NEGA = re.compile(r"\bSEM\b|NAO (?:FORAM|SE|HA|APRESENTA)\w*|AUSENCIA|AUSENTES?\b|NEGATIV|NENHUM|INEXIST|\bNEGA\b|LIVRES?\b|PRESERVAD")
_QUEBRA = re.compile(r"\bCOM\b|\bPOREM\b|\bMAS\b|OBSERVA-SE|NOTA-SE|PRESENCA DE|APRESENTA\b")


def _afirmado(frase: str, ini: int) -> bool:
    antes = frase[:ini]
    nega = list(_NEGA.finditer(antes))
    return not nega or bool(_QUEBRA.search(antes[nega[-1].end():]))


def ler(texto_entrada: str) -> dict:
    linhas = [n for n in (_norm(l) for l in (texto_entrada or "").splitlines()) if n]
    secoes = []
    for i, l in enumerate(linhas):
        if _INICIO.match(l):
            sec = []
            for x in linhas[i + 1:i + 1 + JANELA]:
                if _FIM.match(x) or _INICIO.match(x):
                    break
                sec.append(x)
            if sec:
                texto = " ".join(sec)
                c = _CONDUTA.search(texto)
                secoes.append(texto[:c.start()] if c else texto)
    if not secoes:
        return {"exame_fisico": None, "exame_fisico_achados": ""}
    achados = set()
    for texto in secoes:
        # Negação depois do termo: "Arritmias e distúrbios da condução: NÃO APRESENTOU", "Edema: ausente".
        texto = re.sub(r"[^.;:]{0,70}:\s*(?:NAO|AUSENTES?|NEGATIV\w*|NENHUM\w*)\b", " ", texto)
        for frase in re.split(r"[.;]\s*", texto):
            for nome, rx in _FORTES.items():
                if any(_afirmado(frase, m.start()) for m in rx.finditer(frase)):
                    achados.add(nome)
            for nome, rx in _FRACOS.items():
                for m in rx.finditer(frase):
                    pos = list(_POSITIVO.finditer(frase[:m.start()]))
                    if pos and _afirmado(frase[pos[-1].start():], m.start() - pos[-1].start()):
                        achados.add(nome)
                        break
    return {"exame_fisico": "alterado" if achados else "normal", "exame_fisico_achados": "|".join(sorted(achados))}
