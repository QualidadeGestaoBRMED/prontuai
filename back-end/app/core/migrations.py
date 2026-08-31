"""
Auto-migration system - Executa migrações automaticamente no startup.
"""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def check_if_migration_needed() -> tuple[bool, list[str]]:
    """
    Verifica quais migrações são necessárias checando colunas específicas.

    Returns:
        (needs_migration, migrations_to_run): tupla indicando se precisa migrar
        e lista de arquivos de migração a executar
    """
    import psycopg2

    try:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            logger.info("DATABASE_URL não configurado - pulando verificação de migração")
            return False, []

        # Conectar ao banco para verificar colunas
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()

        migrations_needed = []

        # Verificar migration 001: clinic_id em users
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='users' AND column_name='clinic_id'
        """)
        if not cursor.fetchone():
            logger.warning("⚠️  Migration 001 necessária: coluna clinic_id não existe")
            migrations_needed.append("001_add_multi_tenant.sql")

        # Verificar migration 002: cnpj em clinics
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='clinics' AND column_name='cnpj'
        """)
        if not cursor.fetchone():
            logger.warning("⚠️  Migration 002 necessária: coluna cnpj não existe")
            migrations_needed.append("002_update_clinic_fields.sql")

        # Verificar migration 004: review_active_ms em documents
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='documents' AND column_name='review_active_ms'
        """)
        if not cursor.fetchone():
            logger.warning("⚠️  Migration 004 necessária: coluna review_active_ms não existe")
            migrations_needed.append("004_add_review_timing.sql")

        # Verificar migration 005: tabelas do catálogo de exames
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name='exam_parents'
        """)
        if not cursor.fetchone():
            logger.warning("⚠️  Migration 005 necessária: tabela exam_parents não existe")
            migrations_needed.append("005_add_exam_catalog.sql")

        # Verificar migration 006: vector_id no catálogo de exames
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='exam_parents' AND column_name='vector_id'
        """)
        if not cursor.fetchone():
            logger.warning("⚠️  Migration 006 necessária: coluna vector_id não existe")
            migrations_needed.append("006_add_exam_vector_id.sql")

        cursor.close()
        conn.close()

        if not migrations_needed:
            logger.info("✓ Banco de dados já migrado (todas as colunas existem)")
            return False, []

        return True, migrations_needed

    except Exception as e:
        logger.error(f"Erro ao verificar migração: {e}")
        return False, []


def run_migration(migration_files: list[str]) -> bool:
    """
    Executa as migrações SQL necessárias em sequência.

    Args:
        migration_files: Lista de arquivos de migração a executar

    Returns:
        True se todas as migrações executadas com sucesso, False caso contrário
    """
    import psycopg2

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL não configurado")
        return False

    if not migration_files:
        logger.info("Nenhuma migração para executar")
        return True

    logger.info(f"🔄 Executando {len(migration_files)} migração(ões)...")

    try:
        # Conectar ao banco
        conn = psycopg2.connect(database_url)
        conn.autocommit = False
        cursor = conn.cursor()

        # Executar cada migration em sequência
        for migration_file in migration_files:
            migration_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "migrations",
                migration_file
            )

            if not os.path.exists(migration_path):
                logger.error(f"Arquivo de migração não encontrado: {migration_path}")
                conn.rollback()
                conn.close()
                return False

            logger.info(f"📜 Executando: {migration_file}")

            with open(migration_path, "r") as f:
                sql_script = f.read()

            cursor.execute(sql_script)
            conn.commit()

            logger.info(f"✅ {migration_file} executada com sucesso!")

        cursor.close()
        conn.close()

        logger.info("✅ Todas as migrações executadas com sucesso!")
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
        default_clinic_name = "Grupo BRMED - Legado"

        existing_clinic = user_db.get_clinic_by_name(default_clinic_name)

        if existing_clinic:
            logger.info(f"✓ Clínica padrão já existe: {existing_clinic.id}")
            default_clinic_id = existing_clinic.id
        else:
            default_clinic = user_db.create_clinic(
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
    needs_migration, migration_files = check_if_migration_needed()

    if not needs_migration:
        logger.info("Nenhuma migração necessária - banco já atualizado")
        return

    # 2. Executar migrações SQL
    logger.info(f"Migração necessária detectada! {len(migration_files)} arquivo(s) a executar")

    if not run_migration(migration_files):
        logger.error("Falha ao executar migração SQL - aplicação pode não funcionar corretamente")
        return

    # 3. Migrar dados existentes (somente se migration 001 foi executada)
    if "001_add_multi_tenant.sql" in migration_files:
        if not run_data_migration():
            logger.warning("Falha ao migrar dados existentes - verifique manualmente")
            return

    logger.info("=" * 60)
    logger.info("✅ AUTO-MIGRAÇÃO CONCLUÍDA COM SUCESSO")
    logger.info("=" * 60)
