"""
Vocabulário de nomes de pessoa, para o aviso de nome diferente no laudo.

O aviso só pelo nome (`identidade_laudo.pessoas_no_documento`) exige que o nome
achado seja feito de nomes de verdade: o OCR de nome escrito à mão inventa
palavras ("Quelgo Varnip", "Brx Tulfe"), e um nome de outra pessoa digitado
num laudo usa nomes que já apareceram em outros pacientes.

O vocabulário sai dos nomes de paciente já gravados em `documents`: cada palavra
do nome (como `identidade_laudo._tokens` a lê) que aparece em pelo menos
`MINIMO_PACIENTES` pacientes distintos (por CPF). Contar por paciente, e não por
documento, deixa de fora o sobrenome raro de um paciente só, mesmo que ele tenha
vários envios: entram nomes comuns, não o nome de alguém.

Fica só em memória; nada vai para log nem para disco. A consulta nunca roda no
caminho da validação, a não ser na primeira vez:

- o startup dispara a carga em segundo plano (`aquecer`);
- vencido o prazo (`VALIDADE_SEGUNDOS`), quem pede recebe o vocabulário que já
  existe e a recarga corre em segundo plano, uma de cada vez;
- recarga que falha mantém o último vocabulário bom e tenta de novo em
  `NOVA_TENTATIVA_SEGUNDOS`, em vez de zerar o aviso por um dia;
- só a primeira chamada, se o startup ainda não terminou, espera a carga, por
  até `ESPERA_PRIMEIRA_CARGA` segundos.

Sem vocabulário (banco fora desde o startup), o aviso só pelo nome não sai —
preferir não avisar a avisar ruído. Com mais de um worker, cada processo carrega
a sua cópia (são ~1.300 palavras).
"""
from __future__ import annotations

import logging
import threading
import time
from collections import Counter
from typing import Optional

logger = logging.getLogger(__name__)

MINIMO_PACIENTES = 3
VALIDADE_SEGUNDOS = 24 * 3600
NOVA_TENTATIVA_SEGUNDOS = 600
ESPERA_PRIMEIRA_CARGA = 5.0

_lock = threading.Lock()
_vocabulario: Optional[frozenset[str]] = None
_proxima_carga = 0.0
_carga_em_andamento: Optional[threading.Event] = None


def _consultar() -> frozenset[str]:
    """Lê os nomes do banco. Levanta exceção se a consulta falhar."""
    from sqlalchemy import text  # import tardio de propósito, como em exam_catalog_source

    from app.core.database import user_db
    from app.services.identidade_laudo import _tokens

    contagem: Counter[str] = Counter()
    with user_db.engine.connect() as conexao:
        for (nome,) in conexao.execute(
            text(
                "SELECT MIN(patient_name) FROM documents "
                "WHERE patient_name IS NOT NULL AND cpf IS NOT NULL GROUP BY cpf"
            )
        ):
            contagem.update(set(_tokens(nome)))
    return frozenset(t for t, n in contagem.items() if n >= MINIMO_PACIENTES)


def _carregar() -> None:
    global _vocabulario, _proxima_carga, _carga_em_andamento
    try:
        novo = _consultar()
        with _lock:
            _vocabulario = novo
            _proxima_carga = time.monotonic() + VALIDADE_SEGUNDOS
        logger.info(f"[NOMES] Vocabulário de nomes carregado: {len(novo)} palavras")
    except Exception as e:
        with _lock:
            _proxima_carga = time.monotonic() + NOVA_TENTATIVA_SEGUNDOS
            mantido = len(_vocabulario) if _vocabulario is not None else 0
        logger.warning(
            f"[NOMES] Vocabulário de nomes indisponível ({type(e).__name__}); "
            f"mantendo {mantido} palavras, nova tentativa em {NOVA_TENTATIVA_SEGUNDOS}s"
        )
    finally:
        with _lock:
            evento, _carga_em_andamento = _carga_em_andamento, None
        if evento is not None:
            evento.set()


def _disparar_carga() -> threading.Event:
    """Começa uma carga em segundo plano, ou devolve a que já está correndo."""
    global _carga_em_andamento
    with _lock:
        if _carga_em_andamento is None:
            _carga_em_andamento = threading.Event()
            threading.Thread(target=_carregar, daemon=True, name="nomes-conhecidos").start()
        return _carga_em_andamento


def aquecer() -> None:
    """Chamado no startup: carrega sem bloquear."""
    _disparar_carga()


def vocabulario() -> frozenset[str]:
    """As palavras de nome conhecidas. Vazio enquanto nenhuma carga deu certo."""
    evento = _disparar_carga() if time.monotonic() >= _proxima_carga else None
    if _vocabulario is None and evento is not None:
        evento.wait(ESPERA_PRIMEIRA_CARGA)
    return _vocabulario or frozenset()
