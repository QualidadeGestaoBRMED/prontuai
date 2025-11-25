from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class Clinic(BaseModel):
    """Modelo de clínica credenciada do sistema"""
    id: Optional[str] = None
    name: str
    cnpj: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Clínica Exemplo",
                "cnpj": "12.345.678/0001-90",
                "phone": "(11) 98765-4321",
                "address": "Rua Exemplo, 123",
                "city": "São Paulo",
                "state": "SP",
                "is_active": True
            }
        }


class ClinicCreate(BaseModel):
    """Schema para criação de clínica"""
    name: str
    cnpj: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Clínica Exemplo",
                "cnpj": "12.345.678/0001-90",
                "phone": "(11) 98765-4321"
            }
        }


class ClinicUpdate(BaseModel):
    """Schema para atualização de clínica"""
    name: Optional[str] = None
    cnpj: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    is_active: Optional[bool] = None

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Novo Nome da Clínica",
                "phone": "(11) 91234-5678",
                "is_active": True
            }
        }
