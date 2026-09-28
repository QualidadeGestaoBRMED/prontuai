"""Regressão do "Event loop is closed" na comparação de exames.

Rodar sem o conftest, que importa main.py e exige DATABASE_URL:

    PYTHONPATH=back-end pytest back-end/tests/test_openai_client_por_loop.py -q --noconftest

O bug: `app/core/clients.py` tinha um `AsyncOpenAI` global criado no import, e
`v1_brmed._run_background_job_in_thread` roda cada job em `asyncio.run()` numa
thread nova — que fecha o loop ao terminar. O pool httpx do cliente ficava preso
ao loop morto e o job seguinte quebrava com `RuntimeError: Event loop is closed`,
ALTERNANDO: 10 de 20 documentos em staging (24/set/2026).

Estes testes não tocam a rede. Verificam a propriedade que faz o bug ser
impossível: cliente distinto por loop, e um só dentro do mesmo loop.
"""
import asyncio
import threading

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


def test_entrada_morre_com_o_loop():
    """O cache não pode segurar loop vivo nem crescer a cada job."""
    antes = len(clients._clientes_por_loop)
    for _ in range(5):
        asyncio.run(_pegar())

    assert len(clients._clientes_por_loop) <= antes + 1


async def _pegar():
    return clients.get_client()
