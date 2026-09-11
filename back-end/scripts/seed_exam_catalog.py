#!/usr/bin/env python3
"""
Importa `exames_similares_final.csv` para o catálogo de exames do painel.

Uso:
  cd back-end
  DATABASE_URL=postgresql://... python3 scripts/seed_exam_catalog.py --dry-run
  DATABASE_URL=postgresql://... python3 scripts/seed_exam_catalog.py

As três regras de modelagem do catálogo são aplicadas aqui:

  1. **Pai é nome do BRNET.** A lista de nomes válidos sai de
     `documents.exams_brnet` (o que o BRNET realmente pediu nos documentos) ou
     de `--brnet-names arquivo.txt`. Pai fora dessa lista entra como
     `quarentena`: não vale como canônico, mas o nome continua servindo de
     vocabulário. Nada é descartado.

  2. **Árvore estrita.** Uma variação pertence a um único pai. Quando o CSV
     manda o mesmo termo para dois pais, a linha NÃO entra — vai para
     `exam_variation_conflicts` e espera decisão humana no painel. O importador
     não escolhe.

  3. **"(externo)" é flag**, não pai separado. O BRNET usa "externo" em 1 de
     134 nomes, mas o CSV gastava 61 de 371 linhas criando pais espelhados.

Sobre o parse: a coluna `Similares` traz **um** similar por linha. O
carregador antigo (`_load_exam_similarity_csv`) fazia `split(",")` e picava em
fragmentos os 13 similares que têm vírgula no próprio nome — foi assim que
`"2,5-hexanodiona urinaria"` virou `["2", "5-hexanodiona urinaria"]` dentro do
índice FAISS. Aqui a linha é lida como um par (pai, uma variação).

Idempotente: termo que já existe no catálogo é contado como "já presente" e
não vira erro nem duplicata.
"""
from __future__ import annotations

import argparse
import csv
import sys
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.exam_normalize import (  # noqa: E402
    limpar_texto,
    normalizar_termo,
    separar_marcador_externo,
)

CSV_PADRAO = ROOT / "exames_similares_final.csv"
ORIGEM = "csv_seed"


def carregar_csv(caminho: Path) -> list[tuple[str, str]]:
    """Lê o CSV como pares (nome do pai, nome da variação), sem split de vírgula."""
    pares: list[tuple[str, str]] = []
    with open(caminho, newline="", encoding="utf-8") as handle:
        for linha in csv.DictReader(handle):
            pai = limpar_texto(linha.get("Exame") or linha.get("exame") or "")
            variacao = limpar_texto(linha.get("Similares") or linha.get("similares") or "")
            if not pai:
                continue
            pares.append((pai, variacao))
    return pares


def carregar_nomes_brnet(arquivo: Path | None) -> set[str]:
    """Nomes normalizados que o BRNET usa — a lista de pais legítimos (regra 1)."""
    if arquivo:
        with open(arquivo, encoding="utf-8") as handle:
            return {
                normalizar_termo(linha) for linha in handle if normalizar_termo(linha)
            }

    from sqlalchemy import text  # noqa: PLC0415

    from app.core.database import user_db  # noqa: PLC0415

    nomes: set[str] = set()
    with user_db.engine.connect() as conexao:
        linhas = conexao.execute(
            text(
                "SELECT DISTINCT unnest(exams_brnet) FROM documents "
                "WHERE exams_brnet IS NOT NULL"
            )
        )
        for (nome,) in linhas:
            normalizado = normalizar_termo(nome or "")
            if normalizado:
                nomes.add(normalizado)
    return nomes


