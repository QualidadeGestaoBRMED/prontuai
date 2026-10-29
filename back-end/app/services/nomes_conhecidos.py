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

Fica só em memória; nada vai para log nem para disco. Banco fora ou consulta com
erro devolve vocabulário vazio, e com ele o aviso só pelo nome não sai — preferir
não avisar a avisar ruído. O cache vale `VALIDADE_SEGUNDOS`; com `WORKERS=1` há
um processo só.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import Counter

logger = logging.getLogger(__name__)

MINIMO_PACIENTES = 3
VALIDADE_SEGUNDOS = 24 * 3600

_lock = threading.Lock()
_vocabulario: frozenset[str] | None = None
_carregado_em = 0.0


def _carregar() -> frozenset[str]:
    try:
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
        vocabulario = frozenset(t for t, n in contagem.items() if n >= MINIMO_PACIENTES)
        logger.info(f"[NOMES] Vocabulário de nomes carregado: {len(vocabulario)} palavras")
        return vocabulario
    except Exception as e:
        logger.warning(f"[NOMES] Vocabulário de nomes indisponível: {type(e).__name__}")
        return frozenset()


def vocabulario() -> frozenset[str]:
    """As palavras de nome conhecidas. Vazio quando o banco não respondeu."""
    global _vocabulario, _carregado_em
    if _vocabulario is None or time.monotonic() - _carregado_em > VALIDADE_SEGUNDOS:
        with _lock:
            if _vocabulario is None or time.monotonic() - _carregado_em > VALIDADE_SEGUNDOS:
                _vocabulario = _carregar()
                _carregado_em = time.monotonic()
    return _vocabulario
