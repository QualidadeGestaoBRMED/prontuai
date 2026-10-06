#!/usr/bin/env python3
"""
Cadastra como exame pai as pendências do catálogo que o BRNET já pede e que o
motor já reconhece.

O PROBLEMA QUE ISSO RESOLVE
    `listar_pendencias_catalogo` acusa um exame quando ele não tem pai no
    catálogo OU nunca foi encontrado em documento. Medido no dev: das 70
    pendências, **69 são do primeiro caso** — exames que o BRNET pede, que os
    documentos trazem e que o motor reconhece normalmente, mas que ninguém
    cadastrou. Só 1 é do segundo caso, que é o alerta que o painel existe para
    dar.

    Com o painel 98,6% ocupado por exames que estão funcionando, o único que
    realmente precisa de olhar humano fica invisível.

    Eles são reconhecidos sem cadastro porque o portão de extração é o catálogo
    UNIDO aos nomes que o BRNET pede (`_filtrar_exames_ocr`): nome pedido entra
    no vocabulário automaticamente. Reconhecer e estar cadastrado são coisas
    diferentes, e a pendência aponta a segunda.

O QUE ENTRA
    Só pendência com `parent_id is None` E `never_found is False`: o BRNET pede,
    o documento traz, o catálogo não tem.

    O `never_found` fica DE FORA de propósito. É o exame que o BRNET pede e que
    nunca conseguimos reconhecer — cadastrá-lo apagaria o único sinal verdadeiro
    do painel, trocando um alerta por um registro que não corrige nada.

O QUE É GRAVADO
    `status="ativo"`, porque é literalmente o que o status significa aqui ("nome
    confirmado no BRNET" — ver `app/models/exam.py`) e a origem destes nomes é
    `documents.exams_brnet`.

    `source="brnet_pendencias"` para a curadoria distinguir de `csv_seed` e de
    `manual`, e conseguir desfazer em bloco se decidir diferente.

    **Sem variações.** Cadastrar sinônimo é decisão de curadoria, não de script:
    o mapa órfão de `front-end/app/api/comparar-exames/route.ts` traz candidatos
    (`tsh` → `hormonio estimulante da tireoide`, ...), mas alguns são discutíveis
    clinicamente — ele trata `funcao tireoidiana` como sinônimo de `tsh`. Fica
    para uma revisão à parte.

COLISÃO COM VARIAÇÃO EXISTENTE
    O catálogo é árvore estrita: um termo normalizado existe uma vez só, como pai
    ou como variação. Se a pendência já existir como variação de outro pai, o
    cadastro é recusado pelo repositório — e está certo, porque o exame JÁ está
    no catálogo.

    Isso expõe um defeito da consulta de pendências, não deste script:
    `listar_pendencias_catalogo` monta `pai_por_chave` só de `exam_parents` e
    ignora `exam_variations`, então exame coberto por variação aparece como
    pendência e não há como tirá-lo dali. No dev é 1 caso (`CREATININA SÉRICA`).
    O script reporta como `ja_no_catalogo` em vez de falhar.

DEPOIS DE GRAVAR
    O cache de `exam_catalog_source` é invalidado. Ele é por processo e o painel
    invalida a cada escrita; um script que grava por fora precisa fazer o mesmo,
    senão o processo que já está de pé segue com o vocabulário antigo. Com mais
    de um worker, só o processo deste script é atingido — reinicie a aplicação.

USO
    python scripts/cadastrar_pendencias_catalogo.py              # dry-run
    python scripts/cadastrar_pendencias_catalogo.py --aplicar
    python scripts/cadastrar_pendencias_catalogo.py --aplicar --ator seu.email@grupobrmed.com.br
"""
import argparse
import json
import os
import sys
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import user_db  # noqa: E402
from app.models.audit_log import AuditLogCreate  # noqa: E402
from app.services import exam_catalog_source  # noqa: E402

ORIGEM = "brnet_pendencias"
NOTA = (
    "Cadastrado em lote a partir das pendências do catálogo: exame pedido pelo "
    "BRNET e já reconhecido em documento, que estava sem pai. Sem variações — "
    "sinônimos pendentes de curadoria."
)