def montar_catalogo(pares: list[tuple[str, str]], nomes_brnet: set[str]) -> dict:
    """
    Aplica as três regras e devolve o catálogo a gravar, mais os conflitos.

    Retorna dict com:
      pais       -> {normalizado: {"name", "is_external", "status"}}
      variacoes  -> {normalizado: {"name", "pai_norm"}}
      conflitos  -> {normalizado: {"name", "candidatos": [nomes de pai]}}
    """
    # Regra 3: "(externo)" sai do nome e vira flag do pai.
    pais: dict[str, dict] = {}
    variacao_para_pais: dict[str, set[str]] = defaultdict(set)
    nome_original_variacao: dict[str, str] = {}

    for pai_bruto, variacao_bruta in pares:
        pai_nome, pai_externo = separar_marcador_externo(pai_bruto)
        pai_norm = normalizar_termo(pai_nome)
        if not pai_norm:
            continue

        registro = pais.setdefault(
            pai_norm, {"name": pai_nome, "is_external": False}
        )
        registro["is_external"] = registro["is_external"] or pai_externo

        if not variacao_bruta:
            continue
        var_nome, _ = separar_marcador_externo(variacao_bruta)
        var_norm = normalizar_termo(var_nome)
        if not var_norm or var_norm == pai_norm:
            continue
        variacao_para_pais[var_norm].add(pai_norm)
        nome_original_variacao.setdefault(var_norm, var_nome)

    # Regra 1: pai só é canônico se o BRNET usa esse nome.
    for pai_norm, registro in pais.items():
        registro["status"] = "ativo" if pai_norm in nomes_brnet else "quarentena"

    # Regra 2: árvore estrita. Termo que também é pai, ou que serve a mais de
    # um pai, não entra automaticamente.
    variacoes: dict[str, dict] = {}
    conflitos: dict[str, dict] = {}
    for var_norm, pais_candidatos in variacao_para_pais.items():
        if var_norm in pais:
            # O termo já é um exame pai; virar variação de outro pai quebraria
            # a árvore. Fica como conflito para decisão humana.
            conflitos[var_norm] = {
                "name": nome_original_variacao[var_norm],
                "candidatos": sorted(pais[p]["name"] for p in pais_candidatos),
                "motivo": "termo também existe como exame pai",
            }
            continue
        if len(pais_candidatos) > 1:
            conflitos[var_norm] = {
                "name": nome_original_variacao[var_norm],
                "candidatos": sorted(pais[p]["name"] for p in pais_candidatos),
                "motivo": "termo aparece sob mais de um pai",
            }
            continue
        variacoes[var_norm] = {
            "name": nome_original_variacao[var_norm],
            "pai_norm": next(iter(pais_candidatos)),
        }

    return {"pais": pais, "variacoes": variacoes, "conflitos": conflitos}


