"""
Rate limiting compartilhado entre instâncias.

Com `REDIS_URL` configurado, os contadores vivem no Redis (janela fixa via
INCR+EXPIRE atômicos), valendo para todas as instâncias/workers e
sobrevivendo a restarts. Sem Redis, cai para o contador em memória —
adequado apenas para instância única (deploy atual usa WORKERS=1).
"""
import logging
import os
import threading
import time

logger = logging.getLogger(__name__)


class MemoryRateLimiter:
    """Janela fixa em memória (por processo). Fallback para dev/instância única."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, tuple[float, int]] = {}

    def allow(self, key: str, limit: int, window: float) -> bool:
        if limit <= 0:
            return True
        now = time.monotonic()
        with self._lock:
            start, count = self._state.get(key, (now, 0))
            if now - start >= window:
                start, count = now, 0
            if count >= limit:
                return False
            self._state[key] = (start, count + 1)
        return True


class RedisRateLimiter:
    """Janela fixa no Redis, compartilhada entre instâncias.

    INCR + EXPIRE em pipeline: a primeira requisição da janela cria a chave
    com TTL; as demais só incrementam. Falha de conexão vira fail-open com
    log de erro (indisponibilidade do Redis não pode derrubar a API).
    """

    def __init__(self, redis_url: str) -> None:
        import redis  # import tardio: dependência só é exigida com REDIS_URL

        self._client = redis.Redis.from_url(
            redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        self._client.ping()

    def allow(self, key: str, limit: int, window: float) -> bool:
        if limit <= 0:
            return True
        try:
            redis_key = f"ratelimit:{key}"
            pipe = self._client.pipeline()
            pipe.incr(redis_key)
            pipe.expire(redis_key, int(window), nx=True)
            count, _ = pipe.execute()
            return int(count) <= limit
        except Exception:
            logger.error("Rate limit Redis indisponível; liberando requisição (fail-open).", exc_info=True)
            return True


def create_rate_limiter():
    """Cria o rate limiter conforme o ambiente (Redis se REDIS_URL existir)."""
    redis_url = os.getenv("REDIS_URL", "").strip()
    if redis_url:
        try:
            limiter = RedisRateLimiter(redis_url)
            logger.info("Rate limit usando Redis compartilhado.")
            return limiter
        except Exception as exc:
            logger.error(
                "Falha ao conectar no Redis (%s); rate limit caindo para memória local. "
                "Em múltiplas instâncias os limites NÃO serão compartilhados.",
                exc,
            )
    else:
        logger.warning(
            "REDIS_URL não configurado; rate limit em memória local. "
            "Adequado apenas para instância única."
        )
    return MemoryRateLimiter()
