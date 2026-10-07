"""
Ajuste determinístico do veredito por exame a partir do CONTEÚDO do laudo.

Roda depois da comparação (FAISS + GPT) e corrige os dois erros mais medidos nela,
lendo o markdown do OCR já normalizado. Não chama API e não envia dado a ninguém.

  1. Recuperar faltante pelo conteúdo. O exame foi pedido com um nome e o laudo
     traz outro formato: lipidograma em laudos separados por componente, triagem
     toxicológica com um laudo por droga, glicemia de jejum como "Glicose … mg/dL",
     etanol identificado pelo material, RX com a conclusão do laudo. Se o conteúdo
     prova o exame, ele deixa de ser faltante. Só tira pendência; nunca cria.

  2. Exigir laudo. Para seis tipos de exame com laudo de formato estável, o exame
     dado como encontrado só continua encontrado se a marca do laudo aparece no
     documento. Sem ela o exame foi só CITADO (lista do ASO, voucher) e vira faltante.

Medido por replay no texto gravado de 2.581 documentos revisados (14/09 a 05/10/2026),
contra a decisão do revisor: (1) +15 corrigidos, −2; (2) +25 corrigidos, −9. Os
tipos de (2) foram escolhidos em 14/09–28/09 e confirmados fora da amostra em 05/10.
Glicose e transaminases ficaram FORA de (2): barravam mais documentos certos do que
pegavam. Hemograma, espirometria, RX comum, EEG e toxicológico também ficaram fora.
Mexer nas listas sem medir de novo reintroduz o erro.
"""
from __future__ import annotations

import re
from typing import Any, Optional

# ---------------------------------------------------------------------------
# 1. Recuperar faltante pelo conteúdo do laudo
# ---------------------------------------------------------------------------

_COMPONENTES_LIPIDOGRAMA = ("COLESTEROL TOTAL", "HDL", "LDL", "TRIGLICER")
_DROGAS = ("COCAINA", "BENZOILECGONINA", "CANABIN", "THC", "ANFETAMIN", "OPIACE",
           "BARBITUR", "BENZODIAZEP", "METADONA", "FENCICLIDINA")
_RESULTADO_TOXICOLOGICO = re.compile(r"NEGATIVO|NAO DETECTADO|POSITIVO|DETECTADO")
_GLICOSE_COM_RESULTADO = re.compile(r"(GLICOSE|GLICEMIA).{0,150}MG ?DL")
_ETANOL_URINA = re.compile(r"(ETANOL|ALCOOL ETILICO).{0,200}URINA|URINA.{0,200}(ETANOL|ALCOOL ETILICO)")
_ETANOL_SANGUE = re.compile(r"(ETANOL|ALCOOL ETILICO).{0,200}(SORO|SANGUE|PLASMA)|(SORO|SANGUE|PLASMA).{0,200}(ETANOL|ALCOOL ETILICO)")
_RX_COM_CONCLUSAO = re.compile(
    r"(RAIO X|RADIOGRAFIA|\bRX\b).{0,300}"
    r"(CONCLUS|IMPRESSAO|CORPOS VERTEBRAIS|ESPACOS INTERVERTEBRAIS|CAMPOS PULMONARES|SEIOS COSTOFRENICOS)"
)


def evidencia_de_faltante(exame_norm: str, markdown_norm: str) -> Optional[str]:
    """Motivo pelo qual o conteúdo do laudo prova o exame, ou None."""
    if "LIPIDOGRAMA" in exame_norm or "PERFIL LIPIDICO" in exame_norm:
        achados = sum(bool(re.search(c + r".{0,150}MG ?DL", markdown_norm)) for c in _COMPONENTES_LIPIDOGRAMA)
        if achados >= 3:
            return "laudos dos componentes do perfil lipídico com resultado em mg/dL"
    if "TOXICOL" in exame_norm and "CAPILAR" not in exame_norm:
        drogas = sum(d in markdown_norm for d in _DROGAS)
        if drogas >= 4 and _RESULTADO_TOXICOLOGICO.search(markdown_norm):
            return f"laudos por substância ({drogas} drogas) com resultado"
    if "GLICEMIA" in exame_norm and _GLICOSE_COM_RESULTADO.search(markdown_norm):
        return "laudo de glicose com resultado em mg/dL"
    if "ETANOL" in exame_norm or "ALCOOL" in exame_norm:
        if "URIN" in exame_norm:
            if _ETANOL_URINA.search(markdown_norm):
                return "laudo de etanol em urina"
        elif _ETANOL_SANGUE.search(markdown_norm):
            return "laudo de etanol em sangue/soro"
    if re.search(r"RADIOGRAF|RAIO X|\bRX\b", exame_norm) and _RX_COM_CONCLUSAO.search(markdown_norm):
        return "laudo radiológico com conclusão"
    return None


# ---------------------------------------------------------------------------
# 2. Exigir laudo nos tipos de formato estável
# ---------------------------------------------------------------------------

