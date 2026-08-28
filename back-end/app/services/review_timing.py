"""Sanitização da cronometragem da tela de revisão.

O tempo de revisão é medido no cliente — `performance.now()`, monotônico, imune
a skew e a ajuste de hora — e viaja junto do PATCH da decisão. Como o valor vem
de fora, nada aqui confia nele.

Duas regras de ouro, ambas por causa do lugar onde isso roda (o caminho que o
revisor usa para aprovar documento):

1. Nada levanta exceção. Cronometragem suspeita é descartada com log; medição
   não pode impedir ninguém de decidir um documento.
2. Todo limite mora aqui, não no schema Pydantic. Constraint em `DocumentUpdate`
   viraria 422 e bloquearia a decisão inteira por causa de um número torto.

Desenho completo em docs/tempo-de-revisao-desenho.md.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.models.document import ReviewTiming

logger = logging.getLogger(__name__)

# Teto de parede por documento. Acima disso não é revisão longa, é aba
# esquecida aberta a noite inteira.
MAX_WALL_MS = 4 * 60 * 60 * 1000

# O ativo nunca deveria passar do bruto. Até 2s é arredondamento entre os dois
# relógios do cliente; acima disso é bug ou adulteração.
TOLERANCIA_ATIVO_MS = 2000

# started_at é relógio de parede do cliente, então aceita skew — mas não
# aceita viagem no tempo.
MAX_SKEW_FUTURO = timedelta(hours=24)
MAX_IDADE = timedelta(days=90)

# review_open_count é SMALLINT no banco.
MAX_OPEN_COUNT = 255


def _para_utc_naive(valor: datetime) -> datetime:
    """Normaliza para UTC sem tzinfo, que é o formato das colunas TIMESTAMP."""
    if valor.tzinfo is None:
        return valor
    return valor.astimezone(timezone.utc).replace(tzinfo=None)


def sanitizar_review_timing(
    timing: Optional[ReviewTiming],
    document_id: str,
    agora: Optional[datetime] = None,
) -> Optional[dict[str, Any]]:
    """Valida a cronometragem recebida do cliente.

    Devolve os incrementos a somar nas colunas de `documents`, ou None quando
    não há cronometragem confiável. `agora` é injetável para teste.
    """
    if timing is None:
        return None

    active_ms = timing.active_ms
    wall_ms = timing.wall_ms
    open_count = timing.open_count

    if active_ms is None or wall_ms is None:
        return None

    if active_ms < 0 or wall_ms < 0:
        logger.warning("Cronometragem negativa descartada doc_id=%s", document_id)
        return None

    if wall_ms > MAX_WALL_MS:
        logger.warning(
            "Cronometragem acima do teto descartada doc_id=%s wall_ms=%s", document_id, wall_ms
        )
        return None

    if active_ms > wall_ms + TOLERANCIA_ATIVO_MS:
        logger.warning(
            "Cronometragem inconsistente descartada doc_id=%s active_ms=%s wall_ms=%s",
            document_id,
            active_ms,
            wall_ms,
        )
        return None

    # started_at fora de faixa derruba só ele: as durações são monotônicas e não
    # dependem do relógio de parede, então continuam válidas.
    started_at = None
    if timing.started_at is not None:
        agora = agora or datetime.utcnow()
        candidato = _para_utc_naive(timing.started_at)
        if candidato > agora + MAX_SKEW_FUTURO or candidato < agora - MAX_IDADE:
            logger.warning(
                "Início de revisão fora de faixa ignorado doc_id=%s started_at=%s",
                document_id,
                candidato.isoformat(),
            )
        else:
            started_at = candidato

    return {
        "started_at": started_at,
        # min() absorve a tolerância de arredondamento sem perder o registro.
        "active_ms": min(active_ms, wall_ms),
        "wall_ms": wall_ms,
        "open_count": max(1, min(open_count or 1, MAX_OPEN_COUNT)),
    }
