#!/usr/bin/env python3
"""
Replay da regra "só na lista do ASO" (`app/services/evidencia_laboratorio.py`)
sobre o texto gravado, cruzado com o modal de feedback.

Uso:
  cd back-end
  DATABASE_URL=postgresql://... .venv/bin/python scripts/replay_evidencia_laboratorio.py
  DATABASE_URL=postgresql://... .venv/bin/python scripts/replay_evidencia_laboratorio.py --de 2026-09-28 --ate 2026-10-21
  DATABASE_URL=postgresql://... .venv/bin/python scripts/replay_evidencia_laboratorio.py --documentos id1,id2

**Somente leitura.** Não altera documento, não chama OpenAI, não roda OCR. Usa o
`ocr_markdown` e a `tabela_comparacao` gravados (achada em qualquer nível de
`result_payload`) e o catálogo do banco pelo mesmo caminho do motor
(`exam_catalog_source.sinonimos_de`). Aponte para um snapshot restaurado.

O que é medido
--------------
  positivos   exames de laboratório que o revisor marcou "Não estava"
              (ENCONTRADO_INCORRETO em `document_feedbacks.issue_items`) e que a
              IA deu como encontrados: quantos a regra sela "so_lista".
  selo à toa  exames de laboratório encontrados em documentos aprovados
              corretamente (feedback IA_CORRETA + validation_status validated)
              que a regra sela "so_lista" — exames e documentos.
  alcance     documentos julgados (validated/rejected) com algum selo, sobre o
              total de julgados com tabela de comparação.

`--de/--ate` filtram por `documents.created_at` as três medidas. Sem eles, vale
o banco inteiro.

`--documentos` imprime, por documento, cada exame encontrado com a evidência e a
linha de origem. A linha vem do documento e pode ter dado de paciente: é saída
de terminal para conferência, não cole em canal nem em ticket.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from app.services import evidencia_laboratorio as ev  # noqa: E402

_FILTRO_PERIODO = """
  AND (CAST(:de AS date) IS NULL OR d.created_at >= CAST(:de AS date))
  AND (CAST(:ate AS date) IS NULL OR d.created_at < CAST(:ate AS date) + 1)
"""

SQL_FEEDBACK = """
SELECT d.id, f.status, d.validation_status, f.issue_items::text, d.ocr_markdown,
       jsonb_path_query_first(COALESCE(d.result_payload, d.result_payload_compact)::jsonb,
                              'strict $.**.tabela_comparacao')::text
FROM document_feedbacks f
JOIN documents d ON d.id = f.document_id
WHERE d.ocr_markdown IS NOT NULL
""" + _FILTRO_PERIODO

SQL_JULGADOS = """
SELECT d.id, d.ocr_markdown,
       jsonb_path_query_first(COALESCE(d.result_payload, d.result_payload_compact)::jsonb,
                              'strict $.**.tabela_comparacao')::text
FROM documents d
WHERE d.ocr_markdown IS NOT NULL
  AND d.validation_status IN ('validated', 'rejected')
""" + _FILTRO_PERIODO

SQL_DOCUMENTOS = """
SELECT d.id, d.validation_status, d.ocr_markdown,
       jsonb_path_query_first(COALESCE(d.result_payload, d.result_payload_compact)::jsonb,
                              'strict $.**.tabela_comparacao')::text
