"""
Resultado das avaliações PSICOLÓGICA e PSICOSSOCIAL no texto de OCR do prontuário (regex, sem LLM, sem rede).
STC-1065, 23/11. Só o RESULTADO: nenhum conteúdo clínico do laudo é lido ou devolvido (dado sensível).

Saída de ler(texto_entrada):
  psicologica    "favoravel" | "favoravel_com_ressalva" | "desfavoravel" | None
  psicossocial   "favoravel" | "favoravel_com_ressalva" | "desfavoravel" | None
None = não há laudo dessa avaliação no texto, ou o resultado não está legível.

Regras (amostra de 400 da base de 10 mil e 400 da nossa):
- Janela: título do laudo (LAUDO PSICOLÓGICO, AVALIAÇÃO/PARECER PSICOLÓGICO(A), RESULTADO DA AVALIAÇÃO PSICOLÓGICA;
  AVALIAÇÃO PSICOSSOCIAL, ATESTADO DE AVALIAÇÃO PSICOSSOCIAL, "## PSICOSSOCIAL") até o título de outro exame/ASO
  ou 150 linhas. Item da lista do ASO ("AVALIAÇÃO PSICOSSOCIAL - 15/09/2025"), "Histórico psicossocial" da ficha
  médica e o questionário de anamnese não abrem janela.
- Só linhas de resultado: "RECOMENDADO", "NÃO RECOMENDADO", "favorável", "apto/inapto (ao exercício
  profissional / para a função)", "considerado apto", "com ressalvas/restrições". Perguntas ("?", "em caso de
  sim, qual o resultado") nunca contam.
- Opção sem marca não conta: "( ) INAPTO ..." sai; linha com as duas opções impressas ("RECOMENDADO NÃO
  RECOMENDADO", "APTO / FIT ... INAPTO / UNFIT" do formulário bilíngue) não decide nada, salvo marca explícita.
- Precedência: com ressalva > favorável ("sem ressalvas/sem restrições" é favorável). Desfavorável só sem
  nenhuma afirmação favorável no mesmo laudo: as duas juntas são marca de formulário perdida -> None.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", t).strip().lstrip("#*>| ").strip()


_TITULO = {
    "psicologica": re.compile(r"LAUDO PSICOLOGIC|AVALIACAO PSICOLOGICA|PARECER PSICOLOGIC|RESULTADO DA AVALIACAO PSICOLOG"
                              r"|ATESTADO PSICOLOGIC|^PSICOLOGICO$"),
    "psicossocial": re.compile(r"AVALIACAO PSICOSSOCIAL|ATESTADO DE AVALIACAO PSICOSSOCIAL|^PSICOSSOCIAL\b|PARECER PSICOSSOCIAL"
                               r"|PSYCHOSOCIAL ASSESSMENT"),
}
_DATA = re.compile(r"\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{2,4}")
_NAO_TITULO = re.compile(r"\?|HISTORICO|QUESTIONARIO|DEMANDA|PARTE INTEGRANTE|VISA INVESTIGAR|INSTRUMENTOS"
                         r"|PROCEDIMENTOS|FINALIDADE|TRATAMENTO|CONSELHO")
# Título de outro exame no começo da linha. O laudo ODONTOLÓGICO ("( ) APTO ao exercício profissional, sem risco
# iminente de dor", "RECOMENDADO para o trabalho marítimo") fechava mal e era lido como psicológico (23/11).
_FIM = re.compile(r"CONCLUSAO ?/ ?CONCLUSION|LAUDO ODONTOLOG|AVALIA\w{0,4}O ODONTOLOG|FICHA DE AVALIA\w* ODONTO"
                  r"|RISCO IMINENTE DE DOR|TRABALHO MARITIMO"
                  r"|^(?:\d+\W*)?(?:ATESTADO DE SAUDE OCUPACIONAL|AUDIOMETR|AVALIACAO AUDIOLOG|ACUIDADE VISUAL|ESPIROMETR|HEMOGRAMA"
                  r"|RADIOGRAF|ELETROCARDIOGRAM|LAUDO DE ELETRO|TESTE ERGOMETRICO|ELETROENCEFALO|FICHA MEDICA|FICHA CLINICA"
                  r"|EXAME CLINICO|GLICEMIA|PARASITOLOG|TOXICOLOG)")
JANELA = 150

_PERGUNTA = re.compile(r"\?|EM CASO DE SIM|QUAL O RESULTADO|RESULTADOS ANTERIORES|MUDANCA DE RISCO|RISCO IMINENTE A MINHA")
_CAIXA_VAZIA = re.compile(r"[\(\[\{]\s*[\)\]\}]\s*[A-Z][A-Z /.,-]{0,60}")
_FORM_BILINGUE = re.compile(r"\bUNFIT\b|/ ?FIT\b|APTO FIT|INAPTO / INAPTO")
_AMBAS = re.compile(r"\bRECOMENDAD\w*\W+NAO RECOMENDAD|NAO RECOMENDAD\w*\W+RECOMENDAD|\bAPTO\W+INAPTO|INAPTO\W+APTO\b"
                    r"|FAVORAVEL\W+DESFAVORAVEL|DESFAVORAVEL\W+FAVORAVEL")
_MARCA = re.compile(r"[\(\[]\s*X\s*[\)\]]\s*([A-Z][A-Z /.,-]{0,60})")

_DESFAV = re.compile(r"NAO RECOMENDAD|DESFAVORAV|CONTRA-?INDICAD|NAO INDICAD|\bINAPTO\b|NAO APTO")
_RESSALVA = re.compile(r"(?<!SEM )RESSALVA|(?<!SEM )RESTRIC|RECOMENDADO COM|APTO COM (?:RECOMENDAC|RESTRIC|RESSALV|ACOMPANHAMENTO)"
                       r"|FAVORAVEL COM|COM ACOMPANHAMENTO|RECOMENDADO MEDIANTE")
_FAV = re.compile(r"SEM RESSALVAS|SEM RESTRICOES|(?<!NAO )\bRECOMENDAD[OA]\b|(?<!DES)FAVORAVEL|(?<!IN)\bAPTO\b|(?<!NAO )\bINDICAD[OA]\b|ADEQUAD[OA] (?:AO|PARA) (?:O |A )?(?:CARGO|FUNCAO|PERFIL)")
# Frase de resultado (evita "apto" solto em texto corrido que não é parecer).
_CONTEXTO = re.compile(r"^(?:IV\W*)?(?:CONCLUS|PARECER|RESULTADO|SINTESE|DIANTE|DE ACORDO|NO MOMENTO|CONSIDERA|RECOMEND|NAO RECOMEND"
                       r"|APTO|INAPTO|FAVORAV|DESFAVORAV|O COLABORADOR|O AVALIADO|A AVALIADA|ENCONTRA-SE|ESTA APTO|\(\s*X)"
                       r"|CONSIDERAD[OA] APTO|APTO (?:AO|PARA|A EXERCER)|EXERCICIO PROFISSIONAL"
                       r"|ENCONTRA-SE|ESTANDO APT|TORNAM? APT|SE APTO|CONCLUI-SE|CONCLUIMOS|SEM RESSALVAS|ESTA (?:ATUALMENTE )?APTO")


def _eh_titulo(l: str, chave: str) -> bool:
    return bool(_TITULO[chave].search(l)) and not _DATA.search(l) and not _NAO_TITULO.search(l) and len(l) <= 90


def _janelas(linhas: list[str], chave: str) -> list[list[str]]:
    out, i = [], 0
    while i < len(linhas):
        if not _eh_titulo(linhas[i], chave):
            i += 1
            continue
        outra = "psicologica" if chave == "psicossocial" else "psicossocial"
        j = i + 1
        while (j < len(linhas) and j - i <= JANELA and not _FIM.search(linhas[j])
               and not _eh_titulo(linhas[j], outra)):  # a outra avaliação tem a sua janela
            j += 1
        out.append(linhas[i:j])
        i = j
    return out


# Opção impressa sozinha na linha ("## APTO" / "## INAPTO"): o par sem marca não decide nada.
_OPCAO_SO = re.compile(r"(?:IN)?APTO|(?:NAO )?RECOMENDADO|(?:DES)?FAVORAVEL")


def _linhas_resultado(jan: list[str]) -> list[tuple[int, str]]:
    sos = [l for l in jan if _OPCAO_SO.fullmatch(l)]
    ambos = any(l.startswith(("IN", "NAO", "DES")) for l in sos) and any(not l.startswith(("IN", "NAO", "DES")) for l in sos)
    return [(k, l) for k, l in enumerate(jan) if k > 0 and not (ambos and _OPCAO_SO.fullmatch(l))]


def _resultado_linha(l: str) -> Optional[str]:
    # Pergunta; opção impressa em branco ("APTO COM RESTRIÇÃO (DEFINA A RESTRIÇÃO):"); "APTO / FIT" bilíngue com OCR torto.
    if _PERGUNTA.search(l) or re.search(r"DEFINA|:\s*$|\b(?:IN)?APTO ?/", l):
        return None
    # Opção sozinha na linha ("NAO RECOMENDADO" impresso no formulário, com o "RECOMENDADO" comido pelo OCR):
    # só vale logo abaixo de "CONCLUSÃO/PARECER/RESULTADO" (regra em _ler/_cabecalho).
    if _OPCAO_SO.fullmatch(l.strip(" .")):
        return None
    marcadas = _MARCA.findall(l)
    if marcadas:
        l = " ".join(marcadas)
    else:
        l = _CAIXA_VAZIA.sub(" ", l)
        if _FORM_BILINGUE.search(l) or _AMBAS.search(l):
            return None
    if not _CONTEXTO.search(l.strip()):
        return None
    if _DESFAV.search(l):
        return "desfavoravel"
    if _RESSALVA.search(l):
        return "favoravel_com_ressalva"
    if _FAV.search(l):
        return "favoravel"
    return None


def _cabecalho(jan: list[str], k: int) -> Optional[str]:
    """"IV - CONCLUSÃO" numa linha e a opção ("RECOMENDADO", "APTO"...) sozinha na seguinte."""
    l = jan[k].strip(" .")
    if not (re.fullmatch(r"(?:NAO )?RECOMENDAD[OA](?: COM RESSALVAS?)?|(?:IN)?APTO|(?:DES)?FAVORAVEL", l)
            and re.search(r"^(?:IV\W*|\d+\W*)?(?:CONCLUS|PARECER|RESULTADO|SINTESE)", jan[k - 1])):
        return None
    # A opção contrária impressa logo abaixo ("CONCLUSÃO / RECOMENDADO / NÃO RECOMENDADO") desfaz.
    seg = jan[k + 1].strip(" .") if k + 1 < len(jan) else ""
    if re.fullmatch(r"(?:NAO )?RECOMENDAD\w?|(?:IN)?APTO\w*|(?:DES)?FAVORAVEL", seg):
        return None
    if l.startswith(("NAO", "IN", "DES")):
        return "desfavoravel"
    return "favoravel_com_ressalva" if "RESSALV" in l else "favoravel"


# Marca de opção: "(X) APTO", "[X] ...", e o X colado pelo OCR ("XAPTO", "X>APTO").
_MARCADA = re.compile(r"^\W*(?:[\(\[\{]\s*[XK]\s*[\)\]\}]|X\W?(?=\s*(?:IN)?AP[TR]O|\s*NAO REC|\s*REC|\s*(?:DES)?FAVOR))\s*")
# Desfavorável sem marca só em frase ("encontra-se inapto", "não está apto", "não recomendado para..."):
# linha que começa pela opção é formulário impresso ("NAO RECOMENDADC", "INAPTO TEMPORARIO", "RECOMENDADONAO RECOMENDADO").
_DESFAV_FRASE = re.compile(r"(?:ENCONTRA-SE|ESTA|CONSIDERAD[OA]|CONCLUI-SE QUE|SE ENCONTRA|FOI CONSIDERAD[OA])\W+(?:\w+\W+){0,4}?"
                           r"(?:INAPTO|NAO APTO|NAO RECOMENDAD|CONTRA-?INDICAD|DESFAVORAV)")


def _resultados_janela(jan: list[str]) -> list[str]:
    marcadas = [(k, l) for k, l in enumerate(jan) if k > 0 and _MARCADA.match(l)]
    if marcadas:
        out = []
        for _, l in marcadas:
            l = _MARCADA.sub("", l, count=1).replace("APRO ", "APTO ")
            # Só o texto da opção marcada: corta na próxima caixa/opção ("(X)APTO ( )INAPTO ( )APTO COM RESTRIÇÕES",
            # "XRECOMENDADO RECOMEN NAO RECOMENDADO").
            corte = re.search(r"[\(\[\{]|\bNAO RECOMEND|\bINAPTO|\bRECOMEN\b|\bAPTO COM", l[3:])
            if corte:
                l = l[:3 + corte.start()]
            r = (_DESFAV.search(l) and "desfavoravel") or (_RESSALVA.search(l) and "favoravel_com_ressalva") \
                or (_FAV.search(l) and "favoravel")
            if r:
                out.append(r)
        return out
    out = []
    for k, l in _linhas_resultado(jan):
        r = _resultado_linha(l) or _cabecalho(jan, k)
        if r == "desfavoravel" and not (_DESFAV_FRASE.search(l) or _cabecalho(jan, k)):
            continue
        if r == "favoravel_com_ressalva" and re.match(r"\W*APTO COM", l) and not _cabecalho(jan, k):
            continue  # "APTO COM RECOMENDAÇÕES" impresso na lista de opções
        if r:
            out.append(r)
    return out


def _ler(linhas: list[str], chave: str) -> Optional[str]:
    vistos = set()
    for jan in _janelas(linhas, chave):
        for r in _resultados_janela(jan):
            vistos.add(r)
    # Favorável e desfavorável explícitos no mesmo laudo: marca de formulário perdida/deslocada no OCR
    # ("APTO(A) para a ocupação" / "INAPTO(A) para o risco"; "RECOMENDADO" + "(X) INAPTO"). Não decide.
    if "desfavoravel" in vistos and vistos & {"favoravel", "favoravel_com_ressalva"}:
        return None
    for r in ("desfavoravel", "favoravel_com_ressalva", "favoravel"):
        if r in vistos:
            return r
    return None


def ler(texto_entrada: str) -> dict[str, Optional[str]]:
    linhas = [n for n in (_norm(l) for l in (texto_entrada or "").splitlines()) if n]
    return {"psicossocial": _ler(linhas, "psicossocial"), "psicologica": _ler(linhas, "psicologica")}


def debug_resultados(texto_entrada: str) -> list[tuple[str, str]]:
    """Só as linhas que decidiram (para conferência), nunca o corpo do laudo."""
    linhas = [n for n in (_norm(l) for l in (texto_entrada or "").splitlines()) if n]
    out = []
    for chave in ("psicologica", "psicossocial"):
        for jan in _janelas(linhas, chave):
            marcadas = [l for k, l in enumerate(jan) if k > 0 and _MARCADA.match(l)]
            linhas_r = marcadas or [l for _, l in _linhas_resultado(jan)]
            for r, l in zip(_resultados_janela(jan), linhas_r):
                out.append((chave, f"{r}: {l[:90]}"))
    return out
