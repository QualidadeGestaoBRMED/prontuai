"""Regressão do "Event loop is closed" na comparação de exames.

Rodar sem o conftest, que importa main.py e exige DATABASE_URL:

    PYTHONPATH=back-end pytest back-end/tests/test_openai_client_por_loop.py -q --noconftest

O bug: `app/core/clients.py` tinha um `AsyncOpenAI` global criado no import, e
`v1_brmed._run_background_job_in_thread` roda cada job em `asyncio.run()` numa
thread nova — que fecha o loop ao terminar. O pool httpx do cliente ficava preso
ao loop morto e o job seguinte quebrava com `RuntimeError: Event loop is closed`,
ALTERNANDO: 10 de 20 documentos em staging (24/set/2026).

Os primeiros testes não tocam a rede. Verificam a propriedade que faz o bug ser
impossível: cliente distinto por loop, e um só dentro do mesmo loop. Os de
vazamento falam com um servidor HTTP local, porque só uma conexão aberta prende
o loop ao cliente.
"""
import asyncio
import gc
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.core import clients


def test_loops_diferentes_recebem_clientes_diferentes():
    """O caso que quebrava: dois `asyncio.run` seguidos, como dois jobs."""
    primeiro = asyncio.run(_pegar())
    segundo = asyncio.run(_pegar())

    assert primeiro is not segundo


def test_mesmo_loop_reaproveita_o_cliente():
    """Não é criar um cliente por chamada: dentro do loop, o pool é reusado."""

    async def duas_chamadas():
        return clients.get_client(), clients.get_client()

    a, b = asyncio.run(duas_chamadas())

    assert a is b


def test_threads_com_loop_proprio_nao_compartilham_cliente():
    """Desenho real do worker: uma thread por job, cada uma com seu asyncio.run."""
    colhidos: dict[int, object] = {}

    def job(n: int) -> None:
        colhidos[n] = asyncio.run(_pegar())

    for i in range(3):
        t = threading.Thread(target=job, args=(i,))
        t.start()
        t.join()

    assert len({id(c) for c in colhidos.values()}) == 3


def test_fora_de_loop_nao_estoura():
    """Chamada síncrona (script, shell) não pode levantar RuntimeError."""
    assert clients.get_client() is not None


def test_cliente_com_conexao_nao_fica_preso_ao_loop(servidor_openai):
    """O vazamento de 17/nov/2026: 2,3 GB e 1.119 sockets após ~1.200 documentos.

    Sem chamada de rede o cliente não segura o loop e a entrada fraca morre, por
    isso este teste PRECISA fazer a chamada de verdade, contra um servidor local.
    Com a conexão aberta, cliente → pool → transport → loop mantém a chave do
    `WeakKeyDictionary` viva, e só o fechamento explícito solta o loop.
    """
    gc.collect()
    antes = len(clients._clientes_por_loop)

    for _ in range(5):
        t = threading.Thread(target=clients.rodar_em_loop_novo, args=(_embedding(),))
        t.start()
        t.join()
    gc.collect()

    assert len(clients._clientes_por_loop) == antes
    assert servidor_openai.chamadas == 5


def test_asyncio_run_puro_vazaria(servidor_openai):
    """Prova de que o teste acima mede o defeito, e não passa por acaso."""
    gc.collect()
    antes = len(clients._clientes_por_loop)

    asyncio.run(_embedding())
    gc.collect()

    assert len(clients._clientes_por_loop) == antes + 1
    clients._clientes_por_loop.clear()


def test_cliente_fechado_mesmo_quando_o_job_falha(servidor_openai):
    """O job que estoura no meio também devolve a conexão."""

    async def job_que_falha():
        await _embedding()
        raise ValueError("falha do job")

    gc.collect()
    antes = len(clients._clientes_por_loop)

    with pytest.raises(ValueError):
        clients.rodar_em_loop_novo(job_que_falha())
    gc.collect()

    assert len(clients._clientes_por_loop) == antes


async def _pegar():
    return clients.get_client()


async def _embedding():
    await clients.get_client().embeddings.create(input=["x"], model="teste")


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # keep-alive: é a conexão no pool que segura o loop

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        self.server.chamadas += 1
        corpo = json.dumps({
            "object": "list",
            "model": "teste",
            "usage": {"prompt_tokens": 1, "total_tokens": 1},
            "data": [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2]}],
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *args):
        pass


@pytest.fixture
def servidor_openai(monkeypatch):
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    servidor.chamadas = 0
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{servidor.server_port}/v1")
    monkeypatch.setattr(clients.settings, "OPENAI_API_KEY", "sk-teste")
    yield servidor
    servidor.shutdown()
