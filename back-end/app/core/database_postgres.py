"""
Implementação PostgreSQL do banco de dados.

Modelos SQLAlchemy ficam em `app.core.db.models`; este módulo contém
apenas a classe de operações `PostgresUserDatabase`. Próximo passo de
refactor (documentado em CONTEXTO.md): quebrar a classe em mixins por
agregado dentro de `app.core.db`.
"""
import os
import time
import json
import logging
from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy import create_engine, text, func, or_, and_, case
from sqlalchemy.orm import sessionmaker, Session, defer
from app.models.user import User, UserCreate, UserUpdate, UserRole
from app.models.clinic import Clinic, ClinicCreate, ClinicUpdate
from app.models.document import Document, DocumentCreate, DocumentUpdate
from app.models.notification import Notification, NotificationCreate, NotificationUpdate
from app.models.audit_log import AuditLog, AuditLogCreate
from app.models.exam import (
    ExamCatalogStats,
    ExamPendency,
    ExamParent,
    ExamParentDetail,
    ExamVariation,
    ExamVariationConflict,
)
from app.core.exam_normalize import limpar_texto, normalizar_termo
from app.services.exam_vector_service import derivar_vector_id
from app.core.db.models import (
    Base,
    ClinicModel,
    UserModel,
    DocumentModel,
    NotificationModel,
    AuditLogModel,
    JobModel,
    MaintenanceWindowModel,
    RefreshTokenModel,
    ExamParentModel,
    ExamVariationModel,
    ExamVariationConflictModel,
)

logger = logging.getLogger(__name__)


