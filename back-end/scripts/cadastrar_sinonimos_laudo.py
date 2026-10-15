#!/usr/bin/env python3
"""
Cadastra como variação os nomes de exame que os laudos usam e o catálogo não tem.

O PROBLEMA QUE ISSO RESOLVE
    O portão de extração e a varredura determinística só enxergam o que está no
    catálogo. Nome que o laudo usa e o catálogo desconhece é descartado em
    `_filtrar_exames_ocr` antes de qualquer comparação, e a varredura de
    `exam_catalog_source.varrer_markdown` não tem o que procurar no texto.

    Medido nos 50 documentos com markdown gravado (semanas de 28/09 e 05/10 de
    2026), varrendo todo cabeçalho `##` dos laudos e comparando com o vocabulário
    efetivo (catálogo UNIDO aos artefatos de disco): os laudos da BR MED são
    **bilíngues** e o catálogo só tem o lado português. `PURE TONE AUDIOMETRY`
    aparece 41 vezes, `CLINICAL EXAMINATION` 58, `ELECTROCARDIOGRAM` 36 — todos
    invisíveis para o motor.

    Caso concreto: em `be1f8b3e` o BRNET pediu AUDIOMETRIA TONAL e o OCR extraiu
    `PURE TONE AUDIOMETRY` e `AVALIAÇÃO AUDIOMÉTRICA OCUPACIONAL`. As duas foram
    para o comparativo como `extra_no_ocr`, porque nenhuma liga ao que o BRNET
    pediu.

O QUE ENTRA
    Só o que foi CONTADO nesses 50 documentos, com o pai já existente no
    catálogo. A tabela abaixo é literal de propósito: cadastrar sinônimo é
    decisão de curadoria, e uma lista inferida em tempo de execução esconderia
    essa decisão (ver `cadastrar_pendencias_catalogo.py`, que por isso não
    cadastra variação nenhuma).

O QUE FICOU DE FORA, E POR QUÊ
    `AV`     Grafia real de acuidade visual em `5d722b94` (`## 1. AV`). NÃO
             ENTRA: a normalização derruba a pontuação, então `Av.` de endereço
             vira o mesmo token — 6 colisões no mesmo documento ("Av. Sul Gov.
             Cid Sampaio", "Av Wilson Tavares Ribeiro"). Dois caracteres não
             discriminam nada.

    `AST`,   Nunca aparecem sozinhos: nos 50 documentos as 15 ocorrências estão
    `ALT`    todas coladas em TGO/TGP (`## TGO (AST)`, `TRANSAMINASE OXALACETICA
             - AST/TGO`), e o catálogo já cobre esses. As únicas ocorrências
             isoladas são "D. alt." e "S, alt" em prosa.

    `AUDIOMETRIA`  Casaria dentro de `AUDIOMETRIA VOCAL`, que é outro exame. O
             motor já trata audiometria com folga em `_is_audiometria_marker`.

    `AUDIOMETRIA NORMAL`  É conclusão de laudo, não nome de exame.

    `GLUCOSE`  38 ocorrências, mas glicose aparece também em EAS e a decisão de
             glicose do catálogo está pendente desde a carga de 06/10. Fica para
             a curadoria resolver junto com chumbo.

    `TESTE DE PATERNIDADE DNA`  Cabeçalho vindo da tabela de preços do
             laboratório, não de laudo. Bom lembrete de que nem todo `##` do
             markdown é exame.

EFEITO ESPERADO
    Variação cadastrada entra em três lugares de uma vez: no portão de extração
    (`MASTER_EXAM_TERMS`), no casamento determinístico (`EXAM_SYNONYM_MAP`) e na
    varredura do markdown. Nos exames não laboratoriais a varredura continua sem
    recuperar, porque `exigir_valor` pede unidade ou vocabulário de laudo por
    perto e `VISUAL ACUITY` não tem — mas os outros dois caminhos não têm essa
    exigência, e são eles que resolvem o caso do `PURE TONE AUDIOMETRY`.

DEPOIS DE GRAVAR
    O cache de `exam_catalog_source` é por processo. O script invalida o dele;
    reinicie a aplicação para que a API pegue o vocabulário novo.

USO
    python scripts/cadastrar_sinonimos_laudo.py              # dry-run
    python scripts/cadastrar_sinonimos_laudo.py --aplicar
    python scripts/cadastrar_sinonimos_laudo.py --aplicar --ator seu.email@grupobrmed.com.br
"""
import argparse
import json
import os
import sys
from typing import Any, Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import user_db  # noqa: E402
from app.services import exam_catalog_source  # noqa: E402

ORIGEM = "laudo_bilingue"

