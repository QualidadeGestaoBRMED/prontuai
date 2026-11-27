"""
Conclusão do laudo de ELETROCARDIOGRAMA (ECG) no texto de OCR do prontuário — determinístico, sem LLM.

    ler(texto_entrada) -> {"ecg": "alterado" | "normal" | "sem_conclusao" | None}

None = não há laudo de ECG no texto. "sem_conclusao" = há laudo (título + conteúdo de ECG: ritmo,
QRS, FC em bpm, derivações...) mas nenhuma frase decide (traçado do aparelho sem laudo escrito).

Janela do laudo: começa numa linha curta (<= 60) com o nome do exame (ELETROCARDIOGRAMA / ECG /
ELECTROCARDIOGRAM / "ECG de Repouso"), sem data, e vai até 80 linhas com palavra (a tabela numérica do
aparelho não gasta orçamento), o título de outro exame, a conclusão do ASO ou a quebra de página.
Não abre janela:
  - item da lista do ASO/guia: nome com data ("ELETROCARDIOGRAMA 09/09/2026"), item numerado
    ("3. ECG CONVENCIONAL") ou nome com a data na linha de baixo seguido de outro exame; a tradução logo
    abaixo ("## ELECTROCARDIOGRAM") abre, mas fecha na linha seguinte e cai por não ter conteúdo de ECG;
  - janela de teste ergométrico/Holter ("ECG de repouso", "ECG durante o esforço"): é outro exame.
A conclusão do ASO (Apto/Inapto) e a carta de encaminhamento nunca entram: o encaminhamento já saiu em
separar_rotulo, e a janela fecha em "5. Conclusão /", APTO/INAPTO e no título de qualquer outro exame.
Fallback: sem nenhum título lido (laudo manuscrito), a página com "ritmo sinusal" + FC/QRS/derivações.

Decisão por janela (entre janelas, alterado vence normal):
  1. Apaga o que não é achado: avisos-padrão ("alterado ou normal", "presença ou ausência de doenças"),
     faixas de referência entre parênteses ("(normal: 50 a 100 bpm)"), opção de formulário sem marca
     ("( ) Alterado") e trecho negado ("ausência de arritmias", "sem desvio de eixo", "não há ...").
  2. A conclusão escrita (primeiro rótulo CONCLUSÃO/IMPRESSÃO, até 3 linhas) vence a descrição:
     "alterações inespecíficas da repolarização" na análise + "dentro dos limites da normalidade" na
     conclusão = normal. Se a conclusão não decide ("correlacionar com dados clínicos"), lê a janela toda.
  3. Alterado: bradicardia/taquicardia, bloqueios/hemibloqueios/BRD, distúrbio ou atraso de condução,
     sobrecargas, extrassístoles/ectopias, fibrilação/flutter, arritmia, alteração/distúrbio da
     repolarização, repolarização precoce, pré-excitação/WPW/onda delta/PR curto, QT longo, isquemia,
     área inativa, desvio de eixo, "ECG/exame alterado", "fora da normalidade", "(X) Alterado",
     "dentro dos padrões normais: Não", "sugiro avaliação cardiológica: Sim". Alterado vence normal.
  4. Normal: "dentro dos limites/padrões da normalidade", "ECG/traçado/exame normal", "(X) Normal",
     "padrões normais: Sim", "sem alterações", "ritmo sinusal" (sozinho é normal; "repolarização
     ventricular normal/estável" e "eixo normal" não são alteração).
  5. Nada decide: FC escrita < 50 ou > 100 bpm = alterado; restos de OCR de laudo manuscrito
     ("FC-80BPM NORMAL", "ALTERACAC") decidem; senão sem_conclusao. Traçado sem conclusão num documento
     com teste ergométrico é o ECG de repouso da ergometria → None.

Bradicardia sinusal leve (FC 50–59, ou o 49 bpm da conferência) CONTA como alterado quando o laudo a
escreve: o médico da conferência tratou FC 49 como alteração, e o que se quer prever é a conduta dele.
A FC numérica sozinha só decide quando nenhuma frase decide — se o cardiologista escreveu "dentro dos
padrões normais" com FC 48, vale o que ele escreveu.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", t).strip()


_TITULO_ECG = re.compile(r"ELETROCARDIOGRAM|ELECTROCARDIOGRAM|\bECG\b|\bE\.C\.G\b")
# Título de outro exame (ou do ASO) fecha a janela.
_OUTRO_TITULO = re.compile(
    r"AUDIOMETRI|AUDIOLOG|AUDIOGRAMA|PURE TONE|ESPIROMETRI|SPIROMETR|ACUIDADE VISUAL|VISUAL ACUITY|"
    r"HEMOGRAMA|GLICOSE|GLICEMIA|GLUCOSE|RADIOGRAFIA|RADIOGRAPHY|\bRX\b|ELETROENCEFALO|ELECTROENCEPHALO|"
    r"ATESTADO DE SAUDE OCUPACIONAL|FICHA MEDICA|FICHA CLINICA|AVALIACAO PSICO|ODONTOLOG|EXAME CLINICO|"
    r"CLINICAL EXAMINATION|TOXICOLOG|LIPIDOGRAMA|CREATININA|GAMA ?GT|\bTGO\b|\bTGP\b|URINA|PARASITOLOG|"
    r"ANAMNESE|CONCLUSAO / CONCLUS|^\d\.? ?CONCLUSAO ?/|\bAPTO\b|\bINAPTO\b|ERGOMETRI|HOLTER|\bMAPA\b|PROVA DE FUNCAO|VOLUMES PULMONARES")
_ERGOMETRIA = re.compile(r"ERGOMETR|ESFORCO|PRE-ESF|RECUPERACAO|HOLTER")
_PAGINA = re.compile(r"<!-- ?PAGINA")
_DATA = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")
# Conteúdo que só um laudo de ECG tem; sem isso a janela é lista/orientação de preparo, não laudo.
_CONTEUDO_ECG = re.compile(
    r"RITMO|SINUSAL|\bQRS\b|\bBPM\b|\bFC\b|FREQUENCIA CARDIACA|REPOLARIZ|ONDA P\b|INTERVALO PR|\bPR\b|"
    r"\bQTC?\b|DERIVAC|\bEIXO\b|BRADICARDIA|TAQUICARDIA|BLOQUEIO|SOBRECARGA|LIMITES DA NORMAL|"
    r"PADROES NORMAIS|SINUS|RHYTHM|D[EU]NTRO D[AO]S? (?:\w+ )?NORMA|ALTERAD")
_JANELA_MAX = 80

# 1. Texto que não é achado.
_AVISOS = re.compile(
    r"ALTERADO OU NORMAL|NORMAL OU ALTERADO|PRESENCA OU (?:A )?AUSENCIA DE[^.;]{0,60}|"
    r"NEM SEMPRE REFLETE[^.;]{0,80}")
_REFERENCIA = re.compile(r"\((?:[^()]{0,40}\bNORMA[LI][^()]{0,60})\)|\(VR[^()]{0,40}\)|\(HR: ?\d+ ?- ?\d+\)")
_CAIXA_VAZIA = re.compile(r"[\(\[]\s*[\)\]]\s*[A-Z]+(?: [A-Z]+){0,3}")
_NEGACAO = re.compile(
    r"\b(?:AUSENCIA D[EOA]S?|SEM|NAO HA|NAO SE OBSERVA[MN]?|NAO APRESENTA|NAO FORAM OBSERVAD[AO]S|NEGATIV[AO] PARA"
    r"|INEXISTENCIA DE|NENHUMA)\b[^.;:|\n]{0,70}")

# 2. Alteração.
_ALTERADO = re.compile(
    r"BRADICARDIA|TAQUICARDIA|\bBLOQUEIO (?:DE |DO |AV|ATRIO|DIVISIONAL|INCOMPLETO|COMPLETO|FASCIC|SINO|INTRA)"
    r"|HEMIBLOQUEIO|\bBRD\b|\bBRE\b|\bBAV\b|\bBDAS\b|\bBDAM\b|DISTURBIO (?:DE|DA|DO) CONDUCAO|ATRASO (?:FINAL )?DE CONDUCAO"
    r"|SOBRECARGA (?:ATRIAL|VENTRICULAR|DE (?:VENTRICULO|ATRIO|CAMARA)|BI|SISTOLICA|DIASTOLICA)"
    r"|EXTRA ?-?S+IST|ECTOPIA|FIBRILACAO|FLUTTER|ARRITMIA|"
    r"(?:ALTERACA?O?E?S?|DISTURBIOS?) (?:\w+ )?(?:\w+ )?(?:DA|DE|NA) REPOLARIZ|REPOLARIZ\w{0,5} PRECOCE"
    # OCR de "alterações" ("ALTERAQ6ES", "ALTERA^OES"), até 3 palavras antes de "da repolarização" ("difusas e inespecíficas"),
    # repolarização ventricular precoce e inversão de onda T (conferência da v.24, 27/11).
    r"|ALTERA\S{0,4}E?S? (?:\S+ ){0,3}(?:DA|DE|NA) REPOLARIZ|REPOLARIZ\S{0,5} VENTRICULAR PRECOCE|INVERSAO DE (?:ONDA )?T\b"
    r"|PRE ?-? ?EXCITA|PREEXCITA|WOLFF|\bWPW\b|ONDA DELTA|PR CURTO|QT (?:LONGO|PROLONGADO)"
    r"|ISQUEMI|AREA ELETRICAMENTE INATIVA|INFARTO|NECROSE"
    r"|DESVIO (?:DO |DE )?EIXO|DESVIO ACENTUADO DO SAQRS|EIXO DESVIADO"
    r"|(?:ECG|ELETROCARDIOGRAMA|EXAME|TRACADO) (?:\w+ )?ALTERADO|\(X ?\) ?ALTERADO|\bANORMAL\b"
    r"|PADROES NORMAIS: ?NAO|FORA D[AO]S? (?:LIMITES DA )?NORMALIDADE|AVALIACAO CARDIOLOGICA: ?SIM|ALTERACOES? (?:\w+ )?(?:ELETROCARDIOGRAFIC|INESPECIFIC)")
# 3. Normal.
_NORMAL = re.compile(
    r"DENTRO DOS (?:LIMITES|PADROES) (?:DA )?NORMA|LIMITES DA NORMALIDADE|PADROES NORMAIS: ?SIM|COMPATIVEL COM (?:A )?NORMALIDADE"
    r"|(?:ECG|ELETROCARDIOGRAMA|EXAME|TRACADO) (?:\w+ )?NORMAL|\(X ?\) ?NORMAL|SEM ALTERACO"
    r"|D[EU]NTRO D[AO]S? (?:\w+ )?NORMA|RITMO:? SINUSAL|\bSINUSAL\b(?!:? ?NAO)|RITMO SI[MN]\w{0,3}L\b|SINUSAL:? SIM|NORMAL ECG|SINUS RHYTHM|WITHIN NORMAL LIMITS")
_FC = re.compile(r"(?:\bFC\b|FREQUENCIA CARDIACA|HEART RATE)\.? ?:? ?(\d{2,3}) ?(?:BPM\b|\||$)")
_ROTULO_CONCLUSAO = re.compile(r"^(?:CONCLUS|IMPRESSAO)[A-Z()]*\s*:?\s*")
_FIM_CONCLUSAO = re.compile(r"^(?:DR\.?A?\b|DADOS DO MEDICO|NOTAS|OBS|CARDIOLOG|ASSINAD|IMPORTANTE|CRM|RQE|A INTERPRETACAO"
                            r"|O RESULTADO|EMITIDO|<!--)")


_TEM_PALAVRA = re.compile(r"[A-Z]{4,}")
_SO_DATA = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$")
_ITEM_NUMERADO = re.compile(r"^\d{1,2}[.)] ?[A-Z]")


def _item_de_lista(linhas: list[str], i: int) -> bool:
    """Item de lista de exames (ASO/guia) com a data na linha de baixo: "3. ECG CONVENCIONAL" / "26/10/2026" /
    "7. AUDIOMETRIA TONAL". Laudo com data na linha de baixo é seguido de cabeçalho, não de outro exame."""
    if _ITEM_NUMERADO.match(linhas[i]) and i + 1 < len(linhas) and (
            _ITEM_NUMERADO.match(linhas[i + 1]) or _SO_DATA.match(linhas[i + 1])):
        return True
    if i + 2 >= len(linhas) or not _SO_DATA.match(linhas[i + 1]):
        return False
    prox = linhas[i + 2]
    return bool(_ITEM_NUMERADO.match(prox) or (len(prox) <= 90 and _OUTRO_TITULO.search(prox)))


def _janelas(linhas: list[str]) -> list[str]:
    janelas: list[str] = []
    i = 0
    while i < len(linhas):
        n = linhas[i]
        if _TITULO_ECG.search(n) and len(n) <= 60 and not _DATA.search(n) and not _item_de_lista(linhas, i):
            corpo = [n]
            orcamento = _JANELA_MAX  # só linha com palavra gasta orçamento: a tabela numérica do aparelho não
            j = i + 1
            while j < len(linhas) and orcamento > 0:
                lj = linhas[j]
                if len(lj) <= 90 and _OUTRO_TITULO.search(lj) and not _TITULO_ECG.search(lj):
                    break
                if _PAGINA.match(lj) and len(corpo) > 3:  # laudo não costuma atravessar página
                    break
                corpo.append(lj)
                if _TEM_PALAVRA.search(lj):
                    orcamento -= 1
                j += 1
            # O título entra no texto: às vezes ele é a própria conclusão ("ELETROCARDIOGRAMA DENTRO DA NORMALIDADE").
            texto = " | ".join(corpo)
            # Teste ergométrico / Holter têm "ECG de repouso" e "ECG durante o esforço": não é o laudo de ECG.
            if _CONTEUDO_ECG.search(texto) and not _ERGOMETRIA.search(" ".join(corpo[:12])):
                janelas.append(texto)
            i += len(corpo)
        else:
            i += 1
    return janelas


def _limpar(t: str) -> str:
    t = _AVISOS.sub(" ", t)
    t = _REFERENCIA.sub(" ", t)
    t = _CAIXA_VAZIA.sub(" ", t)
    return t


def _decidir(t: str) -> Optional[str]:
    t = _limpar(t)
    if _ALTERADO.search(_NEGACAO.sub(" ", t)):
        return "alterado"
    if _NORMAL.search(t):
        return "normal"
    return None


def _secao_conclusao(janela: str) -> str:
    """Texto sob o primeiro rótulo CONCLUSÃO/IMPRESSÃO: até 3 linhas, parando na assinatura ou num aviso."""
    partes = [p.strip() for p in janela.split("|")]
    out = []
    for k, p in enumerate(partes):
        m = _ROTULO_CONCLUSAO.match(p)
        if not m:
            continue
        resto = p[m.end():].strip()
        if resto:
            out.append(resto)
        for q in partes[k + 1:k + 4]:
            if not q or _FIM_CONCLUSAO.match(q):
                break
            out.append(q)
        break  # só o primeiro rótulo: os seguintes costumam ser de outro exame que entrou na janela
    return " | ".join(out)


def _conclusao(janela: str) -> str:
    # O que o cardiologista escreveu na conclusão vence a descrição (ex.: "alterações inespecíficas da
    # repolarização" na análise e "dentro dos limites da normalidade" na conclusão = normal).
    conc = _secao_conclusao(janela)
    r = _decidir(conc) if conc else None
    if r is None:
        r = _decidir(janela)
    if r is not None:
        return r
    # Laudo manuscrito em que o OCR só salvou pedaços: "FC-80BPM NORMAL PR-0,12S" / "ALTERACAC ...".
    resto = _NEGACAO.sub(" ", _limpar(janela))
    if re.search(r"\bALTERACA[OC]\b", resto):
        return "alterado"
    if re.search(r"(?:LAUDO|\bF[CA]\b)[^|]{0,40}\bNORMAL\b", resto):
        return "normal"
    # Nenhuma frase decide: FC escrita fora de 50–100 bpm conta como alteração.
    fcs = [int(m.group(1)) for m in _FC.finditer(_limpar(janela)) if 20 <= int(m.group(1)) <= 250]
    if any(fc < 50 or fc > 100 for fc in fcs):
        return "alterado"
    return "sem_conclusao"


_RITMO = re.compile(r"RITMO:? SINUSAL|RITMO SINUSAL")
_FC_BPM = re.compile(r"\bFC\b[^|]{0,6}\d{2,3} ?BPM|\bQRS\b|DERIVAC")


def _paginas_sem_titulo(linhas: list[str]) -> list[str]:
    """Fallback quando nenhum título de ECG foi lido (laudo manuscrito, título perdido no OCR): a página
    que tem ritmo sinusal + FC em bpm/QRS/derivações vira a janela. Ergometria fica de fora."""
    paginas: list[list[str]] = [[]]
    for l in linhas:
        if _PAGINA.match(l):
            paginas.append([])
        else:
            paginas[-1].append(l)
    out = []
    for pg in paginas:
        t = " | ".join(pg)
        if _RITMO.search(t) and _FC_BPM.search(t) and not _ERGOMETRIA.search(t) and len(pg) <= 150:
            out.append(t)
    return out


def janelas(texto_entrada: str) -> list[str]:
    """As janelas de laudo de ECG achadas (para conferência)."""
    linhas = [_norm(l).lstrip("#* ").strip() for l in (texto_entrada or "").splitlines()]
    linhas = [l for l in linhas if l]
    return _janelas(linhas) or _paginas_sem_titulo(linhas)


# Detalhe do laudo (pedido do Breno, 23/11): o médico encaminha pelo TIPO de achado, não por "alterado".
# Lido de cada janela já limpa (avisos, faixas de referência, caixinha vazia) e sem os trechos negados.
_ACHADOS_ECG = {k: re.compile(v) for k, v in {
    "bradicardia": r"BRADICARDIA",
    "taquicardia": r"TAQUICARDIA",
    "bloqueio_ramo_direito": r"\bBRD\b|BLOQUEIO (?:INCOMPLETO |COMPLETO )?(?:DO |DE )?RAMO DIREITO|RAMO DIREITO",
    "bloqueio_ramo_esquerdo": r"\bBRE\b|BLOQUEIO (?:INCOMPLETO |COMPLETO )?(?:DO |DE )?RAMO ESQUERDO|RAMO ESQUERDO",
    "hemibloqueio": r"HEMIBLOQUEIO|\bBDAS\b|\bBDAM\b|\bBDPI\b|BLOQUEIO (?:DIVISIONAL|FASCICULAR)",
    "bloqueio_av": r"\bBAV\b|BLOQUEIO (?:AV|ATRIO)",
    "disturbio_conducao": r"DISTURBIO (?:DE|DA|DO) CONDUCAO|ATRASO (?:FINAL )?DE CONDUCAO",
    "sobrecarga": r"SOBRECARGA",
    "repolarizacao": r"(?:ALTERACA?O?E?S?|DISTURBIOS?) (?:\w+ )?(?:\w+ )?(?:DA|DE|NA) REPOLARIZ|REPOLARIZ\w{0,5} PRECOCE",
    "extrassistole": r"EXTRA ?-?S+IST|ECTOPIA",
    "fibrilacao_flutter": r"FIBRILACAO|FLUTTER",
    "pre_excitacao": r"PRE ?-? ?EXCITA|PREEXCITA|WOLFF|\bWPW\b|ONDA DELTA|PR CURTO",
    "qt_longo": r"QT (?:LONGO|PROLONGADO)",
    "isquemia_area_inativa": r"ISQUEMI|AREA ELETRICAMENTE INATIVA|INFARTO|NECROSE",
    "desvio_eixo": r"DESVIO (?:DO |DE )?EIXO|DESVIO ACENTUADO DO SAQRS|EIXO DESVIADO",
    "arritmia_sinusal": r"ARRITMIA SINUSAL",
    "arritmia_outra": r"ARRITMIA(?! SINUSAL)",
}.items()}
_INTERVALO = {k: re.compile(r"(?<![A-Z])" + v + r"\s*(?:\(MS\))?\s*[:=\-]?\s*(\d+(?:[.,]\d+)?)\s*(MS\b|S\b|SEG)?")
              for k, v in {"pr": r"(?:INTERVALO )?PR", "qrs": r"(?:DURACAO DO )?QRS", "qtc": r"QTC\w*"}.items()}
_LIMITE_MS = {"pr": (60, 400), "qrs": (40, 250), "qtc": (250, 650)}


def _ms(valor: str, unidade: Optional[str], chave: str) -> Optional[int]:
    v = float(valor.replace(",", "."))
    if unidade in ("S", "SEG") or v < 1:
        v *= 1000
    lo, hi = _LIMITE_MS[chave]
    return int(round(v)) if lo <= v <= hi else None


# Laudo do teste ergométrico que cai dentro da janela do ECG ("ECG de repouso", "durante o esforço", "objetivos:
# detectar isquemia, avaliar arritmias"): o detalhe do ECG para antes dele.
_CORTE_ERGO = re.compile(r"TESTE ERGOMETRICO|ERGOMETRI|ESFOR[CPG]O|OBJETIVOS PRINCIPA|PROTOCOLO (?:DE )?(?:BRUCE|RAMPA|ELLESTAD)"
                         r"|RECUPERA[CGP]AO|CRONOTR|EXAUST|EXERCICI|FREQUENCIA CARDIACA (?:MAXIMA|ATINGIDA|ATMGIDA|SUBMAXIMA)"
                         r"|COMPORTAMENTO (?:FISIOLOGICO )?DA PRESSAO|\bMETS?\b")
# O ECG de repouso/pré-teste descrito DENTRO do laudo da ergometria é ECG e entra ("Alterações ECG pré-teste: QRS >
# 120 ms, sugestivo de BRE"); só o resto da ergometria (objetivos, esforço, recuperação) fica fora.
_ECG_PRE_TESTE = re.compile(r"ALTERA\w* (?:D[OE] )?ECG (?:PRE-? ?TESTE|BASAL|DE REPOUSO)\s*:\s*([^|]{0,220})")


def _sem_ergometria(j: str) -> str:
    m = _CORTE_ERGO.search(j)
    if not m:
        return j
    pre = [x.group(1) for x in _ECG_PRE_TESTE.finditer(j) if not re.match(r"\s*(?:AUSENTES?|NENHUMA|NAO|SEM)\b", x.group(1))]
    return j[:m.start()] + (" | " + " | ".join(pre) if pre else "")


# Negação depois do termo: "Achados sugestivos de isquemia: AUSENTES", "Presença de arritmias malignas: ausente".
_NEGADO_DEPOIS = re.compile(r"[^.;|:]{0,70}:\s*(?:AUSENTES?|NAO|NEGATIV[AO])\b")
# Faixa impressa, não valor medido: "Intervalo PR: 120 a 200 ms".
_FAIXA = re.compile(r"^\s*(?:A|-|ATE)\s*\d")


def detalhes(js: list[str]) -> dict:
    achados, fcs, ritmo = set(), [], None
    inter: dict[str, Optional[int]] = {"pr": None, "qrs": None, "qtc": None}
    for j in js:
        j = _sem_ergometria(j)
        limpo = _limpar(j)
        resto = _NEGACAO.sub(" ", _NEGADO_DEPOIS.sub(" ", limpo))
        achados |= {k for k, rx in _ACHADOS_ECG.items() if rx.search(resto)}
        fcs += [int(m.group(1)) for m in _FC.finditer(limpo) if 20 <= int(m.group(1)) <= 250]
        if ritmo is None:
            if re.search(r"FIBRILACAO ATRIAL|FLUTTER", resto):
                ritmo = "fa_flutter"
            elif re.search(r"\bSINUSAL\b(?!:? ?NAO)|SINUS RHYTHM", limpo):
                ritmo = "sinusal"
            elif re.search(r"RITMO (?:JUNCIONAL|ECTOPICO|ATRIAL|IDIOVENTRICULAR)|MARCAPASSO", resto):
                ritmo = "outro"
        for k, rx in _INTERVALO.items():
            if inter[k] is None:
                for m in rx.finditer(limpo):
                    if _FAIXA.match(limpo[m.end():m.end() + 8]):
                        continue
                    v = _ms(m.group(1), m.group(2), k)
                    if v is not None:
                        inter[k] = v
                        break
    return {"ecg_ritmo": ritmo, "ecg_fc": fcs[0] if fcs else None, "ecg_pr_ms": inter["pr"],
            "ecg_qrs_ms": inter["qrs"], "ecg_qtc_ms": inter["qtc"], "ecg_achados": "|".join(sorted(achados))}


# ECG de repouso descrito no laudo do teste ergométrico ("Comentários do ECG de repouso e no pré-esforço: ritmo sinusal
# com BRD de 1º grau", "ECG basal: ...", "Alterações ECG pré-teste: ..."). Só entra quando o documento não tem laudo de
# ECG próprio que decida: é o único ECG que o médico viu (auditoria de exames sem dado, 27/11: 75 casos).
_ECG_REPOUSO_ERGO = re.compile(r"COMENTARIOS DO ECG DE REPOUSO|^-? ?ECG (?:DE REPOUSO|BASAL)\b|ALTERA\w* (?:D[OE] )?ECG (?:PRE-? ?TESTE|BASAL|DE REPOUSO)")
_FIM_REPOUSO = re.compile(r"ESFOR\S?O|RECUPERA|COMENTARIOS DO ECG DURANTE|CONCLUS|OBJETIVO|PROTOCOLO|\bMETS?\b|ISQUEMIA")


def _ecg_da_ergometria(texto_entrada: str) -> list[str]:
    linhas = [l for l in (_norm(x) for x in (texto_entrada or "").splitlines()) if l]
    trechos = []
    for i, l in enumerate(linhas):
        if not _ECG_REPOUSO_ERGO.search(l):
            continue
        resto = l.split(":", 1)[1] if ":" in l else ""
        parte = [resto] if resto.strip() else []
        for k in range(i + 1, min(i + 3, len(linhas))):
            if _FIM_REPOUSO.search(linhas[k]) or _ECG_REPOUSO_ERGO.search(linhas[k]):
                break
            parte.append(linhas[k])
        if parte and not _FIM_REPOUSO.search(parte[0]):
            trechos.append(" | ".join(parte))
    return trechos


def ler(texto_entrada: str) -> dict[str, Optional[str]]:
    js = janelas(texto_entrada)
    res: dict[str, Optional[str]] = {"ecg": None}
    if js:
        # Texto do teste ergométrico dentro da janela não decide o ECG: em 13 de 62 "alterados" de uma amostra de 400
        # (23/11) a alteração vinha dos objetivos/achados da ergometria ("detectar isquemia", "isquemia: ausentes").
        cortadas = [_sem_ergometria(j) for j in js]
        res = {**_ler_conclusao(texto_entrada, cortadas), **detalhes(js)}
    if res.get("ecg") in (None, "sem_conclusao"):
        trechos = _ecg_da_ergometria(texto_entrada)
        decs = [d for d in (_decidir(t) for t in trechos) if d]
        if decs:
            return {"ecg": "alterado" if "alterado" in decs else "normal", **detalhes(trechos)}
    return res


def _ler_conclusao(texto_entrada: str, js: list[str]) -> dict[str, Optional[str]]:
    res = [_conclusao(j) for j in js]
    # Traçado sem conclusão num documento com teste ergométrico é o "ECG de repouso" da ergometria
    # (o laudo dela fica fora: _ERGOMETRIA), não um laudo de ECG.
    if set(res) == {"sem_conclusao"} and re.search(r"TESTE ERGOMETRICO|ERGOMETRIA", _norm(texto_entrada)):
        return {"ecg": None}
    if "alterado" in res:
        return {"ecg": "alterado"}
    if "normal" in res:
        return {"ecg": "normal"}
    return {"ecg": "sem_conclusao"}
