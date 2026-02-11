#!/usr/bin/env python3
"""
Reset de dados operacionais com backup automático e limpeza de uploads.

Mantém: users, clinics
Limpa: documents, notifications, audit_logs (e dependências via CASCADE)

Uso:
  python scripts/reset_production.py --confirm

Opcional:
  --skip-backup      Não gera backup
  --skip-uploads     Não limpa uploads
  --backup-dir DIR   Diretório de backup customizado
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.core.config import settings


TABLES_TO_TRUNCATE = ["documents", "notifications", "audit_logs"]
TABLES_TO_BACKUP = ["documents", "notifications", "audit_logs", "users", "clinics"]


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _pg_dump_available() -> bool:
    return shutil.which("pg_dump") is not None


def _backup_with_pg_dump(database_url: str, backup_dir: Path) -> Path:
    backup_file = backup_dir / "backup_tables.dump"
    cmd = [
        "pg_dump",
        "--format=custom",
        "--data-only",
        "--no-owner",
        "--no-privileges",
        "--dbname",
        database_url,
    ]
    for table in TABLES_TO_BACKUP:
        cmd.extend(["--table", table])

    subprocess.run(cmd, check=True, stdout=open(backup_file, "wb"))
    return backup_file


def _backup_with_json(database_url: str, backup_dir: Path) -> None:
    conn = psycopg2.connect(database_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            for table in TABLES_TO_BACKUP:
                cur.execute(f"SELECT * FROM {table}")
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description]
                payload = [
                    {columns[i]: row[i] for i in range(len(columns))} for row in rows
                ]
                with open(backup_dir / f"{table}.json", "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    finally:
        conn.close()


def _truncate_tables(database_url: str) -> None:
    conn = psycopg2.connect(database_url)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            tables = ", ".join(TABLES_TO_TRUNCATE)
            cur.execute(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE;")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _clear_uploads(upload_dir: Path) -> int:
    if not upload_dir.exists() or not upload_dir.is_dir():
        return 0

    removed = 0
    for entry in upload_dir.iterdir():
        try:
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
            removed += 1
        except Exception:
            # Não interrompe o reset por falhas pontuais em arquivos
            continue
    return removed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", action="store_true", help="Confirma o reset destrutivo")
    parser.add_argument("--skip-backup", action="store_true", help="Não gera backup")
    parser.add_argument("--skip-uploads", action="store_true", help="Não limpa uploads")
    parser.add_argument("--backup-dir", type=str, default="", help="Diretório customizado de backup")
    args = parser.parse_args()

    if not args.confirm:
        print("❌ Operação cancelada. Use --confirm para executar.")
        return 1

    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL não configurado")
        return 1

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_dir = Path(args.backup_dir) if args.backup_dir else Path("backups") / f"reset_{timestamp}"
    _ensure_dir(backup_dir)

    if not args.skip_backup:
        print("🔄 Gerando backup...")
        try:
            if _pg_dump_available():
                _backup_with_pg_dump(database_url, backup_dir)
                print(f"✓ Backup pg_dump salvo em {backup_dir}")
            else:
                _backup_with_json(database_url, backup_dir)
                print(f"✓ Backup JSON salvo em {backup_dir}")
        except Exception as exc:
            print(f"❌ Falha ao gerar backup: {exc}")
            return 1

    print("🧹 Limpando tabelas...")
    try:
        _truncate_tables(database_url)
        print("✓ Tabelas limpas com sucesso.")
    except Exception as exc:
        print(f"❌ Falha ao limpar tabelas: {exc}")
        return 1

    if not args.skip_uploads:
        upload_dir = Path(settings.DOCUMENT_STORAGE_DIR)
        removed = _clear_uploads(upload_dir)
        print(f"✓ Uploads removidos: {removed} itens em {upload_dir}")

    print("🎉 Reset concluído.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
