"""
Modelos SQLAlchemy do ProntuAI.

Mantidos isolados para que a definição das tabelas seja lida sem precisar
abrir o arquivo de 1400+ linhas de operações em
`app.core.database_postgres`. A `Base` declarativa exportada daqui é a
única usada pelo `engine.create_all()` no startup.
"""
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.ext.declarative import declarative_base

from app.models.user import UserRole

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
    uploaded_by_user_email = Column(String, nullable=True, index=True)
    content_hash = Column(String, nullable=True, index=True)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=True)
    cpf = Column(String, nullable=True)
    # Extraído de result_payload.patient_name para permitir busca server-side
    patient_name = Column(String, nullable=True, index=True)
    uploaded_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    exams_found = Column(ARRAY(String), nullable=True)
    exams_ocr = Column(ARRAY(String), nullable=True)
    exams_brnet = Column(ARRAY(String), nullable=True)
    validation_status = Column(String, nullable=False, default='pending')
    ocr_markdown = Column(Text, nullable=True)
    run_id = Column(String, nullable=True)
    result_payload = Column(Text, nullable=True)
    result_payload_compact = Column(Text, nullable=True)
    reviewed_by = Column(String, nullable=True, index=True)
    reviewed_at = Column(DateTime, nullable=True)
    approval_reason = Column(Text, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    confidence_score = Column(Float, nullable=True)
    quality_score = Column(Float, nullable=True)
    mandatory_coverage = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class NotificationModel(Base):
    """Modelo SQLAlchemy para tabela Notification."""
    __tablename__ = "notifications"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=True, index=True)
    user_email = Column(String, nullable=True, index=True)
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


class JobModel(Base):
    """Modelo SQLAlchemy para tabela Job (progresso assíncrono)."""
    __tablename__ = "jobs"

    id = Column(String, primary_key=True)
    job_type = Column(String, nullable=False)
    status = Column(String, nullable=False)
    progress = Column(Integer, nullable=False, default=0)
    current_step = Column(String, nullable=True)
    message = Column(Text, nullable=True)
    result_json = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


class MaintenanceWindowModel(Base):
    """Janela operacional de manutenção da aplicação."""
    __tablename__ = "maintenance_windows"

    id = Column(String, primary_key=True)
    status = Column(String, nullable=False, default="scheduled", index=True)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    starts_at = Column(DateTime, nullable=False, index=True)
    ends_at = Column(DateTime, nullable=True)
    eta = Column(String, nullable=True)
    created_by = Column(String, nullable=True)
    created_by_email = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    activated_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
