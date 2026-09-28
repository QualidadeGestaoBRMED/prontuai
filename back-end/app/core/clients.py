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

`WeakKeyDictionary`: a entrada morre junto com o loop, sem manter loop vivo nem
acumular cliente por job. Mesmo padrão que `exam_vector_service` já fazia por
conta própria, criando o cliente dentro da função.
"""
import asyncio
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