def _candidatos(limite: int) -> List[Any]:
    """Pendências que o BRNET pede e que o motor já reconhece.

    `never_found` fica fora: é o alerta legítimo do painel (ver docstring).
    """
    pendencias = user_db.listar_pendencias_catalogo(limit=limite)
    return [p for p in pendencias if p.parent_id is None and not p.never_found]


def _cadastrar(pendencia, ator: str) -> Dict[str, Any]:
    linha = {
        "nome": pendencia.name,
        "normalizado": pendencia.name_normalized,
        "documentos": pendencia.documents,
        "pedidos": pendencia.requests,
    }
    try:
        criado = user_db.create_exam_parent(
            name=pendencia.name,
            status="ativo",
            is_external=False,
            notes=NOTA,
            variations=None,
            source=ORIGEM,
            actor=ator,
        )
        return {**linha, "situacao": "cadastrado", "parent_id": criado.id}
    except ValueError as colisao:
        # Termo já ocupado no catálogo (como pai ou como variação). O exame já
        # está coberto; quem precisa de conserto é a consulta de pendências.
        return {**linha, "situacao": "ja_no_catalogo", "detalhe": str(colisao)}
    except Exception as erro:
        return {**linha, "situacao": "falhou", "detalhe": str(erro)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Cadastra como exame pai as pendências que o BRNET pede e o motor já "
            "reconhece."
        ),
        epilog="Sem --aplicar não grava nada. Nunca cadastra pendência 'nunca encontrada'.",
    )
    parser.add_argument("--aplicar", action="store_true", help="grava (padrão é dry-run)")
    parser.add_argument("--limite", type=int, default=500, help="teto de pendências lidas")
    parser.add_argument(
        "--ator",
        default="script:cadastrar_pendencias_catalogo",
        help="quem fica registrado como autor do cadastro",
    )
    parser.add_argument("--json", metavar="ARQUIVO", help="salva o relatório em JSON")
    args = parser.parse_args()

    candidatos = _candidatos(args.limite)
    if not candidatos:
        print("Nenhuma pendência cadastrável.")
        return 0

    print(
        f"{len(candidatos)} pendência(s) sem pai e já reconhecidas | "
        f"{'GRAVANDO' if args.aplicar else 'DRY-RUN (use --aplicar)'}\n"
    )

    if not args.aplicar:
        for pendencia in candidatos:
            print(f"  {pendencia.documents:>5} docs  {pendencia.name}")
        print(f"\nSeriam cadastrados como status=ativo, source={ORIGEM}, sem variações.")
        return 0

    resultados = [_cadastrar(p, args.ator) for p in candidatos]

    for linha in resultados:
        marca = {"cadastrado": "+", "ja_no_catalogo": "=", "falhou": "!"}[linha["situacao"]]
        print(f"  {marca} {linha['documentos']:>5} docs  {linha['nome']}", end="")
        print(f"   ({linha['detalhe']})" if linha.get("detalhe") else "")

    contagem: Dict[str, int] = {}
    for linha in resultados:
        contagem[linha["situacao"]] = contagem.get(linha["situacao"], 0) + 1
    print()
    for situacao, quantos in sorted(contagem.items()):
        print(f"  {situacao}: {quantos}")

    # Sem isto o processo segue com o vocabulário antigo em memória.
    exam_catalog_source.invalidar()
    print("\ncache do catálogo invalidado")

    try:
        user_db.create_audit_log(
            AuditLogCreate(
                action="exams.catalogo_cadastro_em_lote",
                resource="exam_parents",
                user_email=args.ator,
                status_code=200,
                metadata={
                    # Nome de exame não é PII.
                    "origem": ORIGEM,
                    "cadastrados": contagem.get("cadastrado", 0),
                    "ja_no_catalogo": contagem.get("ja_no_catalogo", 0),
                    "falhas": contagem.get("falhou", 0),
                    "nomes": [l["nome"] for l in resultados if l["situacao"] == "cadastrado"],
                },
            )
        )
    except Exception as erro_auditoria:
        print(f"AVISO: falha ao registrar auditoria: {erro_auditoria}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as saida:
            json.dump(resultados, saida, ensure_ascii=False, indent=2)
        print(f"Relatório em {args.json}")

    return 1 if contagem.get("falhou") else 0


if __name__ == "__main__":
    sys.exit(main())
