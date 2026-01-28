"""
Implementação PostgreSQL do banco de dados de usuários.
Migração futura do JSON file-based database.
"""
import os
import time
import logging
from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, String, Boolean, DateTime, Enum as SQLEnum, ForeignKey, Text, ARRAY, Float, Integer, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship, defer
from app.models.user import User, UserCreate, UserUpdate, UserRole
from app.models.clinic import Clinic, ClinicCreate, ClinicUpdate
from app.models.document import Document, DocumentCreate, DocumentUpdate
from app.models.notification import Notification, NotificationCreate, NotificationUpdate
from app.models.audit_log import AuditLog, AuditLogCreate

Base = declarative_base()
logger = logging.getLogger(__name__)

class ClinicModel(Base):
    """Modelo SQLAlchemy para tabela Clinic."""
    __tablename__ = "clinics"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    cnpj = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    address = Column(String, nullable=True)
    city = Column(String, nullable=True)
    state = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserModel(Base):
    """Modelo SQLAlchemy para tabela User."""
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    role = Column(SQLEnum(UserRole), nullable=False, default=UserRole.CHECKER)
    is_active = Column(Boolean, nullable=False, default=True)
    clinic_id = Column(String, ForeignKey('clinics.id'), nullable=True)  # NULL para CHECKER/ADMIN
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class DocumentModel(Base):
    """Modelo SQLAlchemy para tabela Document."""
    __tablename__ = "documents"

    id = Column(String, primary_key=True)
    clinic_id = Column(String, ForeignKey('clinics.id'), nullable=False)
    uploaded_by_user_id = Column(String, ForeignKey('users.id'), nullable=False)
    filename = Column(String, nullable=False)
    cpf = Column(String, nullable=True)
    uploaded_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    exams_found = Column(ARRAY(String), nullable=True)  # Array de strings
    exams_ocr = Column(ARRAY(String), nullable=True)
    exams_brnet = Column(ARRAY(String), nullable=True)
    validation_status = Column(String, nullable=False, default='pending')
    ocr_markdown = Column(Text, nullable=True)
    run_id = Column(String, nullable=True)
    result_payload = Column(Text, nullable=True)
    result_payload_compact = Column(Text, nullable=True)
    confidence_score = Column(Float, nullable=True)
    quality_score = Column(Float, nullable=True)
    mandatory_coverage = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

class NotificationModel(Base):
    """Modelo SQLAlchemy para tabela Notification."""
    __tablename__ = "notifications"

    id = Column(String, primary_key=True)
    clinic_id = Column(String, ForeignKey('clinics.id'), nullable=True)
    document_id = Column(String, ForeignKey('documents.id'), nullable=True)
    type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    variant = Column(String, nullable=True)
    action_url = Column(String, nullable=True)
    action_label = Column(String, nullable=True)
    metadata_json = Column(Text, nullable=True)
    read = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

