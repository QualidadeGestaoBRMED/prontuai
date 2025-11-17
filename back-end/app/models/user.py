from enum import Enum
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class UserRole(str, Enum):
    """Roles de usuários no sistema"""
    ADMIN = "ADMIN"      # Acesso total + gerenciar usuários
    CHECKER = "CHECKER"  # Apenas checagem de exames
    SENDER = "SENDER"    # Apenas enviar documentos (pendentes)


class User(BaseModel):
    """Modelo de usuário do sistema"""
    id: Optional[str] = None
    email: EmailStr
    name: str
    role: UserRole = UserRole.CHECKER
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "email": "usuario@grupobrmed.com.br",
                "name": "João Silva",
                "role": "CHECKER",
                "is_active": True
            }
        }


class UserCreate(BaseModel):
    """Schema para criação de usuário"""
    email: EmailStr
    name: str
    role: UserRole = UserRole.CHECKER

    class Config:
        json_schema_extra = {
            "example": {
                "email": "novo@grupobrmed.com.br",
                "name": "Novo Usuário",
                "role": "CHECKER"
            }
        }


class UserUpdate(BaseModel):
    """Schema para atualização de usuário"""
    name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None

    class Config:
        json_schema_extra = {
            "example": {
                "role": "ADMIN",
                "is_active": True
            }
        }


class UserInDB(User):
    """Usuário com informações adicionais do banco"""
    hashed_password: Optional[str] = None  # Para futuro, se implementar senha


class TokenData(BaseModel):
    """Dados decodificados do JWT token"""
    email: EmailStr
    role: UserRole
    name: str
