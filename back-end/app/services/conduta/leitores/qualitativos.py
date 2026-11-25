"""
Conclusão escrita nos laudos de exames sem valor numérico: audiometria, ECG, espirometria e acuidade
visual (com o valor 20/xx do pior olho e o senso cromático).

Lê só a janela do LAUDO de cada exame: do título do laudo até 45 linhas ou o título de outro exame.
Item da lista do ASO ("AUDIOMETRIA TONAL 20/10/2026") não abre janela, e a conclusão do ASO
("5. Conclusão / Conclusion: Apto") nunca é lida — aquilo é o rótulo.

Saída por exame: "alterado" | "normal" | "sem_conclusao". Alterado vence normal no mesmo laudo
(um olho normal e o outro alterado é alterado). Negação ("ausência de arritmia", "sem bloqueio") e
opção de formulário sem marca ("( ) Alterado") não contam.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Optional


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", t).strip()


TITULOS = {
    "audiometria": r"AUDIOMETRI|AUDIOLOG|AUDIOGRAMA|PURE TONE",
    "ecg": r"ELETROCARDIOGRAM|\bECG\b|ELECTROCARDIOGRAM",
    "espirometria": r"ESPIROMETRI|SPIROMETR|PROVA DE FUNCAO PULMONAR",
    "acuidade_visual": r"ACUIDADE VISUAL|VISUAL ACUITY|SNELLEN|TESTE DE ACUIDADE",
}
_QUALQUER_TITULO = re.compile("|".join(TITULOS.values()) + r"|HEMOGRAMA|GLICOSE|GLICEMIA|RADIOGRAFIA|\bRX\b|"
                              r"ELETROENCEFALO|ATESTADO DE SAUDE OCUPACIONAL|FICHA MEDICA|AVALIACAO PSICO|ODONTOLOG")
_DATA = re.compile(r"\d{1,2}/\d{1,2}/\d{2,4}")

NORMAL = {
    "audiometria": r"DENTRO D[OA]S? (?:PADR|LIMITE)|LIMIARES AUDITIVOS (?:NORMAIS|DENTRO)|AUDIOMETRIA NORMAL|AUDICAO NORMAL"
                   r"|NORMOACUSIA|\(X ?\) ?NORMAL|EXAME NORMAL|LIMIARES NORMAIS",
    "ecg": r"DENTRO DOS LIMITES DA NORMALIDADE|ECG NORMAL|ELETROCARDIOGRAMA NORMAL|EXAME NORMAL|TRACADO NORMAL"
           r"|RITMO SINUSAL NORMAL|\(X ?\) ?NORMAL|SEM ALTERACOES",
    "espirometria": r"DENTRO DOS (?:PADROES|LIMITES)|ESPIROMETRIA NORMAL|EXAME NORMAL|\(X ?\) ?NORMAL|PADRAO NORMAL"
                    r"|SEM DISTURBIO|NORMAL",
    "acuidade_visual": r"LAUDO NORMAL|EXAME NORMAL|\(X ?\) ?NORMAL|ACUIDADE NORMAL|VISAO NORMAL",
}
ALTERADO = {
    "audiometria": r"PERDA AUDITIVA|DISACUSIA|HIPOACUSIA|\bPAIR\b|PAINPSE|REBAIXAMENTO|\bPANS\b|ALTERAD|ENTALHE"
                   r"|\(X ?\) ?ALTERADO|EXCETO",
    "ecg": r"BRADICARDIA|TAQUICARDIA|BLOQUEIO|SOBRECARGA|EXTRA-?SSISTOL|FIBRILA|FLUTTER|ISQUEMIA|REPOLARIZA"
           r"|DESVIO D[OE] EIXO|PRE-? ?EXCITA|WOLFF|ARRITMIA|ALTERAD|QT LONGO|HEMIBLOQUEIO|\(X ?\) ?ALTERADO",
    "espirometria": r"DISTURBIO VENTILATORIO|OBSTRUTIV|RESTRITIV|\bDVO\b|\bDVR\b|DISTURBIO MISTO|ALTERAD"
                    r"|\(X ?\) ?ALTERADO|LIMITACAO AO FLUXO",
    "acuidade_visual": r"ANORMAL|ALTERAD|NECESSITA DE AVALIACAO|REDUCAO DA ACUIDADE|BAIXA ACUIDADE|\(X ?\) ?ALTERADO",
}
# Negação e formulário sem marca: saem antes de procurar alteração.
_NEGACAO = re.compile(r"\b(?:AUSENCIA DE|SEM|NAO HA|NAO APRESENTA|NAO SE OBSERVA|NEGA)\b[^.;]{0,70}")
_CAIXA_VAZIA = re.compile(r"[\(\[]\s*[\)\]]\s*[A-Z]+(?: [A-Z]+){0,3}")
_AV = re.compile(r"\b(OD|OE|O\.D\.|O\.E\.)\b[^0-9\n]{0,15}\(?\s*20\s*/\s*(\d{2,3})\b")
_ISHIHARA_ALT = re.compile(r"ISHIHARA[^.]{0,120}(?:ANORMAL|ALTERAD|NAO IDENTIFIC|DISCROMATOPSIA|DALTON)|DISCROMATOPSIA")
_ISHIHARA_NORMAL = re.compile(r"ISHIHARA[^.]{0,80}NORMAL|SENSO CROMATICO[^.]{0,40}NORMAL|TESTE CROMATICO[^.]{0,40}NORMAL")


def _janelas(linhas: list[str], exame: str) -> list[str]:
    rx = re.compile(TITULOS[exame])
    janelas = []
    i = 0
    while i < len(linhas):
        n = linhas[i]
        # Título de laudo: linha curta com o nome do exame e sem data (item da lista do ASO tem data).
        if rx.search(n) and len(n) <= 90 and not _DATA.search(n):
            corpo = [n]
            for j in range(i + 1, min(i + 46, len(linhas))):
                if _QUALQUER_TITULO.search(linhas[j]) and not rx.search(linhas[j]) and len(linhas[j]) <= 90:
                    break
                corpo.append(linhas[j])
            janelas.append(" ".join(corpo))
            i += len(corpo)
        else:
            i += 1
    return janelas


def _conclusao(texto: str, exame: str) -> str:
    t = _CAIXA_VAZIA.sub(" ", texto)
    sem_negacao = _NEGACAO.sub(" ", t)
    if re.search(ALTERADO[exame], sem_negacao):
        return "alterado"
    if re.search(NORMAL[exame], t):
        return "normal"
    return "sem_conclusao"


def ler_qualitativos(texto_entrada: str) -> dict[str, Any]:
    linhas = [_norm(l).lstrip("# ") for l in texto_entrada.splitlines()]
    linhas = [l for l in linhas if l]
    out: dict[str, Any] = {}
    for exame in TITULOS:
        js = _janelas(linhas, exame)
        if not js:
            out[exame] = None  # sem laudo achado
            continue
        res = [_conclusao(j, exame) for j in js]
        out[exame] = "alterado" if "alterado" in res else ("normal" if "normal" in res else "sem_conclusao")
    # Acuidade: pior olho (maior denominador 20/xx) e senso cromático, dentro do laudo de acuidade.
    av_txt = " ".join(_janelas(linhas, "acuidade_visual"))
    denominadores = [int(m.group(2)) for m in _AV.finditer(av_txt) if 10 <= int(m.group(2)) <= 400]
    out["acuidade_pior_olho"] = max(denominadores) if denominadores else None
    if _ISHIHARA_ALT.search(av_txt):
        out["senso_cromatico"] = "alterado"
    elif _ISHIHARA_NORMAL.search(av_txt):
        out["senso_cromatico"] = "normal"
    else:
        out["senso_cromatico"] = None
    return out
