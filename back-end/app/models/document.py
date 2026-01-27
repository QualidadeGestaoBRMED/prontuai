from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class Document(BaseModel):
    """Modelo de documento processado no sistema"""
    id: Optional[str] = None
    clinic_id: str  # Chave estrangeira para Clinic
    uploaded_by_user_id: str  # Chave estrangeira para User
    uploaded_by_user_email: Optional[str] = None
    filename: str
    cpf: Optional[str] = None  # CPF extraído do documento
    uploaded_at: Optional[datetime] = None
    exams_found: Optional[List[str]] = None  # Lista de exames encontrados
    validation_status: Optional[str] = "pending"  # pending, validated, rejected
    ocr_markdown: Optional[str] = None  # Resultado do OCR em markdown
    run_id: Optional[str] = None
    result_payload: Optional[Dict[str, Any]] = None
    confidence_score: Optional[float] = None
    quality_score: Optional[float] = None
    mandatory_coverage: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "clinic_id": "uuid-clinica",
                "uploaded_by_user_id": "uuid-usuario",
                "filename": "documento.pdf",
                "cpf": "12345678901",
                "exams_found": ["Hemograma", "Glicemia"],
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
    validation_status: Optional[str] = "pending"
    ocr_markdown: Optional[str] = None
    run_id: Optional[str] = None
    result_payload: Optional[Dict[str, Any]] = None
    confidence_score: Optional[float] = None
    quality_score: Optional[float] = None
    mandatory_coverage: Optional[float] = None

    class Config:
        json_schema_extra = {
            "example": {
                "clinic_id": "uuid-clinica",
                "uploaded_by_user_id": "uuid-usuario",
                "filename": "documento.pdf",
                "cpf": "12345678901"
            }
        }


class DocumentUpdate(BaseModel):
    """Schema para atualização de documento"""
    validation_status: Optional[str] = None
    exams_found: Optional[List[str]] = None
    ocr_markdown: Optional[str] = None
    run_id: Optional[str] = None
    result_payload: Optional[Dict[str, Any]] = None
    confidence_score: Optional[float] = None
    quality_score: Optional[float] = None
    mandatory_coverage: Optional[float] = None

    class Config:
        json_schema_extra = {
            "example": {
                "validation_status": "validated"
            }
        }
