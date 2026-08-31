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
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
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
    # Cronometragem da tela de revisão (migration 004). NULL = revisão sem
    # instrumentação, nunca zero — consulta de BI precisa filtrar.
    review_opened_at = Column(DateTime, nullable=True)
    review_active_ms = Column(Integer, nullable=True)
    review_wall_ms = Column(Integer, nullable=True)
    review_open_count = Column(SmallInteger, nullable=True)
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


class RefreshTokenModel(Base):
    """Sessão de refresh token (rotação de uso único com detecção de reuso).

    Armazena apenas o hash SHA-256 do `jti` — nunca o token em si. Tokens da
    mesma cadeia de rotação compartilham `family_id`; reuso de um jti já
    rotacionado revoga a família inteira.
    """
    __tablename__ = "refresh_tokens"

    jti_hash = Column(String, primary_key=True)
    user_email = Column(String, nullable=False, index=True)
    family_id = Column(String, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    revoked_at = Column(DateTime, nullable=True)
    replaced_by_jti_hash = Column(String, nullable=True)


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


class ExamParentModel(Base):
    """
    Exame pai (canônico) do catálogo de similaridade.

    O pai é o nome pelo qual o BRNET pede o exame: a comparação do motor é
    sempre BRNET → OCR, então um pai que não seja nome do BRNET nunca aparece
    do lado esquerdo de um match. Daí a coluna `status`:

    - `ativo`      — nome confirmado no BRNET, vale como canônico;
    - `quarentena` — herdado do CSV sem correspondência no BRNET. Não serve de
      canônico, mas o nome continua valendo como vocabulário (ele alarga o
      portão de extração do OCR), então não é descartado.

    `is_external` é o antigo sufixo "(externo)" promovido a flag — ver
    `app.core.exam_normalize.separar_marcador_externo`.

    As colunas de embedding ficam nulas nesta fase: o painel só cataloga. A
    geração de vetor e a reconstrução do índice FAISS entram na fase seguinte.
    """
    __tablename__ = "exam_parents"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    name_normalized = Column(String, nullable=False, unique=True, index=True)
    # Id int64 no índice FAISS, derivado da UUID. Ver migrations/006.
    vector_id = Column(BigInteger, nullable=True, unique=True)
    status = Column(String, nullable=False, default="quarentena")
    is_external = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    source = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    # Reservado para a fase de lógica: vetor de 3072 dims (text-embedding-3-large).
    embedding = Column(LargeBinary, nullable=True)
    embedding_model = Column(String, nullable=True)
    embedding_generated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_by = Column(String, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('ativo', 'quarentena')",
            name="ck_exam_parents_status",
        ),
    )


class ExamVariationModel(Base):
    """
    Variação (sinônimo) de um exame pai.

    Árvore estrita: `name_normalized` é único no catálogo inteiro, ou seja uma
    variação pertence a exatamente um pai. Quando o CSV de origem manda o mesmo
    termo para dois pais, a linha não entra — vai para
    `exam_variation_conflicts` e espera decisão humana no painel.

    `occurrences` guarda quantas vezes o termo foi visto nos documentos, para
    ordenar a curadoria. Nulo = nunca medido (não é zero).
    """
    __tablename__ = "exam_variations"

    id = Column(String, primary_key=True)
    parent_id = Column(String, ForeignKey("exam_parents.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    name_normalized = Column(String, nullable=False, unique=True, index=True)
    # Id int64 no índice FAISS, derivado da UUID. Ver migrations/006.
    vector_id = Column(BigInteger, nullable=True, unique=True)
    is_active = Column(Boolean, nullable=False, default=True)
    source = Column(String, nullable=True)
    occurrences = Column(Integer, nullable=True)
    embedding = Column(LargeBinary, nullable=True)
    embedding_model = Column(String, nullable=True)
    embedding_generated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_by = Column(String, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String, nullable=True)


class ExamVariationConflictModel(Base):
    """
    Variação que a importação não soube atribuir: o mesmo termo apareceu sob
    mais de um pai.

    Existe porque a alternativa era o importador escolher sozinho. São poucas
    e todas são pergunta de negócio ("chumbo sérico e chumbo sanguíneo são o
    mesmo exame?"), não defeito de dado — então param aqui e o painel pergunta.
    """
    __tablename__ = "exam_variation_conflicts"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    name_normalized = Column(String, nullable=False, index=True)
    candidate_parents = Column(ARRAY(String), nullable=False)
    source = Column(String, nullable=True)
    resolution = Column(String, nullable=True)
    resolved_parent_id = Column(String, ForeignKey("exam_parents.id", ondelete="SET NULL"), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("name_normalized", name="uq_exam_variation_conflicts_name"),
        CheckConstraint(
            "resolution IS NULL OR resolution IN ('atribuida', 'descartada')",
            name="ck_exam_variation_conflicts_resolution",
        ),
    )
