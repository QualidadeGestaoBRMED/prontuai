"""
Ajuste determinístico do veredito por exame a partir do CONTEÚDO do laudo.

Roda depois da comparação (FAISS + GPT) e corrige os dois erros mais medidos nela,
lendo o markdown do OCR já normalizado. Não chama API e não envia dado a ninguém.

  1. Recuperar faltante pelo conteúdo. O exame foi pedido com um nome e o laudo
     traz outro formato: lipidograma em laudos separados por componente, triagem
     toxicológica com um laudo por droga, glicemia de jejum como "Glicose … mg/dL",
     etanol identificado pelo material, RX com a conclusão do laudo, acuidade com a
     fração de Snellen anotada nos dois olhos (ficha manuscrita). Se o conteúdo
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

Ajustes de 20/10/2026, cada um medido no texto gravado de 14/09 a 19/10 (conferência
das divergências de outubro no PDF): a marca de RX OIT passou a aceitar a ficha
da CMTL, a acuidade passou a ser reconhecida em tabela de oftalmologista e a
sorologia passou a exigir o resultado perto do analito, fora das listas de exames.
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
# Acuidade: "Snellen" está IMPRESSO no formulário da BR MED, preenchido ou em branco
# (2.570 ocorrências desde ago/26), então a palavra não prova nada. O que prova é a
# fração de Snellen anotada nos DOIS olhos; na ficha em branco "OLHO DIREITO" vem
# colado em "OLHO ESQUERDO".
_ACUIDADE_OD = re.compile(r"OLHO DIREITO (?:COM CORRECAO |SEM CORRECAO )?20 \d{2,3}\b")
_ACUIDADE_OE = re.compile(r"OLHO ESQUERDO (?:COM CORRECAO |SEM CORRECAO )?20 \d{2,3}\b")
# Tabela de oftalmologista: os dois olhos são cabeçalho de coluna e as frações vêm
# depois dos dois ("AV PARA LONGE OLHO DIREITO OLHO ESQUERDO S C 20 50 ..."), sem
# a palavra "acuidade". As duas regex de cima não casam. A ficha em branco também
# traz os olhos colados, mas sem fração logo depois. Casa em 23 documentos de
# 14/09 a 19/10, todos com fração preenchida.
_ACUIDADE_TABELA = re.compile(
    r"OLHO DIREITO OLHO ESQUERDO (?:S C |C C |SEM CORRECAO |COM CORRECAO )?20 \d{2,3}\b"
)
_SENSO_CROMATICO = re.compile(r"ISHIHARA|CROMATIC")


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
    if "ACUIDADE" in exame_norm and (
        (_ACUIDADE_OD.search(markdown_norm) and _ACUIDADE_OE.search(markdown_norm))
        or _ACUIDADE_TABELA.search(markdown_norm)
    ):
        if "CROMATIC" not in exame_norm or _SENSO_CROMATICO.search(markdown_norm):
            return "tabela de Snellen com resultado nos dois olhos"
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
    # A ficha OIT da CMTL escreve "Qualidade da radiografia", "Profusão" e "Pequenas
    # opacidades", e nenhuma das quatro primeiras marcas: era rebaixada em todo envio.
    # De 14/09 a 19/10, 7 documentos dela; o revisor aprovou 6 e rejeitou 1 por data
    # invertida no ASO.
    ("RX_OIT", re.compile(r"OIT"),
     re.compile(r"LEITURA RADIOLOGICA|PNEUMOCONIOSE|CLASSIFICACAO INTERNACIONAL|QUALIDADE TECNICA"
                r"|QUALIDADE DA RADIOGRAFIA|PROFUSAO|PEQUENAS OPACIDADES|GRANDES OPACIDADES")),
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
    # A marca daqui só vale para analito sem padrão próprio: os demais são julgados
    # por proximidade, em `_sorologia_tem_laudo`. "HVA" é como o BRNET grafa a
    # hepatite A ("ANTI-HVA IGG"); sem ele o exame nem era classificado.
    ("SOROLOGIA", re.compile(r"ANTI ?HBS|HBSAG|HCV|ANTI ?HAV|ANTI ?HVA|VDRL|\bHIV\b|ANTI ?HBC"),
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


# Sorologia: a marca precisa estar PERTO do analito pedido, fora das listas de
# exames. Valendo para o documento inteiro, o "NÃO REAGENTE" do laudo de HBsAg
# provava um anti-HCV que só aparecia listado no ASO e no voucher.
#
# Medido de 14/09 a 19/10 (4.706 documentos): passa a barrar 4, todos rejeitados
# pelo revisor por falta da sorologia (anti-HBs duas vezes, anti-HCV, anti-HAV), e
# nenhum que ele aprovou. As grafias abaixo saíram dos aprovados que as primeiras
# versões barravam: "ANT HBS" no OCR da Qualimetra, "HBS ANTI" (colunas trocadas)
# nos laudos da Clínica AP e laudo de hepatite C escrito sem a sigla.
_SOROLOGIA_ANALITOS: list[tuple[re.Pattern, re.Pattern]] = [
    (re.compile(r"HCV"), re.compile(r"\bHCV\b|HEPATITE C\b")),
    (re.compile(r"HBSAG|HBS AG"), re.compile(r"HBS ?AG")),
    (re.compile(r"ANTI ?HBS\b"), re.compile(r"ANTI? ?HBS\b|\bHBS ANTI\b")),
    (re.compile(r"(?:HAV|HVA) IGG|IGG (?:HAV|HVA)"),
     re.compile(r"(?:HAV|HVA)\b.{0,25}IGG|IGG.{0,25}(?:HAV|HVA)\b|HEPATITE A.{0,40}IGG")),
    (re.compile(r"(?:HAV|HVA) IGM|IGM (?:HAV|HVA)"),
     re.compile(r"(?:HAV|HVA)\b.{0,25}IGM|IGM.{0,25}(?:HAV|HVA)\b|HEPATITE A.{0,40}IGM")),
    (re.compile(r"ANTI ?(?:HAV|HVA)\b"), re.compile(r"\b(?:HAV|HVA)\b|HEPATITE A")),
    (re.compile(r"VDRL"), re.compile(r"VDRL|SIFILIS")),
    (re.compile(r"\bHIV\b"), re.compile(r"\bHIV\b")),
    (re.compile(r"ANTI ?HBC|HBC"), re.compile(r"HBC")),
]
_SOROLOGIA_MARCA = re.compile(r"NAO REAGENTE|\bREAGENTE\b|\bINDICE\b|MUI ML|\bUI ML\b|\bS CO\b|INDETERMINADO")
_SOROLOGIA_JANELA = 400

# Listas de exames que citam o nome sem ser laudo: (abertura, fechamento, alcance).
# O bloco só sai quando o fechamento aparece dentro do alcance; sem ele, o texto
# fica, que é o lado seguro.
_BLOCOS_DE_LISTA: list[tuple[re.Pattern, re.Pattern, int]] = [
    # ASO: "Procedimentos realizados / Exames complementares" até a conclusão
    (re.compile(r"PROCEDIMENTOS REALIZADOS|EXAMES COMPLEMENTARES"),
     re.compile(r"CONCLUSAO CONCLUSION|PACIENTE E CONSIDERADO|PATIENT IS CONSIDERED"), 2500),
    # voucher BR MED
    (re.compile(r"\b04 EXAMES\b"),
     re.compile(r"TODOS OS EXAMES LISTADOS SAO OBRIGATORIOS|\b05 ORIENTACOES|\b05 OBSERVACOES"), 2000),
    (re.compile(r"\b05 ORIENTACOES DE PREPARO\b"), re.compile(r"\b06 OBSERVACOES|PARA OS DEMAIS EXAMES"), 3000),
    # e-mail de agendamento
    (re.compile(r"\bEXAMES (?:ADMISSIONAL|PERIODICO|DEMISSIONAL|MUDANCA DE \w+|RETORNO AO TRABALHO)\b"),
     re.compile(r"LOCAL DO ATENDIMENTO|OPCIONAL"), 2000),
    (re.compile(r"ORIENTACOES DE PREPARO PARA EXAMES"),
     re.compile(r"OBSERVACOES IMPORTANTES|IMPORTANT NOTICE|ASSINATURA DO RESPONSAVEL"), 2000),
]


def sem_listas(markdown_norm: str) -> str:
    """O markdown normalizado sem os blocos de lista de exames."""
    trechos: list[tuple[int, int]] = []
    for abertura, fechamento, alcance in _BLOCOS_DE_LISTA:
        for inicio in abertura.finditer(markdown_norm):
            fim = fechamento.search(markdown_norm[inicio.end():inicio.end() + alcance])
            if fim:
                trechos.append((inicio.start(), inicio.end() + fim.start()))
    trechos.sort()
    partes: list[str] = []
    ultimo = 0
    for inicio, fim in trechos:
        inicio = max(inicio, ultimo)
        if fim <= inicio:
            continue
        partes.append(markdown_norm[ultimo:inicio])
        partes.append(" ")
        ultimo = fim
    partes.append(markdown_norm[ultimo:])
    return " ".join(partes)


def _sorologia_tem_laudo(exame_norm: str, markdown_norm: str, marca_documento: re.Pattern) -> bool:
    for tipo, analito in _SOROLOGIA_ANALITOS:
        if tipo.search(exame_norm):
            texto = sem_listas(markdown_norm)
            return any(
                _SOROLOGIA_MARCA.search(texto[m.start():m.end() + _SOROLOGIA_JANELA])
                for m in analito.finditer(texto)
            )
    return bool(marca_documento.search(markdown_norm))


def falta_laudo(exame_norm: str, markdown_norm: str) -> Optional[str]:
    """Tipo do exame quando ele exige laudo e a marca do laudo não está no documento."""
    for nome, padrao, marca in _TIPOS:
        if padrao.search(exame_norm):
            if nome == "SOROLOGIA":
                return None if _sorologia_tem_laudo(exame_norm, markdown_norm, marca) else nome
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
