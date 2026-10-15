"""
Cache das pendências do catálogo de exames.

**Por que existe.** `listar_pendencias_catalogo` é a consulta mais cara da API:
ela varre `documents` inteiro e, para cada linha, faz o Postgres parsear o
`result_payload` (TEXT) como JSONB para abrir a `tabela_comparacao`. Medido no
dev com 11.188 documentos: 1,65s só nessa parte.

E ela rodava **duas vezes** em cada carga do painel de curadoria, porque
`get_exam_catalog_stats` chamava a mesma função para preencher
`pendencies_total` e `brnet_never_found` — o cabeçalho e a aba de pendências
pagavam o scan separadamente, dando ~3,5s de espera.

**Por que TTL, e não só invalidação por escrita.** A lista depende de duas
fontes: o catálogo (que a curadoria edita, e aí a invalidação explícita resolve)
e os documentos processados (que chegam o tempo todo, sem passar por aqui). Sem
TTL, um exame recém-visto num prontuário continuaria aparecendo como "nunca
encontrado" até alguém mexer no catálogo.

Cinco minutos é folgado para um painel de curadoria — ninguém cadastra exame
olhando o relógio — e derruba o custo da navegação entre abas a zero.

Cache por processo, como o do dashboard: com `WORKERS=1` (ver CLAUDE.md) é o
processo todo; com mais de um, cada um aquece o seu, o que é correto porque o
dado é idêntico em todos.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import List, Optional

from app.models.exam import ExamPendency

logger = logging.getLogger(__name__)

TTL_SEGUNDOS = 300

# O cache guarda a lista COMPLETA (limite alto) e serve qualquer `limit` por
# fatiamento: a ordenação é fixa, então o topo de uma lista menor é o mesmo.
# Guardar por `limit` daria uma entrada por chamador e recalcularia à toa.
_LIMITE_INTERNO = 10000

_lock = threading.Lock()
_cache: Optional[tuple[float, List[ExamPendency]]] = None


def obter(carregar, limit: int = 200) -> List[ExamPendency]:
    """
    Pendências do catálogo, do cache enquanto ele valer.

    `carregar` é a função que faz o scan de verdade — recebida por parâmetro
    para este módulo não importar o banco (e para o teste não precisar de um).
    É chamada com `limit=_LIMITE_INTERNO`.

    O lock serializa o recálculo: sem ele, duas abas abertas ao mesmo tempo com
    o cache vencido disparariam dois scans de 1,65s em paralelo.
    """
    global _cache

    agora = time.monotonic()
    if _cache and agora < _cache[0]:
        return _cache[1][:limit]

    with _lock:
        # Outra thread pode ter preenchido enquanto esperávamos o lock.
        agora = time.monotonic()
        if _cache and agora < _cache[0]:
            return _cache[1][:limit]

        inicio = time.perf_counter()
        pendencias = carregar(limit=_LIMITE_INTERNO)
        decorrido = time.perf_counter() - inicio
        _cache = (time.monotonic() + TTL_SEGUNDOS, pendencias)
        logger.info(
            "[EXAMS] Pendências recalculadas em %.2fs (%d itens, TTL %ds)",
            decorrido,
            len(pendencias),
            TTL_SEGUNDOS,
        )
        return pendencias[:limit]


def invalidar() -> None:
    """Descarta o cache. Chamado por toda escrita no catálogo."""
    global _cache
    with _lock:
        _cache = None
