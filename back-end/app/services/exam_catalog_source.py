"""
Vocabulário de exames vindo do catálogo curado no banco.

O motor tem três consumidores do catálogo, e este módulo alimenta os dois que
importam mais:

  `MASTER_EXAM_TERMS`  portão de extração. Nome de exame do OCR que não está
                       aqui é descartado em `_filtrar_exames_ocr` **antes** de
                       qualquer comparação. Medido no corpus de 6153 documentos:
                       118 dos 122 casos em que o motor perdeu um exame que
                       estava no documento são resolvidos só por este conjunto.

  `EXAM_SYNONYM_MAP`   match determinístico de sinônimo, em `_match_ocr_exame`.

**Nunca reduz o vocabulário.** O que vem daqui é sempre unido ao que os
artefatos de disco já forneciam, nunca os substitui: catálogo vazio, banco
indisponível ou tabela inexistente deixam o motor exatamente como estava. Por
isso o import de `user_db` é tardio e toda falha é engolida com log — um erro de
banco não pode piorar a validação.

O cache é invalidado explicitamente pelo painel a cada escrita
(`invalidar()`). Com `WORKERS=1` há um processo só, então isso basta; com mais
de um worker cada processo manteria seu próprio cache e ficaria defasado até o
próximo restart.
"""
from __future__ import annotations

import logging
import re
import threading

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_termos: set[str] | None = None
_sinonimos: dict[str, set[str]] | None = None


def invalidar() -> None:
    """Descarta o cache. Chamado pelo painel depois de cada escrita."""
    global _termos, _sinonimos
    with _lock:
        _termos = None
        _sinonimos = None
    logger.info("[EXAM_CATALOG] Cache de vocabulário invalidado")


def _carregar() -> None:
    """
    Lê o catálogo e monta os dois agregados.

    Só linhas ativas entram. Pai em quarentena entra também: ele não vale como
    canônico na comparação, mas o nome continua sendo vocabulário legítimo para
    o portão de extração — 58% dos termos do catálogo estão sob pai em
    quarentena, e descartá-los estreitaria justamente o gargalo.
    """
    global _termos, _sinonimos

    termos: set[str] = set()
    grupos: dict[str, set[str]] = {}

    try:
        from sqlalchemy import text  # import tardio de propósito

        from app.core.database import user_db

        with user_db.engine.connect() as conexao:
            # Duas consultas, não uma por pai: o cache carrega inteiro de uma vez.
            chave_do_pai = {
                pid: chave
                for pid, chave in conexao.execute(
                    text(
                        "SELECT id, name_normalized FROM exam_parents "
                        "WHERE is_active AND name_normalized <> ''"
                    )
                )
            }
            grupo_do_pai: dict[str, set[str]] = {
                pid: {chave} for pid, chave in chave_do_pai.items()
            }
            for pid, chave in conexao.execute(
                text(
                    "SELECT parent_id, name_normalized FROM exam_variations "
                    "WHERE is_active AND name_normalized <> ''"
                )
            ):
                if pid in grupo_do_pai:
                    grupo_do_pai[pid].add(chave)

        for grupo in grupo_do_pai.values():
            grupo.discard("")
            if not grupo:
                continue
            termos |= grupo
            for termo in grupo:
                grupos.setdefault(termo, set()).update(grupo)

        logger.info(
            f"[EXAM_CATALOG] Vocabulário carregado do banco: {len(termos)} termos, "
            f"{len(chave_do_pai)} exames pai"
        )
    except Exception as e:
        # Banco fora, tabela inexistente, DATABASE_URL ausente: segue só com o
        # vocabulário de disco. Nunca deixa o motor pior do que estava.
        logger.warning(
            f"[EXAM_CATALOG] Catálogo do banco indisponível, usando apenas artefatos "
            f"de disco: {type(e).__name__}: {e}"
        )
        termos, grupos = set(), {}

    _termos = termos
    _sinonimos = grupos


def _garantir_carregado() -> None:
    if _termos is None:
        with _lock:
            if _termos is None:
                _carregar()


def termos_do_catalogo() -> set[str]:
    """Termos normalizados do catálogo (pais e variações ativas)."""
    _garantir_carregado()
    return _termos or set()


def sinonimos_de(termo_normalizado: str) -> set[str]:
    """
    Grupo de sinônimos do termo, segundo o catálogo.

    Lookup direto em vez de mesclar o mapa inteiro: isto é chamado uma vez por
    exame obrigatório de cada documento.
    """
    _garantir_carregado()
    if not _sinonimos:
        return set()
    return _sinonimos.get(termo_normalizado, set())


def estatisticas() -> dict:
    """Para diagnóstico: o que o motor está enxergando neste processo."""
    _garantir_carregado()
    return {
        "termos_do_banco": len(_termos or set()),
        "grupos_de_sinonimo": len(_sinonimos or {}),
        "cache_carregado": _termos is not None,
    }


