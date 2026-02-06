import os
import re
from collections import defaultdict

from app.core.config import settings
from app.core.database import user_db


def _safe_filename(filename: str) -> str:
    base = os.path.basename(filename or "documento")
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    return safe or "documento"


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _split_prefixed_name(name: str) -> str:
    # Remove prefixos tipo UUID_
    return re.sub(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_", "", name, flags=re.IGNORECASE)


def _index_uploads(base_dir: str) -> dict[str, list[str]]:
    suffix_map: dict[str, list[str]] = defaultdict(list)
    if not os.path.isdir(base_dir):
        return suffix_map
    for entry in os.listdir(base_dir):
        full = os.path.join(base_dir, entry)
        if not os.path.isfile(full):
            continue
        name = entry
        name_lower = name.lower()
        name_norm = _normalize(name)
        suffix = _split_prefixed_name(name)
        suffix_lower = suffix.lower()
        suffix_norm = _normalize(suffix)

        suffix_map[name].append(full)
        suffix_map[name_lower].append(full)
        suffix_map[name_norm].append(full)
        suffix_map[suffix_lower].append(full)
        suffix_map[suffix_norm].append(full)
    return suffix_map


def _pick_best(paths: list[str]) -> str:
    if len(paths) == 1:
        return paths[0]
    paths.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return paths[0]


def main() -> None:
    base_dir = os.path.abspath(settings.DOCUMENT_STORAGE_DIR)
    print(f"DOCUMENT_STORAGE_DIR={base_dir}")
    uploads = _index_uploads(base_dir)
    if not uploads:
        print("Nenhum arquivo encontrado na pasta de uploads.")
        return

    docs = user_db.get_all_documents()
    updated = 0
    skipped = 0
    missing = 0

    for doc in docs:
        file_path = getattr(doc, "file_path", None)
        if file_path:
            continue

        original_name = getattr(doc, "filename", "documento")
        safe_name = _safe_filename(original_name)
        candidates: list[str] = []

        # Match exato
        if safe_name in uploads:
            candidates.extend(uploads[safe_name])

        # Match com prefixo (uuid_arquivo.pdf)
        suffix = f"_{safe_name}"
        suffix_lower = suffix.lower()
        suffix_norm = _normalize(suffix)
        for name, paths in uploads.items():
            if name.endswith(suffix) or name.endswith(suffix_lower) or name.endswith(suffix_norm):
                candidates.extend(paths)

        # Match case-insensitive e normalizado
        safe_lower = safe_name.lower()
        safe_norm = _normalize(safe_name)
        original_lower = original_name.lower()
        original_norm = _normalize(original_name)
        for key in (safe_lower, safe_norm, original_lower, original_norm):
            if key in uploads:
                candidates.extend(uploads[key])

        if not candidates:
            missing += 1
            continue

        chosen = _pick_best(list(set(candidates)))
        try:
            user_db.update_document(document_id=doc.id, file_path=chosen)
            updated += 1
        except Exception as exc:
            print(f"Falha ao atualizar doc_id={doc.id}: {exc}")
            skipped += 1

    print(f"Atualizados: {updated} | Sem arquivo: {missing} | Falhas: {skipped}")


if __name__ == "__main__":
    main()
