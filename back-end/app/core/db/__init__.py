"""
Pacote `app.core.db`.

Camada física do banco de dados (modelos SQLAlchemy + base declarativa).
Operações de domínio ainda vivem em `app.core.database_postgres.PostgresUserDatabase`;
um split incremental por agregado (users, documents, jobs, ...) está documentado
em `CONTEXTO.md` como próximo passo.
"""
from app.core.db.models import (
    Base,
    ClinicModel,
    UserModel,
    DocumentModel,
    NotificationModel,
    AuditLogModel,
    JobModel,
)

__all__ = [
    "Base",
    "ClinicModel",
    "UserModel",
    "DocumentModel",
    "NotificationModel",
    "AuditLogModel",
    "JobModel",
]
