"""
Conclusão do laudo de ESPIROMETRIA lida do texto de OCR do prontuário (sem LLM, sem rede).

Saída: {"espirometria": "alterado" | "normal" | "sem_conclusao" | None}
  None           não há laudo de espirometria no texto;
  sem_conclusao  há laudo, mas nenhuma frase de conclusão reconhecida.

Regras:
- Lê só a JANELA do laudo: de uma linha com o nome do exame até 180 linhas, parando no título de outro
  exame, na ficha/ASO ("Conclusion", "Apto") ou em outro documento (declaração, termo, questionário).
- Item da lista do ASO (nome do exame com data) não abre janela; pergunta de questionário ("já realizou
  espirometria?") e a "Declaração de reconhecimento de alteração respiratória" também não.
- Texto padrão ("a interpretação do resultado deste exame e a conclusão diagnóstica são atos médicos",
  "uma espirometria alterada ou normal não exclui...") sai antes de procurar conclusão.
- Formulário "( X) Normal ( ) Alterado": vale só a opção marcada; caixa vazia não conta.
- A tabela de índices (FVC/CVF/FEV1/VEF1 no início da linha) também abre janela: há laudo cujo
  título o OCR perdeu. Janela que só tem o nome do exame (lista do ASO) não conta como laudo.
- A conclusão do médico (até 4 linhas após "Conclusão", "Laudo", "Análise médica", "Resultado:"...)
  vence a interpretação automática do aparelho ("Interpretação: Restrição moderada"); se o campo do
  médico está vazio, vale a do aparelho. Dentro do mesmo nível, alterado vence normal.
- Cada linha é lida junto com a seguinte (o OCR quebra "...DENTRO DOS LIMITES DA" / "NORMALIDADE.").
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", t).strip().lstrip("#* ").strip()


_TITULO = re.compile(r"ESPIROM|SPIROM|SPIRO ?ME ?TRY|PROVA DE FUNCAO PULMONAR|TESTE'? ?DE FUNCAO PULMONAR"
                     r"|FUNCAO PULMONAR ESPIRO|PULMONAR ESPIRO|FUNCOES PULMONARES|RELATORIO DE CAPACIDADE VITAL|LUNG FUNCTION"
                     r"|LUNG VOLUME TEST")
# Laudo sem título legível (cabeçalho perdido no OCR): a tabela de índices também abre janela.
_INDICE = re.compile(r"^(?:FVC|CVF|FEV ?1|VEF ?1)\b")
_DATA = re.compile(r"\d{1,2} ?[/.-] ?(?:\d{1,2}|[A-Z]{3})\.? ?[/.-]? ?\d{2,4}|\b\d{1,2} ?[A-Z]{3}\.? ?\d{4}\b"
                   r"|\b[A-Z]{3}\.? \d{4}\b|\d{1,2}/\d{1,2}\b")
# Linhas com o nome do exame que não são laudo.
_NAO_LAUDO = re.compile(r"\?|DETECTADO NO EXAME COMPLEMENTAR|JA REALIZOU|RECONHECIMENTO DE ALTERACAO"
                        r"|DEVE SER ANALISADO|MEDICO ASSISTENTE")
# Fim da janela: título de outro exame (linha curta) ou outro documento.
_OUTRO_EXAME = re.compile(
    r"AUDIOMETR|AUDIOLOG|AUDIOGRAMA|PURE TONE|ELETROCARDIO|ELECTROCARDIO|\bECG\b|ACUIDADE VISUAL|VISUAL ACUITY"
    r"|AVALIACAO DE VISAO|OFTALMO|RADIOGRAF|RAIOS? ?-?X|COLUNA (?:CERVICAL|LOMBAR|LOMBO|TORACICA)|\bRX\b|TELERRADIO|TELERADIO|HEMOGRAMA|BLOOD COUNT|GLICEMIA"
    r"|GLICOSE|GLUCOSE|HEMOGLOBINA|COLESTEROL|TRIGLICER|\bTGO\b|\bTGP\b|CREATININA|ELETROENCEFALO|\bEEG\b"
    r"|PSICOLOG|PSYCHOLOG|TOXICOLOG|CLINICO OCUPACIONAL|CLINICAL EXAM|EXAME CLINICO|ANAMNESE|ATESTADO DE SAUDE"
    r"|FICHA (?:MEDICA|CLINICA)|QUESTIONARIO|DECLARACAO|TERMO DE|LABORATORIO|LABORATORIAL|EQUILIBRIO|ESCALA DE BERG")
_FIM_ASO = re.compile(r"^EXAME ?: (?!.*(?:ESPIRO|SPIRO|PULMONAR))|^EXAME REALIZADO$|CONCLUSION|\bAPTO\b|\bINAPTO\b|\bFIT\b|UNFIT|RECONHECIMENTO DE ALTERACAO")
JANELA = 180
# Prova de que a janela é laudo, e não só o nome do exame numa lista: índice espirométrico, curva,
# cabeçalho de laudo ou frase de conclusão.
_EVIDENCIA = re.compile(r"\bCVF\b|\bFVC\b|\bVEF ?1|\bFEV ?1|TIFFENEAU|\bPEF|\bFEF|PREVIST|PREDICTED|ACCEPTABLE"
                        r"|ACEITAVE|ESFORCOS|INTERPRETACAO|CONCLUS|ANALISE MEDICA|LAUDO|PNEUMOLOG|BRONCODILATADOR")

# Texto padrão que cita normal/alterado sem ser conclusão.
_BOILERPLATE = re.compile(
    r"A INTERPRETACAO DO RESULTADO DESTE EXAME[^.]*(?:\.|$)|CONCLUSAO DIAGNOSTICA SAO ATOS MEDICOS[^.]*"
    r"|UMA ESPIROMETRIA ALTERAD[OA] OU NORMAL[^.]*|ALTERAD[OA] OU NORMAL NAO EXCLU[^.]*"
    r"|DEVE SER ANALISADO PELO MEDICO[^.]*|ANALISE DO MEDICO ASSISTENTE[^.]*")
_CAIXA_VAZIA = re.compile(r"[\(\[]\s*[\)\]]\s*(?:NORMAL|ALTERAD[OA]|ENCAMINHAD[OA]|LIMITROFE|OBSTRUTIV[OA]"
                          r"|RESTRITIV[OA]|MIST[OA])")
_NEGACAO = re.compile(r"\b(?:AUSENCIA DE|SEM|NAO HA|NAO APRESENTA|NAO SE OBSERVA|NAO FORAM OBSERVAD[OA]S|NAO EVIDENCIA)"
                      r"\b[^.;]{0,60}")

ALTERADO = re.compile(
    r"DIST\w{0,3}RBIO (?:VENTILATORIO|OBSTRUTIVO|RESTRITIVO|MISTO|COMBINADO)|DIST\w{0,3}RBIO VENT|\bDV[OR]\b"
    r"|PADRAO (?:OBSTRUTIVO|RESTRITIVO|MISTO)|OBSTRUCAO|RESTRICAO (?:LEVE|MEDIA|MODERADA|GRAVE|SEVERA|ACENTUADA)"
    r"|(?:LEVE|MEDIA|MODERADA|GRAVE|SEVERA) RESTRICAO"
    r"|(?:SUGESTIV[OA]|COMPATIVEL) (?:DE|COM) (?:OBSTRU|RESTRI)|PROVAVEL RESTRICAO|LIMITACAO AO FLUXO"
    r"|CVF\)? ?REDUZIDA|CAPACIDADE VITAL FORCADA (?:\(CVF\) ?)?REDUZIDA|REDUCAO (?:DA|DE) (?:CVF|CAPACIDADE VITAL)"
    r"|FORA DOS (?:LIMITES|PADROES) DA NORMALIDADE|ESPIROMETRIA ALTERADA|EXAME ALTERADO"
    r"|[\(\[] ?X ?[\)\]] ?ALTERAD")
NORMAL = re.compile(
    r"[A-Z]*ROMETRIA (?:OCUPACIONAL )?(?:COM PADRAO )?NORMAL|EXAME DE ESPIROMETRIA NORMAL|ESPIROMETRIA DENTRO"
    r"|FUNCAO VENTILATORIA (?:DENTRO|NORMAL)|CVF[^.]{0,30}DENTRO DOS VALORES DE REFERENCIA"
    r"|(?<!FORA )(?:DENTRO )?D[OE]S? (?:LIMITES|PADROES) D[AE] NORMALIDADE|INDICES? ESPIROMETRICOS? DENTRO"
    r"|PARAMETROS (?:ENCONTRADOS|ESPIROMETRICOS)[^.]{0,40}(?:DENTRO|NORMA)|FUNCAO PULMONAR NORMAL"
    r"|PROVA DE FUNCAO PULMONAR NORMAL|EXAME NORMAL|PADRAO NORMAL|CURVAS DENTRO DOS PADROES"
    r"|[\(\[] ?X ?[\)\]] ?NORMAL")
# Âncora da conclusão escrita pelo médico (vence a interpretação automática do aparelho).
_ANCORA = re.compile(r"^(?:TEST RESULT|CONCLUSA|CONCLUSOES|CONDUSA|LAUDO\b|ANALISE (?:MEDICA|DA ESPIROMETRIA)|PARECER|IMPRESSAO"
                     r"|DESCRICAO|RESULTADO ?:|NO MOMENTO)")


def _eh_titulo(linha: str) -> bool:
    if not _TITULO.search(linha) or _NAO_LAUDO.search(linha) or len(linha) > 120:
        return False
    # Item da lista do ASO: nome do exame com data na mesma linha.
    return not _DATA.search(linha)


def _janelas(linhas: list[str]) -> list[tuple[int, int]]:
    """Intervalos [ini, fim) cobertos por laudos de espirometria (unidos)."""
    cobertos: list[tuple[int, int]] = []
    for i, l in enumerate(linhas):
        if not (_eh_titulo(l) or _INDICE.search(l)):
            continue
        fim = i + 1
        while fim < min(len(linhas), i + JANELA):
            x = linhas[fim]
            if _FIM_ASO.search(x):
                break
            if len(x) <= 90 and _OUTRO_EXAME.search(x) and not _TITULO.search(x):
                break
            fim += 1
        if cobertos and i <= cobertos[-1][1]:
            cobertos[-1] = (cobertos[-1][0], max(cobertos[-1][1], fim))
        else:
            cobertos.append((i, fim))
    return cobertos


def _limpar(linha: str) -> str:
    x = _BOILERPLATE.sub(" ", linha)
    return _CAIXA_VAZIA.sub(" ", x)


def _veredito(linha: str) -> Optional[str]:
    x = _limpar(linha)
    if ALTERADO.search(_NEGACAO.sub(" ", x)):
        return "alterado"
    if NORMAL.search(x):
        return "normal"
    return None


def ler(texto_entrada: str) -> dict:
    linhas = [_norm(l) for l in (texto_entrada or "").splitlines()]
    linhas = [l for l in linhas if l]
    janelas = _janelas(linhas)
    if not janelas:
        return {"espirometria": None}
    medico: list[str] = []
    todos: list[str] = []
    linhas_medico: list[str] = []
    linhas_laudo: list[str] = []
    laudo = False
    for a, b in janelas:
        if not any(_EVIDENCIA.search(linhas[k]) or _veredito(linhas[k]) for k in range(a, b)):
            continue  # só o nome do exame (lista do ASO, pedido): não é laudo
        laudo = True
        ultima_ancora = -99
        linhas_laudo.extend(linhas[a:b])
        for k in range(a, b):
            if _ANCORA.search(linhas[k]):
                ultima_ancora = k
            if k - ultima_ancora <= 4:
                linhas_medico.append(linhas[k])
            # A conclusão quebra linha no OCR ("...DENTRO DOS LIMITES DA" / "NORMALIDADE."): lê a linha
            # junto com a seguinte, sem passar do fim da janela.
            v = _veredito(" ".join(linhas[k:min(k + 2, b)]))
            if v is None:
                continue
            todos.append(v)
            if k - ultima_ancora <= 4:
                medico.append(v)
    if not laudo:
        return {"espirometria": None}
    base = medico or todos
    if not base:
        return {"espirometria": "sem_conclusao", **_detalhe(linhas_medico or linhas_laudo, "sem_conclusao")}
    conclusao = "alterado" if "alterado" in base else "normal"
    return {"espirometria": conclusao, **_detalhe(linhas_medico or linhas_laudo, conclusao)}


# Detalhe (pedido do Breno, 23/11): padrão, grau e broncodilatador, lidos nas linhas da conclusão do médico (ou, sem
# elas, do laudo inteiro), já limpas de texto-padrão e caixinha vazia e sem os trechos negados. Os índices (CVF, VEF1)
# não são lidos: a tabela do aparelho sai do OCR sem a coluna de cada número (previsto, pré, %).
_PADRAO = [
    ("misto", re.compile(r"\bMIST[OA]\b|COMBINAD|OBSTRUTIV\w* E RESTRITIV|RESTRITIV\w* E OBSTRUTIV")),
    ("obstrutivo", re.compile(r"OBSTRU|LIMITACAO AO FLUXO|DPOC|BRONCOESPASMO")),
    ("restritivo", re.compile(r"RESTRI|REDUCAO D[AO] (?:CVF|CAPACIDADE VITAL)")),
    ("inespecifico", re.compile(r"INESPECIFIC|NAO ESPECIFIC|REDUCAO PROPORCIONAL")),
]
_GRAU_ESP = [("grave", re.compile(r"\bGRAVE|SEVER|ACENTUAD|IMPORTANTE")), ("moderado", re.compile(r"MODERAD")),
             ("leve", re.compile(r"\bLEVE|DISCRET|LIGEIR"))]
_BD_COM = re.compile(r"(?<!SEM )(?<!NAO HOUVE )(?<!AUSENCIA DE )RESPOSTA (?:SIGNIFICATIVA|POSITIVA|IMPORTANTE)|COM RESPOSTA (?:AO |A )?BRONCO"
                     r"|REVERSIBILIDADE|REVERSIVEL|MELHORA (?:SIGNIFICATIVA )?(?:APOS|POS|COM) (?:O )?(?:USO DE )?BRONCO")
_BD_SEM = re.compile(r"SEM RESPOSTA|RESPOSTA (?:NAO SIGNIFICATIVA|AUSENTE|NEGATIVA)|AUSENCIA DE RESPOSTA|NAO HOUVE RESPOSTA"
                     r"|IRREVERSIVEL|SEM REVERSIBILIDADE|NAO REVERS")


def _detalhe(linhas: list[str], conclusao: str) -> dict:
    texto = " | ".join(_limpar(l) for l in linhas)
    afirmado = _NEGACAO.sub(" ", texto)
    padrao = next((n for n, rx in _PADRAO if rx.search(afirmado)), None) if conclusao != "normal" else "normal"
    grau = None
    if padrao not in (None, "normal"):
        grau = next((n for n, rx in _GRAU_ESP if rx.search(afirmado)), None)
    bd = None
    if re.search(r"BRONCODILAT|POS-? ?BD|\bBD\b|POS-? ?BRONCO", texto):
        bd = "sem_resposta" if _BD_SEM.search(texto) else ("com_resposta" if _BD_COM.search(texto) else None)
    return {"espirometria_padrao": padrao, "espirometria_grau": grau, "espirometria_broncodilatador": bd}
