from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


def pedido_exame_id_do_payload(result_payload: Any) -> Optional[int]:
    """Número do pedido de exame no BRNET, lido do resultado do processamento.

    Vem em `brmed_result.pedido_exame_id`, número ou texto ("123"). A coluna
    `documents.pedido_exame_id` é derivada daqui, e a migration 015 segue a
    mesma regra para os documentos anteriores a ela.
    """
    if not isinstance(result_payload, dict):
        return None
    brmed = result_payload.get("brmed_result")
    valor = brmed.get("pedido_exame_id") if isinstance(brmed, dict) else None
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor if valor > 0 else None
    if isinstance(valor, str) and valor.strip().isdigit():
        return int(valor.strip())
    return None


class DocumentQueue(str, Enum):
    PENDENTES = "pendentes"
    CHECAGEM = "checagem"
    # Histórico não filtra nada: é a tela que mostra TODOS os documentos do
    # escopo do usuário. Existe como fila mesmo assim para a tela poder pedir
    # paginação sem precisar omitir o parâmetro — omitir significaria "sem
    # fila", que é o mesmo resultado mas não diz a intenção em log nem em trace.
    HISTORICO = "historico"


# Motivos de rejeição estruturados: o que a CLÍNICA precisa corrigir.
#
# Substituem o texto livre "Motivo da rejeição", que saiu do modal. Medido em
# 272 rejeições escritas à mão no banco de dev: 149 (55%) eram "falta X" — o
# revisor confirmando o faltante que a IA tinha apontado —, e o resto se
# divide entre exame que veio errado (carimbo, data, ilegível) e problema do
# documento (ASO, peça faltando, anexos separados). O texto continua em
# `rejection_reason`, composto pelo modal a partir destes códigos, porque é
# ele que a clínica lê e que vai para o PDF; os códigos existem para contar.
#
# Espelho de `CODIGOS_REJEICAO` em `front-end/types/feedback.ts` —
# `test_codigos_de_rejeicao_batem_com_os_do_front` compara os dois.
CODIGOS_REJEICAO_EXAME: frozenset[str] = frozenset({
    "EXAME_FALTANTE",
    "EXAME_OUTRA_DATA",
    "EXAME_ILEGIVEL",
    "EXAME_SEM_ASSINATURA",
})
CODIGOS_REJEICAO_DOCUMENTO: frozenset[str] = frozenset({
    "ASO_INCOMPLETO",
    "ASO_SEM_APTIDAO",
    "ASO_DADO_ERRADO",
    "ASO_SEM_REAPROVEITAMENTO",
    "PRONTUARIO_INCOMPLETO",
    "ANEXOS_SEPARADOS",
    "ENVIO_DUPLICADO",
    "PACIENTE_TROCADO",
    "DOC_ILEGIVEL",
})
CODIGOS_REJEICAO: frozenset[str] = CODIGOS_REJEICAO_EXAME | CODIGOS_REJEICAO_DOCUMENTO