# ---------------------------------------------------------------------------
# Varredura determinística do markdown
#
# Existe porque a extração de exames é uma chamada de LLM e é instável: medido
# em 4 execuções sobre o MESMO markdown, o extrator devolveu 14, 13, 9 e 13
# exames, com só 9 termos presentes em todas — "AVALIACAO OFTALMOLOGICA" saiu em
# 1 de 4. Nenhum catálogo conserta termo que o extrator não emitiu.
#
# A varredura fecha esse buraco pelo outro lado: em vez de esperar o LLM citar o
# exame, procura no texto os sinônimos catalogados do que o BRNET pediu. É
# determinística, não custa chamada de API e só ACRESCENTA candidato — nunca
# remove, então não pode piorar o que já funcionava.
# ---------------------------------------------------------------------------

MIN_TERMO_VARREDURA = 3
# Janela em caracteres do texto normalizado, para CADA LADO do termo. Os dois
# lados importam: medido no corpus, em "TRANSAMINASE PIRUVICA TGP 19 U L" e em
# "DE REFERENCIA HOMENS INFERIOR A 42 0 U L" a unidade vem ANTES do termo, e uma
# janela só para frente perdia 16 achados legítimos.
JANELA_VALOR = 120

# Evidência de que o exame foi REALIZADO, não apenas pedido.
#
# A primeira versão aceitava qualquer dígito na janela, e isso é fraco: nos
# laudos, o nome do exame aparece numa lista numerada de exames solicitados
# ("2. Avaliação de Visão Ocupacional ... 30 07 2026 6 ESPIROMETRIA 3 ECG"), e
# número de item e data satisfaziam a guarda. Ou seja, um documento que só
# *pediu* o exame passava como se o tivesse feito — o falso positivo caro.
#
# Unidade de medida ou vocabulário de laudo são sinais de resultado real.
_UNIDADE = re.compile(
    r"\b(MG DL|MG L|G DL|U L|UI L|UI ML|MMOL L|NG ML|UG L|MG 24H|MIL MM3|MM3|PG ML|MEQ L)\b"
)
_VOCABULARIO_LAUDO = re.compile(
    r"\b(RESULTADO|VALOR DE REFERENCIA|VALORES DE REFERENCIA|REFERENCIA|METODO|"
    r"MATERIAL|AMOSTRA|LAUDO|NEGATIVO|POSITIVO|NAO REAGENTE|REAGENTE)\b"
)

_cache_regex: dict[str, "re.Pattern"] = {}


def _regex(termo: str):
    import re

    padrao = _cache_regex.get(termo)
    if padrao is None:
        padrao = re.compile(rf"\b{re.escape(termo)}\b")
        _cache_regex[termo] = padrao
    return padrao


def varrer_markdown(
    markdown_norm: str,
    alvos_norm: list[str],
    exigir_valor: bool = True,
) -> dict[str, tuple[str, bool]]:
    """
    Procura no texto normalizado os termos do catálogo que são sinônimos dos
    exames pedidos pelo BRNET.

    `alvos_norm` são os nomes de exame do BRNET já normalizados.
    Retorna {alvo: (termo encontrado, havia dígito por perto)}.

    `exigir_valor` descarta o achado sem evidência de resultado no contexto —
    unidade de medida ou vocabulário de laudo em ±120 caracteres. Duas armadilhas
    reais do corpus justificam isso: "padronização da determinação laboratorial
    do perfil lipídico" (citação de diretriz, sem resultado) e a lista numerada
    de exames PEDIDOS no topo do prontuário, onde número de item e data faziam
    passar um exame que nunca foi realizado.

    Custo conhecido: exame não-laboratorial (avaliação oftalmológica, ECG, RX)
    não tem unidade nem vocabulário de laudo perto do nome, então deixa de ser
    recuperado. É o lado seguro para errar — deixar de liberar é reversível pelo
    revisor, liberar prontuário incompleto não.
    """
    import re

    if not markdown_norm or not alvos_norm:
        return {}

    achados: dict[str, tuple[str, bool]] = {}
    for alvo in alvos_norm:
        if not alvo:
            continue
        grupo = sinonimos_de(alvo)
        if not grupo:
            continue
        # Termo mais longo primeiro: o achado reportado é o mais específico.
        for termo in sorted(grupo, key=len, reverse=True):
            if len(termo) < MIN_TERMO_VARREDURA:
                continue
            casou = _regex(termo).search(markdown_norm)
            if not casou:
                continue
            contexto = markdown_norm[
                max(0, casou.start() - JANELA_VALOR) : casou.end() + JANELA_VALOR
            ]
            tem_evidencia = bool(
                _UNIDADE.search(contexto) or _VOCABULARIO_LAUDO.search(contexto)
            )
            if exigir_valor and not tem_evidencia:
                logger.info(
                    "[VARREDURA] '%s' encontrado para '%s' sem evidência de resultado "
                    "no contexto; ignorado (provável lista de exames pedidos)",
                    termo,
                    alvo,
                )
                continue
            achados[alvo] = (termo, tem_evidencia)
            break
    return achados
