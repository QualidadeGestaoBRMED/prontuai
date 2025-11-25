"""
Endpoints administrativos (apenas ADMIN).
"""
from fastapi import APIRouter, HTTPException, status, Depends
from app.core.auth import require_admin
from app.models.user import User
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Administração"])


@router.post("/migrate")
async def run_migration_endpoint(
    current_user: User = Depends(require_admin)
):
    """
    Executa migração do banco de dados manualmente.

    **APENAS ADMIN**

    Use este endpoint se a auto-migração falhou ou para forçar re-execução.
    """
    try:
        from app.core.migrations import check_if_migration_needed, run_migration, run_data_migration

        logger.info(f"[ADMIN] {current_user.email} iniciou migração manual")

        # Verificar se é necessário
        needs_migration, migration_files = check_if_migration_needed()

        if not needs_migration:
            return {
                "status": "success",
                "message": "Banco de dados já está atualizado. Nenhuma migração necessária.",
                "migrations_executed": False
            }

        # Executar migrações SQL
        sql_success = run_migration(migration_files)
        if not sql_success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Falha ao executar migração SQL"
            )

        # Executar migração de dados (somente se migration 001 foi executada)
        data_success = True
        if "001_add_multi_tenant.sql" in migration_files:
            data_success = run_data_migration()
            if not data_success:
                logger.warning("Migração SQL executada, mas falha na migração de dados")

        logger.info(f"[ADMIN] Migração manual concluída com sucesso")

        return {
            "status": "success",
            "message": "Migração executada com sucesso!",
            "migrations_executed": True,
            "migration_files": migration_files,
            "sql_migration": sql_success,
            "data_migration": data_success
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao executar migração manual: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao executar migração: {str(e)}"
        )


@router.get("/status")
async def get_system_status(
    current_user: User = Depends(require_admin)
):
    """
    Retorna status do sistema e banco de dados.

    **APENAS ADMIN**
    """
    try:
        from app.core.migrations import check_if_migration_needed
        from app.core.database import user_db

        # Verificar se migração é necessária
        needs_migration, migration_files = check_if_migration_needed()

        # Contar usuários e clínicas
        try:
            users_count = len(user_db.get_all_users())
        except:
            users_count = "N/A"

        try:
            clinics_count = len(user_db.get_all_clinics())
        except:
            clinics_count = "N/A"

        try:
            documents_count = len(user_db.get_all_documents())
        except:
            documents_count = "N/A"

        return {
            "status": "online",
            "database": {
                "migrations_needed": needs_migration,
                "migrations_status": "up-to-date" if not needs_migration else "pending",
                "pending_migrations": migration_files if needs_migration else []
            },
            "statistics": {
                "users": users_count,
                "clinics": clinics_count,
                "documents": documents_count
            }
        }

    except Exception as e:
        logger.exception(f"Erro ao obter status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao obter status: {str(e)}"
        )