def gravar(catalogo: dict, actor: str) -> dict:
    """Grava o catálogo. Idempotente: termo já existente é ignorado."""
    from app.core.db.models import (  # noqa: PLC0415
        ExamParentModel,
        ExamVariationConflictModel,
        ExamVariationModel,
    )
    from app.core.database import user_db  # noqa: PLC0415

    contadores = {
        "pais_criados": 0,
        "pais_existentes": 0,
        "variacoes_criadas": 0,
        "variacoes_existentes": 0,
        "conflitos_criados": 0,
        "conflitos_existentes": 0,
    }
    sessao = user_db._get_session()
    try:
        agora = datetime.utcnow()

        ids_por_norm: dict[str, str] = {}
        for norm, registro in sorted(catalogo["pais"].items()):
            existente = (
                sessao.query(ExamParentModel)
                .filter(ExamParentModel.name_normalized == norm)
                .first()
            )
            if existente:
                ids_por_norm[norm] = existente.id
                contadores["pais_existentes"] += 1
                continue
            novo_id = str(uuid.uuid4())
            sessao.add(
                ExamParentModel(
                    id=novo_id,
                    name=registro["name"],
                    name_normalized=norm,
                    status=registro["status"],
                    is_external=registro["is_external"],
                    is_active=True,
                    source=ORIGEM,
                    created_at=agora,
                    created_by=actor,
                    updated_at=agora,
                    updated_by=actor,
                )
            )
            ids_por_norm[norm] = novo_id
            contadores["pais_criados"] += 1
        sessao.flush()

        for norm, registro in sorted(catalogo["variacoes"].items()):
            ja_existe = (
                sessao.query(ExamVariationModel)
                .filter(ExamVariationModel.name_normalized == norm)
                .first()
            )
            if ja_existe:
                contadores["variacoes_existentes"] += 1
                continue
            sessao.add(
                ExamVariationModel(
                    id=str(uuid.uuid4()),
                    parent_id=ids_por_norm[registro["pai_norm"]],
                    name=registro["name"],
                    name_normalized=norm,
                    is_active=True,
                    source=ORIGEM,
                    created_at=agora,
                    created_by=actor,
                    updated_at=agora,
                    updated_by=actor,
                )
            )
            contadores["variacoes_criadas"] += 1

        for norm, registro in sorted(catalogo["conflitos"].items()):
            ja_existe = (
                sessao.query(ExamVariationConflictModel)
                .filter(ExamVariationConflictModel.name_normalized == norm)
                .first()
            )
            if ja_existe:
                contadores["conflitos_existentes"] += 1
                continue
            sessao.add(
                ExamVariationConflictModel(
                    id=str(uuid.uuid4()),
                    name=registro["name"],
                    name_normalized=norm,
                    candidate_parents=registro["candidatos"],
                    source=ORIGEM,
                    created_at=agora,
                )
            )
            contadores["conflitos_criados"] += 1

        sessao.commit()
    except Exception:
        sessao.rollback()
        raise
    finally:
        sessao.close()
    return contadores


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=CSV_PADRAO)
    parser.add_argument(
        "--brnet-names",
        type=Path,
        default=None,
        help="Arquivo com um nome de exame do BRNET por linha. "
        "Sem ele, a lista sai de documents.exams_brnet.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Só relata, não grava.")
    parser.add_argument("--actor", default="seed:csv", help="Autor gravado nas linhas.")
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"CSV não encontrado: {args.csv}", file=sys.stderr)
        return 1

    pares = carregar_csv(args.csv)
    nomes_brnet = carregar_nomes_brnet(args.brnet_names)
    if not nomes_brnet:
        print(
            "AVISO: nenhum nome do BRNET encontrado — todo pai entrará como "
            "'quarentena'. Passe --brnet-names para classificar corretamente.",
            file=sys.stderr,
        )

    catalogo = montar_catalogo(pares, nomes_brnet)
    pais = catalogo["pais"]
    ativos = sum(1 for p in pais.values() if p["status"] == "ativo")
    externos = sum(1 for p in pais.values() if p["is_external"])

    print(f"linhas lidas do CSV:        {len(pares)}")
    print(f"nomes do BRNET conhecidos:  {len(nomes_brnet)}")
    print(f"exames pai:                 {len(pais)}  ({externos} com flag externo)")
    print(f"  status ativo:             {ativos}")
    print(f"  status quarentena:        {len(pais) - ativos}")
    print(f"variações:                  {len(catalogo['variacoes'])}")
    print(f"conflitos (decisão humana): {len(catalogo['conflitos'])}")
    for norm, registro in sorted(catalogo["conflitos"].items()):
        print(f"    '{registro['name']}' — {registro['motivo']}: {registro['candidatos']}")

    nao_cobertos = sorted(nomes_brnet - set(pais))
    print(f"\nnomes do BRNET sem pai no catálogo: {len(nao_cobertos)}")
    for nome in nao_cobertos[:15]:
        print(f"    - {nome}")
    if len(nao_cobertos) > 15:
        print(f"    ... e outros {len(nao_cobertos) - 15}")

    if args.dry_run:
        print("\n[dry-run] nada foi gravado.")
        return 0

    contadores = gravar(catalogo, args.actor)
    print("\ngravado:")
    for chave, valor in contadores.items():
        print(f"  {chave}: {valor}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
