#!/usr/bin/env python3
"""
Pipeline de teste: confere, documento por documento, se a captação de exames
está correta — e quanto do erro o catálogo do painel resolveria.

Uso:
  cd back-end
  DATABASE_URL=postgresql://... python3 scripts/verificar_captacao_exames.py
  DATABASE_URL=postgresql://... python3 scripts/verificar_captacao_exames.py --out relatorio.csv

**Somente leitura.** Não altera documento nem catálogo, não chama OpenAI, não
roda OCR. Aponte para um snapshot restaurado, não para o banco de produção.

O que é medido
--------------
Para cada exame que a validação marcou como faltante, a pergunta é: **o exame
estava no documento com outro nome?** O árbitro é o `ocr_markdown` (texto bruto
do OCR), normalizado com a mesma função que o catálogo usa, e os termos de busca
são o nome do pai mais todas as variações cadastradas.

Três veredictos possíveis:

  `catalogo_pegaria`     Um termo do catálogo está no texto, mas o exame foi
                         declarado faltante. O motor errou e o catálogo conserta
                         — é o ganho direto de ligar a tabela no motor.

  `ausencia_confirmada`  Nenhum termo do catálogo aparece no texto. O exame
                         provavelmente não foi feito e o revisor liberou por
                         decisão de negócio. Catálogo NÃO resolve, e inventar
                         sinônimo aqui ensinaria o motor a liberar prontuário
                         incompleto.

  `sem_pai_no_catalogo`  O exame faltante não tem nenhuma entrada no catálogo,
                         nem como pai nem como variação. Impossível julgar: só
                         cadastrar o pai destrava.

Duas colunas de evidência acompanham o veredicto `catalogo_pegaria`:

  `estava_em_exams_ocr`  Se falso, o termo estava no texto bruto mas nunca virou
                         item em `exams_ocr` — prova de que o portão de extração
                         (`MASTER_EXAM_TERMS`) descartou antes da comparação.

  `valor_proximo`        Se há dígito perto do termo no texto. Presença do nome
                         não é o mesmo que exame realizado: no corpus, "perfil
                         lipídico" aparecia em frase de protocolo
                         ("padronização da determinação laboratorial do perfil
                         lipídico") sem nenhum resultado. Isto é evidência
                         auxiliar, não filtro — a heurística de unidade na mesma
                         linha falha quando o OCR formata em tabela, então o
                         veredicto não depende dela.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from app.core.exam_normalize import normalizar_termo  # noqa: E402

# Termo com menos de 3 caracteres normalizados casa por acidente em texto
# corrido, mesmo com fronteira de palavra. Fica de fora e é reportado.
MIN_TERMO = 3
# O parêntese do nome do BRNET quase sempre é apelido do exame — mas às vezes é
# o material da coleta: "DOSAGEM DE ÁLCOOL ETÍLICO (SANGUE)", "TESTE RÁPIDO -
# MULTIDROGAS (URINA)". Achar "SANGUE" num laudo não prova nada, então esses
# termos não podem virar critério. Custou 8 falsos positivos na primeira medição.
TERMOS_GENERICOS = frozenset({
    "SANGUE", "SANGUE TOTAL", "URINA", "SORO", "PLASMA", "FEZES", "SALIVA",
    "CABELO", "SUOR", "AR EXPIRADO", "EXTERNO", "MATERIAL", "AMOSTRA",
})
# Janela (em caracteres do texto normalizado) para procurar dígito perto do
# termo. O texto normalizado não tem quebra de linha, então a janela atravessa
# linhas de propósito: em OCR de tabela o valor fica longe do nome.
JANELA_VALOR = 120


def carregar_catalogo(conexao):
    """
    Devolve:
      termo_para_pai:  chave normalizada (pai ou variação) -> id do pai
      termos_do_pai:   id do pai -> chaves normalizadas de busca
      nome_do_pai:     id do pai -> nome legível
      chave_do_pai:    id do pai -> chave normalizada do próprio pai
    """
    termo_para_pai: dict[str, str] = {}
    termos_do_pai: dict[str, list[str]] = defaultdict(list)
    nome_do_pai: dict[str, str] = {}
    chave_do_pai: dict[str, str] = {}

    for pid, nome, chave in conexao.execute(
        text("SELECT id, name, name_normalized FROM exam_parents")
    ):
        nome_do_pai[pid] = nome
        chave_do_pai[pid] = chave
        termo_para_pai[chave] = pid
        termos_do_pai[pid].append(chave)

    for pid, chave in conexao.execute(
        text("SELECT parent_id, name_normalized FROM exam_variations WHERE is_active")
    ):
        if pid not in nome_do_pai:
            continue
        termo_para_pai[chave] = pid
        termos_do_pai[pid].append(chave)

    return termo_para_pai, termos_do_pai, nome_do_pai, chave_do_pai


_cache_regex: dict[str, re.Pattern] = {}


def _regex_do_termo(termo: str) -> re.Pattern:
    padrao = _cache_regex.get(termo)
    if padrao is None:
        padrao = re.compile(rf"\b{re.escape(termo)}\b")
        _cache_regex[termo] = padrao
    return padrao


def procurar_termo(texto_norm: str, termos: list[str]) -> tuple[str | None, bool]:
    """
    Procura qualquer um dos termos no texto normalizado.
    Devolve (termo encontrado, havia dígito por perto).
    """
    for termo in termos:
        if len(termo) < MIN_TERMO:
            continue
        achado = _regex_do_termo(termo).search(texto_norm)
        if not achado:
            continue
        janela = texto_norm[achado.end() : achado.end() + JANELA_VALOR]
        return termo, bool(re.search(r"\d", janela))
    return None, False


def termos_do_nome(nome_bruto: str) -> list[str]:
    """
    Termos de busca derivados do próprio nome do exame do BRNET.

    O BRNET carrega o apelido entre parênteses — "TGP (ALT)", "GGT (Gama-GT)",
    "SUMÁRIO DE URINA (EAS)", "LIPIDOGRAMA (PERFIL LIPÍDICO)". São dois nomes do
    mesmo exame colados num rótulo, então procurar só a frase inteira não acha
    nada: medido no corpus, "TGP (ALT)" completo aparece em 0 documentos,
    enquanto "TGP" isolado aparece em 39 dos 85. Cada pedaço vira um termo.

    Ordem importa: o mais específico primeiro, para o termo reportado ser o mais
    informativo quando mais de um casa.
    """
    candidatos = [nome_bruto]
    dentro = re.findall(r"\(([^)]*)\)", nome_bruto)
    fora = re.sub(r"\([^)]*\)", " ", nome_bruto)
    candidatos.append(fora)
    candidatos.extend(dentro)

    termos: list[str] = []
    for candidato in candidatos:
        chave = normalizar_termo(candidato)
        if chave in TERMOS_GENERICOS:
            continue
        if len(chave) >= MIN_TERMO and chave not in termos:
            termos.append(chave)
    termos.sort(key=len, reverse=True)
    return termos


def cobertura_tokens(nome_norm: str, tokens_texto: set[str]) -> float:
    """
    Fração dos tokens significativos do nome do exame presentes no texto.

    Serve para nome composto, onde casar a frase inteira quase nunca acontece:
    "AVALIACAO OFTALMOLOGICA ACUIDADE VISUAL SENSO CROMATICO E FUNDOSCOPIA"
    não aparece literalmente em documento nenhum, mas se todos os seus tokens
    estão lá, o exame provavelmente está. É sinal graduado, não veredicto.
    """
    tokens = [t for t in nome_norm.split() if len(t) >= MIN_TERMO]
    if not tokens:
        return 0.0
    presentes = sum(1 for t in tokens if t in tokens_texto)
    return round(presentes / len(tokens), 2)


def extrair_faltantes(payload_bruto: str | None) -> list[str] | None:
    """Lista de exames faltantes do result_payload. None = documento sem julgamento."""
    if not payload_bruto:
        return None
    try:
        payload = json.loads(payload_bruto)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    validacao = payload.get("validation_result")
    if not isinstance(validacao, dict):
        return None
    faltantes = validacao.get("exames_faltantes")
    if not isinstance(faltantes, list):
        return None
    return [f for f in faltantes if isinstance(f, str) and f.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None, help="CSV com uma linha por (documento, faltante).")
    parser.add_argument("--limit", type=int, default=0, help="Processa só os N primeiros documentos.")
    parser.add_argument("--top", type=int, default=20, help="Quantos exames mostrar no ranking.")
    args = parser.parse_args()

    from app.core.database import user_db  # noqa: PLC0415

    with user_db.engine.connect() as conexao:
        termo_para_pai, termos_do_pai, nome_do_pai, chave_do_pai = carregar_catalogo(conexao)
        print(
            f"catálogo: {len(nome_do_pai)} pais, "
            f"{len(termo_para_pai) - len(nome_do_pai)} variações, "
            f"{len(termo_para_pai)} termos de busca"
        )

        sql = """
            SELECT id, validation_status, exams_ocr, ocr_markdown,
                   COALESCE(result_payload, result_payload_compact) AS payload
            FROM documents
            ORDER BY uploaded_at
        """
        if args.limit:
            sql += f" LIMIT {int(args.limit)}"

        linhas_saida: list[dict] = []
        veredictos = Counter()
        docs_total = 0
        docs_sem_julgamento = 0
        docs_sem_markdown = 0
        docs_com_faltante = 0
        por_exame: dict[str, Counter] = defaultdict(Counter)
        termos_curtos = set()

        resultado = conexao.execution_options(stream_results=True, max_row_buffer=100).execute(text(sql))
        for doc_id, status_doc, exams_ocr, markdown, payload in resultado:
            docs_total += 1
            faltantes = extrair_faltantes(payload)
            if faltantes is None:
                docs_sem_julgamento += 1
                continue
            if not faltantes:
                continue
            docs_com_faltante += 1
            if not markdown or len(markdown) < 50:
                docs_sem_markdown += 1
                continue

            texto_norm = normalizar_termo(markdown)
            tokens_texto = set(texto_norm.split())
            ocr_norm = {normalizar_termo(e) for e in (exams_ocr or []) if e}

            for faltante in faltantes:
                chave = normalizar_termo(faltante)
                pid = termo_para_pai.get(chave)

                # Sem pai no catálogo não é motivo para desistir do julgamento:
                # procura-se o próprio nome do exame. Se ele está no texto, o
                # motor perdeu um exame que estava lá — e criar o pai resolve,
                # sem precisar descobrir sinônimo nenhum.
                if pid is None:
                    termos = termos_do_nome(faltante)
                    origem_base = "nome_proprio"
                else:
                    termos = termos_do_pai[pid]
                    origem_base = "catalogo"
                termos_curtos.update(t for t in termos if len(t) < MIN_TERMO)

                termo_achado, valor_proximo = procurar_termo(texto_norm, termos)
                cobertura = cobertura_tokens(chave, tokens_texto)

                if termo_achado:
                    veredicto = "motor_perdeu"
                    em_ocr = termo_achado in ocr_norm
                    if origem_base == "nome_proprio":
                        origem = "nome_proprio"
                    elif termo_achado == chave_do_pai[pid]:
                        origem = "nome_do_pai"
                    else:
                        origem = "variacao_do_catalogo"
                else:
                    veredicto = "ausencia_provavel"
                    em_ocr = None
                    origem = ""

                veredictos[veredicto] += 1
                por_exame[chave][veredicto] += 1
                linhas_saida.append({
                    "document_id": doc_id,
                    "validation_status": status_doc,
                    "exame_faltante": faltante,
                    "chave_normalizada": chave,
                    "tem_pai_no_catalogo": str(pid is not None).lower(),
                    "pai_no_catalogo": nome_do_pai.get(pid, "") if pid else "",
                    "veredicto": veredicto,
                    "origem_do_termo": origem,
                    "termo_encontrado": termo_achado or "",
                    "cobertura_tokens": cobertura,
                    "estava_em_exams_ocr": "" if em_ocr is None else str(em_ocr).lower(),
                    "valor_proximo": str(valor_proximo).lower() if termo_achado else "",
                })

    total = sum(veredictos.values())
    print(f"\ndocumentos lidos:                 {docs_total}")
    print(f"  sem julgamento no payload:      {docs_sem_julgamento}")
    print(f"  com ao menos um faltante:       {docs_com_faltante}")
    print(f"  descartados por falta de OCR:   {docs_sem_markdown}")
    print(f"\nocorrências de faltante avaliadas: {total}")

    perdeu = [linha for linha in linhas_saida if linha["veredicto"] == "motor_perdeu"]
    ausente = [linha for linha in linhas_saida if linha["veredicto"] == "ausencia_provavel"]

    if total:
        print(f"  motor_perdeu        {len(perdeu):5d}  ({100 * len(perdeu) / total:5.1f}%)  "
              f"o termo está no texto e o exame foi dado como faltante")
        print(f"  ausencia_provavel   {len(ausente):5d}  ({100 * len(ausente) / total:5.1f}%)  "
              f"nenhum termo conhecido no texto")

    if perdeu:
        origens = Counter(linha["origem_do_termo"] for linha in perdeu)
        print(f"\ndos {len(perdeu)} que o motor perdeu, o que casou foi:")
        rotulos = {
            "variacao_do_catalogo": "uma variação do catálogo (só o catálogo resolve)",
            "nome_do_pai": "o próprio nome do pai, já cadastrado",
            "nome_proprio": "o nome do exame, que NÃO tem pai no catálogo (criar o pai resolve)",
        }
        for origem, n in origens.most_common():
            print(f"  {n:5d}  {rotulos.get(origem, origem)}")

        barrados = sum(1 for linha in perdeu if linha["estava_em_exams_ocr"] == "false")
        com_valor = sum(1 for linha in perdeu if linha["valor_proximo"] == "true")
        print(f"\n  barrados pelo portão de extração (não chegaram em exams_ocr): {barrados}")
        print(f"  com dígito perto do termo (evidência de resultado):            {com_valor}")

    if ausente:
        # Nome composto raramente casa por frase inteira. Cobertura alta de
        # tokens em documento julgado "ausente" é suspeita a investigar, não
        # veredicto — pode ser o exame com nome reorganizado.
        suspeitos = [linha for linha in ausente if float(linha["cobertura_tokens"]) >= 0.75]
        print(f"\ndos {len(ausente)} dados como ausentes, {len(suspeitos)} têm >=75% dos tokens do")
        print("  nome presentes no texto — candidatos a revisão manual, não conclusão.")

    print(f"\ntop {args.top} exames faltantes:")
    print(f"  {'exame':52s} {'total':>6s} {'perdeu':>7s} {'ausente':>8s}  pai?")
    ranking = sorted(por_exame.items(), key=lambda item: -sum(item[1].values()))
    tem_pai_por_chave = {
        linha["chave_normalizada"]: linha["tem_pai_no_catalogo"] for linha in linhas_saida
    }
    for chave, contagem in ranking[: args.top]:
        print(
            f"  {chave[:52]:52s} {sum(contagem.values()):6d} "
            f"{contagem['motor_perdeu']:7d} {contagem['ausencia_provavel']:8d}"
            f"  {'sim' if tem_pai_por_chave.get(chave) == 'true' else 'NAO'}"
        )

    if termos_curtos:
        print(f"\ntermos ignorados por terem menos de {MIN_TERMO} caracteres: {sorted(termos_curtos)}")

    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as handle:
            escritor = csv.DictWriter(handle, fieldnames=list(linhas_saida[0].keys()) if linhas_saida else [])
            if linhas_saida:
                escritor.writeheader()
                escritor.writerows(linhas_saida)
        print(f"\nrelatório: {args.out}  ({len(linhas_saida)} linhas)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