# A ORDEM importa: o exame é classificado pelo primeiro padrão que casa ("RADIOGRAFIA
# DE TÓRAX PADRÃO OIT" é RX_OIT, não RX). Os tipos que não exigem laudo continuam
# aqui só para classificar corretamente e ficar fora da exigência.
_TIPOS: list[tuple[str, re.Pattern, re.Pattern]] = [
    ("AUDIOMETRIA", re.compile(r"AUDIOMETR"),
     re.compile(r"ORELHA (DIREITA|ESQUERDA)|\bKHZ\b|VIA AEREA|LIMIARES|LOGOAUDIOMETRIA|\bIRF\b|\bSRT\b|\bLRF\b")),
    ("RX_OIT", re.compile(r"OIT"),
     re.compile(r"LEITURA RADIOLOGICA|PNEUMOCONIOSE|CLASSIFICACAO INTERNACIONAL|QUALIDADE TECNICA")),
    ("RX", re.compile(r"RADIOGRAF|RAIO X|\bRX\b"), None),
    ("ESPIROMETRIA", re.compile(r"ESPIROMETR"), None),
    ("ECG", re.compile(r"ELETROCARDIO|\bECG\b"),
     re.compile(r"RITMO SINUSAL|\bQRS\b|\bEIXO\b|INTERVALO PR|\bQTC?\b|\bBPM\b")),
    ("EEG", re.compile(r"ELETROENCEFAL|\bEEG\b"), None),
    ("GLICOSE", re.compile(r"GLICEMIA|GLICOSE"), None),
    ("HEMOGRAMA", re.compile(r"HEMOGRAMA"), None),
    ("LIPIDES", re.compile(r"TRIGLICER|LIPIDOGRAMA|COLESTEROL"),
     re.compile(r"(TRIGLICER|COLESTEROL).{0,150}MG ?DL")),
    ("TRANSAMINASES", re.compile(r"\bTGO\b|\bTGP\b|\bAST\b|\bALT\b|GGT|TRANSAMINASE"), None),
    ("CREAT_UREIA", re.compile(r"CREATININA|UREIA"), None),
    ("SOROLOGIA", re.compile(r"ANTI ?HBS|HBSAG|HCV|ANTI ?HAV|VDRL|\bHIV\b|ANTI ?HBC"),
     re.compile(r"NAO REAGENTE|\bREAGENTE\b|\bINDICE\b|MUI ML|\bUI ML\b|\bS CO\b")),
    ("URINA", re.compile(r"\bEAS\b|URINA ROTINA|SUMARIO DE URINA|URINA TIPO"),
     re.compile(r"DENSIDADE|SEDIMENTO|NITRITO|CELULAS EPITELIAIS|CILINDROS")),
    ("TOXICOLOGICO", re.compile(r"TOXICOL"), None),
]


def tipo_do_exame(exame_norm: str) -> Optional[str]:
    for nome, padrao, _ in _TIPOS:
        if padrao.search(exame_norm):
            return nome
    return None


def falta_laudo(exame_norm: str, markdown_norm: str) -> Optional[str]:
    """Tipo do exame quando ele exige laudo e a marca do laudo não está no documento."""
    for nome, padrao, marca in _TIPOS:
        if padrao.search(exame_norm):
            if marca is not None and not marca.search(markdown_norm):
                return nome
            return None
    return None


# ---------------------------------------------------------------------------
# Aplicação sobre o resultado da comparação
# ---------------------------------------------------------------------------

def ajustar_comparativo(
    comparativo: list[dict[str, Any]],
    markdown_norm: str,
    normalizar,
    recuperar: bool = True,
    exigir_laudo: bool = True,
) -> list[dict[str, Any]]:
    """
    Corrige os vereditos do comparativo NO LUGAR e devolve a lista do que mudou.

    `markdown_norm` é o markdown já normalizado pela mesma função de busca do motor
    (`normalizar`), com espaço nas pontas. Cada item alterado ganha `ajuste` com o
    motivo, para a trilha e para a tela do revisor.
    """
    if not markdown_norm.strip():
        return []
    mudancas: list[dict[str, Any]] = []
    for item in comparativo:
        exame = item.get("exame") or ""
        status = item.get("status")
        exame_norm = normalizar(exame)
        if not exame_norm:
            continue
        if exigir_laudo and status == "encontrado":
            tipo = falta_laudo(exame_norm, markdown_norm)
            if tipo:
                item["status"] = "faltante"
                item["justificativa"] = (
                    f"'{exame}' aparece no documento, mas sem o laudo com resultado "
                    "(provavelmente só citado no ASO ou na guia)."
                )
                item["ajuste"] = {"regra": "exigir_laudo", "tipo": tipo, "antes": "encontrado"}
                mudancas.append({"exame": exame, "de": "encontrado", "para": "faltante", "regra": "exigir_laudo", "tipo": tipo})
        elif recuperar and status == "faltante":
            motivo = evidencia_de_faltante(exame_norm, markdown_norm)
            if motivo:
                item["status"] = "encontrado"
                item["justificativa"] = f"'{exame}' reconhecido pelo conteúdo: {motivo}."
                item["ajuste"] = {"regra": "conteudo_do_laudo", "motivo": motivo, "antes": "faltante"}
                mudancas.append({"exame": exame, "de": "faltante", "para": "encontrado", "regra": "conteudo_do_laudo"})
    return mudancas
