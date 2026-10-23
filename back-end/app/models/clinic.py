from pydantic import BaseModel, EmailStr
from typing import List, Optional
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
    # Identificador do credenciado no BRNET ("C25414"); None = sem vínculo.
    brnet_id: Optional[str] = None
    email: Optional[str] = None
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
    """Schema para criação de clínica.

    `brnet_id` é o credenciado escolhido na rede do BRNET. Sem ele, só ADMIN
    cadastra (contas internas, credenciado fora da rede).
    """
    name: str
    cnpj: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    brnet_id: Optional[str] = None
    # Vazio com credenciado escolhido = o e-mail dele na rede do BRNET.
    email: Optional[EmailStr] = None

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
    # Troca o credenciado vinculado. None = não mexe; para tirar o vínculo, use
    # `remover_vinculo_brnet` (só ADMIN).
    brnet_id: Optional[str] = None
    remover_vinculo_brnet: bool = False

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Novo Nome da Clínica",
                "phone": "(11) 91234-5678",
                "is_active": True
            }
        }


class ClinicaVinculada(BaseModel):
    id: str
    name: str
    is_active: bool


class CredenciadoBrnetOpcao(BaseModel):
    """Um credenciado da rede do BRNET, como opção do cadastro de clínica.

    `clinicas` são as clínicas do ProntuAI já vinculadas a ele. Enquanto o
    vínculo não é único (ver migration 014), a tela usa isso para avisar antes
    de criar mais uma clínica para o mesmo credenciado.
    """
    identificador: str
    nome: str
    cidade: Optional[str] = None
    uf: Optional[str] = None
    email: Optional[str] = None
    clinicas: List[ClinicaVinculada] = []
