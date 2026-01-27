"""
Implementação PostgreSQL do banco de dados de usuários.
Migração futura do JSON file-based database.
"""
import os
from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, String, Boolean, DateTime, Enum as SQLEnum, ForeignKey, Text, ARRAY, Float, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from app.models.user import User, UserCreate, UserUpdate, UserRole
from app.models.clinic import Clinic, ClinicCreate, ClinicUpdate
from app.models.document import Document, DocumentCreate, DocumentUpdate
from app.models.notification import Notification, NotificationCreate, NotificationUpdate

Base = declarative_base()

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
    validation_status = Column(String, nullable=False, default='pending')
    ocr_markdown = Column(Text, nullable=True)
    run_id = Column(String, nullable=True)
    result_payload = Column(Text, nullable=True)
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
            connection.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS confidence_score DOUBLE PRECISION"))
            connection.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS quality_score DOUBLE PRECISION"))
            connection.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS mandatory_coverage DOUBLE PRECISION"))

    def _ensure_notification_columns(self) -> None:
        """Garante que colunas novas existam para notificações."""
        with self.engine.begin() as connection:
            connection.execute(text("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS metadata_json TEXT"))

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

    def _model_to_document(self, model: DocumentModel) -> Document:
        """Converte modelo SQLAlchemy para Pydantic Document."""
        result_payload = None
        if model and model.result_payload:
            try:
                import json
                result_payload = json.loads(model.result_payload)
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
            validation_status=model.validation_status,
            ocr_markdown=model.ocr_markdown,
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

    def get_documents_by_clinic(self, clinic_id: str) -> List[Document]:
        """Obtém todos os documentos de uma clínica específica."""
        session = self._get_session()
        try:
            models = session.query(DocumentModel).filter(DocumentModel.clinic_id == clinic_id).all()
            return [self._model_to_document(m) for m in models]
        finally:
            session.close()

    def get_all_documents(self) -> List[Document]:
        """Obtém todos os documentos (para CHECKER/ADMIN)."""
        session = self._get_session()
        try:
            models = session.query(DocumentModel).all()
            return [self._model_to_document(m) for m in models]
        finally:
            session.close()

    def create_document(
        self,
        clinic_id: str,
        uploaded_by_user_id: str,
        filename: str,
        cpf: Optional[str] = None,
        exams_found: Optional[List[str]] = None,
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
            payload_json = json.dumps(result_payload, ensure_ascii=False) if result_payload is not None else None
            document_model = DocumentModel(
                id=str(uuid.uuid4()),
                clinic_id=clinic_id,
                uploaded_by_user_id=uploaded_by_user_id,
                filename=filename,
                cpf=cpf,
                uploaded_at=datetime.utcnow(),
                exams_found=exams_found,
                validation_status=validation_status,
                ocr_markdown=ocr_markdown,
                run_id=run_id,
                result_payload=payload_json,
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
            if ocr_markdown is not None:
                doc_model.ocr_markdown = ocr_markdown
            if run_id is not None:
                doc_model.run_id = run_id
            if result_payload is not None:
                import json
                doc_model.result_payload = json.dumps(result_payload, ensure_ascii=False)
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
