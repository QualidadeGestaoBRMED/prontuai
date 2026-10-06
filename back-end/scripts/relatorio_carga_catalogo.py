#!/usr/bin/env python3
"""
Lista, em texto, os exames e nomes que as cargas acrescentaram à base.

Uso (dentro do container do backend, depois das cargas):
  python scripts/relatorio_carga_catalogo.py
  python scripts/relatorio_carga_catalogo.py --saida logs/exames_acrescentados.txt

Uma carga é reconhecida pelo autor gravado em cada linha (`created_by`), o
mesmo `--actor` usado no `seed_exam_catalog.py`. O relatório separa:

  - exames novos: o exame não existia e passou a existir, com os nomes
    alternativos que ganhou;
  - nomes novos em exames que já existiam.

Só consulta o catálogo; não altera nada.
"""
import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import bindparam, text  # noqa: E402

from app.core.database import user_db  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ATORES_PADRAO = ["seed:planilha-de-para", "seed:variacoes-sugeridas"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Exames e nomes acrescentados à base pelas cargas.")
    parser.add_argument("--ator", action="append",
                        help="autor da carga (repetível). Padrão: as duas cargas de out/2026")
    parser.add_argument("--saida", help="arquivo .txt (padrão: logs/exames_acrescentados_<data>.txt)")
    args = parser.parse_args()
    atores = args.ator or ATORES_PADRAO

    with user_db.engine.connect() as conexao:
        pais = {
            pid: {"nome": nome, "novo": criado_por in atores}
            for pid, nome, criado_por in conexao.execute(
                text("SELECT id, name, created_by FROM exam_parents WHERE is_active")
            )
        }
        consulta = text(
            "SELECT parent_id, name FROM exam_variations "
            "WHERE is_active AND created_by IN :atores ORDER BY name"
        ).bindparams(bindparam("atores", expanding=True))
        nomes = defaultdict(list)
        for pid, nome in conexao.execute(consulta, {"atores": atores}):
            if pid in pais:
                nomes[pid].append(nome)

    novos = sorted((p for p in pais if pais[p]["novo"]), key=lambda p: pais[p]["nome"].upper())
    antigos = sorted((p for p in nomes if not pais[p]["novo"]), key=lambda p: pais[p]["nome"].upper())
    total_nomes = sum(len(v) for v in nomes.values())

    linhas = [
        "EXAMES ACRESCENTADOS À BASE",
        f"Gerado em {datetime.now():%d/%m/%Y %H:%M}",
        f"Cargas: {', '.join(atores)}",
        "",
        f"Exames novos ................................ {len(novos):>5}",
        f"Exames que já existiam e ganharam nome novo . {len(antigos):>5}",
        f"Nomes acrescentados (total) ................. {total_nomes:>5}",
        "",
        "=" * 70,
        f"EXAMES NOVOS ({len(novos)})",
        "=" * 70,
    ]
    for pid in novos:
        linhas.append(pais[pid]["nome"])
        linhas.extend(f"    + {nome}" for nome in nomes.get(pid, []))
    linhas += [
        "",
        "=" * 70,
        f"NOMES NOVOS EM EXAMES QUE JÁ EXISTIAM ({len(antigos)})",
        "=" * 70,
    ]
    for pid in antigos:
        linhas.append(pais[pid]["nome"])
        linhas.extend(f"    + {nome}" for nome in nomes[pid])

    saida = args.saida or os.path.join(RAIZ, "logs", f"exames_acrescentados_{datetime.now():%Y%m%d_%H%M}.txt")
    os.makedirs(os.path.dirname(os.path.abspath(saida)), exist_ok=True)
    with open(saida, "w", encoding="utf-8") as handle:
        handle.write("\n".join(linhas) + "\n")
    print("\n".join(linhas))
    print(f"\nRelatório salvo em {saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
