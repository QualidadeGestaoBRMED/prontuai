"""
Monitoramento silencioso das duas ajudas da checagem: nada aparece na tela e
ninguém precisa responder nada. Roda no fim do processamento de cada documento
novo e grava só contagens (payload, log e métricas OTLP).

1. Clique no exame (`layout_ocr.localizar_termos`). Para cada exame da tabela,
   a primeira página para onde o clique leva tem o CONTEÚDO do laudo daquele
   exame? A régua (`REGUA_LAUDO`) é independente dos títulos que o clique usa:
   anamnese e exame físico para o Clínico, limiares e frequências para a
   Audiometria, CVF e VEF1 para a Espirometria, mg/dL para a Glicemia.
   Resultado por exame: "acerto", "erro", "sem_laudo" (nenhuma página do PDF
   tem o conteúdo — não dá para julgar) ou "sem_ocorrencia" (o clique não acha
   nada, mas o laudo está lá). Exame fora da régua não é medido.

   É a mesma régua da medição de 29/10 nos PDFs da pasta semana (48% → 92%),
   agora sobre o layout do Textract de produção, escaneados incluídos.

2. Aviso de outra pessoa (`identidade_laudo`). A outra pessoa existe como
   paciente de verdade? "cpf": o CPF dela é o de algum documento do banco;
   "nome": o nome dela é o de um paciente da mesma clínica; senão,
   "sem_confirmacao". Confirmado é certeza — a taxa é a precisão MÍNIMA. Não
   confirmado não é erro: a outra pessoa pode não ter documento no ProntuAI (no
   replay de 23/10, 11 dos 14 fortes e 7 dos 15 fracos confirmaram, e os 29
   eram todos reais). Queda da taxa ao longo do tempo é o alarme de ruído.

O CPF de terceiro só é comparado no banco do próprio ProntuAI, nunca sai para
outro sistema, e não vai para log, payload nem métrica.

Desliga sem deploy de código: MONITORAMENTO_CHECAGEM=false. Falha aqui nunca
derruba o processamento: o chamador engole a exceção.
"""
from __future__ import annotations

import os
import re
import unicodedata
from collections import Counter
from typing import Any, Callable, Iterable, Optional

from app.services import identidade_laudo, layout_ocr

HABILITADO = os.getenv("MONITORAMENTO_CHECAGEM", "true").strip().lower() not in ("0", "false", "nao", "no")

_FREQUENCIAS = re.compile(r"\b(?:250|500|1000|1K|2000|2K|3000|3K|4000|4K|6000|6K|8000|8K)\b")


def _todos(*padroes: str) -> Callable[[str], bool]:
    compilados = [re.compile(p) for p in padroes]
    return lambda pagina: all(p.search(pagina) for p in compilados)


def _audiometria(pagina: str) -> bool:
    return len(set(_FREQUENCIAS.findall(pagina))) >= 4 or bool(re.search(r"LIMIAR", pagina) and re.search(r"\bDB\b", pagina))


# (grupo, casa no nome normalizado do exame, conteúdo de laudo na página).
# A página chega sem acento e em maiúsculas.
REGUA_LAUDO: list[tuple[str, re.Pattern, Callable[[str], bool]]] = [
    (grupo, re.compile(exame), conteudo)
    for grupo, exame, conteudo in (
        ("clinico", r"\bCLINICO\b",
         _todos(r"ANAMNESE", r"EXAME FISICO|PRESSAO ARTERIAL|AUSCULTA|FREQUENCIA CARDIACA")),
        ("audiometria", r"\bAUDIOMETRIA\b", _audiometria),
        ("acuidade", r"\bACUIDADE VISUAL\b|\bOFTALMOLOGIC", _todos(r"SNELLEN|ISHIHARA|JAEGER|\b20/\d{2,3}\b")),
        ("espirometria", r"\bESPIROMETRIA\b", _todos(r"\bCVF\b", r"\b(?:VEF|FEV) ?1")),
        ("ecg", r"\bELETROCARDIOGRAMA\b", _todos(r"RITMO SINUSAL|\bQRS\b|EIXO ELETRICO")),
        ("eeg", r"\bELETROENCEFALOGRAMA\b",
         _todos(r"ELETROGENESE|ATIVIDADE DE BASE|RITMO ALFA|ATIVIDADE ELETRICA CEREBRAL|PAROXISM")),
        ("glicemia", r"\bGLICEMIA\b|\bGLICOSE\b", _todos(r"GLICOSE|GLICEMIA", r"MG/ ?DL")),
        ("hemograma", r"\bHEMOGRAMA\b", _todos(r"HEMACIAS|ERITROCITOS", r"LEUCOCITOS")),
        ("rx_torax", r"\bTORAX\b",
         _todos(r"PNEUMOCONIOSE|CAMPOS PULMONARES|SEIOS COSTOFRENICOS|LEITURA RADIOLOGICA")),
    )
]


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)).upper()


