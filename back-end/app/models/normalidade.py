"""
Normalidade e alteração de exames: parâmetros lidos e leitura por documento.

A faixa de cada valor é a impressa pelo laboratório no laudo
(`app/services/normalidade_exames.py`). A tabela `faixas_normalidade` não é mais
consultada; continua no banco porque remover coluna ou tabela não é reversível.
"""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel

from app.models.localizacao import Localizacao

SituacaoParametro = Literal["normal", "acima", "abaixo", "alterado", "sem_resultado", "sem_referencia"]


class AjusteFaixa(BaseModel):
    """Linha da `faixas_normalidade`: o ajuste gravado de um parâmetro."""
    parametro: str
    minimo: Optional[float] = None
    maximo: Optional[float] = None
    atualizado_por_email: Optional[str] = None
    atualizado_por_nome: Optional[str] = None
    atualizado_em: datetime


class ParametroLeitura(BaseModel):
    """Um parâmetro como a tela de Normalidade mostra: o que o ProntuAI lê."""
    parametro: str
    nome: str
    unidade: str
    qualitativo: bool
    # Só nos qualitativos ("Não reagente").
    normal_texto: Optional[str] = None


class ParametroLido(BaseModel):
    chave: str
    nome: str
    unidade: str
    valor: Optional[float] = None
    # Como saiu no laudo ("8,9", "148.000", "Reagente 1/4").
    valor_texto: Optional[str] = None
    referencia: str
    situacao: SituacaoParametro
    # Onde o valor está no PDF (página e caixas do valor e do nome). None sem
    # valor lido ou em documento sem layout do OCR.
    localizacao: Optional[Localizacao] = None


class NormalidadeItem(BaseModel):
    """Um exame da Comparação Detalhada e os valores lidos dos seus parâmetros."""
    exame: str
    parametros: List[ParametroLido]


class NormalidadeDocumento(BaseModel):
    habilitada: bool
    itens: List[NormalidadeItem] = []
