"""
Script para executar migração SQL no banco de dados.

Uso:
    python run_migration.py
"""
import os
import sys
import psycopg2
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

def run_migration():
    """Executa o script de migração SQL."""

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        print("❌ DATABASE_URL não configurado")
        return False

    print("🔄 Conectando ao banco de dados...")

    try:
        # Conectar ao banco
        conn = psycopg2.connect(database_url)
        conn.autocommit = False
        cursor = conn.cursor()

        print("✓ Conectado ao banco de dados")

        # Ler arquivo de migração
        migration_file = (
            sys.argv[1]
            if len(sys.argv) > 1
            else os.getenv("MIGRATION_FILE", "migrations/001_add_multi_tenant.sql")
        )

        if not os.path.exists(migration_file):
            print(f"❌ Arquivo de migração não encontrado: {migration_file}")
            return False

        with open(migration_file, "r") as f:
            sql_script = f.read()

        print(f"📜 Executando migração: {migration_file}")
        print("-" * 60)

        # Executar migração
        cursor.execute(sql_script)

        # Commit
        conn.commit()

        print("-" * 60)
        print("✓ Migração executada com sucesso!")

        # Verificar tabelas criadas
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('clinics', 'documents')
            ORDER BY table_name;
        """)

        tables = cursor.fetchall()
        print(f"\n📊 Tabelas verificadas:")
        for table in tables:
            print(f"  ✓ {table[0]}")

        # Verificar coluna clinic_id em users
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'users'
            AND column_name = 'clinic_id';
        """)

        if cursor.fetchone():
            print(f"  ✓ users.clinic_id")

        cursor.close()
        conn.close()

        print("\n🎉 Migração concluída com sucesso!")
        return True

    except Exception as e:
        print(f"\n❌ Erro durante migração: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False


if __name__ == "__main__":
    import sys
    success = run_migration()
    sys.exit(0 if success else 1)