def medir_clique(
    linhas: list[layout_ocr.LinhaPosicionada],
    exames: Iterable[str],
    termos_do_exame: Callable[[str], set[str]],
    normalizar: Callable[[str], str],
) -> list[dict[str, str]]:
    """[{"grupo", "resultado"}] para cada exame da régua. `termos_do_exame` e
    `normalizar` são os mesmos da rota de localização, para medir o clique que
    a tela faz de verdade."""
    exames = list(dict.fromkeys(e for e in exames if e))
    paginas: dict[int, list[str]] = {}
    for linha in linhas:
        paginas.setdefault(linha.pagina, []).append(linha.texto)
    texto_da_pagina = {p: _sem_acento("\n".join(t)) for p, t in paginas.items()}
    normalizadas = layout_ocr.normalizar_linhas(linhas, normalizar)
    termos = {exame: termos_do_exame(exame) for exame in exames}
    listas = layout_ocr.paginas_de_lista(linhas, normalizadas, termos.values())

    medidas = []
    for exame in exames:
        normalizado = normalizar(exame)
        regua = next(((g, c) for g, e, c in REGUA_LAUDO if e.search(normalizado)), None)
        if regua is None:
            continue
        grupo, conteudo = regua
        certas = {p for p, texto in texto_da_pagina.items() if conteudo(texto)}
        ocorrencias = layout_ocr.localizar_termos(
            linhas, normalizadas, termos[exame], listas, layout_ocr.titulos_do_exame(normalizado)
        )
        if not certas:
            resultado = "sem_laudo"
        elif not ocorrencias:
            resultado = "sem_ocorrencia"
        else:
            resultado = "acerto" if ocorrencias[0]["pagina"] in certas else "erro"
        medidas.append({"grupo": grupo, "resultado": resultado})
    return medidas


def confirmar_avisos(
    pessoas: list[dict],
    cpf_existe: Callable[[str], bool],
    nomes_da_clinica: Callable[[], list[str]],
) -> list[dict[str, str]]:
    """[{"tipo", "confirmacao"}] para cada pessoa de
    `identidade_laudo.pessoas_no_documento` (com o CPF inteiro, ainda em
    memória). As consultas ao banco vêm de fora, para o teste trocá-las; a dos
    nomes só roda se algum aviso precisar dela."""
    nomes: Optional[list[str]] = None
    medidas = []
    for pessoa in pessoas:
        if pessoa.get("cpf") and cpf_existe(pessoa["cpf"]):
            confirmacao = "cpf"
        else:
            if nomes is None:
                nomes = nomes_da_clinica()
            mesmo_nome = any(
                len(identidade_laudo._tokens(nome)) >= 2 and identidade_laudo.mesma_pessoa(nome, pessoa["nome"])
                for nome in nomes
            )
            confirmacao = "nome" if mesmo_nome else "sem_confirmacao"
        medidas.append({"tipo": pessoa.get("tipo", identidade_laudo.NOME_E_CPF), "confirmacao": confirmacao})
    return medidas


# ---------------------------------------------------------------------------
# Consultas ao banco do ProntuAI (import tardio, como em exam_catalog_source)
# ---------------------------------------------------------------------------

def cpf_existe_no_banco(cpf: str) -> bool:
    from sqlalchemy import text

    from app.core.database import user_db

    with user_db.engine.connect() as conexao:
        return conexao.execute(
            text("SELECT 1 FROM documents WHERE regexp_replace(COALESCE(cpf, ''), '\\D', '', 'g') = :cpf LIMIT 1"),
            {"cpf": re.sub(r"\D", "", cpf)},
        ).first() is not None


def nomes_da_clinica_no_banco(clinic_id: Optional[str]) -> list[str]:
    """Nomes de paciente da clínica no último ano. Sem clínica, nenhum."""
    if not clinic_id:
        return []
    from sqlalchemy import text

    from app.core.database import user_db

    with user_db.engine.connect() as conexao:
        return [
            nome
            for (nome,) in conexao.execute(
                text(
                    "SELECT DISTINCT patient_name FROM documents WHERE clinic_id = :clinica "
                    "AND patient_name IS NOT NULL AND created_at >= now() - interval '365 days'"
                ),
                {"clinica": clinic_id},
            )
        ]


def resumo(clique: list[dict[str, str]], avisos: list[dict[str, str]]) -> dict[str, Any]:
    """O que vai ao payload (`analysis_details.monitoramento`) e ao log: só
    contagens por grupo/resultado e por tipo/confirmação."""
    return {
        "clique": dict(Counter(f"{m['grupo']}:{m['resultado']}" for m in clique)),
        "avisos": dict(Counter(f"{m['tipo']}:{m['confirmacao']}" for m in avisos)),
    }
