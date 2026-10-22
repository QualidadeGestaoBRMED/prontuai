"""
Status de abordagem de uma credenciada sem cadastro no ProntuAI.

Alimenta "Quem vale a pena incluir" no dashboard: o time marca em que pé está a
conversa com cada credenciada, e o Top 5/10/20 do simulador para de sugerir
quem já disse não.

A credenciada é identificada pelo rótulo do BRNET ("CIDADE - UF - NOME"): a
API de monitoramento não manda id nem CNPJ, e é o mesmo texto que o ranking
usa como chave. Se o BRNET renomear a credenciada, o status antigo fica órfão
e ela volta à lista como "Não abordada".

Credenciada sem linha na tabela é "Não abordada". Voltar uma credenciada para
esse status grava a linha mesmo assim, para a tela mostrar quem desfez e quando.
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

STATUS_ABORDAGEM = ("NAO_ABORDADA", "EM_CONTATO", "AGUARDANDO_RETORNO", "ACEITOU", "RECUSOU")
StatusAbordagem = Literal["NAO_ABORDADA", "EM_CONTATO", "AGUARDANDO_RETORNO", "ACEITOU", "RECUSOU"]

MOTIVO_MAX = 500


class AbordagemInput(BaseModel):
    credenciado: str = Field(..., min_length=1, max_length=300, description="Rótulo do BRNET")
    status: StatusAbordagem
    motivo: Optional[str] = Field(None, max_length=MOTIVO_MAX)

    @field_validator("credenciado")
    @classmethod
    def _sem_espaco_nas_pontas(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("credenciado vazio")
        return v

    @field_validator("motivo")
    @classmethod
    def _motivo_vazio_vira_none(cls, v: Optional[str]) -> Optional[str]:
        v = (v or "").strip()
        return v or None

    @model_validator(mode="after")
    def _motivo_so_na_recusa(self) -> "AbordagemInput":
        # Recusa sem motivo não ajuda a próxima pessoa que olhar a lista, e
        # motivo em outro status ficaria grudado depois que a conversa avançou.
        if self.status == "RECUSOU" and not self.motivo:
            raise ValueError("Informe o motivo da recusa.")
        if self.status != "RECUSOU":
            self.motivo = None
        return self


class Abordagem(BaseModel):
    credenciado: str
    status: StatusAbordagem
    motivo: Optional[str] = None
    atualizado_por_email: Optional[str] = None
    atualizado_por_nome: Optional[str] = None
    atualizado_em: datetime
