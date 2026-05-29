"""
Ponto de entrada do banco de dados de usuários/documentos/notificações/jobs.

A única implementação ativa em produção é PostgreSQL
(`app.core.database_postgres.PostgresUserDatabase`). O caminho JSON existia
para desenvolvimento e foi movido para `app.core._legacy.json_user_database`
como referência histórica; não é mais carregado em runtime.
"""
import logging
import os
from datetime import datetime
from typing import List, Optional, Protocol

from app.models.audit_log import AuditLog, AuditLogCreate
from app.models.clinic import Clinic, ClinicCreate, ClinicUpdate
from app.models.document import Document
from app.models.notification import Notification, NotificationCreate
from app.models.user import User, UserRole, UserUpdate

logger = logging.getLogger(__name__)


class UserDatabaseProtocol(Protocol):
    """Interface mínima que toda implementação de banco precisa expor.

    Documenta o contrato consumido pelos handlers da API; o tipo concreto
    em produção é `PostgresUserDatabase`.
    """

    def get_user_by_email(self, email: str) -> Optional[User]: ...
    def get_user_by_id(self, user_id: str) -> Optional[User]: ...
    def get_all_users(self) -> List[User]: ...
    def create_user(
        self,
        email: str,
        name: str,
        role: UserRole = UserRole.CHECKER,
        clinic_id: Optional[str] = None,
    ) -> User: ...
    def update_user(self, user_id: str, update: UserUpdate) -> User: ...
    def delete_user(self, user_id: str) -> bool: ...
    def create_notification(self, data: NotificationCreate) -> Notification: ...
    def list_notifications(
        self,
        clinic_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 100,
        include_read: bool = True,
    ) -> List[Notification]: ...
    def mark_notification_read(
        self, notification_id: str, user_id: Optional[str] = None
    ) -> Optional[Notification]: ...
    def mark_all_notifications_read(
        self, clinic_id: Optional[str] = None, user_id: Optional[str] = None
    ) -> int: ...
    def clear_notifications(
        self, clinic_id: Optional[str] = None, user_id: Optional[str] = None
    ) -> int: ...
    def create_audit_log(self, data: AuditLogCreate) -> AuditLog: ...
    def list_audit_logs(
        self,
        limit: int = 200,
        user_id: Optional[str] = None,
        user_email: Optional[str] = None,
        action: Optional[str] = None,
        request_id: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> List[AuditLog]: ...


def get_user_database() -> UserDatabaseProtocol:
    """Retorna a instância do banco de dados.

    Exige `DATABASE_URL` no ambiente. Falha em fail-fast se ausente para
    evitar fallback silencioso para o caminho JSON legado.
    """
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL não configurada. O caminho JSON legado foi "
            "removido do hot path; configure um Postgres antes de subir."
        )

    from app.core.database_postgres import PostgresUserDatabase

    logger.info("Usando banco de dados PostgreSQL")
    return PostgresUserDatabase(database_url)


# Instância global compartilhada por todos os handlers/serviços.
user_db: UserDatabaseProtocol = get_user_database()
