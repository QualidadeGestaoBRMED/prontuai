"""
Compacta result_payload e preenche result_payload_compact para acelerar listagens.

Uso:
    python compact_documents_payloads.py
"""
import os
import sys
import json
import logging
from dotenv import load_dotenv

load_dotenv()

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

from app.core.database_postgres import PostgresUserDatabase, DocumentModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> int:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL não configurado no .env")
        return 1

    user_db = PostgresUserDatabase(database_url)
    session = user_db._get_session()
    updated = 0
    skipped = 0
    errors = 0

    try:
        docs = session.query(
            DocumentModel.id,
            DocumentModel.result_payload,
            DocumentModel.result_payload_compact,
        ).all()

        for doc_id, payload_raw, compact_raw in docs:
            if not payload_raw:
                skipped += 1
                continue
            try:
                payload = json.loads(payload_raw)
            except Exception:
                errors += 1
                continue

            compact_payload = user_db._compact_payload_for_storage(payload)
            compact_json = json.dumps(compact_payload, ensure_ascii=False) if compact_payload is not None else None

            if compact_json == compact_raw:
                skipped += 1
                continue

            session.query(DocumentModel).filter(DocumentModel.id == doc_id).update(
                {DocumentModel.result_payload_compact: compact_json}
            )
            updated += 1

        session.commit()
        logger.info("Compactação concluída. Atualizados=%d, Ignorados=%d, Erros=%d", updated, skipped, errors)
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