# (variação a cadastrar, nome normalizado do pai, ocorrências medidas nos 50 markdowns)
#
# A contagem não é enfeite: é o que separa um sinônimo real de um palpite. Quem
# acrescentar linha aqui mede antes, com o mesmo corpus.
SINONIMOS: List[Tuple[str, str, int]] = [
    # Laudos bilíngues da BR MED — o catálogo só tinha o lado português.
    ("Clinical Examination",           "CLINICO OCUPACIONAL",              58),
    ("Pure Tone Audiometry",           "AUDIOMETRIA TONAL",                41),
    ("Electrocardiogram",              "ELETROCARDIOGRAMA",                36),
    ("Electroencephalogram",           "ELETROENCEFALOGRAMA",              21),
    ("Visual Acuity",                  "ACUIDADE VISUAL",                  20),
    ("Psychosocial Assessment",        "AVALIACAO PSICOSSOCIAL",           18),
    ("Spirometry",                     "ESPIROMETRIA",                     16),
    ("Psychological Assessment",       "AVALIACAO PSICOLOGICA",            13),
    ("Chest Standard OIT Radiography", "RADIOGRAFIA DE TORAX PADRAO OIT",  13),
    ("Dental Assessment",              "AVALIACAO ODONTOLOGICA",            8),
    ("Lumbar Column Radiography",      "RADIOGRAFIA DE COLUNA LOMBAR",      6),
    ("Chest PA Radiography",           "RADIOGRAFIA DE TORAX PA",           6),
    # Grafias em português que faltavam.
    ("Audiometria Ocupacional",        "AUDIOMETRIA TONAL",                15),
    ("Exame Audiométrico",             "AUDIOMETRIA TONAL",                 4),
    ("Acuidade Visual para Longe",     "ACUIDADE VISUAL",                   4),
    ("Acuidade Visual para Perto",     "ACUIDADE VISUAL",                   4),
    # `## LIPIDOGRAMA` puro. O catálogo tinha PERFIL LIPIDICO, LIPIDOGRAMA
    # COMPLETO e PAINEL LIPIDICO, mas não o nome sozinho — que é como o laudo de
    # `3c31aeb6` escreve.
    ("Lipidograma",                    "LIPIDOGRAMA PERFIL LIPIDICO",       1),
]

NOTA = (
    "Sinônimo medido em 50 laudos reais (28/09 e 05/10 de 2026) e ausente do "
    "catálogo. Ver scripts/cadastrar_sinonimos_laudo.py para o corpus, a "
    "contagem e o que ficou de fora."
)


def _pais_por_chave() -> Dict[str, str]:
    """Mapa nome_normalizado -> id, só dos pais ativos."""
    from sqlalchemy import text

    with user_db.engine.connect() as conexao:
        return {
            chave: pid
            for pid, chave in conexao.execute(
                text("SELECT id, name_normalized FROM exam_parents WHERE is_active")
            )
        }


def _cadastrar(variacao: str, pai_chave: str, ocorrencias: int,
               pais: Dict[str, str], ator: str) -> Dict[str, Any]:
    linha = {"variacao": variacao, "pai": pai_chave, "ocorrencias": ocorrencias}

    parent_id = pais.get(pai_chave)
    if not parent_id:
        # Pai cadastrado com outro nome, ou inativo. Não se inventa pai aqui:
        # criar um a partir de um sinônimo rachava o grupo em dois.
        return {**linha, "situacao": "pai_inexistente"}

    try:
        criada = user_db.create_exam_variation(
            parent_id=parent_id,
            name=variacao,
            source=ORIGEM,
            occurrences=ocorrencias,
            actor=ator,
        )
        if criada is None:
            return {**linha, "situacao": "pai_inexistente"}
        return {**linha, "situacao": "cadastrada", "variation_id": criada.id}
    except ValueError as colisao:
        # Catálogo é árvore estrita: o termo já existe como pai ou como variação.
        # Se já existe, o exame já está coberto e não há nada a fazer.
        return {**linha, "situacao": "ja_no_catalogo", "detalhe": str(colisao)}
    except Exception as erro:
        return {**linha, "situacao": "falhou", "detalhe": str(erro)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cadastra variações de exame medidas nos laudos e ausentes do catálogo.",
        epilog="Sem --aplicar não grava nada.",
    )
    parser.add_argument("--aplicar", action="store_true", help="grava (padrão é dry-run)")
    parser.add_argument(
        "--ator",
        default="script:cadastrar_sinonimos_laudo",
        help="quem fica registrado como autor do cadastro",
    )
    parser.add_argument("--json", metavar="ARQUIVO", help="salva o relatório em JSON")
    args = parser.parse_args()

    pais = _pais_por_chave()

    if not args.aplicar:
        print(f"DRY-RUN — {len(SINONIMOS)} variações candidatas. Nada foi gravado.\n")
        for variacao, pai_chave, ocorrencias in SINONIMOS:
            marca = "ok " if pai_chave in pais else "SEM PAI"
            print(f"  [{marca:7}] {variacao:32} -> {pai_chave:34} ({ocorrencias}x)")
        print("\nRode de novo com --aplicar para gravar.")
        return 0

    resultados = [
        _cadastrar(variacao, pai_chave, ocorrencias, pais, args.ator)
        for variacao, pai_chave, ocorrencias in SINONIMOS
    ]

    contagem: Dict[str, int] = {}
    for item in resultados:
        contagem[item["situacao"]] = contagem.get(item["situacao"], 0) + 1

    for item in resultados:
        detalhe = f"  ({item['detalhe']})" if item.get("detalhe") else ""
        print(f"  [{item['situacao']:15}] {item['variacao']:32} -> {item['pai']}{detalhe}")

    print("\nResumo: " + ", ".join(f"{k}={v}" for k, v in sorted(contagem.items())))

    # Cache é por processo; o da aplicação só muda no restart.
    exam_catalog_source.invalidar()
    print("Cache deste processo invalidado. Reinicie a aplicação para a API pegar o novo vocabulário.")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as arquivo:
            json.dump({"origem": ORIGEM, "resultados": resultados, "resumo": contagem},
                      arquivo, ensure_ascii=False, indent=2)
        print(f"Relatório em {args.json}")

    return 0 if not contagem.get("falhou") else 1


if __name__ == "__main__":
    sys.exit(main())
