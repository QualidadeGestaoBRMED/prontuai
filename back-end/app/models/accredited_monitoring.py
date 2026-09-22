"""
Schemas do monitoramento de credenciados (API BRNET
`GET /api/accrediteds/get-accredited-monitoring/`).

Cada item é um pedido de exame agendado num credenciado dentro do mês de
solicitação consultado. A API devolve tudo como string "de planilha" ("Sim"/"Não",
datas dd/mm/aaaa, "" para vazio); aqui os campos já saem tipados. O nome de cada
atributo é o da chave original, exceto onde indicado em `alias`.

Valores observados em set/2026 (6565 linhas), úteis para filtros — não são enum
porque a API pode passar a devolver outros:
- status_agendamento: "01. AUTOMÁTICO", "02. FORA HR COMERCIAL", "03. ATÉ 15MIN",
  "04. DE 16 A 30MIN", "05. DE 31MIN A 60MIN", "06. ACIMA DE 61MIN"
- status_expedicao_cliente: "Em dia", "Atrasado"
- status_expedicao_brmed: "Em dia", "Atrasado", "Pendente - <motivo[ / motivo]>"
- tipo_pedido_exame: "ADMISSIONAL", "PERIÓDICO", "DEMISSIONAL", "RETORNO AO TRABALHO",
  "MUDANÇA DE RISCOS OCUPACIONAIS", ...
"""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class CredenciadoRef(BaseModel):
    """Credenciado decomposto de "CIDADE - UF - NOME". A API não manda id nem CNPJ."""

    rotulo: str = Field(..., description="Texto original, ex.: 'RECIFE - PE - QUALIMETRA'")
    cidade: Optional[str] = None
    uf: Optional[str] = None
    nome: Optional[str] = None


class AtendimentoCredenciado(BaseModel):
    pedido_exame_id: int

    # Credenciado (clínica) e cliente
    credenciado: CredenciadoRef
    empresa: str = Field(..., description="Unidade do cliente, com CNPJ e CR embutidos no texto")
    grupo: str = Field(..., description="Grupo econômico do cliente")

    # Paciente — PII: nunca logar crua (ver app/core/pii.py)
    paciente: str = Field(..., repr=False)
    cpf_passaporte: str = Field(..., repr=False, description="11 dígitos quando CPF; senão passaporte")

    tipo_pedido_exame: str

    # Agendamento — sempre preenchido
    data_solicitacao: datetime
    data_confirmacao: datetime
    mes_agendamento: str = Field(..., description="Ex.: 'Set/2026'")
    status_agendamento: str
    usuario_agendamento: str
    confirmacao_automatica: bool
    tempo_resposta_minutos: int = Field(..., description="Da chave 'tempo_resposta' (HH:MM)")

    # Atendimento — tudo None enquanto o paciente não foi atendido
    data_atendimento: Optional[date] = None
    mes_atendimento: Optional[str] = None
    data_cadastro_atendimento: Optional[date] = None
    usuario_atendimento: Optional[str] = None
    prazo_liberacao: Optional[int] = Field(None, description="Dias")
    data_previsao: Optional[date] = Field(None, description="Previsão de liberação do resultado")
    utilizou_o_br_net: Optional[bool] = None
    status_expedicao_cliente: Optional[str] = None
    status_expedicao_brmed: Optional[str] = None

    # Expedição
    data_liberacao: Optional[date] = None
    usuario_expedicao: Optional[str] = None
    possui_anexo: bool

    # Pendências
    data_inclusao_exame_alterado: Optional[datetime] = None
    data_inclusao_exame_nao_realizado: Optional[datetime] = Field(
        None, description="Da chave 'data_inclusao_exame_não_realizado'"
    )
    data_inclusao_particularidade_nao_atendida: Optional[datetime] = Field(
        None, description="Da chave 'data_inclusao_particularidade_não_atendida'"
    )

    possui_observacao_cliente: bool
    observacoes_cliente: Optional[str] = Field(None, repr=False, description="Texto livre; pode conter PII")

    @property
    def atendido(self) -> bool:
        return self.data_atendimento is not None
