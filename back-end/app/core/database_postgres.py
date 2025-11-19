"""
PostgreSQL implementation of user database.
Migração futura do JSON file-based database.
"""
import os
from typing import List, Optional
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Boolean, DateTime, Enum as SQLEnum, ForeignKey, Text, ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from app.models.user import User, UserCreate, UserUpdate, UserRole
from app.models.clinic import Clinic, ClinicCreate, ClinicUpdate
from app.models.document import Document, DocumentCreate, DocumentUpdate

Base = declarative_base()

class ClinicModel(Base):
    """SQLAlchemy model for Clinic table."""
    __tablename__ = "clinics"

    id = Column(String, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserModel(Base):
    """SQLAlchemy model for User table."""
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
    """SQLAlchemy model for Document table."""
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
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class PostgresUserDatabase:
    """PostgreSQL-based user database implementation."""

    def __init__(self, database_url: Optional[str] = None):
        """
        Initialize PostgreSQL connection.

        Args:
            database_url: PostgreSQL connection string
                         Format: postgresql://user:password@host:port/dbname
        """
        self.database_url = database_url or os.getenv("DATABASE_URL")

        if not self.database_url:
            raise ValueError("DATABASE_URL not set")

        # Neon uses postgresql:// but SQLAlchemy 2.0 requires postgresql+psycopg2://
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

        # Create tables if they don't exist
        Base.metadata.create_all(self.engine)

        # Create default admin if database is empty
        self._ensure_default_admin()

    def _get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()

    def _ensure_default_admin(self):
        """Create default admin user if database is empty."""
        session = self._get_session()
        try:
            count = session.query(UserModel).count()
            if count == 0:
                # Create default admin
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
        """Convert SQLAlchemy model to Pydantic User."""
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
        """Get user by email."""
        session = self._get_session()
        try:
            model = session.query(UserModel).filter(UserModel.email == email).first()
            return self._model_to_user(model) if model else None
        finally:
            session.close()

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID."""
        session = self._get_session()
        try:
            model = session.query(UserModel).filter(UserModel.id == user_id).first()
            return self._model_to_user(model) if model else None
        finally:
            session.close()

    def get_all_users(self) -> List[User]:
        """Get all users."""
        session = self._get_session()
        try:
            models = session.query(UserModel).all()
            return [self._model_to_user(m) for m in models]
        finally:
            session.close()

    def list_users(self, include_inactive: bool = False) -> List[User]:
        """List users with optional filtering."""
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
        """Create a new user."""
        session = self._get_session()
        try:
            # Check if user already exists
            existing = session.query(UserModel).filter(UserModel.email == email).first()
            if existing:
                raise ValueError(f"User with email {email} already exists")

            # Create new user
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
        """Update user."""
        session = self._get_session()
        try:
            user_model = session.query(UserModel).filter(UserModel.id == user_id).first()
            if not user_model:
                raise ValueError(f"User {user_id} not found")

            # Update fields
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
        """Soft delete user (mark as inactive)."""
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

    # =============== CLINIC METHODS ===============

    def _model_to_clinic(self, model: ClinicModel) -> Clinic:
        """Convert SQLAlchemy model to Pydantic Clinic."""
        return Clinic(
            id=model.id,
            email=model.email,
            name=model.name,
            is_active=model.is_active,
            created_at=model.created_at.isoformat(),
            updated_at=model.updated_at.isoformat()
        )

    def get_clinic_by_id(self, clinic_id: str) -> Optional[Clinic]:
        """Get clinic by ID."""
        session = self._get_session()
        try:
            model = session.query(ClinicModel).filter(ClinicModel.id == clinic_id).first()
            return self._model_to_clinic(model) if model else None
        finally:
            session.close()

    def get_clinic_by_email(self, email: str) -> Optional[Clinic]:
        """Get clinic by email."""
        session = self._get_session()
        try:
            model = session.query(ClinicModel).filter(ClinicModel.email == email).first()
            return self._model_to_clinic(model) if model else None
        finally:
            session.close()

    def get_all_clinics(self, include_inactive: bool = False) -> List[Clinic]:
        """Get all clinics."""
        session = self._get_session()
        try:
            query = session.query(ClinicModel)
            if not include_inactive:
                query = query.filter(ClinicModel.is_active == True)
            models = query.all()
            return [self._model_to_clinic(m) for m in models]
        finally:
            session.close()

    def create_clinic(self, email: str, name: str) -> Clinic:
        """Create a new clinic."""
        session = self._get_session()
        try:
            # Check if clinic already exists
            existing = session.query(ClinicModel).filter(ClinicModel.email == email).first()
            if existing:
                raise ValueError(f"Clinic with email {email} already exists")

            # Create new clinic
            import uuid
            clinic_model = ClinicModel(
                id=str(uuid.uuid4()),
                email=email,
                name=name,
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
        is_active: Optional[bool] = None
    ) -> Clinic:
        """Update clinic."""
        session = self._get_session()
        try:
            clinic_model = session.query(ClinicModel).filter(ClinicModel.id == clinic_id).first()
            if not clinic_model:
                raise ValueError(f"Clinic {clinic_id} not found")

            # Update fields
            if name is not None:
                clinic_model.name = name
            if is_active is not None:
                clinic_model.is_active = is_active

            clinic_model.updated_at = datetime.utcnow()

            session.commit()
            session.refresh(clinic_model)

            return self._model_to_clinic(clinic_model)
        finally:
            session.close()

    # =============== DOCUMENT METHODS ===============

    def _model_to_document(self, model: DocumentModel) -> Document:
        """Convert SQLAlchemy model to Pydantic Document."""
        return Document(
            id=model.id,
            clinic_id=model.clinic_id,
            uploaded_by_user_id=model.uploaded_by_user_id,
            filename=model.filename,
            cpf=model.cpf,
            uploaded_at=model.uploaded_at.isoformat(),
            exams_found=model.exams_found,
            validation_status=model.validation_status,
            ocr_markdown=model.ocr_markdown,
            created_at=model.created_at.isoformat(),
            updated_at=model.updated_at.isoformat()
        )

    def get_document_by_id(self, document_id: str) -> Optional[Document]:
        """Get document by ID."""
        session = self._get_session()
        try:
            model = session.query(DocumentModel).filter(DocumentModel.id == document_id).first()
            return self._model_to_document(model) if model else None
        finally:
            session.close()

    def get_documents_by_clinic(self, clinic_id: str) -> List[Document]:
        """Get all documents for a specific clinic."""
        session = self._get_session()
        try:
            models = session.query(DocumentModel).filter(DocumentModel.clinic_id == clinic_id).all()
            return [self._model_to_document(m) for m in models]
        finally:
            session.close()

    def get_all_documents(self) -> List[Document]:
        """Get all documents (for CHECKER/ADMIN)."""
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
        ocr_markdown: Optional[str] = None
    ) -> Document:
        """Create a new document."""
        session = self._get_session()
        try:
            import uuid
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
        ocr_markdown: Optional[str] = None
    ) -> Document:
        """Update document."""
        session = self._get_session()
        try:
            doc_model = session.query(DocumentModel).filter(DocumentModel.id == document_id).first()
            if not doc_model:
                raise ValueError(f"Document {document_id} not found")

            # Update fields
            if validation_status is not None:
                doc_model.validation_status = validation_status
            if exams_found is not None:
                doc_model.exams_found = exams_found
            if ocr_markdown is not None:
                doc_model.ocr_markdown = ocr_markdown

            doc_model.updated_at = datetime.utcnow()

            session.commit()
            session.refresh(doc_model)

            return self._model_to_document(doc_model)
        finally:
            session.close()