FROM documents d
WHERE d.id = ANY(:ids)
"""


def _sinonimos_de(chave: str) -> set[str]:
    from app.services import exam_catalog_source  # noqa: PLC0415

    return exam_catalog_source.sinonimos_de(chave)


def _anotar(markdown: str, tabela_json: str | None) -> list[dict]:
    """Tabela gravada, só com os itens "encontrado", anotada pela regra."""
    tabela = json.loads(tabela_json) if tabela_json else []
    if not isinstance(tabela, list):
        return []
    # Descarta qualquer selo já gravado: o replay mede a regra de agora.
    itens = [
        {"exame": t.get("exame"), "status": t.get("status")}
        for t in tabela
        if isinstance(t, dict) and t.get("status") == "encontrado" and t.get("exame")
    ]
    ev.anotar_comparativo(itens, markdown or "", _sinonimos_de)
    return itens


def _medir_feedback(conexao, de, ate) -> None:
    res = Counter()
    positivos: list[tuple[str, str, str | None]] = []
    selo_a_toa: Counter = Counter()
    aprovados = set()
    for id_, fst, vst, issues, md, tab in conexao.execute(text(SQL_FEEDBACK), {"de": de, "ate": ate}):
        issues = json.loads(issues or "[]")
        errados = {
            ev.normalizar(i.get("exame"))
            for i in issues
            if isinstance(i, dict) and i.get("categoria") == "ENCONTRADO_INCORRETO"
        }
        aprovado = fst == "IA_CORRETA" and vst == "validated"
        if aprovado:
            aprovados.add(id_)
        for item in _anotar(md, tab):
            if not ev.eh_laboratorio(item["exame"]):
                continue
            evidencia = item.get("evidencia")
            if ev.normalizar(item["exame"]) in errados:
                res[f"positivo_{evidencia}"] += 1
                positivos.append((id_[:8], item["exame"], evidencia))
            elif aprovado:
                res[f"aprovado_{evidencia}"] += 1
                if evidencia == ev.SO_LISTA:
                    selo_a_toa[(id_, item["exame"])] += 1

    total_pos = len(positivos)
    pegos = res[f"positivo_{ev.SO_LISTA}"]
    print(f'positivos pegos: {pegos} de {total_pos} "Não estava" de laboratório '
          f'(com_resultado={res["positivo_" + ev.COM_RESULTADO]}, nome ausente={res["positivo_None"]})')
    for doc, exame, evidencia in positivos:
        print(f"  {doc}  {exame}  -> {evidencia}")
    docs_a_toa = {d for d, _ in selo_a_toa}
    print(f"selo à toa em aprovados certos: {len(selo_a_toa)} exames em {len(docs_a_toa)} "
          f"de {len(aprovados)} documentos "
          f"(laboratório avaliado: com_resultado={res['aprovado_' + ev.COM_RESULTADO]}, "
          f"so_lista={res['aprovado_' + ev.SO_LISTA]}, nome ausente={res['aprovado_None']})")
    por_exame = Counter(e for _, e in selo_a_toa)
    print("  por exame:", ", ".join(f"{e} {n}" for e, n in por_exame.most_common(12)))


def _medir_alcance(conexao, de, ate) -> None:
    julgados = selados = exames = 0
    for _id, md, tab in conexao.execute(text(SQL_JULGADOS), {"de": de, "ate": ate}):
        if not tab:
            continue
        julgados += 1
        n = sum(1 for i in _anotar(md, tab) if i.get("evidencia") == ev.SO_LISTA)
        if n:
            selados += 1
            exames += n
    pct = f"{100 * selados / julgados:.1f}%" if julgados else "-"
    print(f"alcance: {selados} de {julgados} documentos julgados com selo ({pct}), {exames} exames selados")


def _imprimir_documentos(conexao, ids: list[str]) -> None:
    for id_, vst, md, tab in conexao.execute(text(SQL_DOCUMENTOS), {"ids": ids}):
        print(f"\n{id_}  ({vst})")
        itens = _anotar(md, tab)
        if not itens:
            print("  sem itens encontrados na tabela de comparação")
        for item in itens:
            tipo = "lab" if ev.eh_laboratorio(item["exame"]) else "   "
            print(f"  [{tipo}] {item['exame']}: {item.get('evidencia', '-')}")
            print(f"        {item.get('linha_origem') or '(nome não achado no texto)'}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--de", metavar="AAAA-MM-DD", help="documentos criados a partir desta data")
    parser.add_argument("--ate", metavar="AAAA-MM-DD", help="documentos criados até esta data (inclusive)")
    parser.add_argument("--documentos", metavar="ID1,ID2", help="imprime exames, evidência e linha de origem")
    args = parser.parse_args()

    from app.core.database import user_db  # noqa: PLC0415

    with user_db.engine.connect() as conexao:
        if args.documentos:
            _imprimir_documentos(conexao, [i.strip() for i in args.documentos.split(",") if i.strip()])
            return 0
        print(f"período: {args.de or 'início'} a {args.ate or 'hoje'}")
        _medir_feedback(conexao, args.de, args.ate)
        _medir_alcance(conexao, args.de, args.ate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
