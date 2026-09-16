"""
Parecer humano sobre o acerto da IA em um documento.

Coletado no modal que abre ao fim da checagem e **sempre opcional**: nenhuma
rota deste módulo trava aprovação, rejeição ou download. É a diferença
deliberada em relação à Triagem BR NET, onde o download responde 409 enquanto
não houver parecer.

Quem responde é `require_checker` — CHECKER, ADMIN e MANAGER. CURATOR fica de
fora (acompanha a checagem sem decidir) e SENDER também: o parecer é sobre a
decisão de revisão, e quem envia o documento não a toma.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core import metrics
from app.core.auth import require_checker
from app.core.database import user_db
from app.core.logging import get_request_id
from app.models.audit_log import AuditLogCreate
from app.models.feedback import (
    STATUS_COM_DETALHES,
    DocumentFeedback,
    DocumentFeedbackInput,
)
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Feedback da Checagem"])


def _auditar(
    document_id: str,
    payload: DocumentFeedbackInput,
    anterior: Optional[DocumentFeedback],
    actor: User,
    request: Request,
) -> None:
    """
    Grava a trilha do parecer direto, sem passar pelo `set_audit_context()`.

    O motivo é chato mas decisivo: o middleware de auditoria é um
    `BaseHTTPMiddleware` do Starlette, que executa o handler em outro contexto —
    os contextvars escritos aqui não sobem de volta. Nenhuma `action` nomeada por
    handler chega à tabela (vale para `documents.py` e `exams.py` também); a
    linha do middleware sai sempre com o fallback `put:/v1/...` e `metadata`
    nula. Escrever direto é o mesmo caminho que `v1_brmed.py` usa para o
    `documents.processed`.

    Isso deixa DUAS linhas por PUT: a genérica do middleware e esta. É o preço
    de ter o antes/depois — e é o que permite descobrir que um parecer foi
    reescrito, já que a `document_feedbacks` guarda só a resposta corrente.

    `notes` fica de fora das duas pontas de propósito: é texto livre do revisor
    e pode conter nome ou CPF de paciente. O que entra é a forma da mudança, não
    o conteúdo digitado.
    """
    try:
        user_db.create_audit_log(
            AuditLogCreate(
                user_id=actor.id,
                user_email=actor.email,
                user_role=actor.role.value if hasattr(actor.role, "value") else str(actor.role),
                action="documents.feedback",
                resource="document_feedbacks",
                resource_id=document_id,
                method=request.method,
                path=request.url.path,
                status_code=200,
                ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
                request_id=get_request_id(),
                metadata={
                    "document_id": document_id,
                    "status": payload.status,
                    "issue_categories": payload.categorias(),
                    # Nome de exame não é PII — é o dado que dá valor à trilha.
                    "issue_items": [
                        {
                            "categoria": item.categoria,
                            "exame": item.exame,
                            "veredito_ia": item.veredito_ia,
                            "fora_da_lista": item.fora_da_lista,
                        }
                        for item in payload.issue_items
                    ],
                    "document_issues": payload.document_issues,
                    # Marca quantos caracteres o revisor escreveu sem guardar o
                    # que ele escreveu: distingue "descreveu" de "deixou vazio".
                    "notes_len": len(payload.notes or ""),
                    "reavaliacao": anterior is not None,
                    "status_anterior": anterior.status if anterior else None,
                    "categorias_anteriores": anterior.issue_categories if anterior else None,
                },
            )
        )
    except Exception as audit_error:
        # Auditoria não derruba o parecer: ele já está commitado neste ponto.
        logger.warning(
            "[FEEDBACK] Falha ao registrar auditoria de %s: %s", document_id, audit_error
        )


def _validar_payload(payload: DocumentFeedbackInput) -> None:
    """
    Coerência entre o parecer e os detalhes. Espelho de `_validar_review_payload`
    da Triagem BR NET — e da validação do modal, que é a mesma regra no cliente.

    O par categoria + descrição não é burocracia: um "a IA errou" sem o quê nem
    o porquê não serve para medir acurácia nem para corrigir o motor, que é a
    razão de o formulário existir.

    422 vai como literal, e não pela constante do `status`: o Starlette renomeou
    `HTTP_422_UNPROCESSABLE_ENTITY` para `..._CONTENT` e qualquer uma das duas
    quebra em metade das versões — o número não muda.
    """
    if payload.status not in STATUS_COM_DETALHES:
        if payload.tem_problema() or payload.notes:
            raise HTTPException(
                422,
                "Um parecer de acerto não pode vir com problema apontado.",
            )
        return
    if not payload.tem_problema():
        raise HTTPException(
            422,
            "Aponte o que a IA errou: em algum exame, ou no documento.",
        )
    if not payload.notes:
        raise HTTPException(
            422,
            "Descreva o que aconteceu com o resultado.",
        )


@router.get("/{document_id}/feedback", response_model=DocumentFeedback | None)
async def get_document_feedback(
    document_id: str,
    current_user: User = Depends(require_checker),
):
    """Parecer atual do documento, ou `null` quando nunca foi avaliado."""
    try:
        if not user_db.get_document_by_id(document_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento não encontrado")
        return user_db.get_document_feedback(document_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[FEEDBACK] Erro ao obter parecer de %s: %s", document_id, e)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Erro ao obter o parecer do documento"
        )


@router.put("/{document_id}/feedback", response_model=DocumentFeedback)
async def put_document_feedback(
    document_id: str,
    payload: DocumentFeedbackInput,
    request: Request,
    current_user: User = Depends(require_checker),
):
    """
    Cria ou substitui o parecer do documento.

    Exige que o documento já tenha uma decisão humana (`reviewed_by`): o parecer
    é sobre o quanto a IA acertou em comparação com o que o revisor concluiu, e
    antes da decisão não há com o que comparar. 409 nesse caso — o modal só abre
    depois da decisão, então na prática isso só pega chamada fora de ordem.
    """
    try:
        document = user_db.get_document_by_id(document_id)
        if not document:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento não encontrado")
        if not document.reviewed_by:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Só é possível avaliar um documento já revisado por uma pessoa.",
            )

        _validar_payload(payload)

        # Lido antes do upsert: é o "de" do antes/depois da auditoria.
        anterior = user_db.get_document_feedback(document_id)

        feedback = user_db.upsert_document_feedback(
            document_id=document_id,
            status=payload.status,
            # Derivada do `issue_items`, nunca vinda do cliente — ver
            # `DocumentFeedbackInput.categorias`.
            issue_categories=payload.categorias(),
            issue_items=[item.model_dump() for item in payload.issue_items],
            document_issues=payload.document_issues,
            notes=payload.notes,
            reviewed_by_id=current_user.id,
            reviewed_by_email=current_user.email,
        )

        # Daqui para baixo o parecer JÁ está commitado. Telemetria e auditoria
        # ficam cada uma no seu try: deixar uma exceção subir viraria 500 num
        # parecer que foi gravado, e o revisor responderia tudo de novo à toa.
        try:
            clinica_nome = getattr(document, "clinic_name", None)
            if not clinica_nome and getattr(document, "clinic_id", None):
                clinica = user_db.get_clinic_by_id(document.clinic_id)
                clinica_nome = clinica.name if clinica else None
            # Uma amostra por item apontado: um parecer com três exames errados
            # conta três vezes, porque a pergunta do painel é "com que frequência
            # cada tipo de erro aparece", não "quantos formulários foram
            # enviados". Logo, o contador NÃO serve para contar pareceres — para
            # isso, o `audit_log`. "nenhuma" cobre o IA_CORRETA, que por
            # definição não aponta nada.
            #
            # O NOME DO EXAME NÃO ENTRA como atributo, por mais tentador que
            # seja: são mais de mil nomes distintos vindos do OCR, e cada um
            # viraria uma série no Prometheus. Para cortar por exame existe o
            # `issue_items` no banco, que é onde a pergunta realmente se responde.
            for categoria in payload.categorias() or ["nenhuma"]:
                quantos = sum(
                    1 for item in payload.issue_items if item.categoria == categoria
                ) or 1
                metrics.FEEDBACK_CHECAGEM.add(
                    quantos,
                    {
                        "status": payload.status,
                        "categoria": categoria,
                        "clinica_id": document.clinic_id or "desconhecida",
                        "clinica_nome": clinica_nome or "desconhecida",
                    },
                )
        except Exception as metric_error:
            logger.warning(
                "[FEEDBACK] Falha ao registrar métrica de %s: %s", document_id, metric_error
            )

        _auditar(document_id, payload, anterior, current_user, request)

        logger.info(
            "[FEEDBACK] %s avaliou %s como %s",
            current_user.email,
            document_id,
            payload.status,
        )
        return feedback
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[FEEDBACK] Erro ao salvar parecer de %s: %s", document_id, e)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Erro ao salvar o parecer do documento"
        )
