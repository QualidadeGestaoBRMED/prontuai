#!/usr/bin/env python3
import os
import sys
import argparse
from typing import Any

from app.core.config import settings
from app.core.database import user_db
from app.services import drive_service


def _get_reviewed_by(result_payload: Any) -> str | None:
    if isinstance(result_payload, dict):
        value = result_payload.get("reviewed_by")
        return value if isinstance(value, str) and value.strip() else None
    return None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Force upload of a document to Google Drive.")
    parser.add_argument("document_id", help="Documento ID")
    parser.add_argument(
        "--file-path",
        dest="file_path",
        help="Caminho local do arquivo para upload (override do file_path do documento)",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    document_id = args.document_id.strip()
    if not document_id:
        print("ERROR: document_id is empty")
        return 2

    doc = user_db.get_document_by_id(document_id)
    if not doc:
        print(f"ERROR: document not found: {document_id}")
        return 1

    file_path = args.file_path or getattr(doc, "file_path", None)
    if args.file_path:
        doc.file_path = args.file_path
    file_exists = os.path.exists(file_path) if file_path else False
    reviewed_by = _get_reviewed_by(getattr(doc, "result_payload", None))

    print("Document info:")
    print(f"  id: {doc.id}")
    print(f"  filename: {doc.filename}")
    print(f"  file_path: {file_path}")
    print(f"  file_exists: {file_exists}")
    print(f"  validation_status: {doc.validation_status}")
    print(f"  reviewed_by: {reviewed_by}")
    print(f"  uploaded_at: {doc.uploaded_at}")

    print("Drive settings:")
    print(f"  GOOGLE_DRIVE_ENABLED: {settings.GOOGLE_DRIVE_ENABLED}")
    print(f"  GOOGLE_DRIVE_FOLDER_ID set: {bool(settings.GOOGLE_DRIVE_FOLDER_ID)}")
    print(f"  GOOGLE_DRIVE_SUPPORTS_ALL_DRIVES: {settings.GOOGLE_DRIVE_SUPPORTS_ALL_DRIVES}")

    print("Starting upload...")
    drive_service.upload_document_to_drive(doc)
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
