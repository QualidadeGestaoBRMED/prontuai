"""
Auto-migration system - Executa migrações automaticamente no startup.
"""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def check_if_migration_needed() -> bool:
    """
    Verifica se a migração é necessária checando se a coluna clinic_id existe.
    """
    try:
        from app.core.database_postgres import PostgresUserDatabase

        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            logger.info("DATABASE_URL não configurado - pulando verificação de migração")
            return False

        # Tentar consultar com clinic_id - se falhar, precisa migrar
        db = PostgresUserDatabase(database_url)

        # Se chegou até aqui sem erro, a migração já foi executada
        logger.info("✓ Banco de dados já migrado (clinic_id existe)")
        return False

    except Exception as e:
        error_msg = str(e).lower()

        # Se o erro for "column clinic_id does not exist", precisa migrar
        if "clinic_id" in error_msg and ("does not exist" in error_msg or "não existe" in error_msg):
            logger.warning("⚠️  Migração necessária: coluna clinic_id não existe")
            return True

        # Outros erros - não tentar migrar
        logger.error(f"Erro ao verificar migração: {e}")
        return False


def run_migration() -> bool:
    """
    Executa a migração SQL se necessário.

    Returns:
        True se migração executada com sucesso, False caso contrário
    """
    import psycopg2

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL não configurado")
        return False

    logger.info("🔄 Executando migração do banco de dados...")

    try:
        # Ler arquivo de migração
        migration_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "migrations",
            "001_add_multi_tenant.sql"
        )

        if not os.path.exists(migration_file):
            logger.error(f"Arquivo de migração não encontrado: {migration_file}")
            return False

        with open(migration_file, "r") as f:
            sql_script = f.read()

        # Conectar e executar
        conn = psycopg2.connect(database_url)
        conn.autocommit = False
        cursor = conn.cursor()

        logger.info("Executando SQL de migração...")
        cursor.execute(sql_script)
        conn.commit()

        logger.info("✅ Migração executada com sucesso!")

        cursor.close()
        conn.close()

        return True

    except Exception as e:
        logger.exception(f"❌ Erro ao executar migração: {e}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return False


def run_data_migration() -> bool:
    """
    Migra dados existentes (usuários para clínica padrão).

    Returns:
        True se migração de dados executada com sucesso
    """
    try:
        from app.core.database_postgres import PostgresUserDatabase
        from app.models.user import UserRole

        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            logger.error("DATABASE_URL não configurado")
            return False

        user_db = PostgresUserDatabase(database_url)

        logger.info("🔄 Migrando dados existentes...")

        # 1. Criar clínica padrão
        default_clinic_email = "legado@grupobrmed.com.br"
        default_clinic_name = "Grupo BRMED - Legado"

        existing_clinic = user_db.get_clinic_by_email(default_clinic_email)

        if existing_clinic:
            logger.info(f"✓ Clínica padrão já existe: {existing_clinic.id}")
            default_clinic_id = existing_clinic.id
        else:
            default_clinic = user_db.create_clinic(
                email=default_clinic_email,
                name=default_clinic_name
            )
            default_clinic_id = default_clinic.id
            logger.info(f"✓ Clínica padrão criada: {default_clinic_id}")

        # 2. Migrar usuários SENDER
        all_users = user_db.get_all_users()
        senders_updated = 0

        for user in all_users:
            # Pular se já tem clinic_id
            if user.clinic_id:
                continue

            # Associar SENDER à clínica padrão
            if user.role == UserRole.SENDER:
                user_db.update_user(
                    user_id=user.id,
                    clinic_id=default_clinic_id
                )
                senders_updated += 1
                logger.info(f"  ✓ SENDER {user.email} associado à clínica padrão")

        logger.info(f"✅ Migração de dados concluída: {senders_updated} SENDERs migrados")
        return True

    except Exception as e:
        logger.exception(f"❌ Erro ao migrar dados: {e}")
        return False


def auto_migrate():
    """
    Função principal - executa migração automaticamente se necessário.
    Chamada no startup da aplicação.
    """
    logger.info("=" * 60)
    logger.info("VERIFICANDO MIGRAÇÕES DO BANCO DE DADOS")
    logger.info("=" * 60)

    # 1. Verificar se migração é necessária
    if not check_if_migration_needed():
        logger.info("Nenhuma migração necessária - banco já atualizado")
        return

    # 2. Executar migração SQL
    logger.info("Migração necessária detectada!")

    if not run_migration():
        logger.error("Falha ao executar migração SQL - aplicação pode não funcionar corretamente")
        return

    # 3. Migrar dados existentes
    if not run_data_migration():
        logger.warning("Falha ao migrar dados existentes - verifique manualmente")
        return

    logger.info("=" * 60)
    logger.info("✅ AUTO-MIGRAÇÃO CONCLUÍDA COM SUCESSO")
    logger.info("=" * 60)
