import base64
import json
import logging
import mimetypes
import os
from datetime import datetime, timezone

from app.core.config import settings

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/drive.file"]
_SERVICE = None


def _load_credentials():
    from google.oauth2 import service_account
    raw_json = settings.GOOGLE_DRIVE_CREDENTIALS_JSON
    if raw_json:
        raw_json = raw_json.strip()
        try:
            if raw_json.startswith("{"):
                info = json.loads(raw_json)
            else:
                decoded = base64.b64decode(raw_json)
                info = json.loads(decoded)
        except Exception as exc:
            raise RuntimeError("Credenciais Google Drive inválidas em GOOGLE_DRIVE_CREDENTIALS_JSON") from exc
        return service_account.Credentials.from_service_account_info(info, scopes=_SCOPES)

    creds_path = settings.GOOGLE_DRIVE_CREDENTIALS_FILE
    if creds_path:
        if not os.path.exists(creds_path):
            raise FileNotFoundError(f"Arquivo de credenciais não encontrado: {creds_path}")
        return service_account.Credentials.from_service_account_file(creds_path, scopes=_SCOPES)

    raise RuntimeError("GOOGLE_DRIVE_CREDENTIALS_FILE ou GOOGLE_DRIVE_CREDENTIALS_JSON não configurado")


def _get_drive_service():
    from googleapiclient.discovery import build
    global _SERVICE
    if _SERVICE is None:
        creds = _load_credentials()
        _SERVICE = build("drive", "v3", credentials=creds, cache_discovery=False)
    return _SERVICE


def _ensure_folder(service, name: str, parent_id: str) -> str:
    supports_all = settings.GOOGLE_DRIVE_SUPPORTS_ALL_DRIVES
    query = (
        "mimeType='application/vnd.google-apps.folder' "
        f"and name='{name}' "
        f"and '{parent_id}' in parents "
        "and trashed=false"
    )
    resp = service.files().list(
        q=query,
        fields="files(id,name)",
        pageSize=1,
        supportsAllDrives=supports_all,
        includeItemsFromAllDrives=supports_all,
    ).execute()
    files = resp.get("files", [])
    if files:
        return files[0]["id"]

    folder_metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(
        body=folder_metadata,
        fields="id",
        supportsAllDrives=supports_all,
    ).execute()
    return folder["id"]


def _get_upload_date(value: datetime | None) -> datetime:
    if value is None:
        value = datetime.utcnow()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def upload_document_to_drive(document) -> None:
    if not settings.GOOGLE_DRIVE_ENABLED:
        logger.info("[DRIVE] Upload ignorado (GOOGLE_DRIVE_ENABLED=false)")
        return
    if not settings.GOOGLE_DRIVE_FOLDER_ID:
        logger.warning("[DRIVE] GOOGLE_DRIVE_FOLDER_ID não configurado; upload ignorado")
        return
    file_path = getattr(document, "file_path", None)
    if not file_path:
        logger.warning("[DRIVE] Documento %s sem file_path; upload ignorado", getattr(document, "id", "-"))
        return
    if not os.path.exists(file_path):
        logger.warning("[DRIVE] Arquivo não encontrado para upload: %s", file_path)
        return

    try:
        logger.info(
            "[DRIVE] Iniciando upload doc_id=%s arquivo=%s",
            getattr(document, "id", "-"),
            file_path,
        )
        service = _get_drive_service()
    except Exception as exc:
        logger.warning("[DRIVE] Falha ao inicializar Drive: %s", exc)
        return

    try:
        upload_date = _get_upload_date(getattr(document, "uploaded_at", None))
        year = upload_date.strftime("%Y")
        month_names = {
            1: "janeiro",
            2: "fevereiro",
            3: "marco",
            4: "abril",
            5: "maio",
            6: "junho",
            7: "julho",
            8: "agosto",
            9: "setembro",
            10: "outubro",
            11: "novembro",
            12: "dezembro",
        }
        month = month_names[upload_date.month]
        day = upload_date.strftime("%d-%m")

        parent_id = settings.GOOGLE_DRIVE_FOLDER_ID
        for folder_name in (year, month, day):
            parent_id = _ensure_folder(service, folder_name, parent_id)

        media_type, _ = mimetypes.guess_type(getattr(document, "filename", "documento.pdf"))
        from googleapiclient.http import MediaFileUpload
        media = MediaFileUpload(
            file_path,
            mimetype=media_type or "application/octet-stream",
            resumable=True,
        )
        file_metadata = {
            "name": getattr(document, "filename", os.path.basename(file_path)),
            "parents": [parent_id],
        }
        supports_all = settings.GOOGLE_DRIVE_SUPPORTS_ALL_DRIVES
        created = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id",
            supportsAllDrives=supports_all,
        ).execute()
        logger.info(
            "[DRIVE] Documento %s enviado (file_id=%s)",
            getattr(document, "id", "-"),
            created.get("id"),
        )
    except Exception as exc:
        logger.warning(
            "[DRIVE] Falha ao enviar documento %s: %s",
            getattr(document, "id", "-"),
            exc,
        )
