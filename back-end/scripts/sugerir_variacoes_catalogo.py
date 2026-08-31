#!/usr/bin/env python3
"""
Cruza todas as fontes disponíveis para sugerir o que cadastrar no catálogo.

Uso:
  cd back-end
  DATABASE_URL=postgresql://... python3 scripts/sugerir_variacoes_catalogo.py

Somente leitura. Não chama OpenAI, não roda OCR, não escreve nada.

Quatro fontes
-------------
1. **Faltantes julgados** — `result_payload.validation_result.exames_faltantes`
   cruzado com `ocr_markdown`: quais exames o motor deu como ausentes tendo o
   termo no texto.

2. **Vocabulário cru do extrator** — `exams_ocr` dos documentos **sem** lista
   BRNET. `_filtrar_exames_ocr` retorna cedo quando `exames_brnet` está vazio
   (`if not exames_brnet: return exames_ocr`), então esses documentos preservam
   a saída do extrator antes do portão. É a única janela para as grafias que o
   OCR realmente produz — nos documentos normais elas são descartadas antes de
   persistir.

3. **Linhas do `ocr_markdown`** onde o termo do exame aparece: a grafia como
   está no laudo.

4. **Catálogo atual**, para não sugerir o que já existe.

Uma sugestão só é emitida quando a grafia candidata **existe de fato** numa das
fontes 2 ou 3. Nada é inventado por semelhança de string.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from app.core.exam_normalize import normalizar_termo  # noqa: E402

# Termos que o extrator emite mas não são exame: tipo de consulta, documento,
# medida antropométrica. Sugerir isso poluiria o portão de extração.
RUIDO = {
    "ADMISSIONAL", "PERIODICO", "DEMISSIONAL", "RETORNO AO TRABALHO",
    "MUDANCA DE RISCOS OCUPACIONAIS", "MUDANCA DE FUNCAO", "CLINICAL EXAMINATION",
    "MEDICAL HEALTH CERTIFICATE", "EXAME FISICO", "EXAME CLINICO", "IMC", "CID",
    "DI", "FICHA MEDICA ADMISSIONAL", "FICHA MEDICA DEMISSIONAL", "ANAMNESE",
    "HISTORICO", "RESULTADO", "OBSERVACOES", "CONCLUSAO", "APTO", "INAPTO",
}
STOPWORDS = {"DE", "DA", "DO", "DAS", "DOS", "E", "COM", "SEM", "PARA", "POR", "NO", "NA"}


def tokens(termo: str) -> set[str]:
    return {t for t in termo.split() if len(t) >= 3 and t not in STOPWORDS}


def aliases_do_nome(nome: str) -> list[str]:
    """Nome inteiro + o que está fora e dentro dos parênteses, normalizados."""
    partes = [nome, re.sub(r"\([^)]*\)", " ", nome), *re.findall(r"\(([^)]*)\)", nome)]
    vistos = []
    for parte in partes:
        chave = normalizar_termo(parte)
        if len(chave) >= 3 and chave not in vistos:
            vistos.append(chave)
    return vistos


def parece_variacao(alvo_aliases: list[str], candidato: str) -> bool:
    """
    O candidato pertence ao exame?

    Critério: um alias do exame está contido no candidato (ou o inverso), ou os
    tokens do alias são subconjunto dos do candidato. Nada de similaridade
    difusa — a ideia é sugerir pouco e certo, não muito e duvidoso.
    """
    if candidato in RUIDO:
        return False
    cand_tokens = tokens(candidato)
    if not cand_tokens:
        return False
    for alias in alvo_aliases:
        alias_tokens = tokens(alias)
        if not alias_tokens:
            continue
        if alias == candidato:
            return False  # já é o próprio nome
        if f" {alias} " in f" {candidato} " or f" {candidato} " in f" {alias} ":
            return True
        if alias_tokens <= cand_tokens or cand_tokens <= alias_tokens:
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=int, default=12, help="Quantos exames detalhar.")
    args = parser.parse_args()

    from app.core.database import user_db  # noqa: PLC0415

    with user_db.engine.connect() as conexao:
        # --- fonte 4: catalogo atual ---
        no_catalogo = {
            chave
            for (chave,) in conexao.execute(
                text("SELECT name_normalized FROM exam_parents WHERE is_active")
            )
        } | {
            chave
            for (chave,) in conexao.execute(
                text("SELECT name_normalized FROM exam_variations WHERE is_active")
            )
        }

        # --- fonte 2: vocabulario cru do extrator (docs sem lista BRNET) ---
        cru: dict[str, int] = {}
        for termo, n in conexao.execute(
            text(
                "SELECT lower(btrim(e)), count(*) FROM documents d, "
                "unnest(coalesce(d.exams_ocr,'{}')) e "
                "WHERE d.exams_brnet IS NULL OR cardinality(d.exams_brnet)=0 "
                "GROUP BY 1"
            )
        ):
            chave = normalizar_termo(termo)
            if chave:
                cru[chave] = cru.get(chave, 0) + int(n)

        # --- fonte 1 e 3: faltantes + texto bruto ---
        faltante_docs: dict[str, list[str]] = collections.defaultdict(list)
        markdown_por_doc: dict[str, str] = {}
        for doc_id, markdown, payload in conexao.execute(
            text(
                "SELECT id, ocr_markdown, COALESCE(result_payload, result_payload_compact) "
                "FROM documents WHERE ocr_markdown IS NOT NULL"
            )
        ):
            try:
                validacao = (json.loads(payload) or {}).get("validation_result") or {}
            except (TypeError, ValueError):
                continue
            faltantes = validacao.get("exames_faltantes")
            if not isinstance(faltantes, list) or not faltantes:
                continue
            markdown_por_doc[doc_id] = markdown
            for exame in faltantes:
                if isinstance(exame, str) and exame.strip():
                    faltante_docs[exame.strip()].append(doc_id)

    ranking = sorted(faltante_docs.items(), key=lambda item: -len(item[1]))

    print(f"vocabulário cru do extrator: {len(cru)} grafias distintas")
    print(f"catálogo atual: {len(no_catalogo)} termos")
    print(f"exames faltantes distintos: {len(ranking)}\n")
    print("=" * 78)

    total_sugestoes = 0
    for nome, docs in ranking[: args.top]:
        aliases = aliases_do_nome(nome)
        chave = normalizar_termo(nome)
        ja_tem_pai = chave in no_catalogo

        # fonte 2: grafias do extrator que pertencem a este exame
        do_extrator = sorted(
            ((t, n) for t, n in cru.items() if parece_variacao(aliases, t)),
            key=lambda x: -x[1],
        )
        # fonte 3: grafias presentes no texto bruto dos documentos deste faltante
        do_texto: collections.Counter = collections.Counter()
        for doc_id in docs:
            texto_norm = normalizar_termo(markdown_por_doc.get(doc_id, ""))
            for alias in aliases:
                if len(alias) >= 3 and re.search(rf"\b{re.escape(alias)}\b", texto_norm):
                    do_texto[alias] += 1

        novos_extrator = [(t, n) for t, n in do_extrator if t not in no_catalogo]
        novos_texto = [(t, n) for t, n in do_texto.items() if t not in no_catalogo]
        if not novos_extrator and not novos_texto and ja_tem_pai:
            continue

        print(f"\n{nome}")
        print(f"  documentos afetados: {len(docs)}   pai no catálogo: {'sim' if ja_tem_pai else 'NÃO'}")
        if novos_texto:
            print("  grafias presentes no texto do laudo (fonte: ocr_markdown):")
            for termo, n in sorted(novos_texto, key=lambda x: -x[1]):
                print(f"      + {termo:52s} em {n} doc(s)")
                total_sugestoes += 1
        if novos_extrator:
            print("  grafias que o EXTRATOR realmente emite (fonte: docs sem BRNET):")
            for termo, n in novos_extrator[:8]:
                print(f"      + {termo:52s} visto {n}x")
                total_sugestoes += 1
        if not novos_extrator and not novos_texto:
            print("  nenhuma grafia nova encontrada nas fontes — provável ausência real do exame")

    print("\n" + "=" * 78)
    print(f"total de grafias sugeridas: {total_sugestoes}")
    print("Toda grafia acima existe de fato numa das fontes; nada foi inferido por semelhança.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
