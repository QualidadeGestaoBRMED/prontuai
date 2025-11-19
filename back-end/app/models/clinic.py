from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class Clinic(BaseModel):
    """Modelo de clínica credenciada do sistema"""
    id: Optional[str] = None
    email: EmailStr
    name: str
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "email": "clinica@example.com",
                "name": "Clínica Exemplo",
                "is_active": True
            }
        }


class ClinicCreate(BaseModel):
    """Schema para criação de clínica"""
    email: EmailStr
    name: str

    class Config:
        json_schema_extra = {
            "example": {
                "email": "clinica@example.com",
                "name": "Clínica Exemplo"
            }
        }


class ClinicUpdate(BaseModel):
    """Schema para atualização de clínica"""
    name: Optional[str] = None
    is_active: Optional[bool] = None

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Novo Nome da Clínica",
                "is_active": True
            }
        }
