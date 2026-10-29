#!/usr/bin/env python3
"""
Replay do alerta de laudo de outra pessoa (`app/services/identidade_laudo.py`,
STC-947) sobre o texto gravado, cruzado com o que o revisor decidiu.

Uso:
  cd back-end
  DATABASE_URL=postgresql://... .venv/bin/python scripts/replay_identidade_laudo.py
  DATABASE_URL=postgresql://... .venv/bin/python scripts/replay_identidade_laudo.py --de 2026-09-28 --ate 2026-10-21
  DATABASE_URL=postgresql://... .venv/bin/python scripts/replay_identidade_laudo.py --listar

**Somente leitura.** Não altera documento, não chama OpenAI, não roda OCR. Usa o
`ocr_markdown`, o CPF/nome do paciente e a `tabela_comparacao` gravados, o
vocabulário de nomes pelo mesmo caminho do motor (`nomes_conhecidos`) e o
catálogo de sinônimos (`workflow_service.obter_sinonimos`). Aponte para um
snapshot restaurado. Lê em lotes, com a transação fechada entre eles: um script
com transação aberta em `documents` trava o `ALTER TABLE` do app no startup.

O que é medido, por desfecho (outro colaborador / aprovado / rejeitado por
outro motivo / pendente):
  forte       documentos com aviso "Laudo de outra pessoa" (nome + CPF)
  fraco       documentos só com o aviso "Nome diferente no laudo"
  no exame    pessoas ligadas a um exame da tabela, contra as que caem na
              Checklist de Campos

"Outro colaborador" é o documento em que o revisor escreveu isso no motivo ou
no parecer (`RE_OUTRO_COLABORADOR`). Os itens "A IA leu o CPF/nome errado" do
parecer NÃO contam: são erro de leitura do OCR, não laudo de outra pessoa — a
primeira conta da vistoria os misturava (17 casos, dos quais 9 eram outro
colaborador).

Precisão não sai daqui: aviso em documento aprovado pode ser erro de revisão
(no replay de 23/10, todos os 10 fortes e os 15 fracos em aprovados eram outra
pessoa de fato, conferidos um a um). `--listar` imprime, por documento com
aviso, o desfecho e o nome achado MASCARADO, para a conferência no PDF.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from app.core.pii import mask_name  # noqa: E402
from app.services import identidade_laudo as il  # noqa: E402
from app.services import nomes_conhecidos  # noqa: E402

RE_OUTRO_COLABORADOR = re.compile(
    r"outr[oa] (paciente|pessoa|colaborador|funcion)|paciente trocad|de terceiro|laudo .{0,40}de outr", re.I
)
LOTE = 200

_FILTRO_PERIODO = """
  AND (CAST(:de AS date) IS NULL OR d.created_at >= CAST(:de AS date))
  AND (CAST(:ate AS date) IS NULL OR d.created_at < CAST(:ate AS date) + 1)
"""
SQL_IDS = "SELECT d.id FROM documents d WHERE d.ocr_markdown IS NOT NULL AND d.archived_at IS NULL" + _FILTRO_PERIODO + " ORDER BY d.id"
SQL_LOTE = """
SELECT d.id, d.cpf, d.ocr_markdown, d.result_payload, d.validation_status,
       COALESCE(d.rejection_reason, '') || ' ' || COALESCE(d.approval_reason, '') || ' ' || COALESCE(f.notes, '')
FROM documents d LEFT JOIN document_feedbacks f ON f.document_id = d.id
WHERE d.id = ANY(:ids)
"""


def _desfecho(status: str | None, motivo: str) -> str:
    if RE_OUTRO_COLABORADOR.search(motivo):
        return "outro colaborador"
    return {"validated": "aprovado", "rejected": "rejeitado (outro motivo)"}.get(status or "", "pendente")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--de", metavar="AAAA-MM-DD", help="documentos criados a partir desta data")
    parser.add_argument("--ate", metavar="AAAA-MM-DD", help="documentos criados até esta data (inclusive)")
    parser.add_argument("--listar", action="store_true", help="imprime cada documento com aviso (nome mascarado)")
    args = parser.parse_args()

    from app.core.database import user_db  # noqa: PLC0415
    from app.services import workflow_service as ws  # noqa: PLC0415

    # Antes de abrir a leitura: o catálogo e o vocabulário abrem conexão própria.
    ws.obter_sinonimos("ESPIROMETRIA")
    vocabulario = nomes_conhecidos._consultar()
    print(f"período: {args.de or 'início'} a {args.ate or 'hoje'} · vocabulário de nomes: {len(vocabulario)} palavras")

    filtros = {"de": args.de, "ate": args.ate}
    with user_db.engine.connect() as conexao:
        ids = [linha[0] for linha in conexao.execute(text(SQL_IDS), filtros)]
        conexao.commit()

    contagem: Counter = Counter()
    lista = []
    for inicio in range(0, len(ids), LOTE):
        with user_db.engine.connect() as conexao:
            linhas_db = conexao.execute(text(SQL_LOTE), {"ids": ids[inicio:inicio + LOTE]}).fetchall()
        for id_, cpf, markdown, payload, status, motivo in linhas_db:
            try:
                payload = json.loads(payload) if isinstance(payload, str) else (payload or {})
            except ValueError:
                payload = {}
            desfecho = _desfecho(status, motivo)
            contagem[(desfecho, "total")] += 1
            linhas = markdown.splitlines()
            cpf = cpf or payload.get("cpf_processado") or payload.get("cpf")
            pessoas = il.pessoas_no_documento(linhas, cpf, payload.get("patient_name"), nomes_conhecidos=vocabulario)
            if not pessoas:
                continue
            forte = any(p["tipo"] == il.NOME_E_CPF for p in pessoas)
            contagem[(desfecho, "forte" if forte else "fraco")] += 1
            il.anotar_comparativo(payload.get("tabela_comparacao") or [], pessoas, linhas, ws._normalizar_busca, ws.obter_sinonimos)
            for pessoa in pessoas:
                contagem[(pessoa["tipo"], "no exame" if pessoa["exames"] else "checklist")] += 1
            if args.listar:
                lista.append((id_[:8], desfecho, [(p["tipo"], mask_name(p["nome"]), p["exames"]) for p in pessoas]))

    print(f"\n{'desfecho':28} {'docs':>6} {'forte':>6} {'fraco':>6}")
    for desfecho in ("outro colaborador", "aprovado", "rejeitado (outro motivo)", "pendente"):
        print(
            f"{desfecho:28} {contagem[(desfecho, 'total')]:6d} "
            f"{contagem[(desfecho, 'forte')]:6d} {contagem[(desfecho, 'fraco')]:6d}"
        )
    print("\npessoas ligadas a exame da tabela (o resto vai para a Checklist de Campos):")
    for tipo in (il.NOME_E_CPF, il.SO_NOME):
        no_exame, checklist = contagem[(tipo, "no exame")], contagem[(tipo, "checklist")]
        print(f"  {tipo:11} {no_exame} de {no_exame + checklist}")
    for id_, desfecho, pessoas in lista:
        print(id_, desfecho, pessoas)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
