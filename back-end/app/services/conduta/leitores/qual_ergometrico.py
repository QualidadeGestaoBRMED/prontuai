"""
Laudo de TESTE ERGOMÉTRICO lido do texto de OCR do prontuário (regex, sem LLM, sem rede). STC-1065, 23/11.

Saída de ler(texto_entrada):
  ergometrico_laudo                "descritivo" | None   (None: nenhum laudo de ergométrico no texto)
  ergometrico                      "normal" | "isquemia" | "arritmia" | "ineficaz" | "alterado_outro" | None
  ergometrico_mets                 float | None          (maior MET atingido escrito no laudo)
  ergometrico_resposta_pressorica  "normal" | "hipertensiva" | "hipotensiva" | None

Regras (medidas numa amostra de 400 da base de 10 mil):
- Janela: linha de título (TESTE ERGOMÉTRICO, ERGOMETRIA, TESTE DE ESFORÇO, laudo Heartware "CONCLUSÕES FINAIS")
  até o título de outro exame/ASO ou 70 linhas. Item da lista de procedimentos do ASO ("TESTE ERGOMÉTRICO -
  15/09/2025", "ERGOMETRIC STRESS TEST") não abre janela. Só é laudo a janela com corpo de laudo (segmento ST,
  arritmias, resposta pressórica/cronotrópica, isquemia, protocolo, FC máxima, interrupção do esforço).
- Frases de objetivo do exame ("* detectar alterações sugestivas de isquemia", "* avaliar arritmias induzidas
  pelo exercício") e perguntas de anamnese nunca contam.
- Negação: "achados sugestivos de isquemia: AUSENTES", "sem evidências de isquemia", "ausência de arritmias",
  "não apresentou alterações ... sugestivas de isquemia", "presença de arritmias malignas: AUSENTE". O campo
  Heartware "RÓTULO: AUSENTE|PRESENTE" é lido pelo valor (o rótulo pode estar numa linha e o valor na seguinte).
- Conclusão, em ordem de precedência: isquemia (afirmada: "sugestivo de isquemia", "teste positivo",
  infra/supradesnivelamento de ST isquêmico, "achados sugestivos de isquemia: presentes") > arritmia
  (extrassístoles, taquicardia, fibrilação/flutter, BAV, "arritmias: presentes") > alterado_outro (resposta
  pressórica anormal, déficit/incompetência cronotrópica declarada, distúrbio de condução/pré-excitação,
  sintoma limitante) > ineficaz ("ineficaz", "inconclusivo", "não atingiu a FC submáxima") > normal.
- METs: maior valor "X MET(S)" do laudo — linhas de estágio "VO2: ... (9,8 MET)", "MET MÁXIMO 10,5". Não contam
  a velocidade da rampa ("1,2 MET/MIN"), o "MMHG/MET", a "faixa de METs (Clinimex questionnaire)" nem
  "metanfetamina (MET)". Fora de 1 a 25 é ruído do OCR.
- Resposta pressórica: "fisiológica/normal/adequada", "comportamento normal da pressão" -> normal;
  "hipertensão reacional", "resposta pressórica exacerbada/hipertensiva" afirmada (Heartware: algum dos
  "sisto-diastólica / sistólica isolada / diastólica isolada: PRESENTE") -> hipertensiva; "hipotensão",
  "queda da pressão", "resposta deprimida/em platô" -> hipotensiva.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Optional


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", t).strip().lstrip("#*>| ").strip()


_TITULO = re.compile(r"TESTE ERGOMETRICO|TESTE DE ESFORCO|ERGOMETRIA\b|^ERGOMETRICO$|^CONCLUSOES FINAIS|ERGOESPIROMETRIA"
                     r"|ELETROCARDIOGRAMA DE ESFORCO|TESTE CARDIOPULMONAR")
_DATA = re.compile(r"\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{2,4}")
_NAO_TITULO = re.compile(r"\?|STRESS TEST|ERGOMETRIC\b|PROCEDIMENTOS|EXAMES COMPLEMENTARES|PREPARO|ORIENTAC|AGENDA|SOLICIT"
                         r"|ESTEIRA ERGOMETRICA|BICICLETA ERGOMETRICA")
_FIM = re.compile(r"^(?:#+ )?(?:AUDIOMETR|AVALIACAO AUDIOLOG|ACUIDADE VISUAL|ESPIROMETR|HEMOGRAMA|RADIOGRAF|ELETROENCEFALO"
                  r"|AVALIACAO PSICO|AVALIACAO ODONTO|ATESTADO DE SAUDE|FICHA MEDICA|FICHA CLINICA|ANAMNESE|GLICEMIA"
                  r"|EXAME CLINICO|QUESTIONARIO|DECLARACAO|PARECER AUDIOLOG|LAUDO PSICO|URINA|EAS\b|PARASITOLOG)"
                  r"|CONCLUSAO ?/ ?CONCLUSION|APTO ?/ ?FIT")
JANELA = 70
_CORPO = re.compile(r"SEGMENTO ST|PONTO J|\bST\b|ARRITMI|EXTRASSIST|PRESSORICA|CRONOTROPICA|ISQUEMI|PROTOCOLO|BRUCE|ELLESTAD"
                    r"|RAMPA|FC MAXIMA|FREQUENCIA CARDIACA MAXIMA|INTERRUP|ESFORCO|\bMETS?\b|VO2|DUPLO PRODUTO|CAPACIDADE FUNCIONAL")
# Objetivo do exame, pergunta de anamnese, legenda: nunca é resultado.
_FORA = re.compile(r"^\W*\*|\?|DETECTAR|AVALIAR|ESTIMAR|OBJETIVO|INDICACAO|HISTORIA|ANTECEDENTE|VOCE|JA TEVE"
                   r"|CONSTITUCIONAIS|POPULACAO NORMAL|INTERPRETACAO DOS RESULTADOS|ATOS MEDICOS"
                   # termo de consentimento / critérios de interrupção impressos
                   r"|RARAMENTE|COMPLICAC|PODEM OCORRER|RISCOS?\b|SINTOMAS IMPORTANTES|MAL-ESTAR\)|CRITERIOS? DE INTERRUP"
                   r"|DESCR\w* DO PROCED|SERA REALIZADO")
# Rótulo sozinho ("ARRITMIAS", "ARRITMIAS CARDIACAS:"): o valor vem na linha seguinte.
_ROTULO_SO = re.compile(r"\W*(?:ARRITMIAS?(?: CARDIACAS)?|EXTRA ?SS?ISTOLES?(?: (?:SUPRA)?VENTRICULARES)?|ISQUEMIA)\W*")

_NEGA = re.compile(r"\bSEM\b|AUSENCIA|AUSENTES?\b|\bNAO\b|\bNO APRESENTOU|NEGATIV|NENHUM|INEXIST|LIVRE|NORMAL|FISIOLOGIC|DIGNA DE NOTA"
                   r"|AFASTAD|DESCARTAD")
_PRESENTE = re.compile(r"[:;]\s*PRESENTES?\b|\bPRESENTES?$|[:;]\s*SIM\b")
_AUSENTE = re.compile(r"^\W*(?:AUS\w{2,5}|NAO|NENHUMA?|NEGATIV\w*)\b|^[^.:;]{0,30}[:;]\s*(?:AUS\w{2,5}|NAO|NENHUMA?|NEGATIV\w*)\b")

# Infra/supradesnível de ST sozinho não basta (o Heartware descreve "infradesnível do ponto J < 1,5 mm com ST
# ascendente", que é fisiológico); vale a palavra isquemia/positivo/insuficiência coronariana afirmada.
_ISQ = re.compile(r"ISQUEMI|TESTE (?:ERGOMETRICO )?POSITIVO|POSITIVO PARA ISQUEMIA|INSUFICIENCIA CORONARI|\bANGINA")
_ARR = re.compile(r"ARRITMI|EXTRA ?-?SS?ISTOL|TAQUICARDIA (?:VENTRICULAR|SUPRAVENTRICULAR|ATRIAL|PAROXISTICA)|\bTVNS\b|FIBRILACAO|FLUTTER"
                  r"|BLOQUEIO ATRIOVENTRICULAR|\bBAV\b|BIGEMIN|TRIGEMIN|PAREADAS|\bSALVAS?\b")
# Extrassístoles raras/isoladas são achado benigno do teste: não fazem "arritmia" sem um sinal de gravidade.
_ARR_BENIGNO = re.compile(r"\bRAR[OA]S?\b|ISOLAD[OA]S?|\bUNIC[OA]\b|OCASIONA|ESPARS[OA]S?|POUC[OA]S")
_ARR_GRAVE = re.compile(r"FREQUENTES|PAREAD|BIGEMIN|TRIGEMIN|TAQUICARDIA|\bTVN?S?\b|FIBRILACAO|FLUTTER|SALVA|COMPLEXA"
                        r"|INTERROMPID|POLIMORF|MULTIPLAS")
_OUTRO = re.compile(r"HIPERTENS\w* REACIONAL|RESPOSTA PRESSORICA (?:EXACERBADA|HIPERTENSIVA|ELEVADA|EXAGERADA|DEPRIMIDA|HIPOTENSIVA"
                    r"|INADEQUADA|EM PLATO|ANORMAL)|HIPOTENS|QUEDA D[AE] (?:PRESSAO|PA)|INCOMPETENCIA CRONOTROP"
                    r"|RESPOSTA CRONOTROPICA (?:DEPRIMIDA|INADEQUADA|DEFICIENTE|ATENUADA|ANORMAL)|DEFICIT CRONOTROPICO (?:IMPORTANTE|SIGNIFICATIVO)"
                    r"|ATRASO DE CONDUCAO|BLOQUEIO DE RAMO|BLOQUEIO DIVISIONAL|PRE-?EXCITACAO|WOLFF|DOR PRECORDIAL|TONTURA|LIPOTIMIA|DISPNEIA LIMITANTE")
# "Submáximo" NÃO é ineficaz: "teste eficaz e submáximo" atingiu >= 85% da FC máxima prevista, só não a máxima.
_INEFICAZ = re.compile(r"INEFICAZ|NAO EFICAZ|INCONCLUSIV|NAO DIAGNOSTIC|NAO ATINGI\w* (?:A |O )?(?:FC|FREQUENCIA CARDIACA|85)"
                       r"|FC ?MAX\w*\s*<\s*85")

# "normal" só com conclusão escrita: negação de isquemia/arritmia ou resposta fisiológica/normal.
_EVID_NORMAL = re.compile(r"ISQUEMI|INSUFICIENCIA CORONARI|FISIO\w*|NORMA\w*|ADEQUAD\w*|AUSENCIA DE (?:ARRITMI|ALTERAC|SINTOMA)"
                          r"|SEM (?:ARRITMI|ALTERAC|EVIDENC)|ECTOPIAS? CARDIACAS?: AUSENTE")
_PA_NORMAL = re.compile(r"PRESS\w{2,4}ICAS?\W{0,3}(?:FISIO\w*|NORMA\w*|ADEQUAD\w*)|E PRESSORICA (?:NORMAIS|ADEQUADAS|FISIOLOGICAS)"
                        r"|RESPOSTA TENSIONAL (?:FOI )?(?:FISIOLOGICA|NORMAL|ADEQUADA)|COMPORTAMENTO (?:NORMAL|FISIOLOGICO|ADEQUADO) D[AE] (?:PRESSAO|PA)"
                        r"|PRESSAO ARTERIAL (?:COM )?(?:COMPORTAMENTO|RESPOSTA) (?:NORMAL|FISIOLOGIC|ADEQUAD)|PA COM COMPORTAMENTO (?:NORMAL|FISIOLOG)")
_PA_HIPER = re.compile(r"HIPERTENS\w* (?:REACIONAL|AO ESFORCO|ARTERIAL REACIONAL)|RESPOSTA PRESSORICA (?:EXACERBADA|HIPERTENSIVA|ELEVADA|EXAGERADA)"
                       r"|COMPORTAMENTO HIPERTENSIVO|^(?:\W*)(?:SISTO-?DIASTOLICA|SISTOLICA ISOLADA|DIASTOLICA ISOLADA)")
_PA_HIPO = re.compile(r"HIPOTENS|QUEDA (?:\w+ )?D[AE] (?:PRESSAO|PA)\b|RESPOSTA PRESSORICA (?:DEPRIMIDA|HIPOTENSIVA|EM PLATO|ATENUADA)"
                      r"|COMPORTAMENTO HIPOTENSIVO")

# Número solto antes de "MET": não pode vir colado em letra/dígito ("V5 MET" do cabeçalho) nem começar com 0 ("02 MET").
_MET = re.compile(r"(?<![A-Z0-9.,])([1-9]\d?(?:[.,]\d{1,2})?)\s*\)?\s*METS?\b(?!\s*/\s*MIN|/MIN)"
                  r"|METS? MAXIMO\W{0,12}([1-9]\d?(?:[.,]\d{1,2})?)")
_MET_FORA = re.compile(r"MMHG\s*/\s*MET|/\s*MET\b|CLINIMEX|QUESTIONNAIRE|METANFETAMINA|\(MET\)|FAIXA DE METS")


def _eh_titulo(l: str) -> bool:
    return bool(_TITULO.search(l)) and not _DATA.search(l) and not _NAO_TITULO.search(l) and len(l) <= 80


def _janelas(linhas: list[str]) -> list[list[str]]:
    out, i = [], 0
    while i < len(linhas):
        if not _eh_titulo(linhas[i]):
            i += 1
            continue
        j = i + 1
        while j < len(linhas) and j - i <= JANELA and not (_FIM.search(linhas[j]) and not _eh_titulo(linhas[j])):
            j += 1
        jan = linhas[i:j]
        if sum(bool(_CORPO.search(l)) for l in jan) >= 2:
            out.append(jan)
        i = j
    return out


_NOVA_FRASE = re.compile(r"^(?:[-.•]|\d{1,2}\s*[.)-]|[A-Z ]{3,40}:|<!--)")


def _frases(linhas: list[str]) -> list[str]:
    """Junta as linhas quebradas pelo OCR numa frase ("... negativo" / "para isquemia ..."). Item de lista
    ("- ...", ". ...", "1) ..."), rótulo ("ARRITMIAS:") ou fim de frase anterior (. ; :) começam outra."""
    out: list[str] = []
    for l in linhas:
        if out and not _NOVA_FRASE.match(l) and not re.search(r"[.;:]\s*$", out[-1]):
            out[-1] = out[-1] + " " + l
        else:
            out.append(l)
    return out


def _afirmado(frase: str, m: re.Match) -> bool:
    """O achado casado em m foi afirmado na frase, e não negado?"""
    depois = re.sub(r"^\w*", "", frase[m.end():])  # resto da palavra ("ISQUEMI|A: AUSENTES")
    if _AUSENTE.search(depois[:45]):
        return False
    if _PRESENTE.search(depois[:40]):
        return True
    # Rótulo Heartware com o valor na linha de baixo ("RESPOSTA PRESSORICA EXACERBADA:" / "SISTO-DIASTOLICA: AUSENTE").
    if re.fullmatch(r"[^:]{0,60}:\s*", frase):
        return False
    antes = frase[:m.start()]
    nega = list(_NEGA.finditer(antes))
    resto = re.sub(r"(?:COMPATIVE\w*|SUGESTIV\w*|CONSISTENTES?|RELACIONAD\w*) COM\b", " ", antes[nega[-1].end():]) if nega else ""
    if nega and not re.search(r"\bCOM\b|\bPOREM\b|\bMAS\b|ENTRETANTO|OBSERVA-SE|OBSERVOU-SE|NOTA-SE", resto):
        return False
    if re.search(r"^\W*(?:AUSENTES?|NAO|NEGATIV)", depois.strip(" .:-")):
        return False
    return True


def _achou(frases: list[str], rx: re.Pattern, benigno: Optional[re.Pattern] = None) -> bool:
    for f in frases:
        if _FORA.search(f) or _ROTULO_SO.fullmatch(f):
            continue
        # Vale a última menção da frase: "ARRITMIAS SEM ARRITMIAS DURANTE O EXAME" (rótulo + valor).
        ms = list(rx.finditer(f))
        if ms and _afirmado(f, ms[-1]) and not (benigno and benigno.search(f) and not _ARR_GRAVE.search(f)):
            return True
    return False


# Modelo "2) Teste ergométrico ... protocolo de Ellestad / [sem] alterações eletrocardiográficas sugestivas de
# isquemia" em que o OCR desloca o "SEM" para outra linha: se o próprio laudo nega alteração de ST, só vale
# isquemia com afirmação explícita (positivo, isquêmico, apresentou/evidenciou/observou, infra/supradesnível).
_ST_NEGADO = re.compile(r"AUSENCIA DE ALTERA\w* (?:EM|NO|DO|DE) (?:SEGMENTO |SEG\.? )?ST|ACHADOS SUGESTIVOS DE ISQUEMIA\W{0,3}AUS")
_ISQ_FORTE = re.compile(r"POSITIV|ISQUEMICO\b|APRESENT|EVIDENCI|OBSERV|INFRA|SUPRA|DESNIVEL|COMPATIVEL COM ISQUEMIA")


def _isquemia(frases: list[str]) -> bool:
    st_negado = any(_ST_NEGADO.search(f) for f in frases)
    for f in frases:
        if _FORA.search(f) or _ROTULO_SO.fullmatch(f):
            continue
        ms = list(_ISQ.finditer(f))
        if ms and _afirmado(f, ms[-1]) and (not st_negado or _ISQ_FORTE.search(f)):
            return True
    return False


def _pressao(frases: list[str]) -> Optional[str]:
    hiper = hipo = normal = False
    for l in frases:
        if _FORA.search(l):
            continue
        m = _PA_HIPER.search(l)
        if m and _afirmado(l, m):
            hiper = True
        m = _PA_HIPO.search(l)
        if m and _afirmado(l, m):
            hipo = True
        if _PA_NORMAL.search(l):
            normal = True
    if hiper:
        return "hipertensiva"
    if hipo:
        return "hipotensiva"
    return "normal" if normal else None


def _mets(linhas: list[str]) -> Optional[float]:
    vals = []
    for l in linhas:
        if _MET_FORA.search(l):
            l = _MET_FORA.sub(" ", l)
        for m in _MET.finditer(l):
            v = m.group(1) or m.group(2)
            try:
                x = float(v.replace(",", "."))
            except ValueError:
                continue
            if 1 <= x <= 25:
                vals.append((x, bool(re.search(r"[.,]", v))))
    # Com valores decimais escritos (estágios "4,2 MET", "5,3 MET"), inteiro solto é ruído do OCR.
    dec = [x for x, d in vals if d]
    vals = dec or [x for x, _ in vals]
    return max(vals) if vals else None


def debug_janelas(texto_entrada: str) -> list[list[str]]:
    linhas = [n for n in (_norm(l) for l in (texto_entrada or "").splitlines()) if n]
    return _janelas(linhas)


def ler(texto_entrada: str) -> dict[str, Any]:
    linhas = [n for n in (_norm(l) for l in (texto_entrada or "").splitlines()) if n]
    jans = _janelas(linhas)
    out: dict[str, Any] = {"ergometrico_laudo": None, "ergometrico": None, "ergometrico_mets": None,
                           "ergometrico_resposta_pressorica": None}
    if not jans:
        return out
    todas = [l for j in jans for l in j]
    frases = [f for j in jans for f in _frases(j)]
    out["ergometrico_laudo"] = "descritivo"
    pa = _pressao(frases)
    out["ergometrico_resposta_pressorica"] = pa
    if _isquemia(frases):
        concl = "isquemia"
    elif _achou(frases, _ARR, benigno=_ARR_BENIGNO):
        concl = "arritmia"
    elif pa in ("hipertensiva", "hipotensiva") or _achou(frases, _OUTRO):
        concl = "alterado_outro"
    elif _achou(frases, _INEFICAZ):
        concl = "ineficaz"
    elif any(_EVID_NORMAL.search(f) for f in frases if not _FORA.search(f)):
        concl = "normal"
    else:
        concl = None  # laudo sem conclusão legível (só tabela/cabeçalho no OCR)
    out["ergometrico"] = concl
    out["ergometrico_mets"] = _mets(todas)
    return out
