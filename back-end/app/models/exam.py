"""
Contrato de API do catálogo de exames similares.

Modelo de dois níveis: um exame pai (nome canônico, o mesmo que o BRNET usa)
e N variações (os nomes alternativos que aparecem nos documentos).
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class ExamVariation(BaseModel):
    """Variação (sinônimo) de um exame pai."""
    id: Optional[str] = None
    parent_id: Optional[str] = None
    name: str
    name_normalized: Optional[str] = None
    is_active: bool = True
    source: Optional[str] = None
    # NULL = nunca medido nos documentos; nunca zero.
    occurrences: Optional[int] = None
    has_embedding: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ExamParent(BaseModel):
    """Exame pai (canônico) do catálogo."""
    id: Optional[str] = None
    name: str
    name_normalized: Optional[str] = None
    # 'ativo' = nome confirmado no BRNET; 'quarentena' = herdado do CSV.
    status: str = "quarentena"
    is_external: bool = False
    is_active: bool = True
    source: Optional[str] = None
    notes: Optional[str] = None
    has_embedding: bool = False
    variation_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ExamParentDetail(ExamParent):
    """Exame pai com as variações carregadas."""
    variations: List[ExamVariation] = Field(default_factory=list)


class ExamParentCreate(BaseModel):
    """Criação de exame pai."""
    name: str = Field(..., min_length=2, max_length=180)
    status: str = "quarentena"
    is_external: bool = False
    notes: Optional[str] = None
    # Variações opcionais já no cadastro, para não exigir dois passos.
    variations: List[str] = Field(default_factory=list)

    @field_validator("status")
    @classmethod
    def validar_status(cls, valor: str) -> str:
        if valor not in ("ativo", "quarentena"):
            raise ValueError("status deve ser 'ativo' ou 'quarentena'")
        return valor

    class Config:
        json_schema_extra = {
            "example": {
                "name": "TGP (ALT)",
                "status": "ativo",
                "is_external": False,
                "variations": ["transaminase pirúvica", "alanina aminotransferase"],
            }
        }


class ExamParentUpdate(BaseModel):
    """Atualização de exame pai. Campos ausentes ficam como estão."""
    name: Optional[str] = Field(None, min_length=2, max_length=180)
    status: Optional[str] = None
    is_external: Optional[bool] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validar_status(cls, valor: Optional[str]) -> Optional[str]:
        if valor is not None and valor not in ("ativo", "quarentena"):
            raise ValueError("status deve ser 'ativo' ou 'quarentena'")
        return valor


class ExamVariationCreate(BaseModel):
    """Criação de variação sob um pai."""
    name: str = Field(..., min_length=2, max_length=180)


class ExamVariationUpdate(BaseModel):
    """Atualização de variação. Permite mover a variação para outro pai."""
    name: Optional[str] = Field(None, min_length=2, max_length=180)
    parent_id: Optional[str] = None
    is_active: Optional[bool] = None


class ExamVariationConflict(BaseModel):
    """
    Termo que a importação viu sob mais de um pai e não soube atribuir.
    Espera decisão humana; nenhuma escolha automática é feita.
    """
    id: Optional[str] = None
    name: str
    name_normalized: Optional[str] = None
    candidate_parents: List[str] = Field(default_factory=list)
    source: Optional[str] = None
    resolution: Optional[str] = None
    resolved_parent_id: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    created_at: Optional[datetime] = None


class ExamConflictResolution(BaseModel):
    """
    Decisão sobre um conflito: atribuir a variação a um pai, ou descartar o
    termo. `parent_id` é obrigatório quando a resolução é 'atribuida'.
    """
    resolution: str
    parent_id: Optional[str] = None

    @field_validator("resolution")
    @classmethod
    def validar_resolucao(cls, valor: str) -> str:
        if valor not in ("atribuida", "descartada"):
            raise ValueError("resolution deve ser 'atribuida' ou 'descartada'")
        return valor


class ExamCatalogStats(BaseModel):
    """Resumo do catálogo, para o cabeçalho do painel."""
    parents_total: int = 0
    parents_ativo: int = 0
    parents_quarentena: int = 0
    parents_sem_variacao: int = 0
    variations_total: int = 0
    conflicts_pending: int = 0
    # `embedding IS NULL` é o marcador de pendência; não há tabela de fila.
    terms_without_vector: int = 0
