"""
Testes do rate limiter e da resolução de IP do cliente com proxies confiáveis.
"""
import types

from app.core.rate_limit import MemoryRateLimiter


def _fake_request(peer_ip=None, headers=None):
    return types.SimpleNamespace(
        headers=headers or {},
        client=types.SimpleNamespace(host=peer_ip) if peer_ip else None,
    )


def test_memory_limiter_blocks_after_limit():
    limiter = MemoryRateLimiter()
    assert limiter.allow("k", limit=3, window=60.0) is True
    assert limiter.allow("k", limit=3, window=60.0) is True
    assert limiter.allow("k", limit=3, window=60.0) is True
    assert limiter.allow("k", limit=3, window=60.0) is False


def test_memory_limiter_isolates_keys():
    limiter = MemoryRateLimiter()
    assert limiter.allow("a", limit=1, window=60.0) is True
    assert limiter.allow("a", limit=1, window=60.0) is False
    assert limiter.allow("b", limit=1, window=60.0) is True


def test_memory_limiter_zero_limit_allows():
    limiter = MemoryRateLimiter()
    assert limiter.allow("k", limit=0, window=60.0) is True


def test_client_ip_ignores_headers_from_untrusted_peer(monkeypatch):
    import main

    monkeypatch.setenv("TRUSTED_PROXY_IPS", "127.0.0.1,::1")
    monkeypatch.setattr(main, "_TRUSTED_PROXY_NETWORKS", main._parse_trusted_proxies())

    # Conexão direta de IP público com header forjado: header deve ser ignorado.
    request = _fake_request(
        peer_ip="203.0.113.50",
        headers={"cf-connecting-ip": "10.0.0.99"},
    )
    assert main._get_client_ip(request) == "203.0.113.50"


def test_client_ip_uses_cf_header_from_trusted_peer(monkeypatch):
    import main

    monkeypatch.setenv("TRUSTED_PROXY_IPS", "127.0.0.1,::1,172.16.0.0/12")
    monkeypatch.setattr(main, "_TRUSTED_PROXY_NETWORKS", main._parse_trusted_proxies())

    # Proxy confiável na rede interna do Docker repassa o IP real do visitante.
    request = _fake_request(
        peer_ip="172.18.0.5",
        headers={"cf-connecting-ip": "198.51.100.7"},
    )
    assert main._get_client_ip(request) == "198.51.100.7"


def test_client_ip_xff_from_trusted_peer_skips_trusted_hops(monkeypatch):
    import main

    monkeypatch.setenv("TRUSTED_PROXY_IPS", "127.0.0.1,::1,172.16.0.0/12")
    monkeypatch.setattr(main, "_TRUSTED_PROXY_NETWORKS", main._parse_trusted_proxies())

    request = _fake_request(
        peer_ip="172.18.0.5",
        headers={"x-forwarded-for": "198.51.100.7, 172.18.0.9"},
    )
    assert main._get_client_ip(request) == "198.51.100.7"


def test_client_ip_falls_back_to_peer_without_headers(monkeypatch):
    import main

    monkeypatch.setenv("TRUSTED_PROXY_IPS", "127.0.0.1,::1")
    monkeypatch.setattr(main, "_TRUSTED_PROXY_NETWORKS", main._parse_trusted_proxies())

    request = _fake_request(peer_ip="127.0.0.1")
    assert main._get_client_ip(request) == "127.0.0.1"


def test_parse_trusted_proxies_accepts_cidr_and_ignores_invalid(monkeypatch):
    import main

    monkeypatch.setenv("TRUSTED_PROXY_IPS", "127.0.0.1, 172.16.0.0/12, nao-e-ip")
    networks = main._parse_trusted_proxies()
    assert len(networks) == 2
