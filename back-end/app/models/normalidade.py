"""
Normalidade e alteração de exames: faixas de referência e leitura por documento.

A faixa de cada parâmetro tem um padrão no código
(`app/services/normalidade_exames.py`) e pode ser ajustada na tela de
Normalidade. O ajuste fica na tabela `faixas_normalidade`; sem ajuste, vale o
padrão.
"""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

SituacaoParametro = Literal["normal", "acima", "abaixo", "alterado", "sem_resultado"]


class AjusteFaixa(BaseModel):
    """Linha da `faixas_normalidade`: o ajuste gravado de um parâmetro."""
    parametro: str
    minimo: Optional[float] = None
    maximo: Optional[float] = None
    atualizado_por_email: Optional[str] = None
    atualizado_por_nome: Optional[str] = None
    atualizado_em: datetime


class FaixaInput(BaseModel):
    minimo: Optional[float] = Field(None, ge=0)
    maximo: Optional[float] = Field(None, ge=0)

    @model_validator(mode="after")
    def _limites(self) -> "FaixaInput":
        if self.minimo is None and self.maximo is None:
            raise ValueError("Informe o mínimo, o máximo ou os dois.")
        if self.minimo is not None and self.maximo is not None and self.minimo > self.maximo:
            raise ValueError("O mínimo não pode ser maior que o máximo.")
        return self


class Faixa(BaseModel):
    """Um parâmetro como a tela de Normalidade mostra: o padrão e o que vale."""
    parametro: str
    nome: str
    unidade: str
    qualitativo: bool
    # Só nos qualitativos ("Não reagente").
    normal_texto: Optional[str] = None
    padrao_minimo: Optional[float] = None
    padrao_maximo: Optional[float] = None
    minimo: Optional[float] = None
    maximo: Optional[float] = None
    referencia: str
    ajustada: bool = False
    atualizado_por_email: Optional[str] = None
    atualizado_por_nome: Optional[str] = None
    atualizado_em: Optional[datetime] = None


class ParametroLido(BaseModel):
    chave: str
    nome: str
    unidade: str
    valor: Optional[float] = None
    # Como saiu no laudo ("8,9", "148.000", "Reagente 1/4").
    valor_texto: Optional[str] = None
    referencia: str
    situacao: SituacaoParametro


class NormalidadeItem(BaseModel):
    """Um exame da Comparação Detalhada e os valores lidos dos seus parâmetros."""
    exame: str
    parametros: List[ParametroLido]


class NormalidadeDocumento(BaseModel):
    habilitada: bool
    itens: List[NormalidadeItem] = []
