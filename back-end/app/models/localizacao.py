"""
Onde um trecho do documento está no PDF: página e caixas, para a checagem rolar
até ele e destacá-lo. Coordenadas em fração da página (0 a 1, origem no canto
superior esquerdo), como o Textract as entrega.
"""
from typing import List

from pydantic import BaseModel


class Caixa(BaseModel):
    x: float
    y: float
    w: float
    h: float


class Localizacao(BaseModel):
    pagina: int
    caixas: List[Caixa]


class LocalizacaoExame(BaseModel):
    """Um exame da Comparação Detalhada e onde ele aparece."""
    # Mesmo texto do `exame` da tabela de comparação.
    exame: str
    # Na ordem em que a tela oferece: primeiro a que tem mais cara de laudo.
    ocorrencias: List[Localizacao]


class LocalizacaoCampo(BaseModel):
    """Um campo da Checklist de Campos (CPF, nome, data, CRM, assinatura) e as
    linhas que o comprovam — as mesmas que a checklist mostra como evidência."""
    campo: str
    ocorrencias: List[Localizacao]


class LinhaTexto(BaseModel):
    """Uma linha do texto lido pelo OCR e a caixa dela na página."""
    pagina: int
    texto: str
    x: float
    y: float
    w: float
    h: float
    # Faixa horizontal de cada palavra, na ordem do texto: [x, w]. Serve para
    # contornar só o termo buscado, e não a linha inteira.
    palavras: List[List[float]] = []


class TextoDocumento(BaseModel):
    # False quando o documento não tem posição gravada: a busca do visualizador
    # cai no texto do próprio PDF, quando ele tem.
    disponivel: bool
    linhas: List[LinhaTexto] = []


class LocalizacoesDocumento(BaseModel):
    # False quando o documento não tem posição gravada (lido antes de existir,
    # ou pelo OCR local): a tela segue sem o atalho.
    disponivel: bool
    exames: List[LocalizacaoExame] = []
    campos: List[LocalizacaoCampo] = []
