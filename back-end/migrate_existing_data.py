"""
Script de migração de dados existentes para o sistema multi-tenant.

Este script:
1. Cria uma clínica padrão "Grupo BRMED" para usuários legados
2. Associa todos os usuários SENDER existentes a essa clínica
3. Mantém CHECKER/ADMIN com clinic_id = NULL

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

# Verificar se DATABASE_URL está configurado
database_url = os.getenv("DATABASE_URL")
if not database_url:
    print("❌ DATABASE_URL não configurado no .env")
    sys.exit(1)

# Usar PostgresUserDatabase diretamente
user_db = PostgresUserDatabase(database_url)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate_users():
    """Migra usuários existentes para o modelo multi-tenant."""

    try:
        # 1. Criar clínica padrão para usuários legados
        logger.info("=" * 60)
        logger.info("MIGRAÇÃO DE DADOS - SISTEMA MULTI-TENANT")
        logger.info("=" * 60)

        default_clinic_email = "legado@grupobrmed.com.br"
        default_clinic_name = "Grupo BRMED - Legado"

        # Verificar se clínica já existe
        existing_clinic = user_db.get_clinic_by_email(default_clinic_email)

        if existing_clinic:
            logger.info(f"✓ Clínica padrão já existe: {existing_clinic.name} ({existing_clinic.id})")
            default_clinic_id = existing_clinic.id
        else:
            # Criar clínica padrão
            default_clinic = user_db.create_clinic(
                email=default_clinic_email,
                name=default_clinic_name
            )
            default_clinic_id = default_clinic.id
            logger.info(f"✓ Clínica padrão criada: {default_clinic.name} ({default_clinic_id})")

        # 2. Buscar todos os usuários
        all_users = user_db.get_all_users()
        logger.info(f"\n📊 Total de usuários: {len(all_users)}")

        # Contadores
        senders_updated = 0
        checkers_admins = 0
        already_migrated = 0
        errors = 0

        # 3. Processar cada usuário
        for user in all_users:
            try:
                # Se já tem clinic_id, pular
                if user.clinic_id:
                    already_migrated += 1
                    logger.debug(f"  - {user.email} ({user.role.value}): já migrado (clinic_id={user.clinic_id})")
                    continue

                # Se for SENDER, associar à clínica padrão
                if user.role == UserRole.SENDER:
                    user_db.update_user(
                        user_id=user.id,
                        clinic_id=default_clinic_id
                    )
                    senders_updated += 1
                    logger.info(f"  ✓ SENDER {user.email} associado à clínica padrão")

                # Se for CHECKER ou ADMIN, manter clinic_id = NULL
                elif user.role in [UserRole.CHECKER, UserRole.ADMIN]:
                    checkers_admins += 1
                    logger.debug(f"  - {user.email} ({user.role.value}): mantido sem clínica")

            except Exception as e:
                errors += 1
                logger.error(f"  ✗ Erro ao migrar {user.email}: {e}")

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
    success = migrate_users()
    sys.exit(0 if success else 1)
