"""Conduta sugerida calculada na aprovação da Checagem, numa fila com N documentos em paralelo.

Montar as features leva ~0,1 s; o que demora na primeira abertura da Conduta Médica é o POST /prever do ml-exams
(até ML_TIMEOUT). Aprovado o documento, ele entra nesta fila: as features e a resposta do modelo ficam guardadas em
`conduta_sugestoes`, e a abertura só remonta as features, acha a resposta pelo hash e responde sem chamar o modelo.

- `CONDUTA_FILA_PARALELO` (padrão 3): quantos documentos chamam o ml-exams ao mesmo tempo. A revisão aprova vários
  seguidos e o serviço de ML é uma máquina só; mais que isso só empilha requisição lá.
- `CONDUTA_NA_APROVACAO=false` desliga a fila e volta ao cálculo só na abertura.
- A fila é em memória, como o JobManager: um restart perde o que estava esperando. Sem prejuízo: esses documentos
  calculam na primeira abertura, como antes.
- Abrir um documento que ainda está na fila espera a vez dele (até CONDUTA_ESPERA_ABERTURA s) em vez de chamar o
  modelo uma segunda vez.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

from app.core.database import user_db
from app.services.conduta import conduta_sugerida as cs

logger = logging.getLogger(__name__)

CONDUTA_NA_APROVACAO = os.getenv("CONDUTA_NA_APROVACAO", "true").lower() == "true"
CONDUTA_FILA_PARALELO = max(1, int(os.getenv("CONDUTA_FILA_PARALELO", "3")))
CONDUTA_ESPERA_ABERTURA = float(os.getenv("CONDUTA_ESPERA_ABERTURA", "60"))


class Guardada:
    """As chamadas ao ml-exams do documento na tabela conduta_sugestoes."""

    def __init__(self, document_id: str):
        self.document_id = document_id

    def ler(self, features_hash):
        return user_db.ultima_conduta_sugestao(self.document_id, features_hash)

    def gravar(self, features_hash, features, versao_modelo, resposta, status_http, erro, duracao_ms, request_id):
        return user_db.registrar_conduta_sugestao(self.document_id, features_hash, cs.VERSAO_FEATURES, versao_modelo,
                                                  features, resposta, status_http, erro, duracao_ms, request_id)


def sugerir_para_documento(document) -> dict[str, Any]:
    """`cs.sugerir` com o que o documento tem; síncrono (leitura + HTTP). Mesmo caminho na fila e na abertura, para
    as duas montarem as mesmas features e a abertura achar a resposta guardada pelo hash."""
    payload = document.result_payload if isinstance(document.result_payload, dict) else {}
    ausentes = [t.get("exame") for t in payload.get("tabela_comparacao") or [] if isinstance(t, dict)
                and t.get("status") == "faltante" and t.get("exame")]
    data = document.uploaded_at.date().isoformat() if getattr(document, "uploaded_at", None) else None
    # Nome e CPF já extraídos localmente reforçam a redação antes de a ficha ir ao 4o mini (pii_redaction).
    conhecidos = tuple(v for v in (getattr(document, "cpf", None), payload.get("patient_name"),
                                   getattr(document, "patient_name", None)) if v)
    return cs.sugerir(document.ocr_markdown or "", data, ausentes, document.exams_ocr or [],
                      document.exams_brnet or [], Guardada(document.id), conhecidos)


class FilaConduta:
    def __init__(self, paralelo: int = CONDUTA_FILA_PARALELO):
        self.paralelo = paralelo
        self._fila: Optional[asyncio.Queue] = None
        self._pendentes: dict[str, asyncio.Event] = {}
        self._tarefas: list[asyncio.Task] = []

    def iniciar(self) -> None:
        """Chamado no startup: a fila e os eventos nascem no loop da aplicação (primitivas do asyncio ficam presas
        ao loop em que foram criadas; ver o lock do JobManager)."""
        if self._fila is not None:
            return
        self._fila = asyncio.Queue()
        self._tarefas = [asyncio.create_task(self._trabalhar(i)) for i in range(self.paralelo)]
        logger.info(f"[CONDUTA] Fila da aprovação iniciada: {self.paralelo} documento(s) em paralelo")

    async def parar(self) -> None:
        for t in self._tarefas:
            t.cancel()
        await asyncio.gather(*self._tarefas, return_exceptions=True)
        self._tarefas, self._fila = [], None
        self._pendentes.clear()

    def enfileirar(self, document_id: str) -> bool:
        """True se entrou; False se a fila está desligada ou o documento já está nela."""
        if self._fila is None or document_id in self._pendentes:
            return False
        self._pendentes[document_id] = asyncio.Event()
        self._fila.put_nowait(document_id)
        logger.info(f"[CONDUTA] Documento {document_id} na fila da conduta ({self._fila.qsize()} esperando)")
        return True

    async def aguardar(self, document_id: str, timeout: float = CONDUTA_ESPERA_ABERTURA) -> None:
        """Se o documento está na fila, espera ele sair dela. Passado o tempo, segue: a abertura calcula sozinha."""
        evento = self._pendentes.get(document_id)
        if evento is None:
            return
        try:
            await asyncio.wait_for(evento.wait(), timeout)
        except asyncio.TimeoutError:
            logger.warning(f"[CONDUTA] Abertura de {document_id} não esperou a fila além de {timeout:.0f} s")

    async def _trabalhar(self, n: int) -> None:
        assert self._fila is not None
        while True:
            document_id = await self._fila.get()
            try:
                document = await asyncio.to_thread(user_db.get_document_by_id, document_id)
                if document is None:
                    continue
                out = await asyncio.to_thread(sugerir_para_documento, document)
                situacao = (out.get("conduta_sugerida") or {}).get("situacao_aso")
                logger.info(f"[CONDUTA] Fila {n}: documento {document_id} → "
                            f"{situacao or out.get('motivo_sem_sugestao')} (sugestao_id={out.get('sugestao_id')})")
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — um documento ruim não para a fila
                logger.warning(f"[CONDUTA] Fila {n}: falha no documento {document_id}: {type(exc).__name__}")
            finally:
                evento = self._pendentes.pop(document_id, None)
                if evento is not None:
                    evento.set()
                self._fila.task_done()


fila = FilaConduta()