class PostgresUserDatabase:
    """Implementação do banco de dados de usuários baseado em PostgreSQL."""

    def __init__(self, database_url: Optional[str] = None):
        """
        Inicializa conexão PostgreSQL.

        Args:
            database_url: String de conexão PostgreSQL
                         Formato: postgresql://user:password@host:port/dbname
        """
        self.database_url = database_url or os.getenv("DATABASE_URL")

        if not self.database_url:
            raise ValueError("DATABASE_URL not set")

        # DATABASE_URL padrão usa postgresql:// mas SQLAlchemy 2.0 requer postgresql+psycopg2://
        if self.database_url.startswith("postgresql://"):
            self.database_url = self.database_url.replace("postgresql://", "postgresql+psycopg2://", 1)

        # Configuração do pool de conexões para evitar erros SSL intermitentes
        self.engine = create_engine(
            self.database_url,
            echo=False,
            pool_pre_ping=True,  # Verifica se a conexão está viva antes de usar
            pool_recycle=3600,   # Recicla conexões a cada hora (evita conexões stale)
            pool_size=5,         # Tamanho base do pool
            max_overflow=10,     # Conexões extras permitidas sob carga
            connect_args={
                "connect_timeout": 10,  # Timeout de conexão em segundos
                "keepalives": 1,        # Habilita TCP keepalive
                "keepalives_idle": 30,  # Tempo antes de enviar keepalive
                "keepalives_interval": 10,  # Intervalo entre keepalives
                "keepalives_count": 5   # Número de keepalives antes de desistir
            }
        )
        self.SessionLocal = sessionmaker(bind=self.engine)

        # Enum userrole pode ter sido criado antes da role MANAGER existir
        self._ensure_role_enum_values()

        # Cria tabelas se não existirem
        Base.metadata.create_all(self.engine)
        self._ensure_document_columns()
        self._ensure_notification_columns()
        self._ensure_audit_log_table()
        self._ensure_job_table()
        self._ensure_maintenance_table()

        # Preenche patient_name de documentos antigos (extraído do result_payload)
        self._backfill_patient_names()

        # Cria admin padrão se banco estiver vazio
        self._ensure_default_admin()

    def _get_session(self) -> Session:
        """Obtém uma nova sessão do banco de dados."""
        return self.SessionLocal()

    @staticmethod
    def _extract_patient_name(result_payload) -> Optional[str]:
        """Extrai o nome do paciente do payload de resultado, se presente."""
        if not isinstance(result_payload, dict):
            return None
        name = result_payload.get("patient_name") or result_payload.get("patientName")
        if isinstance(name, str) and name.strip():
            return name.strip()
        return None

    def _backfill_patient_names(self, batch_size: int = 200) -> None:
        """Preenche patient_name de documentos criados antes da coluna existir.

        Usa '' como sentinela para payloads sem nome, evitando reprocessar a
        cada boot. Roda em lotes para não carregar payloads grandes de uma vez.
        """
        session = self._get_session()
        try:
            total = 0
            while True:
                rows = (
                    session.query(DocumentModel)
                    .options(defer(DocumentModel.ocr_markdown), defer(DocumentModel.result_payload))
                    .filter(DocumentModel.patient_name.is_(None))
                    .filter(
                        or_(
                            DocumentModel.result_payload_compact.isnot(None),
                            DocumentModel.result_payload.isnot(None),
                        )
                    )
                    .limit(batch_size)
                    .all()
                )
                if not rows:
                    break
                for model in rows:
                    raw = model.result_payload_compact or model.result_payload
                    try:
                        payload = json.loads(raw) if raw else None
                    except (TypeError, ValueError):
                        payload = None
                    model.patient_name = self._extract_patient_name(payload) or ""
                session.commit()
                total += len(rows)
            if total:
                logger.info(f"[DB] Backfill de patient_name concluído: {total} documentos atualizados")
        except Exception as e:
            session.rollback()
            logger.error(f"[DB] Erro no backfill de patient_name: {e}")
        finally:
            session.close()

    def _ensure_role_enum_values(self) -> None:
        """Garante que o enum userrole contenha as roles novas (ex.: MANAGER).

        ALTER TYPE ... ADD VALUE precisa rodar fora de transação; em banco novo o
        tipo ainda não existe e o create_all cria com todos os valores.
        """
        with self.engine.connect() as connection:
            autocommit = connection.execution_options(isolation_level="AUTOCOMMIT")
            type_exists = autocommit.execute(
                text("SELECT 1 FROM pg_type WHERE typname = 'userrole'")
            ).scalar()
            if type_exists:
                autocommit.execute(text("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'MANAGER'"))

    def _ensure_document_columns(self) -> None:
        """Garante que colunas novas existam para documentos."""
        with self.engine.begin() as connection:
            connection.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS file_path VARCHAR"))
            connection.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS run_id VARCHAR"))
            connection.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS result_payload TEXT"))
            connection.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS result_payload_compact TEXT"))
            connection.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS reviewed_by VARCHAR"))
            connection.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP"))
            connection.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS approval_reason TEXT"))
            connection.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS rejection_reason TEXT"))
            connection.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS confidence_score DOUBLE PRECISION"))
            connection.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS quality_score DOUBLE PRECISION"))
            connection.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS mandatory_coverage DOUBLE PRECISION"))
            connection.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS exams_ocr TEXT[]"))
            connection.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS exams_brnet TEXT[]"))
            connection.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_hash VARCHAR"))
            connection.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS uploaded_by_user_email VARCHAR"))
            connection.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS patient_name VARCHAR"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_documents_patient_name ON documents(patient_name)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_documents_uploader_email ON documents(uploaded_by_user_email)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_documents_reviewed_by ON documents(reviewed_by)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_documents_clinic_id ON documents(clinic_id)"))

    def _ensure_notification_columns(self) -> None:
        """Garante que colunas novas existam para notificações."""
        with self.engine.begin() as connection:
            connection.execute(text("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS metadata_json TEXT"))
            connection.execute(text("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS user_id VARCHAR"))
            connection.execute(text("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS user_email VARCHAR"))

    def _ensure_audit_log_table(self) -> None:
        """Garante índices úteis para auditoria."""
        with self.engine.begin() as connection:
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_audit_logs_user_email ON audit_logs(user_email)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_audit_logs_request_id ON audit_logs(request_id)"))

    def _ensure_job_table(self) -> None:
        """Garante índices úteis para jobs."""
        with self.engine.begin() as connection:
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at)"))

    def _ensure_maintenance_table(self) -> None:
        """Garante índices úteis para janelas de manutenção."""
        with self.engine.begin() as connection:
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_maintenance_status ON maintenance_windows(status)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_maintenance_starts_at ON maintenance_windows(starts_at)"))

    # =============== MÉTODOS DE NOTIFICAÇÃO ===============

    def _model_to_notification(self, model: NotificationModel) -> Notification:
        metadata = None
        if model and model.metadata_json:
            try:
                import json
                metadata = json.loads(model.metadata_json)
            except Exception:
                metadata = None
        return Notification(
            id=model.id,
            user_id=model.user_id,
            user_email=model.user_email,
            clinic_id=model.clinic_id,
            document_id=model.document_id,
            type=model.type,
            title=model.title,
            message=model.message,
            variant=model.variant,
            action_url=model.action_url,
            action_label=model.action_label,
            metadata=metadata,
            read=model.read,
            created_at=model.created_at.isoformat()
        )

    def create_notification(self, data: NotificationCreate) -> Notification:
        session = self._get_session()
        try:
            import uuid
            import json
            notification_model = NotificationModel(
                id=str(uuid.uuid4()),
                user_id=data.user_id,
                user_email=data.user_email,
                clinic_id=data.clinic_id,
                document_id=data.document_id,
                type=data.type,
                title=data.title,
                message=data.message,
                variant=data.variant,
                action_url=data.action_url,
                action_label=data.action_label,
            metadata_json=json.dumps(data.metadata, ensure_ascii=False) if data.metadata is not None else None,
                read=False,
                created_at=datetime.utcnow()
            )
            session.add(notification_model)
            session.commit()
            session.refresh(notification_model)
            return self._model_to_notification(notification_model)
        finally:
            session.close()

    # =============== MÉTODOS DE AUDITORIA ===============

    def _model_to_audit_log(self, model: AuditLogModel) -> AuditLog:
        metadata = None
        if model and model.metadata_json:
            try:
                import json
                metadata = json.loads(model.metadata_json)
            except Exception:
                metadata = None
        return AuditLog(
            id=model.id,
            user_id=model.user_id,
            user_email=model.user_email,
            user_role=model.user_role,
            action=model.action,
            resource=model.resource,
            resource_id=model.resource_id,
            method=model.method,
            path=model.path,
            status_code=model.status_code,
            ip=model.ip,
            user_agent=model.user_agent,
            request_id=model.request_id,
            metadata=metadata,
            created_at=model.created_at,
        )

    def create_audit_log(self, data: AuditLogCreate) -> AuditLog:
        session = self._get_session()
        try:
            import uuid
            import json
            audit_model = AuditLogModel(
                id=str(uuid.uuid4()),
                user_id=data.user_id,
                user_email=data.user_email,
                user_role=data.user_role,
                action=data.action,
                resource=data.resource,
                resource_id=data.resource_id,
                method=data.method,
                path=data.path,
                status_code=data.status_code,
                ip=data.ip,
                user_agent=data.user_agent,
                request_id=data.request_id,
                metadata_json=json.dumps(data.metadata, ensure_ascii=False) if data.metadata is not None else None,
                created_at=datetime.utcnow(),
            )
            session.add(audit_model)
            session.commit()
            session.refresh(audit_model)
            return self._model_to_audit_log(audit_model)
        finally:
            session.close()

    def list_audit_logs(
        self,
        limit: int = 200,
        user_id: Optional[str] = None,
        user_email: Optional[str] = None,
        action: Optional[str] = None,
        request_id: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> List[AuditLog]:
        session = self._get_session()
        try:
            query = session.query(AuditLogModel)
            if user_id:
                query = query.filter(AuditLogModel.user_id == user_id)
            if user_email:
                normalized = user_email.strip()
                if normalized:
                    query = query.filter(AuditLogModel.user_email.ilike(f"%{normalized}%"))
            if action:
                normalized_action = action.strip()
                if normalized_action:
                    query = query.filter(AuditLogModel.action.ilike(f"%{normalized_action}%"))
            if request_id:
                normalized_request = request_id.strip()
                if normalized_request:
                    query = query.filter(AuditLogModel.request_id.ilike(f"%{normalized_request}%"))
            if since:
                query = query.filter(AuditLogModel.created_at >= since)
            models = query.order_by(AuditLogModel.created_at.desc()).limit(limit).all()
            return [self._model_to_audit_log(model) for model in models]
        finally:
            session.close()

    # =============== MÉTODOS DE REFRESH TOKEN (SESSÕES) ===============

    def create_refresh_session(
        self,
        jti_hash: str,
        user_email: str,
        family_id: str,
        expires_at: datetime,
    ) -> None:
        """Registra uma nova sessão de refresh token."""
        session = self._get_session()
        try:
            session.add(
                RefreshTokenModel(
                    jti_hash=jti_hash,
                    user_email=user_email,
                    family_id=family_id,
                    expires_at=expires_at,
                    created_at=datetime.utcnow(),
                )
            )
            session.commit()
        finally:
            session.close()

    def get_refresh_session(self, jti_hash: str) -> Optional[dict]:
        """Busca uma sessão de refresh token pelo hash do jti."""
        session = self._get_session()
        try:
            model = session.query(RefreshTokenModel).filter(
                RefreshTokenModel.jti_hash == jti_hash
            ).first()
            if model is None:
                return None
            return {
                "jti_hash": model.jti_hash,
                "user_email": model.user_email,
                "family_id": model.family_id,
                "expires_at": model.expires_at,
                "created_at": model.created_at,
                "revoked_at": model.revoked_at,
                "replaced_by_jti_hash": model.replaced_by_jti_hash,
            }
        finally:
            session.close()

    def rotate_refresh_session(
        self,
        old_jti_hash: str,
        new_jti_hash: str,
        user_email: str,
        family_id: str,
        expires_at: datetime,
    ) -> bool:
        """Rotaciona uma sessão de refresh token de forma atômica.

        Revoga a sessão antiga e cria a nova na mesma família em uma única
        transação. Retorna False se a sessão antiga já estava revogada ou não
        existe (o UPDATE condicional impede uso duplo em corrida).
        """
        session = self._get_session()
        try:
            rows = session.query(RefreshTokenModel).filter(
                RefreshTokenModel.jti_hash == old_jti_hash,
                RefreshTokenModel.revoked_at.is_(None),
            ).update(
                {
                    "revoked_at": datetime.utcnow(),
                    "replaced_by_jti_hash": new_jti_hash,
                },
                synchronize_session=False,
            )
            if rows != 1:
                session.rollback()
                return False
            session.add(
                RefreshTokenModel(
                    jti_hash=new_jti_hash,
                    user_email=user_email,
                    family_id=family_id,
                    expires_at=expires_at,
                    created_at=datetime.utcnow(),
                )
            )
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def revoke_refresh_family(self, family_id: str) -> int:
        """Revoga todas as sessões ativas de uma família de rotação."""
        session = self._get_session()
        try:
            rows = session.query(RefreshTokenModel).filter(
                RefreshTokenModel.family_id == family_id,
                RefreshTokenModel.revoked_at.is_(None),
            ).update({"revoked_at": datetime.utcnow()}, synchronize_session=False)
            session.commit()
            return rows
        finally:
            session.close()

    def purge_expired_refresh_sessions(self) -> int:
        """Remove sessões expiradas (housekeeping)."""
        session = self._get_session()
        try:
            rows = session.query(RefreshTokenModel).filter(
                RefreshTokenModel.expires_at < datetime.utcnow()
            ).delete(synchronize_session=False)
            session.commit()
            return rows
        finally:
            session.close()

    # =============== MÉTODOS DE JOBS (PROGRESSO ASSÍNCRONO) ===============

    def _model_to_job_dict(self, model: JobModel) -> dict:
        metadata = None
        result = None
        if model.metadata_json:
            try:
                metadata = json.loads(model.metadata_json)
            except Exception:
                metadata = None
        if model.result_json:
            try:
                result = json.loads(model.result_json)
            except Exception:
                result = None
        return {
            "job_id": model.id,
            "job_type": model.job_type,
            "status": model.status,
            "progress": model.progress,
            "current_step": model.current_step,
            "message": model.message,
            "created_at": model.created_at.isoformat() if model.created_at else None,
            "updated_at": model.updated_at.isoformat() if model.updated_at else None,
            "started_at": model.started_at.isoformat() if model.started_at else None,
            "completed_at": model.completed_at.isoformat() if model.completed_at else None,
            "result": result,
            "error": model.error,
            "metadata": metadata,
        }

    def create_job_record(self, job_id: str, job_type: str, metadata: Optional[dict] = None) -> dict:
        session = self._get_session()
        try:
            job_model = JobModel(
                id=job_id,
                job_type=job_type,
                status="pending",
                progress=0,
                current_step="pending",
                message="Job criado, aguardando processamento",
                metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata is not None else None,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(job_model)
            session.commit()
            session.refresh(job_model)
            return self._model_to_job_dict(job_model)
        finally:
            session.close()

    def update_job_record(
        self,
        job_id: str,
        status: Optional[str] = None,
        progress: Optional[int] = None,
        current_step: Optional[str] = None,
        message: Optional[str] = None,
        result: Optional[dict] = None,
        error: Optional[str] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        metadata: Optional[dict] = None,
    ) -> Optional[dict]:
        session = self._get_session()
        try:
            model = session.query(JobModel).filter(JobModel.id == job_id).first()
            if not model:
                return None
            if status is not None:
                model.status = status
            if progress is not None:
                model.progress = progress
            if current_step is not None:
                model.current_step = current_step
            if message is not None:
                model.message = message
            if result is not None:
                model.result_json = json.dumps(result, ensure_ascii=False)
            if error is not None:
                model.error = error
            if metadata is not None:
                model.metadata_json = json.dumps(metadata, ensure_ascii=False)
            if started_at is not None:
                model.started_at = started_at
            if completed_at is not None:
                model.completed_at = completed_at
            model.updated_at = datetime.utcnow()
            session.commit()
            session.refresh(model)
            return self._model_to_job_dict(model)
        finally:
            session.close()

    def get_job_record(self, job_id: str) -> Optional[dict]:
        session = self._get_session()
        try:
            model = session.query(JobModel).filter(JobModel.id == job_id).first()
            return self._model_to_job_dict(model) if model else None
        finally:
            session.close()

    def get_job_record_scoped(
        self,
        job_id: str,
        *,
        role: UserRole,
        user_id: Optional[str] = None,
        clinic_id: Optional[str] = None,
    ) -> Optional[dict]:
        job = self.get_job_record(job_id)
        if not job:
            return None
        metadata = job.get("metadata") if isinstance(job.get("metadata"), dict) else {}
        if role == UserRole.ADMIN:
            return job
        if role in (UserRole.SENDER, UserRole.MANAGER):
            if user_id and metadata.get("uploaded_by_user_id") == user_id:
                return job
            return None
        if role == UserRole.CHECKER:
            if clinic_id and metadata.get("clinic_id") == clinic_id:
                return job
            return None
        return None

    def list_job_records(self, status: Optional[str] = None, limit: int = 50) -> list[dict]:
        session = self._get_session()
        try:
            query = session.query(JobModel)
            if status:
                query = query.filter(JobModel.status == status)
            models = query.order_by(JobModel.created_at.desc()).limit(limit).all()
            return [self._model_to_job_dict(model) for model in models]
        finally:
            session.close()

    def list_stale_job_records(self, cutoff_time: datetime, limit: int = 100) -> list[dict]:
        """Lista jobs ativos (pending/in_progress) sem atualização desde `cutoff_time`.

        Usado pelo job_watchdog para detectar jobs órfãos que sobreviveram a
        restart de worker ou foram criados em outro processo.
        """
        session = self._get_session()
        try:
            query = (
                session.query(JobModel)
                .filter(JobModel.status.in_(["pending", "in_progress"]))
                .filter(JobModel.updated_at < cutoff_time)
                .order_by(JobModel.updated_at.asc())
                .limit(limit)
            )
            return [self._model_to_job_dict(model) for model in query.all()]
        finally:
            session.close()

    def list_job_records_scoped(
        self,
        *,
        role: UserRole,
        status: Optional[str] = None,
        limit: int = 50,
        user_id: Optional[str] = None,
        clinic_id: Optional[str] = None,
    ) -> list[dict]:
        records = self.list_job_records(status=status, limit=limit)
        if role == UserRole.ADMIN:
            return records
        filtered = []
        for job in records:
            metadata = job.get("metadata") if isinstance(job.get("metadata"), dict) else {}
            if role in (UserRole.SENDER, UserRole.MANAGER) and user_id and metadata.get("uploaded_by_user_id") == user_id:
                filtered.append(job)
            if role == UserRole.CHECKER and clinic_id and metadata.get("clinic_id") == clinic_id:
                filtered.append(job)
        return filtered

    def list_notifications(self, clinic_id: Optional[str] = None, user_id: Optional[str] = None, limit: int = 100, include_read: bool = True) -> List[Notification]:
        session = self._get_session()
        try:
            query = session.query(NotificationModel)
            if user_id:
                query = query.filter(NotificationModel.user_id == user_id)
            if clinic_id:
                query = query.filter(NotificationModel.clinic_id == clinic_id)
            if not include_read:
                query = query.filter(NotificationModel.read == False)
            models = query.order_by(NotificationModel.created_at.desc()).limit(limit).all()
            return [self._model_to_notification(m) for m in models]
        finally:
            session.close()

    def mark_notification_read(self, notification_id: str, user_id: Optional[str] = None) -> Optional[Notification]:
        session = self._get_session()
        try:
            query = session.query(NotificationModel).filter(NotificationModel.id == notification_id)
            if user_id:
                query = query.filter(NotificationModel.user_id == user_id)
            model = query.first()
            if not model:
                return None
            model.read = True
            session.commit()
            session.refresh(model)
            return self._model_to_notification(model)
        finally:
            session.close()

    def mark_all_notifications_read(self, clinic_id: Optional[str] = None, user_id: Optional[str] = None) -> int:
        session = self._get_session()
        try:
            query = session.query(NotificationModel)
            if user_id:
                query = query.filter(NotificationModel.user_id == user_id)
            if clinic_id:
                query = query.filter(NotificationModel.clinic_id == clinic_id)
            updated = query.update({NotificationModel.read: True})
            session.commit()
            return updated
        finally:
            session.close()

    def clear_notifications(self, clinic_id: Optional[str] = None, user_id: Optional[str] = None) -> int:
        session = self._get_session()
        try:
            query = session.query(NotificationModel)
            if user_id:
                query = query.filter(NotificationModel.user_id == user_id)
            if clinic_id:
                query = query.filter(NotificationModel.clinic_id == clinic_id)
            updated = query.update({NotificationModel.read: True})
            session.commit()
            return updated
        finally:
            session.close()

    def _ensure_default_admin(self):
        """Cria usuário admin padrão se banco estiver vazio."""
        session = self._get_session()
        try:
            count = session.query(UserModel).count()
            if count == 0:
                # Cria admin padrão
                admin = UserModel(
                    id="admin-default",
                    email="gabriel.rodrigues@grupobrmed.com.br",
                    name="Gabriel Rodrigues",
                    role=UserRole.ADMIN,
                    is_active=True,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                session.add(admin)
                session.commit()
                print("✅ Default admin created: gabriel.rodrigues@grupobrmed.com.br")
        finally:
            session.close()

    def _model_to_user(self, model: UserModel) -> User:
        """Converte modelo SQLAlchemy para Pydantic User."""
        return User(
            id=model.id,
            email=model.email,
            name=model.name,
            role=model.role,
            is_active=model.is_active,
            clinic_id=model.clinic_id,
            created_at=model.created_at.isoformat(),
            updated_at=model.updated_at.isoformat()
        )

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Busca usuário por email."""
        session = self._get_session()
        try:
            model = session.query(UserModel).filter(UserModel.email == email).first()
            return self._model_to_user(model) if model else None
        finally:
            session.close()

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Busca usuário por ID."""
        session = self._get_session()
        try:
            model = session.query(UserModel).filter(UserModel.id == user_id).first()
            return self._model_to_user(model) if model else None
        finally:
            session.close()

    def get_users_by_ids(self, user_ids: List[str]) -> List[User]:
        """Busca usuários por uma lista de IDs."""
        if not user_ids:
            return []
        session = self._get_session()
        try:
            models = session.query(UserModel).filter(UserModel.id.in_(user_ids)).all()
            return [self._model_to_user(m) for m in models]
        finally:
            session.close()

    def get_all_users(self) -> List[User]:
        """Obtém todos os usuários."""
        session = self._get_session()
        try:
            models = session.query(UserModel).all()
            return [self._model_to_user(m) for m in models]
        finally:
            session.close()

    def list_users(self, include_inactive: bool = False) -> List[User]:
        """Lista usuários com filtragem opcional."""
        session = self._get_session()
        try:
            query = session.query(UserModel)
            if not include_inactive:
                query = query.filter(UserModel.is_active == True)
            models = query.all()
            return [self._model_to_user(m) for m in models]
        finally:
            session.close()

    def create_user(self, email: str, name: str, role: UserRole = UserRole.CHECKER, clinic_id: Optional[str] = None) -> User:
        """Cria um novo usuário."""
        session = self._get_session()
        try:
            # Verifica se usuário já existe
            existing = session.query(UserModel).filter(UserModel.email == email).first()
            if existing:
                if existing.is_active:
                    raise ValueError(f"User with email {email} already exists")
                # Reativa usuário inativo
                existing.name = name
                existing.role = role
                existing.is_active = True
                existing.clinic_id = clinic_id
                existing.updated_at = datetime.utcnow()
                session.commit()
                session.refresh(existing)
                return self._model_to_user(existing)

            # Cria novo usuário
            import uuid
            user_model = UserModel(
                id=str(uuid.uuid4()),
                email=email,
                name=name,
                role=role,
                is_active=True,
                clinic_id=clinic_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            session.add(user_model)
            session.commit()
            session.refresh(user_model)

            return self._model_to_user(user_model)
        finally:
            session.close()

    def update_user(
        self,
        user_id: str,
        name: Optional[str] = None,
        role: Optional[UserRole] = None,
        is_active: Optional[bool] = None,
        clinic_id: Optional[str] = None
    ) -> User:
        """Atualiza usuário."""
        session = self._get_session()
        try:
            user_model = session.query(UserModel).filter(UserModel.id == user_id).first()
            if not user_model:
                raise ValueError(f"User {user_id} not found")

            # Atualiza campos
            if name is not None:
                user_model.name = name
            if role is not None:
                user_model.role = role
            if is_active is not None:
                user_model.is_active = is_active
            if clinic_id is not None:
                user_model.clinic_id = clinic_id

            user_model.updated_at = datetime.utcnow()

            session.commit()
            session.refresh(user_model)

            return self._model_to_user(user_model)
        finally:
            session.close()

    def delete_user(self, user_id: str) -> bool:
        """Exclusão suave do usuário (marca como inativo)."""
        session = self._get_session()
        try:
            user_model = session.query(UserModel).filter(UserModel.id == user_id).first()
            if not user_model:
                raise ValueError(f"User {user_id} not found")

            user_model.is_active = False
            user_model.updated_at = datetime.utcnow()
            session.commit()
            return True
        finally:
            session.close()

    # =============== MÉTODOS DE CLÍNICA ===============

    def _model_to_clinic(self, model: ClinicModel) -> Clinic:
        """Converte modelo SQLAlchemy para Pydantic Clinic."""
        return Clinic(
            id=model.id,
            name=model.name,
            cnpj=model.cnpj,
            phone=model.phone,
            address=model.address,
            city=model.city,
            state=model.state,
            is_active=model.is_active,
            created_at=model.created_at.isoformat(),
            updated_at=model.updated_at.isoformat()
        )

    def get_clinic_by_id(self, clinic_id: str) -> Optional[Clinic]:
        """Busca clínica por ID."""
        session = self._get_session()
        try:
            model = session.query(ClinicModel).filter(ClinicModel.id == clinic_id).first()
            return self._model_to_clinic(model) if model else None
        finally:
            session.close()

    def get_clinic_by_name(self, name: str) -> Optional[Clinic]:
        """Busca clínica por nome."""
        session = self._get_session()
        try:
            model = session.query(ClinicModel).filter(ClinicModel.name == name).first()
            return self._model_to_clinic(model) if model else None
        finally:
            session.close()

    def get_all_clinics(self, include_inactive: bool = False) -> List[Clinic]:
        """Obtém todas as clínicas."""
        session = self._get_session()
        try:
            query = session.query(ClinicModel)
            if not include_inactive:
                query = query.filter(ClinicModel.is_active == True)
            models = query.all()
            return [self._model_to_clinic(m) for m in models]
        finally:
            session.close()

    def create_clinic(
        self,
        name: str,
        cnpj: Optional[str] = None,
        phone: Optional[str] = None,
        address: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None
    ) -> Clinic:
        """Cria uma nova clínica."""
        session = self._get_session()
        try:
            # Cria nova clínica
            import uuid
            clinic_model = ClinicModel(
                id=str(uuid.uuid4()),
                name=name,
                cnpj=cnpj,
                phone=phone,
                address=address,
                city=city,
                state=state,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            session.add(clinic_model)
            session.commit()
            session.refresh(clinic_model)

            return self._model_to_clinic(clinic_model)
        finally:
            session.close()

    def update_clinic(
        self,
        clinic_id: str,
        name: Optional[str] = None,
        cnpj: Optional[str] = None,
        phone: Optional[str] = None,
        address: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> Clinic:
        """Atualiza clínica."""
        session = self._get_session()
        try:
            clinic_model = session.query(ClinicModel).filter(ClinicModel.id == clinic_id).first()
            if not clinic_model:
                raise ValueError(f"Clinic {clinic_id} not found")

            # Atualiza campos
            if name is not None:
                clinic_model.name = name
            if cnpj is not None:
                clinic_model.cnpj = cnpj
            if phone is not None:
                clinic_model.phone = phone
            if address is not None:
                clinic_model.address = address
            if city is not None:
                clinic_model.city = city
            if state is not None:
                clinic_model.state = state
            if is_active is not None:
                clinic_model.is_active = is_active

            clinic_model.updated_at = datetime.utcnow()

            session.commit()
            session.refresh(clinic_model)

            return self._model_to_clinic(clinic_model)
        finally:
            session.close()

    # =============== MÉTODOS DE DOCUMENTO ===============

    def _compact_payload_for_storage(self, payload: Optional[dict]) -> Optional[dict]:
        if not isinstance(payload, dict):
            return payload
        compact = dict(payload)
        ocr_result = compact.get("ocr_result")
        if isinstance(ocr_result, dict):
            ocr_result = dict(ocr_result)
            if "text" in ocr_result:
                ocr_result.pop("text", None)
            compact["ocr_result"] = ocr_result
        return compact

    def _model_to_document(
        self,
        model: DocumentModel,
        include_ocr_markdown: bool = True,
        use_compact_payload: bool = False,
    ) -> Document:
        """Converte modelo SQLAlchemy para Pydantic Document."""
        result_payload = None
        raw_payload = None
        if model:
            if use_compact_payload and getattr(model, "result_payload_compact", None):
                raw_payload = model.result_payload_compact
            elif not use_compact_payload:
                raw_payload = model.result_payload
            elif "result_payload" in model.__dict__:
                raw_payload = model.result_payload
        if raw_payload:
            try:
                import json
                result_payload = json.loads(raw_payload)
            except Exception:
                result_payload = None
        def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
            if not value:
                return None
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return Document(
            id=model.id,
            clinic_id=model.clinic_id,
            clinic_name=getattr(model, "clinic_name", None),
            uploaded_by_user_id=model.uploaded_by_user_id,
            uploaded_by_user_email=getattr(model, "uploaded_by_user_email", None),
            content_hash=getattr(model, "content_hash", None),
            file_path=getattr(model, "file_path", None),
            filename=model.filename,
            cpf=model.cpf,
            uploaded_at=_as_utc(model.uploaded_at),
            exams_found=model.exams_found,
            exams_ocr=getattr(model, "exams_ocr", None),
            exams_brnet=getattr(model, "exams_brnet", None),
            validation_status=model.validation_status,
            ocr_markdown=model.ocr_markdown if include_ocr_markdown else None,
            run_id=model.run_id,
            result_payload=result_payload,
            reviewed_by=getattr(model, "reviewed_by", None),
            reviewed_at=_as_utc(getattr(model, "reviewed_at", None)),
            approval_reason=getattr(model, "approval_reason", None),
            rejection_reason=getattr(model, "rejection_reason", None),
            confidence_score=model.confidence_score,
            quality_score=model.quality_score,
            mandatory_coverage=model.mandatory_coverage,
            created_at=_as_utc(model.created_at),
            updated_at=_as_utc(model.updated_at)
        )

    def get_document_by_id(self, document_id: str) -> Optional[Document]:
        """Busca documento por ID."""
        session = self._get_session()
        try:
            model = session.query(DocumentModel).filter(DocumentModel.id == document_id).first()
            return self._model_to_document(model) if model else None
        finally:
            session.close()

    def get_documents_by_clinic(self, clinic_id: str, use_compact_payload: bool = False) -> List[Document]:
        """Obtém todos os documentos de uma clínica específica."""
        session = self._get_session()
        try:
            t_query = time.perf_counter()
            query_options = [defer(DocumentModel.ocr_markdown)]
            if use_compact_payload:
                query_options.append(defer(DocumentModel.result_payload))
            models = (
                session.query(DocumentModel)
                .options(*query_options)
                .filter(DocumentModel.clinic_id == clinic_id)
                .all()
            )
            query_elapsed = time.perf_counter() - t_query
            t_map = time.perf_counter()
            docs = [
                self._model_to_document(
                    m,
                    include_ocr_markdown=False,
                    use_compact_payload=use_compact_payload,
                )
                for m in models
            ]
            map_elapsed = time.perf_counter() - t_map
            total_elapsed = query_elapsed + map_elapsed
            logger.info(
                "[DB] get_documents_by_clinic query=%.2fs map=%.2fs total=%.2fs rows=%d",
                query_elapsed,
                map_elapsed,
                total_elapsed,
                len(models),
            )
            return docs
        finally:
            session.close()

    def get_all_documents(self, use_compact_payload: bool = False) -> List[Document]:
        """Obtém todos os documentos (para CHECKER/ADMIN)."""
        session = self._get_session()
        try:
            t_query = time.perf_counter()
            query_options = [defer(DocumentModel.ocr_markdown)]
            if use_compact_payload:
                query_options.append(defer(DocumentModel.result_payload))
            models = (
                session.query(DocumentModel)
                .options(*query_options)
                .all()
            )
            query_elapsed = time.perf_counter() - t_query
            t_map = time.perf_counter()
            docs = [
                self._model_to_document(
                    m,
                    include_ocr_markdown=False,
                    use_compact_payload=use_compact_payload,
                )
                for m in models
            ]
            map_elapsed = time.perf_counter() - t_map
            total_elapsed = query_elapsed + map_elapsed
            logger.info(
                "[DB] get_all_documents query=%.2fs map=%.2fs total=%.2fs rows=%d",
                query_elapsed,
                map_elapsed,
                total_elapsed,
                len(models),
            )
            return docs
        finally:
            session.close()

    def list_documents_paged(
        self,
        *,
        role: UserRole,
        clinic_id: Optional[str],
        user_id: Optional[str] = None,
        queue: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        use_compact_payload: bool = True,
        search: Optional[str] = None,
        status_filter: Optional[str] = None,
        sort_by: str = "uploaded_at",
        sort_dir: str = "desc",
        filter_clinic_id: Optional[str] = None,
    ) -> dict:
        """
        Lista documentos paginados com escopo por role e filtros de fila.
        """
        session = self._get_session()
        try:
            query_options = [defer(DocumentModel.ocr_markdown)]
            if use_compact_payload:
                query_options.append(defer(DocumentModel.result_payload))

            base_query = session.query(DocumentModel).options(*query_options)

            if role in [UserRole.CHECKER, UserRole.ADMIN, UserRole.MANAGER]:
                scoped_query = base_query
            else:
                if not clinic_id:
                    raise ValueError("Usuário SENDER deve estar associado a uma clínica")
                scoped_query = base_query.filter(DocumentModel.clinic_id == clinic_id)
                if user_id:
                    scoped_query = scoped_query.filter(DocumentModel.uploaded_by_user_id == user_id)

            if filter_clinic_id:
                scoped_query = scoped_query.filter(DocumentModel.clinic_id == filter_clinic_id)

            normalized_search = (search or "").strip()
            if normalized_search:
                like = f"%{normalized_search}%"
                scoped_query = scoped_query.filter(
                    or_(
                        DocumentModel.cpf.ilike(like),
                        DocumentModel.filename.ilike(like),
                        DocumentModel.uploaded_by_user_email.ilike(like),
                        DocumentModel.patient_name.ilike(like),
                    )
                )

            if queue == "pendentes":
                scoped_query = scoped_query.filter(
                    or_(
                        DocumentModel.validation_status.is_(None),
                        DocumentModel.validation_status != "validated",
                    )
                )
            elif queue == "checagem":
                scoped_query = scoped_query.filter(
                    or_(
                        DocumentModel.validation_status == "validated",
                        DocumentModel.validation_status == "pending",
                        and_(
                            DocumentModel.validation_status == "rejected",
                            DocumentModel.reviewed_by.is_(None),
                        ),
                    )
                )

            if status_filter == "approved":
                scoped_query = scoped_query.filter(DocumentModel.validation_status == "validated")
            elif status_filter == "rejected":
                scoped_query = scoped_query.filter(DocumentModel.validation_status == "rejected")
            elif status_filter == "pending_review":
                scoped_query = scoped_query.filter(
                    or_(
                        DocumentModel.validation_status == "pending",
                        DocumentModel.validation_status.is_(None),
                    )
                )

            # Contagens para dashboard/status cards no frontend
            summary_query = session.query(
                func.count().label("total"),
                func.sum(
                    case((DocumentModel.validation_status == "validated", 1), else_=0)
                ).label("approved"),
                func.sum(
                    case((DocumentModel.validation_status == "rejected", 1), else_=0)
                ).label("rejected"),
                func.sum(
                    case(
                        (
                            or_(
                                DocumentModel.validation_status == "pending",
                                DocumentModel.validation_status.is_(None),
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("pending_review"),
            )

            if role in [UserRole.CHECKER, UserRole.ADMIN, UserRole.MANAGER]:
                scoped_summary_query = summary_query
            else:
                if not clinic_id:
                    raise ValueError("Usuário SENDER deve estar associado a uma clínica")
                scoped_summary_query = summary_query.filter(DocumentModel.clinic_id == clinic_id)
                if user_id:
                    scoped_summary_query = scoped_summary_query.filter(DocumentModel.uploaded_by_user_id == user_id)

            if filter_clinic_id:
                scoped_summary_query = scoped_summary_query.filter(DocumentModel.clinic_id == filter_clinic_id)

            if normalized_search:
                like = f"%{normalized_search}%"
                scoped_summary_query = scoped_summary_query.filter(
                    or_(
                        DocumentModel.cpf.ilike(like),
                        DocumentModel.filename.ilike(like),
                        DocumentModel.uploaded_by_user_email.ilike(like),
                        DocumentModel.patient_name.ilike(like),
                    )
                )

            summary_row = scoped_summary_query.one()
            summary_map = summary_row._mapping if hasattr(summary_row, "_mapping") else {}

            total_items = scoped_query.count()
            total_pages = max(1, (total_items + page_size - 1) // page_size) if page_size > 0 else 1
            safe_page = max(1, min(page, total_pages))

            sort_columns = {
                "uploaded_at": DocumentModel.uploaded_at,
                "updated_at": DocumentModel.updated_at,
                "filename": DocumentModel.filename,
                "cpf": DocumentModel.cpf,
                "status": DocumentModel.validation_status,
            }
            sort_column = sort_columns.get(sort_by, DocumentModel.uploaded_at)
            if sort_dir.lower() == "asc":
                scoped_query = scoped_query.order_by(sort_column.asc())
            else:
                scoped_query = scoped_query.order_by(sort_column.desc())

            if page_size > 0:
                scoped_query = scoped_query.offset((safe_page - 1) * page_size).limit(page_size)

            models = scoped_query.all()
            clinic_ids = sorted({m.clinic_id for m in models if m.clinic_id})
            clinic_names = {}
            if clinic_ids:
                clinic_names = dict(
                    session.query(ClinicModel.id, ClinicModel.name)
                    .filter(ClinicModel.id.in_(clinic_ids))
                    .all()
                )
            items = []
            for model in models:
                document = self._model_to_document(
                    model,
                    include_ocr_markdown=False,
                    use_compact_payload=use_compact_payload,
                )
                document.clinic_name = clinic_names.get(model.clinic_id)
                items.append(document)

            return {
                "items": items,
                "page": safe_page,
                "page_size": page_size,
                "total_items": total_items,
                "total_pages": total_pages,
                "has_next": safe_page < total_pages,
                "summary_counts": {
                    "approved": int(summary_map.get("approved", 0) or 0),
                    "rejected": int(summary_map.get("rejected", 0) or 0),
                    "pending_review": int(summary_map.get("pending_review", 0) or 0),
                    "total": int(summary_map.get("total", 0) or 0),
                },
            }
        finally:
            session.close()

    def create_document(
        self,
        clinic_id: str,
        uploaded_by_user_id: str,
        filename: str,
        file_path: Optional[str] = None,
        content_hash: Optional[str] = None,
        uploaded_by_user_email: Optional[str] = None,
        cpf: Optional[str] = None,
        exams_found: Optional[List[str]] = None,
        exams_ocr: Optional[List[str]] = None,
        exams_brnet: Optional[List[str]] = None,
        validation_status: str = "pending",
        ocr_markdown: Optional[str] = None,
        run_id: Optional[str] = None,
        result_payload: Optional[dict] = None,
        reviewed_by: Optional[str] = None,
        reviewed_at: Optional[datetime] = None,
        approval_reason: Optional[str] = None,
        rejection_reason: Optional[str] = None,
        confidence_score: Optional[float] = None,
        quality_score: Optional[float] = None,
        mandatory_coverage: Optional[float] = None
    ) -> Document:
        """Cria um novo documento."""
        session = self._get_session()
        try:
            import uuid
            import json
            compact_payload = self._compact_payload_for_storage(result_payload)
            payload_json = json.dumps(result_payload, ensure_ascii=False) if result_payload is not None else None
            compact_payload_json = json.dumps(compact_payload, ensure_ascii=False) if compact_payload is not None else None
            payload_reviewed_by = None
            payload_reviewed_at = None
            if isinstance(result_payload, dict):
                payload_reviewed_by = result_payload.get("reviewed_by") or result_payload.get("reviewedBy")
                payload_reviewed_at = result_payload.get("reviewed_at") or result_payload.get("reviewedAt")
            if not reviewed_by and payload_reviewed_by:
                reviewed_by = str(payload_reviewed_by)
            if reviewed_at is None and payload_reviewed_at:
                try:
                    reviewed_at = datetime.fromisoformat(str(payload_reviewed_at).replace("Z", "+00:00"))
                except Exception:
                    reviewed_at = None
            document_model = DocumentModel(
                id=str(uuid.uuid4()),
                clinic_id=clinic_id,
                uploaded_by_user_id=uploaded_by_user_id,
                uploaded_by_user_email=uploaded_by_user_email,
                content_hash=content_hash,
                filename=filename,
                file_path=file_path,
                cpf=cpf,
                patient_name=self._extract_patient_name(result_payload) or "",
                uploaded_at=datetime.utcnow(),
                exams_found=exams_found,
                exams_ocr=exams_ocr,
                exams_brnet=exams_brnet,
                validation_status=validation_status,
                ocr_markdown=ocr_markdown,
                run_id=run_id,
                result_payload=payload_json,
                result_payload_compact=compact_payload_json,
                reviewed_by=reviewed_by,
                reviewed_at=reviewed_at,
                approval_reason=approval_reason,
                rejection_reason=rejection_reason,
                confidence_score=confidence_score,
                quality_score=quality_score,
                mandatory_coverage=mandatory_coverage,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            session.add(document_model)
            session.commit()
            session.refresh(document_model)

            return self._model_to_document(document_model)
        finally:
            session.close()

    def update_document(
        self,
        document_id: str,
        validation_status: Optional[str] = None,
        exams_found: Optional[List[str]] = None,
        exams_ocr: Optional[List[str]] = None,
        exams_brnet: Optional[List[str]] = None,
        ocr_markdown: Optional[str] = None,
        run_id: Optional[str] = None,
        result_payload: Optional[dict] = None,
        reviewed_by: Optional[str] = None,
        reviewed_at: Optional[datetime] = None,
        approval_reason: Optional[str] = None,
        rejection_reason: Optional[str] = None,
        confidence_score: Optional[float] = None,
        quality_score: Optional[float] = None,
        mandatory_coverage: Optional[float] = None,
        file_path: Optional[str] = None,
        content_hash: Optional[str] = None,
        uploaded_by_user_email: Optional[str] = None,
        review_timing: Optional[dict] = None
    ) -> Document:
        """Atualiza documento.

        `review_timing` são os incrementos já sanitizados de
        `app/services/review_timing.py` — nunca o payload cru do cliente.
        """
        session = self._get_session()
        try:
            doc_model = session.query(DocumentModel).filter(DocumentModel.id == document_id).first()
            if not doc_model:
                raise ValueError(f"Document {document_id} not found")

            # Atualiza campos
            if validation_status is not None:
                doc_model.validation_status = validation_status
            if exams_found is not None:
                doc_model.exams_found = exams_found
            if exams_ocr is not None:
                doc_model.exams_ocr = exams_ocr
            if exams_brnet is not None:
                doc_model.exams_brnet = exams_brnet
            if ocr_markdown is not None:
                doc_model.ocr_markdown = ocr_markdown
            if run_id is not None:
                doc_model.run_id = run_id
            if file_path is not None:
                doc_model.file_path = file_path
            if content_hash is not None:
                doc_model.content_hash = content_hash
            if uploaded_by_user_email is not None:
                doc_model.uploaded_by_user_email = uploaded_by_user_email
            if result_payload is not None:
                import json
                doc_model.result_payload = json.dumps(result_payload, ensure_ascii=False)
                compact_payload = self._compact_payload_for_storage(result_payload)
                doc_model.result_payload_compact = json.dumps(compact_payload, ensure_ascii=False) if compact_payload is not None else None
                extracted_name = self._extract_patient_name(result_payload)
                if extracted_name:
                    doc_model.patient_name = extracted_name
                if reviewed_by is None and isinstance(result_payload, dict):
                    payload_reviewed_by = result_payload.get("reviewed_by") or result_payload.get("reviewedBy")
                    if payload_reviewed_by:
                        reviewed_by = str(payload_reviewed_by)
                if reviewed_at is None and isinstance(result_payload, dict):
                    payload_reviewed_at = result_payload.get("reviewed_at") or result_payload.get("reviewedAt")
                    if payload_reviewed_at:
                        try:
                            reviewed_at = datetime.fromisoformat(str(payload_reviewed_at).replace("Z", "+00:00"))
                        except Exception:
                            reviewed_at = None
            if reviewed_by is not None:
                doc_model.reviewed_by = reviewed_by
            if reviewed_at is not None:
                doc_model.reviewed_at = reviewed_at
            if approval_reason is not None:
                doc_model.approval_reason = approval_reason
            if rejection_reason is not None:
                doc_model.rejection_reason = rejection_reason
            if confidence_score is not None:
                doc_model.confidence_score = confidence_score
            if quality_score is not None:
                doc_model.quality_score = quality_score
            if mandatory_coverage is not None:
                doc_model.mandatory_coverage = mandatory_coverage

            if review_timing is not None:
                # Acumula em vez de sobrescrever: reabrir o documento (ou revisar
                # de novo depois) é trabalho adicional e precisa somar. Só o
                # review_opened_at é imutável — guarda a PRIMEIRA abertura, que é
                # o que fecha o tempo de fila contra o uploaded_at.
                # Os min() existem só para não estourar INTEGER/SMALLINT.
                if review_timing.get("started_at") is not None and doc_model.review_opened_at is None:
                    doc_model.review_opened_at = review_timing["started_at"]
                doc_model.review_active_ms = min(
                    2147483647, (doc_model.review_active_ms or 0) + review_timing["active_ms"]
                )
                doc_model.review_wall_ms = min(
                    2147483647, (doc_model.review_wall_ms or 0) + review_timing["wall_ms"]
                )
                doc_model.review_open_count = min(
                    32767, (doc_model.review_open_count or 0) + review_timing["open_count"]
                )

            doc_model.updated_at = datetime.utcnow()

            session.commit()
            session.refresh(doc_model)

            return self._model_to_document(doc_model)
        finally:
            session.close()

    def get_recent_document_by_hash(
        self,
        uploaded_by_user_id: str,
        content_hash: str,
        since: datetime,
        clinic_id: Optional[str] = None,
    ) -> Optional[Document]:
        session = self._get_session()
        try:
            query = (
                session.query(DocumentModel)
                .filter(DocumentModel.uploaded_by_user_id == uploaded_by_user_id)
                .filter(DocumentModel.content_hash == content_hash)
                .filter(DocumentModel.uploaded_at >= since)
            )
            if clinic_id:
                query = query.filter(DocumentModel.clinic_id == clinic_id)
            model = query.order_by(DocumentModel.uploaded_at.desc()).first()
            return self._model_to_document(model, include_ocr_markdown=False, use_compact_payload=True) if model else None
        finally:
            session.close()

    def get_document_by_hash(
        self,
        uploaded_by_user_id: str,
        content_hash: str,
        clinic_id: Optional[str] = None,
    ) -> Optional[Document]:
        session = self._get_session()
        try:
            query = (
                session.query(DocumentModel)
                .filter(DocumentModel.uploaded_by_user_id == uploaded_by_user_id)
                .filter(DocumentModel.content_hash == content_hash)
            )
            if clinic_id:
                query = query.filter(DocumentModel.clinic_id == clinic_id)
            model = query.order_by(DocumentModel.uploaded_at.desc()).first()
            return self._model_to_document(model, include_ocr_markdown=False, use_compact_payload=True) if model else None
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Catálogo de exames similares (exame pai + variações)
    #
    # `ValueError` aqui significa sempre colisão de nome no catálogo — o
    # router traduz para 409. Validação de formato fica nos schemas Pydantic.
    # ------------------------------------------------------------------

    @staticmethod
    def _model_to_exam_variation(model: ExamVariationModel) -> ExamVariation:
        return ExamVariation(
            id=model.id,
            parent_id=model.parent_id,
            name=model.name,
            name_normalized=model.name_normalized,
            is_active=model.is_active,
            source=model.source,
            occurrences=model.occurrences,
            has_embedding=model.embedding is not None,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _model_to_exam_parent(model: ExamParentModel, variation_count: int = 0) -> ExamParent:
        return ExamParent(
            id=model.id,
            name=model.name,
            name_normalized=model.name_normalized,
            status=model.status,
            is_external=model.is_external,
            is_active=model.is_active,
            source=model.source,
            notes=model.notes,
            has_embedding=model.embedding is not None,
            variation_count=variation_count,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _model_to_exam_conflict(model: ExamVariationConflictModel) -> ExamVariationConflict:
        return ExamVariationConflict(
            id=model.id,
            name=model.name,
            name_normalized=model.name_normalized,
            candidate_parents=list(model.candidate_parents or []),
            source=model.source,
            resolution=model.resolution,
            resolved_parent_id=model.resolved_parent_id,
            resolved_at=model.resolved_at,
            resolved_by=model.resolved_by,
            created_at=model.created_at,
        )

    def _assert_termo_livre(
        self,
        session: Session,
        normalizado: str,
        ignorar_parent_id: Optional[str] = None,
        ignorar_variation_id: Optional[str] = None,
    ) -> None:
        """
        Árvore estrita: um termo normalizado existe uma única vez no catálogo,
        seja como pai ou como variação. Levanta ValueError se já estiver em uso.
        """
        query = session.query(ExamParentModel).filter(
            ExamParentModel.name_normalized == normalizado
        )
        if ignorar_parent_id:
            query = query.filter(ExamParentModel.id != ignorar_parent_id)
        colidente = query.first()
        if colidente:
            raise ValueError(f"'{colidente.name}' já existe como exame pai no catálogo")

        query = session.query(ExamVariationModel).filter(
            ExamVariationModel.name_normalized == normalizado
        )
        if ignorar_variation_id:
            query = query.filter(ExamVariationModel.id != ignorar_variation_id)
        colidente = query.first()
        if colidente:
            pai = session.query(ExamParentModel).filter(
                ExamParentModel.id == colidente.parent_id
            ).first()
            nome_pai = pai.name if pai else "?"
            raise ValueError(
                f"'{colidente.name}' já é variação de '{nome_pai}'"
            )

    def list_exam_parents(
        self,
        search: Optional[str] = None,
        status: Optional[str] = None,
        include_inactive: bool = False,
        only_without_variations: bool = False,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[List[ExamParent], int]:
        """Lista exames pai com a contagem de variações. Retorna (itens, total)."""
        session = self._get_session()
        try:
            contagem = (
                session.query(
                    ExamVariationModel.parent_id.label("parent_id"),
                    func.count(ExamVariationModel.id).label("total"),
                )
                .group_by(ExamVariationModel.parent_id)
                .subquery()
            )

            query = session.query(
                ExamParentModel,
                func.coalesce(contagem.c.total, 0).label("variation_count"),
            ).outerjoin(contagem, contagem.c.parent_id == ExamParentModel.id)

            if not include_inactive:
                query = query.filter(ExamParentModel.is_active.is_(True))
            if status:
                query = query.filter(ExamParentModel.status == status)
            if only_without_variations:
                query = query.filter(func.coalesce(contagem.c.total, 0) == 0)
            if search:
                termo = f"%{normalizar_termo(search)}%"
                # Busca pelo nome normalizado do pai ou de qualquer variação dele.
                pais_por_variacao = (
                    session.query(ExamVariationModel.parent_id)
                    .filter(ExamVariationModel.name_normalized.like(termo))
                    .subquery()
                )
                query = query.filter(
                    or_(
                        ExamParentModel.name_normalized.like(termo),
                        ExamParentModel.id.in_(session.query(pais_por_variacao.c.parent_id)),
                    )
                )

            total = query.count()
            linhas = (
                query.order_by(ExamParentModel.name_normalized.asc())
                .limit(limit)
                .offset(offset)
                .all()
            )
            itens = [
                self._model_to_exam_parent(modelo, int(contagem_variacoes or 0))
                for modelo, contagem_variacoes in linhas
            ]
            return itens, total
        finally:
            session.close()

    def get_exam_parent(self, parent_id: str) -> Optional[ExamParentDetail]:
        """Exame pai com as variações carregadas."""
        session = self._get_session()
        try:
            modelo = session.query(ExamParentModel).filter(
                ExamParentModel.id == parent_id
            ).first()
            if not modelo:
                return None

            variacoes = (
                session.query(ExamVariationModel)
                .filter(ExamVariationModel.parent_id == parent_id)
                .order_by(ExamVariationModel.name_normalized.asc())
                .all()
            )
            base = self._model_to_exam_parent(modelo, len(variacoes))
            return ExamParentDetail(
                **base.model_dump(),
                variations=[self._model_to_exam_variation(v) for v in variacoes],
            )
        finally:
            session.close()

    def create_exam_parent(
        self,
        name: str,
        status: str = "quarentena",
        is_external: bool = False,
        notes: Optional[str] = None,
        variations: Optional[List[str]] = None,
        source: str = "manual",
        actor: Optional[str] = None,
    ) -> ExamParentDetail:
        """Cria exame pai e, opcionalmente, suas variações no mesmo passo."""
        import uuid

        nome_limpo = limpar_texto(name)
        normalizado = normalizar_termo(nome_limpo)
        if not normalizado:
            raise ValueError("Nome de exame inválido depois da normalização")

        session = self._get_session()
        try:
            self._assert_termo_livre(session, normalizado)

            agora = datetime.utcnow()
            parent_id = str(uuid.uuid4())
            session.add(
                ExamParentModel(
                    id=parent_id,
                    name=nome_limpo,
                    name_normalized=normalizado,
                    vector_id=derivar_vector_id(parent_id),
                    status=status,
                    is_external=is_external,
                    is_active=True,
                    source=source,
                    notes=notes,
                    created_at=agora,
                    created_by=actor,
                    updated_at=agora,
                    updated_by=actor,
                )
            )

            vistos = {normalizado}
            for variacao in variations or []:
                nome_var = limpar_texto(variacao)
                norm_var = normalizar_termo(nome_var)
                if not norm_var or norm_var in vistos:
                    continue
                self._assert_termo_livre(session, norm_var)
                vistos.add(norm_var)
                variation_id = str(uuid.uuid4())
                session.add(
                    ExamVariationModel(
                        id=variation_id,
                        parent_id=parent_id,
                        name=nome_var,
                        name_normalized=norm_var,
                        vector_id=derivar_vector_id(variation_id),
                        is_active=True,
                        source=source,
                        created_at=agora,
                        created_by=actor,
                        updated_at=agora,
                        updated_by=actor,
                    )
                )

            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

        return self.get_exam_parent(parent_id)

    def update_exam_parent(
        self,
        parent_id: str,
        name: Optional[str] = None,
        status: Optional[str] = None,
        is_external: Optional[bool] = None,
        is_active: Optional[bool] = None,
        notes: Optional[str] = None,
        actor: Optional[str] = None,
    ) -> Optional[ExamParentDetail]:
        """Atualiza exame pai. Campos None ficam como estão."""
        session = self._get_session()
        try:
            modelo = session.query(ExamParentModel).filter(
                ExamParentModel.id == parent_id
            ).first()
            if not modelo:
                return None

            if name is not None:
                nome_limpo = limpar_texto(name)
                normalizado = normalizar_termo(nome_limpo)
                if not normalizado:
                    raise ValueError("Nome de exame inválido depois da normalização")
                if normalizado != modelo.name_normalized:
                    self._assert_termo_livre(session, normalizado, ignorar_parent_id=parent_id)
                modelo.name = nome_limpo
                modelo.name_normalized = normalizado
            if status is not None:
                modelo.status = status
            if is_external is not None:
                modelo.is_external = is_external
            if is_active is not None:
                modelo.is_active = is_active
            if notes is not None:
                modelo.notes = notes

            modelo.updated_at = datetime.utcnow()
            modelo.updated_by = actor
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

        return self.get_exam_parent(parent_id)

    def delete_exam_parent(self, parent_id: str) -> bool:
        """Remove exame pai. As variações vão junto (ON DELETE CASCADE)."""
        session = self._get_session()
        try:
            modelo = session.query(ExamParentModel).filter(
                ExamParentModel.id == parent_id
            ).first()
            if not modelo:
                return False
            # O cascade está no schema, mas o delete via ORM não o dispara
            # sozinho sem relationship configurado — apaga explicitamente.
            session.query(ExamVariationModel).filter(
                ExamVariationModel.parent_id == parent_id
            ).delete(synchronize_session=False)
            session.delete(modelo)
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def create_exam_variation(
        self,
        parent_id: str,
        name: str,
        source: str = "manual",
        occurrences: Optional[int] = None,
        actor: Optional[str] = None,
    ) -> Optional[ExamVariation]:
        """Adiciona variação a um pai. None se o pai não existe."""
        import uuid

        nome_limpo = limpar_texto(name)
        normalizado = normalizar_termo(nome_limpo)
        if not normalizado:
            raise ValueError("Nome de variação inválido depois da normalização")

        session = self._get_session()
        try:
            pai = session.query(ExamParentModel).filter(
                ExamParentModel.id == parent_id
            ).first()
            if not pai:
                return None

            self._assert_termo_livre(session, normalizado)

            agora = datetime.utcnow()
            variation_id = str(uuid.uuid4())
            modelo = ExamVariationModel(
                id=variation_id,
                parent_id=parent_id,
                name=nome_limpo,
                name_normalized=normalizado,
                vector_id=derivar_vector_id(variation_id),
                is_active=True,
                source=source,
                occurrences=occurrences,
                created_at=agora,
                created_by=actor,
                updated_at=agora,
                updated_by=actor,
            )
            session.add(modelo)
            session.commit()
            session.refresh(modelo)
            return self._model_to_exam_variation(modelo)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update_exam_variation(
        self,
        variation_id: str,
        name: Optional[str] = None,
        parent_id: Optional[str] = None,
        is_active: Optional[bool] = None,
        actor: Optional[str] = None,
    ) -> Optional[ExamVariation]:
        """Atualiza variação. `parent_id` move a variação para outro pai."""
        session = self._get_session()
        try:
            modelo = session.query(ExamVariationModel).filter(
                ExamVariationModel.id == variation_id
            ).first()
            if not modelo:
                return None

            if name is not None:
                nome_limpo = limpar_texto(name)
                normalizado = normalizar_termo(nome_limpo)
                if not normalizado:
                    raise ValueError("Nome de variação inválido depois da normalização")
                if normalizado != modelo.name_normalized:
                    self._assert_termo_livre(
                        session, normalizado, ignorar_variation_id=variation_id
                    )
                modelo.name = nome_limpo
                modelo.name_normalized = normalizado

            if parent_id is not None and parent_id != modelo.parent_id:
                novo_pai = session.query(ExamParentModel).filter(
                    ExamParentModel.id == parent_id
                ).first()
                if not novo_pai:
                    raise ValueError("Exame pai de destino não encontrado")
                modelo.parent_id = parent_id

            if is_active is not None:
                modelo.is_active = is_active

            modelo.updated_at = datetime.utcnow()
            modelo.updated_by = actor
            session.commit()
            session.refresh(modelo)
            return self._model_to_exam_variation(modelo)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete_exam_variation(self, variation_id: str) -> bool:
        """Remove uma variação."""
        session = self._get_session()
        try:
            modelo = session.query(ExamVariationModel).filter(
                ExamVariationModel.id == variation_id
            ).first()
            if not modelo:
                return False
            session.delete(modelo)
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_exam_conflicts(
        self, pending_only: bool = True
    ) -> List[ExamVariationConflict]:
        """Conflitos de importação (mesmo termo sob mais de um pai)."""
        session = self._get_session()
        try:
            query = session.query(ExamVariationConflictModel)
            if pending_only:
                query = query.filter(ExamVariationConflictModel.resolution.is_(None))
            modelos = query.order_by(ExamVariationConflictModel.name_normalized.asc()).all()
            return [self._model_to_exam_conflict(m) for m in modelos]
        finally:
            session.close()

    def resolve_exam_conflict(
        self,
        conflict_id: str,
        resolution: str,
        parent_id: Optional[str] = None,
        actor: Optional[str] = None,
    ) -> Optional[ExamVariationConflict]:
        """
        Resolve um conflito. 'atribuida' cria a variação sob o pai escolhido;
        'descartada' apenas marca o conflito como decidido.
        """
        import uuid

        session = self._get_session()
        try:
            modelo = session.query(ExamVariationConflictModel).filter(
                ExamVariationConflictModel.id == conflict_id
            ).first()
            if not modelo:
                return None
            if modelo.resolution is not None:
                raise ValueError("Conflito já resolvido")

            if resolution == "atribuida":
                if not parent_id:
                    raise ValueError("parent_id é obrigatório para atribuir a variação")
                pai = session.query(ExamParentModel).filter(
                    ExamParentModel.id == parent_id
                ).first()
                if not pai:
                    raise ValueError("Exame pai de destino não encontrado")

                self._assert_termo_livre(session, modelo.name_normalized)

                agora = datetime.utcnow()
                variation_id = str(uuid.uuid4())
                session.add(
                    ExamVariationModel(
                        id=variation_id,
                        parent_id=parent_id,
                        name=modelo.name,
                        name_normalized=modelo.name_normalized,
                        vector_id=derivar_vector_id(variation_id),
                        is_active=True,
                        source="conflito_resolvido",
                        created_at=agora,
                        created_by=actor,
                        updated_at=agora,
                        updated_by=actor,
                    )
                )
                modelo.resolved_parent_id = parent_id

            modelo.resolution = resolution
            modelo.resolved_at = datetime.utcnow()
            modelo.resolved_by = actor
            session.commit()
            session.refresh(modelo)
            return self._model_to_exam_conflict(modelo)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_exam_catalog_stats(self) -> ExamCatalogStats:
        """Resumo do catálogo para o cabeçalho do painel."""
        session = self._get_session()
        try:
            pais_com_variacao = (
                session.query(ExamVariationModel.parent_id).distinct().subquery()
            )
            return ExamCatalogStats(
                parents_total=session.query(func.count(ExamParentModel.id)).scalar() or 0,
                parents_ativo=session.query(func.count(ExamParentModel.id))
                .filter(ExamParentModel.status == "ativo")
                .scalar()
                or 0,
                parents_quarentena=session.query(func.count(ExamParentModel.id))
                .filter(ExamParentModel.status == "quarentena")
                .scalar()
                or 0,
                parents_sem_variacao=session.query(func.count(ExamParentModel.id))
                .filter(
                    ~ExamParentModel.id.in_(
                        session.query(pais_com_variacao.c.parent_id)
                    )
                )
                .scalar()
                or 0,
                variations_total=session.query(func.count(ExamVariationModel.id)).scalar() or 0,
                conflicts_pending=session.query(func.count(ExamVariationConflictModel.id))
                .filter(ExamVariationConflictModel.resolution.is_(None))
                .scalar()
                or 0,
                brnet_without_parent=len(self.listar_exames_brnet_sem_pai(limit=10000)),
                terms_without_vector=sum(
                    session.query(func.count(modelo.id))
                    .filter(modelo.embedding.is_(None))
                    .filter(modelo.is_active.is_(True))
                    .scalar()
                    or 0
                    for modelo in (ExamParentModel, ExamVariationModel)
                ),
            )
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Vetores do catálogo
    #
    # O vetor mora na própria linha; o arquivo FAISS é artefato derivado,
    # reconstruído a partir daqui. Assim editar um exame custa uma chamada de
    # embedding, não o catálogo inteiro.
    # ------------------------------------------------------------------

    def salvar_embedding_exame(
        self,
        row_id: str,
        embedding: bytes,
        modelo: str,
        eh_variacao: bool = False,
    ) -> bool:
        """Grava o vetor na linha do pai ou da variação."""
        Modelo = ExamVariationModel if eh_variacao else ExamParentModel
        session = self._get_session()
        try:
            linha = session.query(Modelo).filter(Modelo.id == row_id).first()
            if not linha:
                return False
            linha.embedding = embedding
            linha.embedding_model = modelo
            linha.embedding_generated_at = datetime.utcnow()
            if linha.vector_id is None:
                linha.vector_id = derivar_vector_id(row_id)
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def listar_vetores_catalogo(self) -> List[tuple]:
        """
        Pares (vector_id, bytes) de todo termo ativo com vetor gravado.
        É a entrada da reconstrução do índice.
        """
        session = self._get_session()
        try:
            linhas = []
            for modelo in (ExamParentModel, ExamVariationModel):
                linhas.extend(
                    session.query(modelo.vector_id, modelo.embedding)
                    .filter(modelo.embedding.isnot(None))
                    .filter(modelo.vector_id.isnot(None))
                    .filter(modelo.is_active.is_(True))
                    .all()
                )
            return [(int(vid), bytes(bruto)) for vid, bruto in linhas]
        finally:
            session.close()

    def listar_termos_sem_vetor(self, limit: int = 1000) -> List[dict]:
        """
        Termos ativos ainda sem vetor.

        `embedding IS NULL` é o marcador de pendência — não existe tabela de
        fila. Serve para o painel mostrar o que falta e para uma reprocessagem
        pegar o que ficou atrás depois de uma falha da API.
        """
        session = self._get_session()
        try:
            pendentes: List[dict] = []
            for modelo, eh_variacao in ((ExamParentModel, False), (ExamVariationModel, True)):
                for linha in (
                    session.query(modelo)
                    .filter(modelo.embedding.is_(None))
                    .filter(modelo.is_active.is_(True))
                    .limit(limit)
                    .all()
                ):
                    pendentes.append({
                        "id": linha.id,
                        "name": linha.name,
                        "eh_variacao": eh_variacao,
                    })
            return pendentes[:limit]
        finally:
            session.close()

    def contar_termos_sem_vetor(self) -> int:
        session = self._get_session()
        try:
            total = 0
            for modelo in (ExamParentModel, ExamVariationModel):
                total += (
                    session.query(func.count(modelo.id))
                    .filter(modelo.embedding.is_(None))
                    .filter(modelo.is_active.is_(True))
                    .scalar()
                    or 0
                )
            return total
        finally:
            session.close()

    def listar_exames_brnet_sem_pai(self, limit: int = 200) -> List[ExamPendency]:
        """
        Exames que o BRNET pede e que não têm pai no catálogo.

        A normalização roda em **Python**, não em SQL: as reescritas de sigla de
        `normalizar_termo` (gama-GT → GGT, entre outras) não existem no banco, e
        reimplementá-las em SQL faria as duas divergirem em silêncio — foi o que
        aconteceu num rascunho, onde `ggt (gama-gt)` aparecia como órfão tendo pai.

        Ordena por número de documentos em que o BRNET pediu o exame, que é a
        exposição do problema. O impacto real (quantos faltantes o exame causou)
        exige parsear `result_payload` de todos os documentos — medido em ~3,8s,
        caro demais para carregar tela.
        """
        session = self._get_session()
        try:
            bruto = session.execute(
                text(
                    "SELECT btrim(e), count(*), count(DISTINCT d.id) "
                    "FROM documents d, unnest(d.exams_brnet) e "
                    "WHERE d.exams_brnet IS NOT NULL AND btrim(e) <> '' "
                    "GROUP BY 1"
                )
            ).all()

            agregado: dict[str, dict] = {}
            for nome, pedidos, docs in bruto:
                chave = normalizar_termo(nome)
                if not chave:
                    continue
                # Nomes distintos podem colapsar na mesma chave (acento, sigla).
                item = agregado.setdefault(
                    chave, {"name": nome, "requests": 0, "documents": 0}
                )
                item["requests"] += int(pedidos or 0)
                item["documents"] += int(docs or 0)

            pais = {
                chave
                for (chave,) in session.query(ExamParentModel.name_normalized).all()
            }

            pendencias = [
                ExamPendency(
                    name=item["name"],
                    name_normalized=chave,
                    documents=item["documents"],
                    requests=item["requests"],
                )
                for chave, item in agregado.items()
                if chave not in pais
            ]
            pendencias.sort(key=lambda p: (-p.documents, p.name))
            return pendencias[:limit]
        finally:
            session.close()

    def contar_exames_brnet_sem_pai(self) -> int:
        return len(self.listar_exames_brnet_sem_pai(limit=10000))