class AuditLogModel(Base):
    """Modelo SQLAlchemy para tabela AuditLog."""
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=True)
    user_email = Column(String, nullable=True, index=True)
    user_role = Column(String, nullable=True)
    action = Column(String, nullable=False)
    resource = Column(String, nullable=True)
    resource_id = Column(String, nullable=True)
    method = Column(String, nullable=True)
    path = Column(String, nullable=True)
    status_code = Column(Integer, nullable=True)
    ip = Column(String, nullable=True)
    user_agent = Column(Text, nullable=True)
    request_id = Column(String, nullable=True, index=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


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

        # Neon usa postgresql:// mas SQLAlchemy 2.0 requer postgresql+psycopg2://
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

        # Cria tabelas se não existirem
        Base.metadata.create_all(self.engine)
        self._ensure_document_columns()
        self._ensure_notification_columns()
        self._ensure_audit_log_table()

        # Cria admin padrão se banco estiver vazio
        self._ensure_default_admin()

    def _get_session(self) -> Session:
        """Obtém uma nova sessão do banco de dados."""
        return self.SessionLocal()

    def _ensure_document_columns(self) -> None:
        """Garante que colunas novas existam para documentos."""
        with self.engine.begin() as connection:
            connection.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS run_id VARCHAR"))
            connection.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS result_payload TEXT"))
            connection.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS result_payload_compact TEXT"))
            connection.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS confidence_score DOUBLE PRECISION"))
            connection.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS quality_score DOUBLE PRECISION"))
            connection.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS mandatory_coverage DOUBLE PRECISION"))
            connection.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS exams_ocr TEXT[]"))
            connection.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS exams_brnet TEXT[]"))

    def _ensure_notification_columns(self) -> None:
        """Garante que colunas novas existam para notificações."""
        with self.engine.begin() as connection:
            connection.execute(text("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS metadata_json TEXT"))

    def _ensure_audit_log_table(self) -> None:
        """Garante índices úteis para auditoria."""
        with self.engine.begin() as connection:
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_audit_logs_user_email ON audit_logs(user_email)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_audit_logs_request_id ON audit_logs(request_id)"))

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

    def list_notifications(self, clinic_id: Optional[str] = None, limit: int = 100, include_read: bool = True) -> List[Notification]:
        session = self._get_session()
        try:
            query = session.query(NotificationModel)
            if clinic_id:
                query = query.filter(NotificationModel.clinic_id == clinic_id)
            if not include_read:
                query = query.filter(NotificationModel.read == False)
            models = query.order_by(NotificationModel.created_at.desc()).limit(limit).all()
            return [self._model_to_notification(m) for m in models]
        finally:
            session.close()

    def mark_notification_read(self, notification_id: str) -> Optional[Notification]:
        session = self._get_session()
        try:
            model = session.query(NotificationModel).filter(NotificationModel.id == notification_id).first()
            if not model:
                return None
            model.read = True
            session.commit()
            session.refresh(model)
            return self._model_to_notification(model)
        finally:
            session.close()

    def mark_all_notifications_read(self, clinic_id: Optional[str] = None) -> int:
        session = self._get_session()
        try:
            query = session.query(NotificationModel)
            if clinic_id:
                query = query.filter(NotificationModel.clinic_id == clinic_id)
            updated = query.update({NotificationModel.read: True})
            session.commit()
            return updated
        finally:
            session.close()

    def clear_notifications(self, clinic_id: Optional[str] = None) -> int:
        session = self._get_session()
        try:
            query = session.query(NotificationModel)
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
                raise ValueError(f"User with email {email} already exists")

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
            uploaded_by_user_id=model.uploaded_by_user_id,
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

    def create_document(
        self,
        clinic_id: str,
        uploaded_by_user_id: str,
        filename: str,
        cpf: Optional[str] = None,
        exams_found: Optional[List[str]] = None,
        exams_ocr: Optional[List[str]] = None,
        exams_brnet: Optional[List[str]] = None,
        validation_status: str = "pending",
        ocr_markdown: Optional[str] = None,
        run_id: Optional[str] = None,
        result_payload: Optional[dict] = None,
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
            document_model = DocumentModel(
                id=str(uuid.uuid4()),
                clinic_id=clinic_id,
                uploaded_by_user_id=uploaded_by_user_id,
                filename=filename,
                cpf=cpf,
                uploaded_at=datetime.utcnow(),
                exams_found=exams_found,
                exams_ocr=exams_ocr,
                exams_brnet=exams_brnet,
                validation_status=validation_status,
                ocr_markdown=ocr_markdown,
                run_id=run_id,
                result_payload=payload_json,
                result_payload_compact=compact_payload_json,
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
        confidence_score: Optional[float] = None,
        quality_score: Optional[float] = None,
        mandatory_coverage: Optional[float] = None
    ) -> Document:
        """Atualiza documento."""
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
            if result_payload is not None:
                import json
                doc_model.result_payload = json.dumps(result_payload, ensure_ascii=False)
                compact_payload = self._compact_payload_for_storage(result_payload)
                doc_model.result_payload_compact = json.dumps(compact_payload, ensure_ascii=False) if compact_payload is not None else None
            if confidence_score is not None:
                doc_model.confidence_score = confidence_score
            if quality_score is not None:
                doc_model.quality_score = quality_score
            if mandatory_coverage is not None:
                doc_model.mandatory_coverage = mandatory_coverage

            doc_model.updated_at = datetime.utcnow()

            session.commit()
            session.refresh(doc_model)

            return self._model_to_document(doc_model)
        finally:
            session.close()
