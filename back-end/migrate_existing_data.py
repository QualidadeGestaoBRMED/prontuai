"""
Script de migração de dados do JSON (users.json) para PostgreSQL.

Este script:
1. Cria uma clínica padrão "Grupo BRMED - Legado" se não existir
2. Migra usuários do JSON para PostgreSQL
3. Associa usuários SENDER à clínica padrão
4. Mantém CHECKER/ADMIN com clinic_id = NULL

Uso:
    python migrate_existing_data.py
"""
import sys
import os
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Adicionar o diretório do projeto ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database_postgres import PostgresUserDatabase
from app.models.user import UserRole
import logging
import json

# Verificar se DATABASE_URL está configurado
database_url = os.getenv("DATABASE_URL")
if not database_url:
    print("❌ DATABASE_URL não configurado no .env")
    sys.exit(1)

# Usar PostgresUserDatabase diretamente
user_db = PostgresUserDatabase(database_url)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


USERS_JSON_PATH = os.path.join(os.path.dirname(__file__), "data", "users.json")

def migrate_users_from_json():
    """Migra usuários do users.json para PostgreSQL."""

    try:
        # 1. Criar clínica padrão para usuários legados
        logger.info("=" * 60)
        logger.info("MIGRAÇÃO DE DADOS - SISTEMA MULTI-TENANT")
        logger.info("=" * 60)

        default_clinic_name = "Grupo BRMED - Legado"

        # Verificar se clínica já existe
        existing_clinic = user_db.get_clinic_by_name(default_clinic_name)
        if existing_clinic:
            logger.info(f"✓ Clínica padrão já existe: {existing_clinic.name} ({existing_clinic.id})")
            default_clinic_id = existing_clinic.id
        else:
            default_clinic = user_db.create_clinic(name=default_clinic_name)
            default_clinic_id = default_clinic.id
            logger.info(f"✓ Clínica padrão criada: {default_clinic.name} ({default_clinic_id})")

        # 2. Buscar todos os usuários
        if not os.path.exists(USERS_JSON_PATH):
            logger.error(f"❌ users.json não encontrado em {USERS_JSON_PATH}")
            return False

        with open(USERS_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        users = list((data.get("users") or {}).values())
        logger.info(f"\n📊 Total de usuários no JSON: {len(users)}")

        # Contadores
        senders_updated = 0
        checkers_admins = 0
        already_migrated = 0
        errors = 0

        # 3. Processar cada usuário
        for user in users:
            try:
                email = user.get("email")
                name = user.get("name") or email
                role = UserRole(user.get("role"))

                # Se usuário já existe, pular
                existing = user_db.get_user_by_email(email)
                if existing:
                    already_migrated += 1
                    logger.debug(f"  - {email} ({existing.role.value}): já existe, pulando")
                    continue

                # Se for SENDER, associar à clínica padrão
                if role == UserRole.SENDER:
                    user_db.create_user(email=email, name=name, role=role, clinic_id=default_clinic_id)
                    senders_updated += 1
                    logger.info(f"  ✓ SENDER {email} migrado e associado à clínica padrão")

                # Se for CHECKER ou ADMIN, manter clinic_id = NULL
                elif role in [UserRole.CHECKER, UserRole.ADMIN]:
                    user_db.create_user(email=email, name=name, role=role, clinic_id=None)
                    checkers_admins += 1
                    logger.debug(f"  - {email} ({role.value}): migrado sem clínica")

            except Exception as e:
                errors += 1
                logger.error(f"  ✗ Erro ao migrar {user.get('email')}: {e}")

        # 4. Resumo
        logger.info("\n" + "=" * 60)
        logger.info("RESUMO DA MIGRAÇÃO")
        logger.info("=" * 60)
        logger.info(f"✓ SENDERS associados à clínica padrão: {senders_updated}")
        logger.info(f"✓ CHECKERS/ADMINS (sem clínica): {checkers_admins}")
        logger.info(f"- Já migrados (pulados): {already_migrated}")
        logger.info(f"✗ Erros: {errors}")
        logger.info("=" * 60)

        if errors == 0:
            logger.info("\n🎉 Migração concluída com sucesso!")
        else:
            logger.warning(f"\n⚠️  Migração concluída com {errors} erro(s)")

        return True

    except Exception as e:
        logger.exception(f"❌ Erro fatal durante migração: {e}")
        return False


if __name__ == "__main__":
    logger.info("\n🚀 Iniciando migração de dados...\n")
    success = migrate_users_from_json()
    sys.exit(0 if success else 1)
