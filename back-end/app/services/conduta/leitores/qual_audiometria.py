"""
Conclusão do laudo de AUDIOMETRIA no texto de entrada (OCR do prontuário, já sem a carta de
encaminhamento). Determinístico: regex, sem LLM e sem rede.

    ler(texto) -> {"audiometria": "alterado" | "normal" | "sem_conclusao" | None}

None = nenhum laudo de audiometria no texto. Regras de decisão:

1. Janela: abre num título de laudo de audiometria (AUDIOMETRIA, AUDIOGRAMA, AVALIAÇÃO AUDIOLÓGICA,
   FICHA AUDIOMÉTRICA, PARECER AUDIOLÓGICO...) e vai até o título de outro exame/documento (ASO,
   ECG, questionário, declaração...) ou 200 linhas. Item de lista NÃO abre janela: linha com data,
   linha bilíngue do ASO (PURE TONE), ou vizinha de outro nome de exame (lista do ASO / guia de
   preparo). Janela sem nenhum marcador de laudo (audiômetro, limiar, dB, Hz, orelha, OD/OE, fono,
   conclusão...) é descartada.
2. Dentro da janela saem antes da leitura: linhas de meatoscopia (e os OD/OE logo abaixo), de
   declaração/termo ("Declaro...", "estou ciente"), de critério/legenda (Lloyd, Silman, OMS,
   "normal até 25 dB"), opções de formulário sem marca ("( ) Alterado") e listas de opções soltas
   ("Normal / Estável / Alterado / Agravamento" em linhas seguidas, cuja marca o OCR perdeu).
3. Alterado: perda auditiva, P.A. de grau, PANS/PAIR/PAINPSE, disacusia, hipoacusia, rebaixamento,
   entalhe, alteração/alterado(s) sem negação, e "normal ... EXCETO em 4 e 8 kHz" (inclusive o OCR
   torto "exato ... 4 kHz"). "NÃO sugestivo de PAIR" / "perda NÃO induzida por NPSE" é alterado
   (Portaria 19: perda presente, só não ocupacional). Alterado vence normal (um ouvido basta, e
   vale entre laudos do mesmo documento).
4. Normal: limiares dentro dos padrões/normais, audiometria/audição normal, normoacusia, "(X) Normal",
   "Direita: Normal". Sem nenhum dos dois -> "sem_conclusao". Não se lê a tabela de limiares: o OCR
   solta os números da grade (eixo -10..120 dB, frequências, % de logoaudiometria) sem a coluna a
   que pertencem, então "limiar > 25 dB" não é seguro.
5. Declaração de Ciência de ALTERAÇÃO auditiva ("estou ciente de apresentar alteração auditiva,
   detectada através do Exame Audiométrico") é só FALLBACK: vale alterado quando nenhum laudo deu
   conclusão (sem_conclusao ou laudo não achado). Não vence o laudo: em 22 dos 835 documentos ela
   aparece junto de laudo normal (17 da mesma clínica, que parece anexar o termo a todo exame); nos
   outros 114 em que coexistem, o laudo já é alterado. "Declaro que fui orientado quanto aos cuidados
   com a audição" e "Declaro estar ciente do resultado" são termos neutros e nunca contam. A conclusão
   do ASO (Apto/Inapto) nunca é lida: o ASO é limite de janela.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().upper()
    t = re.sub(r"\s+", " ", t).strip()
    return t.lstrip("#* ").strip()


_TITULO = re.compile(
    r"AUDIOMETRI|AUDIOME ?TRIA|AUDIOMETRICA|AUDIOGRAMA|AVALIACAO AUDIOLOGICA|LAUDO AUDIOLOGICO"
    r"|PARECER AUDIOLOGICO|PARECER DO FONOAUDIOLOG|EXAME AUDIOMETRICO|AUDIOMETRIA DE TONS"
)
# Não é título de laudo: logoaudiometria/weber (campos internos), pergunta de questionário,
# frase corrida de declaração, linha do audiômetro.
_NAO_TITULO = re.compile(
    r"LOGOAUDIOM|OGOAUDIOM|WEBER|\?|REALIZAD|DETECTAD|CIENTE|AUDIOMETRO|AUDIOMETRICOS ANTERIORES"
    r"|EXAMES DE AUDIOMETRIA|TRACADO|CURVA AUDIOMETRICA|CABINE"
)
_DATA = re.compile(r"\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{2,4}|\d{1,2}/\s*\+\s*\d{2}|\b\d{2,3}\+ ?\d{2}\b")
_OUTRO_EXAME = re.compile(
    r"HEMOGRAMA|GLICOSE|GLICEMIA|ACUIDADE|ACUITY|CLINICO|CLINICAL|ODONTOLOG|PARASITOLOG|ELETROCARDIO|"
    r"\bECG\b|ESPIROMETR|SPIROMETR|RADIOGRAF|\bRX\b|RAIO ?X|TGO|TGP|CREATININA|UREIA|LIPIDOGRAMA|ROMBERG|"
    r"ELETROENCEFALO|\bEEG\b|PSICO|TOXICOLOG|ACIDO URICO|GAMA ?GT|\bGGT\b|EXAME CLINICO|AVALIACAO PSICO"
)
_FIM_JANELA = re.compile(
    r"ATESTADO DE SAUDE OCUPACIONAL|\bASO\b|CONCLUSAO ?/ ?CONCLUSION|APTO ?/ ?FIT|"
    r"ELETROCARDIOGRAM|ELECTROCARDIOGRAM|ESPIROMETRI|SPIROMETR|HEMOGRAMA|ACUIDADE VISUAL|VISUAL ACUITY|"
    r"RADIOGRAFIA|RAIO ?X|ODONTOLOG|PSICOSSOCIAL|AVALIACAO PSICOLOG|ANAMNESE|QUESTIONARIO|FICHA CLINICA|"
    r"EXAME CLINICO|ELETROENCEFALO|TOXICOLOG|PRONTUARIO|DECLARACAO|TERMO DE|ENCAMINHAMENTO|"
    r"RESULTADO DE EXAMES|ORIENTACOES DE PREPARO|LAUDO DE (?!AUDIO)|FICHA MEDICA|LABORATORIO|ANALISES CLINICAS"
    r"|ESCLARECIMENTO|GLICEMIA|PSICO|EMOCIONA"
)
_MARCADOR_LAUDO = re.compile(
    r"AUDIOMETRO|LIMIAR|\bDB\b|\bHZ\b|KHZ|ORELHA|OUVIDO|\bOD\b|\bOE\b|\bVA\b|\bVO\b|MEATOSCOPIA|FONOAUD"
    r"|LOGOAUDIO|REPOUSO|CONCLUS|PARECER|RESULTADO|LAUDO|PERDA|NORMAL|ALTERA"
)
MAX_LINHAS = 200

# Linhas que nunca são conclusão.
_MEATO = re.compile(r"MEATOSCOPIA|OTOSCOPIA|INSPECAO DO (?:MEATO|CONDUTO)")
# Achado/opção da meatoscopia, não do limiar: "Obstrução por cerúmen", "Alteração em membrana".
_MEATO_ITEM = re.compile(r"CERUME|MEMBRANA|TIMPAN|OBSTRUCAO|\bMAE\b|CONDUTO")
_DECLARACAO = re.compile(r"\bDECLAR|CIENTE|ORIENTAD[OA]|TERMO DE")
# Legenda de grau ("normal até 25 dB", "leve 26 a 40 dB") sai sempre; citação de critério (Silman,
# Lloyd) sai só quando a linha não é ela mesma a conclusão ("perda ... segundo Silman").
_FAIXA_DB = re.compile(r"ATE \d+ ?DB|\d+ ?(?:A|-|E) ?\d+ ?DB|[<>]=? ?\d+ ?DB")
_CITACAO = re.compile(r"LLOYD|KAPLAN|SILMAN|SILVERMAN|CARHART|CRITERIO|CLASSIFICACAO|\bOMS\b|JERGER|REFERENCIA")
# Anamnese embutida na ficha ("Tem algum caso de surdez na família? (X) Não").
_PERGUNTA = re.compile(r"\?|^(?:TEM|TEVE|JA|VOCE|SENTE|POSSUI|FAZ|USA|USOU|TRABALHA|TRABALHOU|EXPOSTO|EXPOSICAO|HISTORIA|ANTECEDENTE|QUEIXA)\b")
_ROTULO_VAZIO = re.compile(r"\b[A-Z]+:\s*[\(\[\{]\s*[\)\]\}]")  # "Alterações: ( )"
_CAIXA_VAZIA = re.compile(r"[\(\[\{]\s*[\)\]\}]\s*[A-Z][A-Z ./]{0,80}")  # "{)" = "( )" no OCR (23/11)
# Rótulo de formulário sem valor ("PERDA AUDITIVA DE GRAU:", "CONCLUSÃO:"): não é resultado.
_ROTULO_SEM_VALOR = re.compile(r"^[A-Z][A-Z .()/-]{0,40}:\s*$")
_OPCAO = re.compile(
    r"(?:NORMAL|ALTERAD[OA]S?|ESTAVEL|AGRAVAMENTO|DESENCADEAMENTO|PIORA|MELHORA|REFERENCIAL|SEQUENCIAL"
    r"|(?:LIMIARES )?ACEITAVEIS|(?:NAO )?SUGESTIV[OA]S? DE (?:PAIR|PAINPSE|PERDA[A-Z ]*)|CONDUTIVA|NEUROSSENSORIAL"
    r"|MISTA|LEVE|MODERAD[OA]|SEVER[OA]|PROFUND[OA]|SIM|NAO"
    r"|BILATERAL(?:MENTE)?|(?:SOMENTE )?A (?:ESQUERDA|DIREITA)|UNILATERAL|COM ALTERACAO|SEM ALTERACAO)"
)

_NEGACAO = re.compile(r"\b(?:SEM|AUSENCIA DE|NAO HA|NAO APRESENTA|NAO FORAM|NAO SE OBSERV\w*|NEGA)\b[^.;]{0,50}")
_EXCETO = re.compile(r"\b(?:EXCETO|EXCEPTO|EXETO|EXATO|EXCETUANDO|COM EXCECAO)\b[^;|]{0,60}?(?:\d|HZ|KHZ|KG|FREQ|\bOD\b|\bOE\b|AGUD)")
_ALTERADO = re.compile(
    r"PERDA AUDITIVA|PERDA (?:DE GRAU|NEUROSSENSORIAL|CONDUTIVA|MISTA|LEVE|MODERADA|SEVERA|PROFUNDA)"
    r"|\bP\. ?A\.? ?(?:DE GRAU|N\.? ?S\b|NEURO|CONDUT|MIST)|\bPANS\b|\bPAIR\b|PAINPSE|DISACUSIA|HIPOACUSIA"
    r"|\b(?!PROVA)P\w{1,3}A \w{0,2}AUDIT|SENSORIO ?NEU|NEUROSS?ENSORIAL|SENSORIONEMAL|SENSORIOHURRAL"
    r"|REBAIXAMENTO|ENTALHE|ALTERAD[OA]S?\b|ALTERACA?O|ALTERACOES|ANACUSIA"
    r"|PER[DQO]A ?AUD|CONDUTIV|NEUROSS|\bN.{0,3}[UI].{0,2}S{1,2}.{0,3}SO[IR]"  # OCR: "PERQAAUDITIVA", "NEUESSENSOIIAL"
)
# Rodapé/legenda de critério que cita "perda auditiva" sem ser conclusão.
# Ancorado no começo: "Perda auditiva neurossensorial leve bilateral de acordo com a classificação..." é conclusão.
_RODAPE = re.compile(r"^\W*(?:\d+\W*)?(?:\w{0,4}\)?\W*)?(?:REFER\w*\s*QUANTO|QUANTO AO (?:TIPO|GRAU)|REFERENCIAS? CIENTIFICAS"
                     r"|CLASSIFICA\w* D[OAE]S? (?:GRAU|TIPO|IPRF|PERDA))|CERTIFICO QUE")
_NORMAL = re.compile(
    r"DENTRO D[OA]S? (?:PADR|LIMITE|NORMALIDADE|NORMAIS)|LIMIARES (?:AUDITIVOS |TONAIS )?(?:NORMAIS|DENTRO)"
    r"|AUDIOME ?TRIA(?: \|)? NORMAL\b|LAUDO \| NORMAL\b|AUDICAO NORMAL|AUDIOGRAMA NORMAL|NORMOACUSIA|EXAME NORMAL|\(\s*X\s*\)\s*NORMAL"
    r"|(?:DIREIT[AO]|ESQUERD[AO]|\bOD|\bOE|LAUDO|RESULTADO|CONCLUSAO|PARECER)\s*:?\s*NORMAL\b|LIMIARES AUDITIVOS NORMAIS"
    r"|PADRAO DE NORMALIDADE|AUDICAO DENTRO|DE ACORDO COM (?:O PADRAO DE |A )?NORMALIDADE"
    r"|LIMI(?:TES|ARES) ACEITAVEIS"  # Portaria 19: "dentro dos limites aceitáveis"
    # OCR torto (23/11): "DENTRO ADROES DA NORMALIDADE", "DENTRODOS PADROES", "OENTRO DOS", "FADROES DE NORMALDADE"
    r"|[DO]ENTRO\W?\s?(?:D[OA]S?)?\W?\s?\w{0,2}ADR\w{1,3}\b|\bDA ?NORMAL\w*DADE|NORMALDADE|DANORMALIDADE"
    r"|\b\w{0,2}IMIA\w{1,4} (?:\w+ )?NORM\w*"  # OCR torto: "LIMIARES TONAIN NORMAIN"
)
_CIENCIA_ALTERACAO = re.compile(
    r"DECLARACAO DE CIENCIA DE ALTERACAO AUDITIVA|CIENTE DE APRESENTAR ALTERACAO AUDITIVA"
)


# Ficha sem título legível: o cabeçalho da grade ou do resultado abre a janela.
_TITULO_GRADE = re.compile(r"LIMIAR (?:OD|OE)|CURVA AUDIOMETRICA:")


def _eh_titulo(linhas: list[str], i: int) -> bool:
    n = linhas[i]
    if _TITULO_GRADE.fullmatch(n):
        return True
    if not _TITULO.search(n) or _NAO_TITULO.search(n) or len(n) > 80:
        return False
    if _DATA.search(n) or "PURE TONE" in n:
        return False  # item da lista do ASO
    viz = [linhas[j] for j in range(max(0, i - 2), min(len(linhas), i + 3)) if j != i]
    if any("PURE TONE" in v for v in viz):
        return False
    # Lista de exames (guia de preparo, pedido): vizinho imediato é outro nome de exame.
    if any(_OUTRO_EXAME.search(v) and len(v) <= 60 for v in viz[1:3]):
        return False
    return True


def _janelas(linhas: list[str]) -> list[tuple[int, int]]:
    out = []
    for i in range(len(linhas)):
        if not _eh_titulo(linhas, i):
            continue
        fim = min(len(linhas), i + MAX_LINHAS)
        for j in range(i + 1, fim):
            if len(linhas[j]) <= 90 and _FIM_JANELA.search(linhas[j]) and not _TITULO.search(linhas[j]):
                fim = j
                break
        if any(_MARCADOR_LAUDO.search(linhas[k]) for k in range(i + 1, fim)):
            out.append((i, fim))
    return out


def _linhas_lidas(linhas: list[str], a: int, b: int) -> list[str]:
    seg = linhas[a:b]
    fora = [False] * len(seg)
    for k, n in enumerate(seg):
        if _MEATO.search(n):
            for m in range(k, min(len(seg), k + 4)):
                if m == k or re.match(r"(?:OD|OE|O\.D|O\.E|ORELHA)\b|(?:S\.? ?)?ALT\.?$|NORMAL$", seg[m]):
                    fora[m] = True
        if _DECLARACAO.search(n):  # o termo continua nas linhas seguintes
            for m in range(k, min(len(seg), k + 4)):
                fora[m] = True
        elif (_FAIXA_DB.search(n) or _PERGUNTA.search(n) or _MEATO_ITEM.search(n) or n.count(";") >= 2
              or _ROTULO_SEM_VALOR.match(n)):
            # n.count(";"): linha de opções "do tipo: ( ) neurossensorial; ( ) condutiva; ( ) mista;"
            # em que o OCR some com a caixa marcada e às vezes com a vazia -> ilegível, sai inteira.
            fora[k] = True
        elif _CITACAO.search(n) and not re.search(r"PERDA|LIMIAR|AUDIOMETRIA|AUDICAO", n):
            fora[k] = True
    opc = [bool(_OPCAO.fullmatch(n)) for n in seg]
    for k in range(len(seg)):
        if opc[k] and ((k > 0 and opc[k - 1]) or (k + 1 < len(seg) and opc[k + 1])):
            fora[k] = True
    return [_CAIXA_VAZIA.sub(" ", _ROTULO_VAZIO.sub(" ", n)) for k, n in enumerate(seg) if not fora[k]]


def _conclusao(lidas: list[str]) -> str:
    # 23/11: o rodapé "Referência quanto ao tipo de PERDA AUDITIVA, Silman e Silverman (1997). Certifico..."
    # passava pelo filtro de citação (tem "perda") e virava "alterado" em laudo normal: na amostra de 400 da
    # base de 10 mil, 115 dos 222 "alterado" eram "dentro dos padrões da normalidade em ambas as orelhas".
    texto = " | ".join(l for l in lidas if not _RODAPE.search(l))
    if _EXCETO.search(texto):
        return "alterado"
    if _ALTERADO.search(_NEGACAO.sub(" ", texto)):
        return "alterado"
    if _NORMAL.search(texto):
        return "normal"
    return "sem_conclusao"


# ---------------------------------------------------------------------------------------------------
# Detalhe do laudo (STC-1065, 23/11): tipo, grau, lado e agravamento. Lidos nas MESMAS linhas limpas da
# conclusão (_linhas_lidas: sem meatoscopia, declaração, legenda de dB, pergunta, opção sem marca).
#   audiometria_tipo          pair | neurossensorial_outra | condutiva | mista | normal | None
#   audiometria_grau          leve | moderada | severa | profunda | None
#   audiometria_lado          bilateral | od | oe | None
#   audiometria_agravamento   sim | nao | None
# Regras:
# - Só valem linhas de conclusão: as de citação de critério (Silman, Lloyd, OMS, Davis...) e as de legenda
#   de grau ("LV LEVE", "MD MODERADA", "GRAU: 0 - NORMAL") nunca contam, nem quando citam "perda auditiva".
# - Tipo: PAIR/PAINPSE afirmado ("sugestivo de PAIR", "P.A.I.N.P.S.E.") -> pair; "NÃO sugestivo de PAIR" não
#   é pair (a perda segue com o tipo escrito). Mista, ou condutiva + neurossensorial no mesmo laudo -> mista;
#   condutiva -> condutiva; neurossensorial/sensorioneural/PANS (ou perda em 3-8 kHz sem tipo, "entalhe")
#   -> neurossensorial_outra. Laudo normal -> "normal". Perda sem tipo escrito -> None.
# - Grau: palavra de grau na mesma linha de uma perda/PAIR ("perda ... de grau leve", "PAINPSE - leve",
#   "leve a moderada" -> o pior). "Moderadamente severa" -> severa. Vale o pior grau do documento.
# - Lado: perda em "ambas as orelhas", "bilateral", ou perda escrita para OD e para OE -> bilateral; só uma
#   orelha (OD:/OE:, "orelha direita", "à direita") -> od | oe.
# - Agravamento (NR-7 Anexo II, audiograma sequencial): "sugestivo de desencadeamento/agravamento" -> sim;
#   "estável em relação ao exame de referência", "sem agravamento", "não sugestivo de desencadeamento/
#   agravamento" -> nao. Título "Diagnóstico evolutivo" e orientação ("para que não haja desencadeamento ou
#   agravamento") não decidem nada; sem frase explícita -> None.
# Limiares por frequência não são lidos (o OCR perde o gráfico e solta os números sem coluna; ver regra 4).
# ---------------------------------------------------------------------------------------------------
_LEGENDA = re.compile(r"^(?:LV|MD|SV|PR|MS)\s+(?:LEVE|MODERAD|SEVER|PROFUND)|^GRAU\s*:?\s*\d|DAVIS|\bOMS\b|^(?:\d+ )*(?:LEVE|MODERAD\w*|SEVER\w*|PROFUND\w*)(?: \d+)*$")
_PERDA = re.compile(r"PERDA|\bP\.? ?A\.? ?(?:I\.? ?N\.? ?)?P\.? ?S\.? ?E\b|PAINPSE|\bPAIR\b|\bPANS\b|NEURO ?S+ENS|SENSORIO ?-?NEU|SENSORIONE"
                    r"|CONDUTIV|\bMISTA\b|DISACUSIA|HIPOACUSIA|REBAIXAMENTO|ENTALHE|ANACUSIA")
_PAIR = re.compile(r"\bPAIR\b|PAINPSE|P\.? ?A\.? ?I\.? ?N\.? ?[PR]\.? ?S\.? ?E|INDUZIDA POR (?:NIVEIS|NPS|RUIDO)|INDUZIDA PELO RUIDO")
_NAO_PAIR = re.compile(r"NAO (?:E |EH )?SUGESTIV\w* DE[^|]{0,15}(?:\bPAIR\b|PAINPSE|P\.? ?A\.? ?[IL]|PERDA AUDITIVA INDUZIDA)"
                       r"|NAO (?:INDUZIDA|OCUPACIONAL|RELACIONADA)")
_MISTA = re.compile(r"\bMISTA\b")
_CONDUTIVA = re.compile(r"CONDUTIV")
_NEURO = re.compile(r"NEURO ?S+|\bN.{0,3}[UI].{0,2}S{1,2}.{0,3}SO[IR]|SENSORIO ?-?NEU|SENSORIONE|SENSORIONEMAL|SENSORIOHURRAL"
                    r"|\bPANS\b|ENTALHE"
                    r"|(?:PERDA|REBAIXAMENTO)[^|]{0,40}\b[3-8] ?(?:K ?HZ|000)")
_GRAU = [("profunda", re.compile(r"PROFUND")), ("severa", re.compile(r"SEVER")),
         ("moderada", re.compile(r"MODERAD|MEDERA")), ("leve", re.compile(r"\bLEVE"))]
_AMBAS = re.compile(r"AMBAS|BILATERA|AMBOS OS OUVIDOS|\bA\.? ?O\.?\b|BIAURAL|BINAURAL")
_OD = re.compile(r"\bO\.? ?D\b|ORELHA DIREIT|OUVIDO DIREIT|A DIREITA\b|\bDIREITA\s*:")
_OE = re.compile(r"\bO\.? ?E\b|ORELHA ESQUERD|OUVIDO ESQUERD|A ESQUERDA\b|\bESQUERDA\s*:")
_AGRAVA_SIM = re.compile(r"(?<!NAO )SUGESTIV\w* DE (?:DESENCADEAMENTO|AGRAVAMENTO)|\(\s*X\s*\)\s*(?:DESENCADEAMENTO|AGRAVAMENTO)"
                         r"|(?<!NAO )HOUVE (?:DESENCADEAMENTO|AGRAVAMENTO)|(?:COM|APRESENTA) AGRAVAMENTO|PIORA (?:EM RELACAO|DOS LIMIARES)")
_AGRAVA_NAO = re.compile(r"ESTAVEL EM RELA|NAO SUGESTIV\w* DE (?:DESENCADEAMENTO|AGRAVAMENTO)|SEM (?:SINAIS DE )?(?:DESENCADEAMENTO|AGRAVAMENTO)"
                         r"|NAO HOUVE (?:DESENCADEAMENTO|AGRAVAMENTO)|\(\s*X\s*\)\s*ESTAVEL|LIMIARES ESTAVEIS|SEM (?:ALTERACAO|MUDANCA) SIGNIFICATIVA")
_ORIENTA = re.compile(r"PARA QUE NAO HAJA|EVITAR|PREVEN|ORIENT")


def _detalhe(lidas: list[str], conclusao: str) -> dict[str, Optional[str]]:
    concl = [l for l in lidas if not _LEGENDA.search(l) and not _RODAPE.search(l)]
    perda = [l for l in concl if _PERDA.search(l)]
    texto = " | ".join(perda)
    tipo = None
    if perda:
        sem_neg = _NEGACAO.sub(" ", _NAO_PAIR.sub(" ", texto))
        if _PAIR.search(sem_neg):
            tipo = "pair"
        elif _MISTA.search(sem_neg) or (_CONDUTIVA.search(sem_neg) and _NEURO.search(sem_neg)):
            tipo = "mista"
        elif _CONDUTIVA.search(sem_neg):
            tipo = "condutiva"
        elif _NEURO.search(sem_neg):
            tipo = "neurossensorial_outra"
    if tipo is None and conclusao == "normal":
        tipo = "normal"
    grau = None
    for nome, rx in _GRAU:
        if any(rx.search(l) for l in perda) or any(re.search(r"GRAU\W{0,3}(?:DE )?\W{0,2}$", concl[k]) and rx.search(concl[k + 1])
                                                    for k in range(len(concl) - 1)):
            grau = nome
            break
    lado = None
    if perda:
        if _AMBAS.search(texto):
            lado = "bilateral"
        else:
            od, oe = any(_OD.search(l) for l in perda), any(_OE.search(l) for l in perda)
            lado = "bilateral" if od and oe else "od" if od else "oe" if oe else None
    agrava = None
    t2 = " | ".join(l for l in concl if not _ORIENTA.search(l))
    if _AGRAVA_SIM.search(t2):
        agrava = "sim"
    elif _AGRAVA_NAO.search(t2):
        agrava = "nao"
    return {"audiometria_tipo": tipo, "audiometria_grau": grau, "audiometria_lado": lado,
            "audiometria_agravamento": agrava}


_ORDEM_TIPO = ["pair", "mista", "condutiva", "neurossensorial_outra", "normal"]
_ORDEM_GRAU = ["profunda", "severa", "moderada", "leve"]


def _juntar(detalhes: list[dict]) -> dict[str, Optional[str]]:
    out: dict[str, Optional[str]] = {"audiometria_tipo": None, "audiometria_grau": None, "audiometria_lado": None,
                                     "audiometria_agravamento": None}
    tipos = [d["audiometria_tipo"] for d in detalhes if d["audiometria_tipo"]]
    if tipos:
        out["audiometria_tipo"] = min(tipos, key=_ORDEM_TIPO.index)
    graus = [d["audiometria_grau"] for d in detalhes if d["audiometria_grau"]]
    if graus:
        out["audiometria_grau"] = min(graus, key=_ORDEM_GRAU.index)
    lados = {d["audiometria_lado"] for d in detalhes if d["audiometria_lado"]}
    if lados:
        out["audiometria_lado"] = "bilateral" if "bilateral" in lados or lados == {"od", "oe"} else lados.pop()
    ag = [d["audiometria_agravamento"] for d in detalhes if d["audiometria_agravamento"]]
    if ag:
        out["audiometria_agravamento"] = "sim" if "sim" in ag else "nao"
    return out


def debug_janelas(texto_entrada: str) -> list[list[str]]:
    linhas = [n for n in (_norm(l) for l in (texto_entrada or "").splitlines()) if n]
    return [_linhas_lidas(linhas, a, b) for a, b in _janelas(linhas)]


def ler(texto_entrada: str) -> dict[str, Optional[str]]:
    linhas = [n for n in (_norm(l) for l in (texto_entrada or "").splitlines()) if n]
    lidas = [_linhas_lidas(linhas, a, b) for a, b in _janelas(linhas)]
    res = [_conclusao(l) for l in lidas]
    det = _juntar([_detalhe(l, r) for l, r in zip(lidas, res)])
    if "alterado" in res:
        out = {"audiometria": "alterado"}
    elif "normal" in res:
        out = {"audiometria": "normal"}
    elif _CIENCIA_ALTERACAO.search(" ".join(linhas)):
        out = {"audiometria": "alterado"}
    else:
        out = {"audiometria": "sem_conclusao" if res else None}
    if out["audiometria"] != "normal" and det["audiometria_tipo"] == "normal":
        det["audiometria_tipo"] = None  # outro laudo do documento é alterado: o tipo da perda não foi escrito
    if out["audiometria"] == "normal":
        det.update(audiometria_tipo="normal", audiometria_grau=None, audiometria_lado=None)
    out.update(det)
    return out
