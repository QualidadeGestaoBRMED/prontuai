"""
Cliente OpenAI assíncrono, um por event loop.

Era um único `AsyncOpenAI` global, criado no import. Isso quebrava metade dos
documentos: `v1_brmed._run_background_job_in_thread` roda cada job em
`asyncio.run()` numa thread nova, e `asyncio.run` **fecha** o loop ao terminar.
O pool de conexões httpx do cliente fica amarrado ao loop que o criou, então o
job seguinte reaproveitava uma conexão TLS de um loop morto:

    APIConnectionError: Connection error.
      ← RuntimeError: Event loop is closed
        ← SSLWantReadError: the operation did not complete (read)

O erro ALTERNAVA — job com conexão reaproveitável quebrava, o seguinte abria uma
nova e passava. Medido em staging (24/set/2026): 10 de 20 documentos. Cada falha
vira `{"erro": ...}` no fallback da comparação, e `validar_exames` devolve
`status_liberado: False` com comparativo vazio: o documento cai na checagem
humana com confiança baixa como se a IA tivesse achado problema, quando ela nem
chegou a comparar. Infla a fila e contamina a medição de acurácia.

O OCR nunca sofreu disso porque usa o `OpenAI` **síncrono**, que não depende de
event loop.

O cliente precisa ser FECHADO no fim do loop, e o `WeakKeyDictionary` não basta.
A ideia era a entrada morrer junto com o loop, mas o valor segura a chave:
cliente → pool httpx → conexão → transport → `_loop`. Depois da primeira chamada
de rede o loop nunca vira lixo, e loop, cliente, contexto SSL e socket ficam
vivos para sempre. Em produção (17/nov/2026) foram 2,3 GB de RSS e 1.119 sockets
em CLOSE-WAIT para a api.openai.com após ~1.200 documentos, cerca de 1,2 MB por
documento, até o container ser reiniciado. Por isso o job roda por
`rodar_em_loop_novo`, que fecha o cliente antes de o loop terminar.
"""
import asyncio
from typing import Any, Coroutine, TypeVar
from weakref import WeakKeyDictionary

from openai import AsyncOpenAI

from app.core.config import settings

_clientes_por_loop: "WeakKeyDictionary[asyncio.AbstractEventLoop, AsyncOpenAI]" = (
    WeakKeyDictionary()
)


def get_client() -> AsyncOpenAI:
    """Cliente do loop corrente, criado na primeira chamada dentro dele.

    Chame a cada uso — nunca guarde o retorno em variável de módulo, que é
    exatamente o que causava o bug.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Fora de um loop não há pool a reaproveitar nem loop a fechar depois:
        # devolve um cliente avulso em vez de estourar.
        return AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    cliente = _clientes_por_loop.get(loop)
    if cliente is None:
        cliente = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        _clientes_por_loop[loop] = cliente
    return cliente


async def fechar_cliente_do_loop() -> None:
    """Fecha e esquece o cliente do loop corrente, se houver.

    Tem de rodar DENTRO do loop, antes de ele terminar: `close()` é assíncrono e
    devolve as conexões do pool. Depois que o loop fecha já não há como.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    cliente = _clientes_por_loop.pop(loop, None)
    if cliente is not None:
        await cliente.close()


T = TypeVar("T")


def rodar_em_loop_novo(corrotina: Coroutine[Any, Any, T]) -> T:
    """`asyncio.run` que fecha o cliente OpenAI do loop no fim, com ou sem erro.

    Use no lugar de `asyncio.run` em todo código que roda trabalho com IA num
    loop próprio, como o worker de `v1_brmed._run_background_job_in_thread`.
    """

    async def _com_fechamento() -> T:
        try:
            return await corrotina
        finally:
            await fechar_cliente_do_loop()

    return asyncio.run(_com_fechamento())
