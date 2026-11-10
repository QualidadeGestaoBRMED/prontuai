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

Ajustes de 03/11/2026: Clínico, glicemia, teste ergométrico e GGT passaram a exigir
laudo. Regras escolhidas nos envios de 14/09 a 18/10 e confirmadas nos de 19/10 a
03/11 (5.863 documentos revisados, contra a decisão do revisor): +39 corrigidos, −7.
Hemograma ficou FORA (+17, −31) e reticulócitos também (+4, −4).

Desde o STC-1052 os exames e as marcas vêm do Catálogo de Exames
(`regras_identificacao`): papel `prova_conteudo` para (1), `marca_laudo` e
`sorologia_analito` para (2). As medições acima estão nas notas de cada regra.
Aqui ficou só o algoritmo e o que é estrutura do documento (as listas do ASO,
do voucher e do e-mail de agendamento).
"""
from __future__ import annotations

import re
from typing import Any, Optional

from app.services import evidencia_laboratorio, regras_identificacao

# ---------------------------------------------------------------------------
# 1. Recuperar faltante pelo conteúdo do laudo
# ---------------------------------------------------------------------------


def evidencia_de_faltante(exame_norm: str, markdown_norm: str) -> Optional[str]:
    """Motivo pelo qual o conteúdo do laudo prova o exame, ou None.

    As regras `prova_conteudo` do catálogo são tentadas na ordem; vale o motivo
    da primeira cujo nome casa o exame e cuja condição o conteúdo satisfaz."""
    for regra in regras_identificacao.do_nome(regras_identificacao.PROVA_CONTEUDO, exame_norm):
        vale, contexto = regra.avaliar(markdown_norm)
        if vale:
            return regra.motivo_formatado(contexto)
    return None


# ---------------------------------------------------------------------------
# 2. Exigir laudo nos tipos de formato estável
# ---------------------------------------------------------------------------

# Regras `marca_laudo`: a ORDEM importa — o exame é classificado pela primeira
# que casa ("RADIOGRAFIA DE TÓRAX PADRÃO OIT" é RX_OIT, não RX). As que não
# exigem laudo (sem condição) continuam no catálogo só para classificar e ficar
# fora da exigência.


def tipo_do_exame(exame_norm: str) -> Optional[str]:
    regra = regras_identificacao.primeira_do_nome(regras_identificacao.MARCA_LAUDO, exame_norm)
    return regra.parametros["tipo"] if regra else None


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


def _sorologia_tem_laudo(exame_norm: str, markdown_norm: str, regra: regras_identificacao.Regra) -> bool:
    """Sorologia: a marca precisa estar PERTO do analito pedido, fora das listas
    de exames (regras `sorologia_analito`). Analito sem regra própria cai na
    marca do documento inteiro, a condição da regra `marca_laudo`."""
    analito = regras_identificacao.primeira_do_nome(regras_identificacao.SOROLOGIA_ANALITO, exame_norm)
    if analito is not None:
        marca = re.compile(regra.parametros["marca_proximidade"])
        janela = int(regra.parametros["janela"])
        texto = sem_listas(markdown_norm)
        return any(
            marca.search(texto[m.start():m.end() + janela])
            for m in analito.regex.finditer(texto)
        )
    return regra.vale(markdown_norm)


def falta_laudo(exame_norm: str, markdown_norm: str) -> Optional[str]:
    """Tipo do exame quando ele exige laudo e a marca do laudo não está no documento."""
    regra = regras_identificacao.primeira_do_nome(regras_identificacao.MARCA_LAUDO, exame_norm)
    if regra is None:
        return None
    tipo = regra.parametros["tipo"]
    estrategia = regra.parametros.get("estrategia", "marca")
    if estrategia == "nome_fora_das_listas":
        # O nome do exame no laudo, fora das listas do ASO/voucher (ergométrico).
        return None if regra.vale(sem_listas(markdown_norm)) else tipo
    if estrategia == "laboratorio":
        # Resultado perto do nome, como o selo de laboratório (GGT).
        evidencia, _linha = evidencia_laboratorio.avaliar(markdown_norm, exame_norm)
        return tipo if evidencia == evidencia_laboratorio.SO_LISTA else None
    if estrategia == "sorologia":
        return None if _sorologia_tem_laudo(exame_norm, markdown_norm, regra) else tipo
    if regra.condicao_json is not None and not regra.vale(markdown_norm):
        return tipo
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
