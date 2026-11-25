"""
Leitor determinístico (regex, sem LLM, sem rede) do laudo de ACUIDADE VISUAL no texto de OCR do
prontuário ocupacional. Parte do rascunho de `qualitativos.py` (que não lia o 20/xx em nenhum caso),
sem editá-lo.

Saída de `ler(texto_entrada)`:
    acuidade_visual    "alterado" | "normal" | "sem_conclusao" | None (não há laudo de acuidade)
    acuidade_pior_olho maior denominador 20/xx entre os olhos (sem correção, se houver com e sem)
    senso_cromatico    "alterado" | "normal" | None

Regras de decisão
1. Só se lê a JANELA do laudo: linha de título (ACUIDADE VISUAL, VISUAL ACUITY, SNELLEN, ORTHO RATER,
   AVALIAÇÃO OFTALMOLÓGICA...) até o título de outro exame, a conclusão do ASO, quebra de página ou 60
   linhas. Linha de título com data é item da lista do ASO e não abre janela; janela sem nenhum
   conteúdo de laudo (20/xx, olho, Snellen, Jaeger, conclusão...) é descartada (guia de agendamento,
   lista de exames). A conclusão do ASO ("5. Conclusão / Conclusion", "Apto / Fit") encerra a janela
   e nunca é lida; o texto de encaminhamento já sai antes, em `separar_rotulo`.
2. Opção de formulário sem marca não conta: "( ) Alterado" é apagado; caixa solta numa linha vale para a
   opção da linha seguinte. Num grupo de opções sem nenhuma marca legível, a opção sem caixa (o OCR
   comeu o "(X)") é a marcada se as vizinhas têm caixa vazia explícita; duas candidatas assim, ou um
   grupo todo sem caixa (formulário impresso, "NORMAL / ALTERADO"), não decidem nada. Legenda da régua ("20/40, 20/50 ... = Recomenda-se procurar um
   oftalmologista") e a frase de atestado "igual ou superior a 20/xx" não são resultado.
3. Conclusão escrita vence o valor: alteração ("anormal", "alterada", "necessita de avaliação
   oftalmológica", "recomendamos avaliação com o oftalmologista", "insatisfatória") vence normal no
   mesmo laudo. Frases do teste de cores (Ishihara/cromático) vão para `senso_cromatico`, não para a
   acuidade; um laudo de Ishihara separado também abre janela própria, só para o senso cromático.
4. Laudo com 20/xx e sem conclusão escrita: decide o valor do pior olho — 20/30 ou melhor (denominador
   <= 30) = normal; 20/40 ou pior (denominador >= 40) = alterado. Sem valor e sem conclusão:
   "sem_conclusao".
5. Pior olho = maior denominador 20/xx da janela; se o laudo traz medidas sem e com correção, valem as
   sem correção. Se não há janela de laudo mas a ficha médica relata o resultado ("realizou acuidade
   visual com resultado de 20/40 ... 20/200") — caso em que a página do laudo saiu junto com o
   encaminhamento —, o valor relatado é usado com a regra 4.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Optional


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", t).strip().lstrip("#* ").strip()


_DATA = re.compile(r"\b\d{1,2}\s*[/.-]\s*\d{1,2}\s*[/.-]\s*\d{2,4}\b|\b\d{1,2} (?:DE )?[A-Z]{3}\.?,? ?\d{4}\b")
_TITULO_AV = re.compile(r"ACUIDADE VISUAL|VISUAL ?ACUITY|SNELLEN|ORTHO ?RATER|AVALIACAO OFTALMOLOGICA"
                        r"|OPHTHALMIC ASSESSMENT|ACUIDADE$")
_TITULO_COR = re.compile(r"ISHIHARA|ISHIRA")
# Título de outro exame (ou do ASO) encerra a janela.
_OUTRO_TITULO = re.compile(
    r"AUDIOMETRI|AUDIOLOG|AUDIOGRAMA|PURE TONE|AUDIOMETRY|ELETROCARDIOGRAM|ELECTROCARDIOGRAM|\bECG\b"
    r"|ESPIROMETRI|SPIROMETR|FUNCAO PULMONAR|HEMOGRAMA|GLICEMIA|GLICOSE|RADIOGRAFIA|RAIO ?-?X|\bRX\b"
    r"|TELERRADIOGRAFIA|TELERADIOGRAFIA|ELETROENCEFALO|\bEEG\b|PSICOLOG|PSICOSSOCIAL|ODONTOLOG"
    r"|TOXICOLOG|ATESTADO DE SAUDE OCUPACIONAL|^ASO\b|FICHA MEDICA|FICHA CLINICA|ANAMNESE"
    r"|CLINICO OCUPACIONAL|CLINICAL EXAMINATION|EXAME CLINICO|DECLARACAO|^ENCAMINHAMENTO"
    r"|CONCLUSAO ?/ ?CONCLUSION|^\d\s*[.)]\s*CONCLUSAO|APTO ?/ ?FIT|INAPTO ?/ ?UNFIT|PROCEDIMENTOS REALIZADOS"
    r"|^EXAMES? COMPLEMENTARES|LAUDO PSICO|QUESTIONARIO|<!-- PAGINA|REALIZADOS (?:NA|EM) |OBSERVACOES IMPORTANTES"
    r"|ORIENTACOES DE PREPARO|PNEUMOCONIOSE|\bOIT\b|\bILO\b|ANORMALIDADES? PLEURA|QUALIDADE TECNICA|^\d(?:\.\d)?\s*[.)]?\s*EXAMES ?/ ?EXAMS")
_MAX_LINHAS = 60

# Conteúdo que só um laudo de acuidade tem (a lista do ASO e a guia de agendamento não têm).
_EVIDENCIA = re.compile(r"(?<![\d/])20\s*/\s*\d{2,3}(?![\d/])|SNELLEN|JAEGER|OLHO|\bO\.?\s?[DE]\b|RIGHT EYE"
                        r"|LEFT EYE|OPTOMETR|CONCLUS|LAUDO|SATISFATORIA|ALTERAD|NORMAL")

_VALOR = re.compile(r"(?<![\d/])20\s*/\s*(\d{2,3})(?![\d/])")
_OLHO = re.compile(r"OLHO|\bO\.?\s?[DE]\b|RIGHT EYE|LEFT EYE")
_VALOR_OCR = re.compile(r"(?<![\d/])\b20\s*(?:\s[1Il|](?=[1-9]\d\b)|[1Il|](?=[1-9]\d\b)|\s)\s*([1-9]\d{1,2})\b(?![\d/])")
_IGUAL_SUPERIOR = re.compile(r"IGUAL OU SUPERIOR A\s*20\s*/\s*\d{2,3}")
_CAIXA_VAZIA_INLINE = re.compile(r"[\(\[]\s*[\)\]]\s*[A-Z][A-Z.\-]*(?: [A-Z][A-Z.\-]*){0,4}")
_CAIXA_VAZIA_SO = re.compile(r"^[\(\[]\s*[\)\]]\.?$")
_MARCA_SO = re.compile(r"^(?:[\(\[]\s*[XK]\s*[\)\]]|X)$")
# Opção de formulário: caixa (marcada, vazia ou comida pelo OCR) + texto da opção.
_OPCAO = re.compile(r"^(?:CONCLUSAO:?\s*)?(?P<caixa>[\(\[]\s*[^\s\)\]]?\s*[\)\]]|[\(\[]|\)|X\b)?\s*\)?\s*"
                    r"(?P<txt>(?:EXAME |LAUDO )?(?:NORMAL|ALTERADO|ALTERADA|ANORMAL)\b|SATISFATORIA|INSATISFATORIA"
                    r"|NECESSITY? DE AVALIACAO|NECESSITA DE AVALIACAO|RECOMENDA\w* (?:A )?AVALIACAO|ACUIDADE VISUAL (?:ALTERADA|DENTRO)"
                    r"|PACIENTE RELATA|DALTONICO)")

_COR = re.compile(r"ISHIHARA|ISHIRA|CROMATIC|CORES|COLOR|DALTON|DISCROMAT")
_COR_ALT = re.compile(r"ANORMAL|ALTERAD|NAO IDENTIFIC|DISCROMATOPSIA|^\(X\) DALTONICO|DEFICIENCIA|INSATISF")
_COR_NORMAL = re.compile(r"NORMAL|SEM ALTERAC|ACERTOU|IDENTIFICOU TODAS|SATISFAT|DENTRO D")

_AV_ALT = re.compile(r"ANORMAL|ALTERAD|NECESSITA DE AVALIACAO|RECOMENDA\w* (?:A )?AVALIACAO|PROCURAR (?:UM |O )?OFTALMO|ENCAMINHAD[OA] (?:AO|PARA) OFTALMO|REDUCAO DA ACUIDADE"
                     r"|BAIXA (?:DA )?ACUIDADE|INSATISFATORIA|DEFICIT VISUAL|AMBLIOPIA")
_AV_NORMAL = re.compile(r"LAUDO NORMAL|EXAME NORMAL|ACUIDADE (?:VISUAL )?(?:NORMAL|DENTRO|SATISFATORIA)|VISAO NORMAL"
                        r"|DENTRO DOS? (?:LIMITES|PADROES|PARAMETROS)|DENTRO DA NORMALIDADE|BOA VISAO|SATISFATORIA|^NORMAL\.?$"
                        r"|^\(X\) ?NORMAL|RESULTADO:? NORMAL|CONCLUSAO:? NORMAL")
_NEGACAO = re.compile(r"\b(?:AUSENCIA DE|SEM|NAO HA|NAO APRESENTA|NAO SE OBSERVA|NEGA)\b[^.;]{0,60}")
_LEGENDA = re.compile(r"BOA VISAO|RECOMENDA-?SE|MONOCULAR|20\s*/\s*\d{2,3}\s*,\s*(?:20\s*/|J\d)")
_RELATO = re.compile(r"ACUIDADE VISUAL[^.]{0,80}?(?<![\d/])20\s*/\s*\d{2,3}")


def _eh_titulo_av(l: str) -> bool:
    return bool(_TITULO_AV.search(l)) and len(l) <= 100 and not _DATA.search(l)


def _janelas(linhas: list[str], titulo, contexto: int = 0) -> list[list[str]]:
    """Janelas (listas de linhas) a partir de cada título, até o título de outro exame.

    `contexto` > 0 prefixa as linhas anteriores ao título marcadas com "\x00" (só servem para ver
    opções impressas vizinhas; `_limpar` as descarta)."""
    out = []
    i = 0
    while i < len(linhas):
        if titulo(linhas[i]):
            corpo = [linhas[i]]
            j = i + 1
            while j < len(linhas) and len(corpo) < _MAX_LINHAS:
                l = linhas[j]
                if (_OUTRO_TITULO.search(l) and len(l) <= 100 and not titulo(l)) or \
                        (titulo is _eh_titulo_cor and _eh_titulo_av(l)):
                    break
                corpo.append(l)
                j += 1
            antes = ["\x00" + l for l in linhas[max(0, i - contexto):i]] if contexto else []
            out.append(antes + corpo)
            i = j
        else:
            i += 1
    return out


def _eh_titulo_cor(l: str) -> bool:
    return bool(_TITULO_COR.search(l)) and len(l) <= 120 and not _DATA.search(l)


def _estado_caixa(caixa: Optional[str]) -> str:
    if not caixa:
        return "ambigua"  # sem caixa nenhuma: o OCR pode ter comido o "(X)"
    if caixa in ("(", "[", ")", "(?)"):
        return "resto"  # sobrou metade da caixa: pode ser "( )" ou "(X)"
    if caixa == "X" or re.search(r"[^\s\(\)\[\]]", caixa):
        return "marcada"
    return "vazia"


def _opcoes(linhas: list[str]) -> list[str]:
    """Decide quais opções de formulário estão marcadas, por grupo de opções consecutivas.

    Com alguma opção marcada no grupo, só as marcadas contam. Sem nenhuma marcada mas com caixa vazia
    explícita nas vizinhas, a opção sem caixa é a marcada (o OCR comeu o "(X)"). Grupo só com opções
    sem caixa é formulário impresso sem marca legível: nenhuma conta; duas ou mais candidatas sem caixa
    também não (o valor 20/xx decide).
    """
    out = list(linhas)
    linhas = [l.lstrip("\x00") for l in linhas]
    grupo: list[tuple[int, str, str]] = []

    def fechar():
        if not grupo:
            return
        estados = [e for _, e, _ in grupo]
        if len(grupo) == 1 and estados[0] in ("ambigua", "resto"):
            # Opção sozinha e sem caixa é resultado de tabela ("TESTE DE ISHIHARA / NORMAL"), a menos que
            # a opção contrária esteja impressa logo ao lado (formulário sem marca legível).
            i, _, txt = grupo[0]
            oposta = r"ALTERAD|ANORMAL|INSATISF|NECESSIT|RECOMENDA|DALTONICO" if re.match(r"(?:EXAME )?NORMAL|SATISF", txt) else r"NORMAL|SATISF"
            vizinhas = []
            for passo in (-1, 1):  # vizinhas do mesmo bloco: para em "CONCLUSÃO" ou cabeçalho "XXX:"
                for v in linhas[i + passo::passo][:3] if passo == 1 else linhas[max(0, i - 3):i][::-1]:
                    if v.startswith("CONCLUS") or v.endswith(":"):
                        break
                    vizinhas.append(v)
            if not any(_OPCAO.match(v) and re.search(oposta, v) for v in vizinhas):
                grupo.clear()
                return
        if "marcada" in estados:
            valem = {i for i, e, _ in grupo if e == "marcada"}
        elif "vazia" in estados or "resto" in estados:
            # Sem marca legível: a opção sem caixa nenhuma é a marcada; não havendo, a que tem só um resto
            # de caixa, desde que haja caixa vazia explícita ao lado. Duas candidatas: indecidível.
            valem = {i for i, e, _ in grupo if e == "ambigua"}
            if not valem and "vazia" in estados:
                valem = {i for i, e, _ in grupo if e == "resto"}
            if len(valem) > 1:
                valem = set()
        else:
            valem = set()
        for i, _, txt in grupo:
            pref = "CONCLUSAO: " if linhas[i].startswith("CONCLUS") else ""
            out[i] = (pref + "(X) " + txt) if i in valem else ""
        grupo.clear()

    for i, l in enumerate(linhas):
        m = _OPCAO.match(l)
        if m and len(l) <= 120:
            if l.startswith("CONCLUS"):
                fechar()
            grupo.append((i, _estado_caixa(m.group("caixa")), l[m.start("txt"):]))
        else:
            fechar()
    fechar()
    return [l for l in out if l and not l.startswith("\x00")]


def _limpar(corpo: list[str]) -> list[str]:
    """Tira opções sem marca, legenda e frase de atestado; junta caixa solta à opção seguinte."""
    pre: list[str] = []
    k = 0
    while k < len(corpo):
        l = corpo[k]
        prox = corpo[k + 1] if k + 1 < len(corpo) else ""
        if l in ("(", "[") and prox.startswith(")"):  # "( )" partido em duas linhas
            if prox.strip() == ")":
                corpo = corpo[:k + 1] + ["( )"] + corpo[k + 2:]  # vira caixa vazia solta
                k += 1
                continue
            pre.append("( " + prox)
            k += 2
            continue
        if l in ("(", "[", ")") and _OPCAO.match(prox) and not _MARCA_SO.match(prox):
            m = _OPCAO.match(prox)
            if not m.group("caixa"):  # resto de caixa numa linha, opção na seguinte
                pre.append("(?) " + prox[m.start("txt"):])
                k += 2
                continue
        solta = _CAIXA_VAZIA_SO.match(l) or _MARCA_SO.match(l)
        if solta and prox and len(prox) <= 120 and _OPCAO.match(prox) and not (
                _MARCA_SO.match(prox) or _CAIXA_VAZIA_SO.match(prox)):
            m = _OPCAO.match(prox)
            pre.append(("(X) " if _MARCA_SO.match(l) else "( ) ") + prox[m.start("txt"):])
            k += 2
            continue
        if solta:
            k += 1
            continue
        pre.append(l)
        k += 1
    out = []
    for l in _opcoes(pre):
        if len(_VALOR.findall(l)) >= 3 or (_VALOR.search(l) and _LEGENDA.search(l)) or re.match(r"^\S+ ?= ", l):
            continue  # legenda da régua de Snellen
        l = _IGUAL_SUPERIOR.sub(" ", l)
        l = _CAIXA_VAZIA_INLINE.sub(" ", l)
        out.append(l)
    return out


def _valores(linhas: list[str]) -> Optional[int]:
    """Maior denominador 20/xx; com medidas sem e com correção separadas, só as sem correção."""
    estado = None
    vals: list[tuple[Optional[str], int]] = []
    # Formulário com a régua inteira em caixas ("( ) 20/100", "( ) 20/200"): só vale o valor marcado.
    if sum(bool(re.match(r"^[\(\[]?\s*[\)\]]\s*20\s*/", l)) for l in linhas) >= 3:
        marcados = [int(m.group(1)) for l in linhas
                    for m in re.finditer(r"[\(\[]\s*[XK]\s*[\)\]]\s*20\s*/\s*(\d{2,3})", l)]
        marcados = [v for v in marcados if 10 <= v <= 400]
        return max(marcados) if marcados else None
    # Régua impressa em coluna (uma linha "20/200", outra "20/100", ...): a marca não sai no OCR.
    soltos = {re.sub(r"\s", "", l) for l in linhas if re.fullmatch(r"20\s*/\s*\d{2,3}", l)}
    if len(soltos) >= 4:
        linhas = [l for l in linhas if not re.fullmatch(r"20\s*/\s*\d{2,3}", l)]
    for l in linhas:
        sem = re.search(r"SEM CORREC|S/ ?CORREC|WITHOUT CORREC|UNCORRECTED", l)
        com = re.search(r"COM CORREC|C/ ?CORREC|WITH CORREC(?!T)|CORRECTED|WITH GLASSES", l)
        if sem and not com:
            estado = "sem"
        elif com and not sem:
            estado = "com"
        achados = [int(m.group(1)) for m in _VALOR.finditer(l)]
        if not achados and _OLHO.search(l):
            # OCR troca a barra por espaço ou "1" ("OLHO DIREITO: 20 130" = 20/30); só em linha de olho.
            achados = [int(m.group(1)) for m in _VALOR_OCR.finditer(l)]
        for v in achados:
            if 10 <= v <= 400:
                vals.append((estado, v))
    if not vals:
        return None
    sem_v = [v for e, v in vals if e == "sem"]
    com_v = [v for e, v in vals if e == "com"]
    if sem_v and com_v:
        return max(sem_v)
    return max(v for _, v in vals)


def _separar_cor(linhas: list[str]) -> tuple[list[str], list[str]]:
    """Linhas do teste de cores (e as opções logo abaixo do cabeçalho dele) x linhas da acuidade."""
    av, cor = [], []
    resta_cor = 0
    for l in linhas:
        if _COR.search(l):
            cor.append(l)
            resta_cor = 3 if len(l) <= 40 else 0  # cabeçalho curto ("Teste Cromático:"): opções seguem
            continue
        if resta_cor and len(l) <= 40 and not re.search(r"CONCLUS|OBS|LONGE|PERTO|OLHO|EXAME|NECESSIT|RECOMEND|PACIENTE|ACUIDADE|LAUDO", l):
            cor.append(l)
            resta_cor -= 1
            continue
        resta_cor = 0
        av.append(l)
    return av, cor


_OUTRO_ACHADO = re.compile(r"FUNDOSCOP|BIOMICROSCOP|TONOMETR|TONO \d|DECRETO|DETALHES DO EXAME")


def _conclusao_av(linhas: list[str]) -> Optional[str]:
    alt = norm = False
    for l in linhas:
        if _OUTRO_ACHADO.search(l):  # fundo de olho, pressão ocular, texto legal: não é a acuidade
            continue
        if _AV_ALT.search(_NEGACAO.sub(" ", l)):
            alt = True
        elif _AV_NORMAL.search(l):
            norm = True
    return "alterado" if alt else ("normal" if norm else None)


def _conclusao_cor(linhas: list[str]) -> Optional[str]:
    alt = norm = False
    for l in linhas:
        if _COR_ALT.search(_NEGACAO.sub(" ", l)):
            alt = True
        elif _COR_NORMAL.search(l):
            norm = True
    return "alterado" if alt else ("normal" if norm else None)


def _cor_por_colunas(corpo: list[str]) -> Optional[str]:
    """Formulário em colunas NORMAL | ALTERADO: a linha do Ishihara seguida das duas caixas soltas."""
    for i, l in enumerate(corpo):
        if not _COR.search(l):
            continue
        marcas = []
        for m in corpo[i + 1:i + 6]:
            if _MARCA_SO.match(m) or _CAIXA_VAZIA_SO.match(m):
                marcas.append(bool(_MARCA_SO.match(m)))
            elif len(m) > 2 and marcas:
                break
        if len(marcas) >= 2 and marcas[0] != marcas[1]:
            return "normal" if marcas[0] else "alterado"
    return None


def _por_valor(pior: Optional[int]) -> Optional[str]:
    # Régua de Snellen usada pelos próprios laudos: 20/30 ou melhor = boa visão; 20/40 ou pior =
    # "recomenda-se procurar um oftalmologista".
    if pior is None:
        return None
    return "normal" if pior <= 30 else "alterado"


# ---------------------------------------------------------------------------------------------------
# Detalhe (STC-1065, 23/11), lido nas mesmas linhas limpas da acuidade (sem legenda da régua nem opção sem marca):
#   acuidade_od, acuidade_oe   int: denominador do PIOR valor de LONGE de cada olho (20/40 -> 40). Valor de perto
#                              (Jaeger "J1", "PERTO", "NEAR") não conta. Com medidas sem e com correção, valem as
#                              sem correção (mesma regra de acuidade_pior_olho). "AO/ambos" não é de um olho.
#                              Olho = marcador na linha (OD, OE, olho direito/esquerdo, right/left eye) ou na linha
#                              de cima quando ela é só o rótulo ("OLHO DIREITO:" / "20/25"). OCR "20120" = 20/20.
#   acuidade_correcao          "com" | "sem" | None: "CORREÇÃO: SIM" / "(X) COM CORREÇÃO" / só medidas com correção
#                              -> com; "CORREÇÃO: NÃO" / "(X) SEM CORREÇÃO" / só medidas sem correção escritas -> sem.
#                              "Retorna para refazer o exame com correção" e "usa óculos?" não decidem.
#   senso_cromatico_erros      int | None: pranchas erradas, só se escrito ("errou 2 pranchas", "3 erros",
#                              "acertou 12 de 14" -> 2, "acertou todas"/"sem erros" -> 0).
# ---------------------------------------------------------------------------------------------------
_OD = re.compile(r"\bO\.?\s?D\b|OLHO DIREITO|RIGHT EYE|\bDIREITO\s*:")
_OE = re.compile(r"\bO\.?\s?E\b|OLHO ESQUERDO|LEFT EYE|\bESQUERDO\s*:")
_PERTO = re.compile(r"\bJ\s?\d\b|JAEGER|PERTO|\bNEAR\b|LEITURA")
# "( ) Com correção x Sem correção": o Textract escreve a marca como "x" solto, sem os parênteses (54e41257, 23/11).
_CORR_COM = re.compile(r"CORRECAO\s*:\s*SIM|[\(\[]\s*[XK]\s*[\)\]]\s*(?:COM CORREC|C/ ?CORREC)|^COM CORRECAO$|(?:^|\s)X\s+(?:COM CORREC|C/ ?CORREC)")
_CORR_SEM = re.compile(r"CORRECAO\s*:\s*N[AO]O?\b|[\(\[]\s*[XK]\s*[\)\]]\s*(?:SEM CORREC|S/ ?CORREC)|^SEM CORRECAO$|(?:^|\s)X\s+(?:SEM CORREC|S/ ?CORREC)")
# Régua inteira na mesma linha ("(X) 20/20 ( ) 20/25 ... ( ) 20/200"): só vale o valor com a caixa marcada (0a36072f).
_OPCAO_20 = re.compile(r"[\(\[]\s*[XK]?\s*[\)\]]\s*20\s*/\s*\d{2,3}")
_OPCAO_20_MARCADA = re.compile(r"[\(\[]\s*[XK]\s*[\)\]]\s*20\s*/\s*(\d{2,3})")


def _por_olho(linhas: list[str]) -> tuple[Optional[int], Optional[int], Optional[str]]:
    vals: dict[str, list[tuple[Optional[str], int]]] = {"od": [], "oe": []}
    estado = None
    olho_rotulo = None
    corr = None
    corr_perto = None
    zona = "longe"
    for l in linhas:
        if re.search(r"REFAZER|RETORN|\?", l):
            continue
        if re.search(r"^PERTO\b|VISAO DE PERTO|JAEGER", l):
            zona = "perto"
        elif re.search(r"^LONGE\b|VISAO DE LONGE|SNELLEN", l):
            zona = "longe"
        # A correção marcada na visão de perto não é a do exame de longe (d634e65b: longe sem, perto com).
        if _CORR_COM.search(l):
            if zona == "perto":
                corr_perto = corr_perto or "com"
            else:
                corr = corr or "com"
        elif _CORR_SEM.search(l):
            if zona == "perto":
                corr_perto = corr_perto or "sem"
            else:
                corr = corr or "sem"
        sem = re.search(r"SEM CORREC|S/ ?CORREC|WITHOUT CORREC|UNCORRECTED", l)
        com = re.search(r"COM CORREC|C/ ?CORREC|WITH CORREC(?!T)|CORRECTED|WITH GLASSES", l)
        if sem and not com:
            estado = "sem"
        elif com and not sem:
            estado = "com"
        if _PERTO.search(l):
            olho_rotulo = None
            continue
        marcas = sorted([(m.start(), "od") for m in _OD.finditer(l)] + [(m.start(), "oe") for m in _OE.finditer(l)])
        achados = [(m.start(), int(m.group(1))) for m in _VALOR.finditer(l)]
        if len(_OPCAO_20.findall(l)) >= 2:
            achados = [(m.start(), int(m.group(1))) for m in _OPCAO_20_MARCADA.finditer(l)]
            if not achados:
                continue  # linha só com opções vazias (continuação da régua): não muda o olho do rótulo
        elif not achados and (marcas or olho_rotulo):
            achados = [(m.start(), int(m.group(1))) for m in _VALOR_OCR.finditer(l)]
        if not achados:
            olho_rotulo = marcas[-1][1] if marcas and len(l) <= 25 else None
            continue
        for pos, v in achados:
            antes = [o for p, o in marcas if p < pos]
            olho = antes[-1] if antes else (olho_rotulo if not marcas else None)
            # "20/20 EM OLHO DIREITO E <20/400 EM OLHO ESQUERDO": o olho vem logo depois do valor.
            dep = re.match(r"[^A-Z]{0,4}\s*(?:EM|NO|NA|DO|DA)?\s*(OLHO DIREITO|OLHO ESQUERDO|\bO\.?\s?[DE]\b)", l[pos + 5:pos + 30])
            if dep:
                olho = "od" if ("DIREITO" in dep.group(1) or dep.group(1).replace(".", "").replace(" ", "").endswith("D")) else "oe"
            if olho and 10 <= v <= 400:
                vals[olho].append((estado, v))
        olho_rotulo = None

    def pior(lst):
        if not lst:
            return None
        s = [v for e, v in lst if e == "sem"]
        return max(s) if s and any(e == "com" for e, _ in lst) else max(v for _, v in lst)

    todos = vals["od"] + vals["oe"]
    corr = corr or corr_perto
    if corr is None and todos:
        estados = {e for e, _ in todos}
        if estados == {"com"}:
            corr = "com"
        elif estados == {"sem"}:
            corr = "sem"
        elif estados == {"sem", "com"}:
            corr = "com"  # mediu também com correção: usa correção
    return pior(vals["od"]), pior(vals["oe"]), corr


_ERROS = [
    (re.compile(r"ERROU\s*(\d{1,2})\b|(\d{1,2})\s*(?:PRANCHAS?|LAMINAS?|PLACAS?)\s*(?:ERRAD|INCORRET|NAO IDENTIFIC)"
                r"|(\d{1,2})\s*ERROS?\b|ERROS?\s*:\s*(\d{1,2})\b"), None),
    (re.compile(r"ACERT[A-Z]*\s*(\d{1,2})\s*(?:DE|/|EM)\s*(\d{1,2})|(\d{1,2})\s*/\s*(\d{1,2})\s*PRANCHAS"), "dif"),
    (re.compile(r"ACERTOU TODAS|SEM ERROS?\b|NENHUM ERRO|IDENTIFICOU TODAS|TODAS AS (?:PRANCHAS|PLACAS) (?:CORRETAS|IDENTIFICADAS)"), "zero"),
]


def _erros_cor(linhas: list[str]) -> Optional[int]:
    for l in linhas:
        for rx, tipo in _ERROS:
            m = rx.search(l)
            if not m:
                continue
            if tipo == "zero":
                return 0
            g = [x for x in m.groups() if x]
            if tipo == "dif" and len(g) >= 2:
                a, b = int(g[0]), int(g[1])
                if 0 < b <= 38 and a <= b:
                    return b - a
            elif tipo is None and g:
                return int(g[0])
    return None


def ler(texto_entrada: str) -> dict[str, Any]:
    out = _ler_base(texto_entrada)
    linhas = _linhas(texto_entrada)
    janelas = [_limpar(c) for c in _janelas(linhas, _eh_titulo_av)]
    janelas = [c for c in janelas if any(_EVIDENCIA.search(l) for l in c if not _eh_titulo_av(l))]
    av, cor = [], []
    for c in janelas:
        a, k = _separar_cor(c)
        av += a
        cor += k
    od, oe, corr = _por_olho(av) if av else (None, None, None)
    for c in _janelas(linhas, _eh_titulo_cor, contexto=3):
        cor += _limpar(c)
    out.update(acuidade_od=od, acuidade_oe=oe, acuidade_correcao=corr,
               senso_cromatico_erros=_erros_cor(cor) if (cor or out["senso_cromatico"]) else None)
    return out


def debug_janelas(texto_entrada: str) -> list[list[str]]:
    linhas = [l for l in (_norm(x) for x in (texto_entrada or "").splitlines()) if l]
    return [_limpar(c) for c in _janelas(linhas, _eh_titulo_av)]


def _marcas_antes_da_limpeza(l: str, regua: bool = False) -> str:
    """Formas do Textract/RapidOCR que a limpeza de caixas vazias apagaria inteiras (23/11, comparação Textract ×
    RapidOCR, conferidas no PDF):
    - "( ) Com correção x Sem correção" -> "(X) SEM CORRECAO" (54e41257); "( ) COM CORRECAO ( SEM CORRECAO": o X de
      caneta cobriu o parêntese da opção marcada (d634e65b);
    - régua de opções ("(X) 20/20 ( ) 20/25 ... ( ) 20/200", numa linha ou em coluna): só fica o valor marcado, com a
      marca (0a36072f, c1cb0760, 797b4646); a linha que é só opção vazia ou fim de opção quebrada some;
    - "OD: () 20/20" fora de régua: o valor foi escrito à mão e a caixa é só o formato do campo (41aa9fe1)."""
    l = re.sub(r"(?:^|\s)X\s+((?:SEM|COM) CORREC)", r" (X) \1", l)
    l = re.sub(r"[\(\[]\s*[\)\]]\s*(COM|SEM) (CORREC\w*)\s*\((?!\s*[\)X])\s*(SEM|COM) (CORREC)",
               r"( ) \1 \2 (X) \3 \4", l)
    # Caixa depois do rótulo ("Dentro dos padrões de normalidade: (x)", "Alteração da visão para longe: ( )", c1cb0760):
    # vira opção comum, com a caixa na frente; a vazia some.
    # "Orientado procurar oftalmologista para avaliação especializada: ( ) Sim (x) Não" é a negação da recomendação.
    if re.search(r"OFTALMO|PROCURAR|ENCAMINH", l) and re.search(r"[\(\[]\s*[XK]\s*[\)\]]\s*NAO\b", l) \
            and not re.search(r"[\(\[]\s*[XK]\s*[\)\]]\s*SIM\b", l):
        return ""
    m = re.fullmatch(r"(?P<rot>[A-Z][^()\[\]]{2,90}?)\s*:?\s*[\(\[]\s*(?P<x>[XK]?)\s*[\)\]]", l.strip())
    if m and _OLHO.fullmatch(m.group("rot").strip(" :")):
        return m.group("rot").strip() + ":"
    if m:
        return f"(X) {m.group('rot').strip()}" if m.group("x") else ""
    if _OLHO.search(l):
        l = re.sub(r"(?<![\d/])[7Z]0\s*/\s*(\d{2,3})(?![\d/])", r"20/\1", l)
        # Traço do formulário lido como "1/" antes do valor ("OE: 1/20/20" = 20/20; Textract, 24/11).
        l = re.sub(r"(?<![\d/])[1Il|]\s*/\s*(?=20\s*/\s*\d{2,3}(?![\d/]))", "", l)
    opcoes = _OPCAO_20.findall(l)
    if not opcoes:
        return l
    marcados = _OPCAO_20_MARCADA.findall(l)
    if not regua and len(opcoes) == 1 and not marcados and _OLHO.search(l):
        return l
    resto = _OPCAO_20.sub(" ", l)
    resto = re.sub(r"(?<![\d/])20\s*/\s*\d{2,3}(?![\d/])", " ", resto)
    return re.sub(r"\s+", " ", resto + " " + " ".join(f"(X) 20/{v}" for v in marcados)).strip()


def _linhas(texto_entrada: str) -> list[str]:
    # "(×)20/25": o RapidOCR lê a marca como sinal de multiplicação, que a normalização para ASCII apagaria.
    brutas = [_norm(x.replace("×", "X").replace("✕", "X").replace("✗", "X")) for x in (texto_entrada or "").splitlines()]
    regua = sum(bool(_OPCAO_20.search(l)) for l in brutas) >= 3
    # "Exame(s) realizado(s) com lente(s) de correção: ( ) Sim (x) Não" (a resposta pode vir até 3 linhas abaixo):
    # é a condição do exame de longe, como "(X) Sem correção". "Usa lentes de correção" não: usar óculos não diz
    # se o exame foi feito com eles.
    for i, l in enumerate(brutas):
        if re.search(r"REALIZAD\w* COM LENTES?", l):
            trecho = " ".join(brutas[i:i + 4])
            nao = re.search(r"[\(\[]\s*[XK]\s*[\)\]]\s*NAO\b", trecho)
            sim = re.search(r"[\(\[]\s*[XK]\s*[\)\]]\s*SIM\b", trecho)
            if nao and not sim:
                brutas[i] = "(X) SEM CORRECAO"
            elif sim and not nao:
                brutas[i] = "(X) COM CORRECAO"
        # "Orientado procurar oftalmologista para / (x) Não / avaliação especializada" em linhas separadas (797b4646).
        elif re.search(r"PROCURAR\w* (?:UM |O )?OFTALMO|ENCAMINHA\w* (?:AO |PARA )?OFTALMO", l):
            trecho = " ".join(brutas[i:i + 3])
            if re.search(r"[\(\[]\s*[XK]\s*[\)\]]\s*NAO\b", trecho) and not re.search(r"[\(\[]\s*[XK]\s*[\)\]]\s*SIM\b", trecho):
                brutas[i] = ""
    return [l for l in (_marcas_antes_da_limpeza(x, regua) for x in brutas) if l]


def _ler_base(texto_entrada: str) -> dict[str, Any]:
    linhas = _linhas(texto_entrada)
    out: dict[str, Any] = {"acuidade_visual": None, "acuidade_pior_olho": None, "senso_cromatico": None}

    janelas = [_limpar(c) for c in _janelas(linhas, _eh_titulo_av)]
    janelas = [c for c in janelas if any(_EVIDENCIA.search(l) for l in c if not _eh_titulo_av(l))]

    cor_linhas: list[str] = []
    if janelas:
        av_linhas: list[str] = []
        for c in janelas:
            a, k = _separar_cor(c)
            av_linhas += a
            cor_linhas += k
        pior = _valores(av_linhas)
        escrita = _conclusao_av(av_linhas)
        out["acuidade_pior_olho"] = pior
        out["acuidade_visual"] = escrita or _por_valor(pior) or "sem_conclusao"
    else:
        # Sem janela de laudo: resultado relatado na ficha médica ("realizou acuidade visual com
        # resultado de 20/40 ... e 20/200 ..."). Só o valor; a conclusão sai pela régua.
        for k, l in enumerate(linhas):
            if _RELATO.search(l) or (re.search(r"ACUIDADE VISUAL", l) and k + 1 < len(linhas)
                                     and _RELATO.search(l + " " + linhas[k + 1])):
                trecho = _IGUAL_SUPERIOR.sub(" ", l + " " + (linhas[k + 1] if k + 1 < len(linhas) else ""))
                if len(_VALOR.findall(trecho)) >= 3 and _LEGENDA.search(trecho):
                    continue
                pior = _valores([trecho])
                if pior is not None:
                    out["acuidade_pior_olho"] = pior
                    out["acuidade_visual"] = _por_valor(pior)
                    break

    # Laudo de Ishihara separado (fora da janela da acuidade).
    for c in _janelas(linhas, _eh_titulo_cor, contexto=3):
        cor_linhas += _limpar(c)
    out["senso_cromatico"] = _conclusao_cor(cor_linhas)
    if out["senso_cromatico"] is None:
        for c in _janelas(linhas, _eh_titulo_av) + _janelas(linhas, _eh_titulo_cor):
            r = _cor_por_colunas(c)
            if r:
                out["senso_cromatico"] = r
                break
    return out