class RejectionCode(BaseModel):
    """Um motivo de rejeição. Os de exame dizem qual; os de documento, não."""

    codigo: str
    exame: Optional[str] = Field(default=None, max_length=300)

    @field_validator("codigo")
    @classmethod
    def codigo_valido(cls, value: str) -> str:
        if value not in CODIGOS_REJEICAO:
            raise ValueError(f"Motivo de rejeição inválido: {value}")
        return value

    @field_validator("exame")
    @classmethod
    def exame_sem_espaco_solto(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def exame_conforme_o_codigo(self) -> "RejectionCode":
        # "Faltou" sem dizer o quê não serve para contar quais exames as
        # clínicas mais deixam de mandar — que é a razão de existir do código.
        if self.codigo in CODIGOS_REJEICAO_EXAME and not self.exame:
            raise ValueError(f"{self.codigo} precisa dizer o exame.")
        if self.codigo in CODIGOS_REJEICAO_DOCUMENTO and self.exame:
            raise ValueError(f"{self.codigo} é do documento inteiro e não leva exame.")
        return self


class Document(BaseModel):
    """Modelo de documento processado no sistema"""
    id: Optional[str] = None
    clinic_id: str  # Chave estrangeira para Clinic
    clinic_name: Optional[str] = None
    uploaded_by_user_id: str  # Chave estrangeira para User
    uploaded_by_user_email: Optional[str] = None
    file_path: Optional[str] = Field(default=None, exclude=True)
    content_hash: Optional[str] = Field(default=None, exclude=True)
    filename: str
    cpf: Optional[str] = None  # CPF extraído do documento
    uploaded_at: Optional[datetime] = None
    exams_found: Optional[List[str]] = None  # Lista de exames encontrados
    exams_ocr: Optional[List[str]] = None  # Lista de exames recebidos do OCR
    exams_brnet: Optional[List[str]] = None  # Lista de exames obrigatórios do BRNET
    validation_status: Optional[str] = "pending"  # pending, validated, rejected, reenvio
    ocr_markdown: Optional[str] = None  # Resultado do OCR em markdown
    run_id: Optional[str] = None
    result_payload: Optional[Dict[str, Any]] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    approval_reason: Optional[str] = None
    rejection_reason: Optional[str] = None
    rejection_codes: Optional[List[Dict[str, Any]]] = None
    confidence_score: Optional[float] = None
    quality_score: Optional[float] = None
    mandatory_coverage: Optional[float] = None
    # Preenchido quando o PDF foi movido para o arquivo morto e removido do
    # disco. Serve para a UI avisar que a recuperação é manual, em vez de
    # mostrar erro genérico.
    archived_at: Optional[datetime] = None
    # Reenvio de prontuário já liberado: id do documento liberado.
    reenvio_de: Optional[str] = None
    # Nome do arquivo como ele existe no armazenamento (e, portanto, no Drive):
    # "<uuid-do-upload>_<nome-sanitizado>.pdf". É o que Qualidade e Gestão
    # precisa para localizar o PDF no arquivo morto — o `id` do documento NÃO
    # serve, porque o prefixo do arquivo é o job_id gerado no upload, não ele.
    # Só o basename: o caminho completo continua fora da resposta (file_path
    # tem exclude=True) para não expor a árvore de diretórios do servidor.
    storage_filename: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        fields = {"file_path": {"exclude": True}}
        json_schema_extra = {
            "example": {
                "clinic_id": "uuid-clinica",
                "uploaded_by_user_id": "uuid-usuario",
                "filename": "documento.pdf",
                "cpf": "12345678901",
                "exams_found": ["Hemograma", "Glicemia"],
                "exams_ocr": ["Hemograma", "Glicemia"],
                "exams_brnet": ["Hemograma", "Glicemia"],
                "validation_status": "pending",
                "run_id": "abc123",
            }
        }


class DocumentCreate(BaseModel):
    """Schema para criação de documento"""
    clinic_id: str
    uploaded_by_user_id: str
    filename: str
    cpf: Optional[str] = None
    exams_found: Optional[List[str]] = None
    exams_ocr: Optional[List[str]] = None
    exams_brnet: Optional[List[str]] = None
    validation_status: Optional[str] = "pending"
    ocr_markdown: Optional[str] = None
    run_id: Optional[str] = None
    result_payload: Optional[Dict[str, Any]] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    approval_reason: Optional[str] = None
    rejection_reason: Optional[str] = None
    confidence_score: Optional[float] = None
    quality_score: Optional[float] = None
    mandatory_coverage: Optional[float] = None
    content_hash: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "clinic_id": "uuid-clinica",
                "uploaded_by_user_id": "uuid-usuario",
                "filename": "documento.pdf",
                "cpf": "12345678901"
            }
        }


class ReviewTiming(BaseModel):
    """Cronometragem da tela de revisão, medida no cliente.

    As durações vêm de `performance.now()` (monotônico): imunes a skew e a
    ajuste de hora do relógio do cliente. `started_at` é relógio de parede e
    serve só para derivar o tempo de fila.

    Sem constraint nenhuma de propósito — todo limite fica em
    `app/services/review_timing.py`, que descarta em vez de levantar 422. Um
    número torto não pode impedir o revisor de decidir o documento.
    """
    started_at: Optional[datetime] = None
    active_ms: Optional[int] = None
    wall_ms: Optional[int] = None
    open_count: Optional[int] = None


class DocumentUpdate(BaseModel):
    """Schema para atualização de documento"""
    validation_status: Optional[str] = None
    exams_found: Optional[List[str]] = None
    exams_ocr: Optional[List[str]] = None
    exams_brnet: Optional[List[str]] = None
    ocr_markdown: Optional[str] = None
    run_id: Optional[str] = None
    result_payload: Optional[Dict[str, Any]] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    approval_reason: Optional[str] = None
    rejection_reason: Optional[str] = None
    # Só é gravado quando o documento termina rejeitado (ver update_document em
    # app/api/v1/documents.py). O teto barra payload absurdo, não uso real.
    rejection_codes: Optional[List[RejectionCode]] = Field(default=None, max_length=200)
    confidence_score: Optional[float] = None
    quality_score: Optional[float] = None
    mandatory_coverage: Optional[float] = None
    content_hash: Optional[str] = None
    # Cronometragem da tela de revisão; só é gravada quando o PATCH é uma
    # decisão de verdade (ver update_document em app/api/v1/documents.py).
    review_timing: Optional[ReviewTiming] = None

    class Config:
        json_schema_extra = {
            "example": {
                "validation_status": "validated"
            }
        }


class DocumentSummaryCounts(BaseModel):
    approved: int = 0
    rejected: int = 0
    pending_review: int = 0
    total: int = 0


class PaginatedDocumentsResponse(BaseModel):
    items: List[Document]
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    summary_counts: DocumentSummaryCounts
