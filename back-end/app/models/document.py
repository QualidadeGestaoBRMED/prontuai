from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class DocumentQueue(str, Enum):
    PENDENTES = "pendentes"
    CHECAGEM = "checagem"


class Document(BaseModel):
    """Modelo de documento processado no sistema"""
    id: Optional[str] = None
    clinic_id: str  # Chave estrangeira para Clinic
    clinic_name: Optional[str] = None
    uploaded_by_user_id: str  # Chave estrangeira para User
    uploaded_by_user_email: Optional[str] = None
    file_path: Optional[str] = Field(default=None, exclude=True)
    content_hash: Optional[str] = Field(default=None, exclude=True)
    filename: str
    cpf: Optional[str] = None  # CPF extraído do documento
    uploaded_at: Optional[datetime] = None
    exams_found: Optional[List[str]] = None  # Lista de exames encontrados
    exams_ocr: Optional[List[str]] = None  # Lista de exames recebidos do OCR
    exams_brnet: Optional[List[str]] = None  # Lista de exames obrigatórios do BRNET
    validation_status: Optional[str] = "pending"  # pending, validated, rejected
    ocr_markdown: Optional[str] = None  # Resultado do OCR em markdown
    run_id: Optional[str] = None
    result_payload: Optional[Dict[str, Any]] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    approval_reason: Optional[str] = None
    rejection_reason: Optional[str] = None
    confidence_score: Optional[float] = None
    quality_score: Optional[float] = None
    mandatory_coverage: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        fields = {"file_path": {"exclude": True}}
        json_schema_extra = {
            "example": {
                "clinic_id": "uuid-clinica",
                "uploaded_by_user_id": "uuid-usuario",
                "filename": "documento.pdf",
                "cpf": "12345678901",
                "exams_found": ["Hemograma", "Glicemia"],
                "exams_ocr": ["Hemograma", "Glicemia"],
                "exams_brnet": ["Hemograma", "Glicemia"],
                "validation_status": "pending",
                "run_id": "abc123",
            }
        }


class DocumentCreate(BaseModel):
    """Schema para criação de documento"""
    clinic_id: str
    uploaded_by_user_id: str
    filename: str
    cpf: Optional[str] = None
    exams_found: Optional[List[str]] = None
    exams_ocr: Optional[List[str]] = None
    exams_brnet: Optional[List[str]] = None
    validation_status: Optional[str] = "pending"
    ocr_markdown: Optional[str] = None
    run_id: Optional[str] = None
    result_payload: Optional[Dict[str, Any]] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    approval_reason: Optional[str] = None
    rejection_reason: Optional[str] = None
    confidence_score: Optional[float] = None
    quality_score: Optional[float] = None
    mandatory_coverage: Optional[float] = None
    content_hash: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "clinic_id": "uuid-clinica",
                "uploaded_by_user_id": "uuid-usuario",
                "filename": "documento.pdf",
                "cpf": "12345678901"
            }
        }


class ReviewTiming(BaseModel):
    """Cronometragem da tela de revisão, medida no cliente.

    As durações vêm de `performance.now()` (monotônico): imunes a skew e a
    ajuste de hora do relógio do cliente. `started_at` é relógio de parede e
    serve só para derivar o tempo de fila.

    Sem constraint nenhuma de propósito — todo limite fica em
    `app/services/review_timing.py`, que descarta em vez de levantar 422. Um
    número torto não pode impedir o revisor de decidir o documento.
    """
    started_at: Optional[datetime] = None
    active_ms: Optional[int] = None
    wall_ms: Optional[int] = None
    open_count: Optional[int] = None


class DocumentUpdate(BaseModel):
    """Schema para atualização de documento"""
    validation_status: Optional[str] = None
    exams_found: Optional[List[str]] = None
    exams_ocr: Optional[List[str]] = None
    exams_brnet: Optional[List[str]] = None
    ocr_markdown: Optional[str] = None
    run_id: Optional[str] = None
    result_payload: Optional[Dict[str, Any]] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    approval_reason: Optional[str] = None
    rejection_reason: Optional[str] = None
    confidence_score: Optional[float] = None
    quality_score: Optional[float] = None
    mandatory_coverage: Optional[float] = None
    content_hash: Optional[str] = None
    # Cronometragem da tela de revisão; só é gravada quando o PATCH é uma
    # decisão de verdade (ver update_document em app/api/v1/documents.py).
    review_timing: Optional[ReviewTiming] = None

    class Config:
        json_schema_extra = {
            "example": {
                "validation_status": "validated"
            }
        }


class DocumentSummaryCounts(BaseModel):
    approved: int = 0
    rejected: int = 0
    pending_review: int = 0
    total: int = 0


class PaginatedDocumentsResponse(BaseModel):
    items: List[Document]
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    summary_counts: DocumentSummaryCounts
