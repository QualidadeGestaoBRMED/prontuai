from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from app.services import validacao_service
from app.core.auth import require_checker, get_current_user
from app.models.user import User
from app.core.pii import mask_identifier
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

class ValidacaoRequest(BaseModel):
    cpf: str
    exames_obrigatorios: list[str]
    exames_enviados: list[str]

@router.post("/validacao", summary="Validar exames enviados vs. obrigatórios")
async def validar_exames(
    request: ValidacaoRequest,
    current_user: User = Depends(require_checker)  # Apenas CHECKER ou ADMIN
):
    if not request.cpf or not request.exames_obrigatorios or not request.exames_enviados:
        logger.warning("Parâmetros obrigatórios ausentes na validação.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CPF, exames obrigatórios e exames enviados são obrigatórios.")
    try:
        logger.info(f"Usuário {current_user.email} ({current_user.role.value}) validando exames para CPF {mask_identifier(request.cpf)}")
        # `validar_exames` é assíncrona e compara `exames_enviados` contra
        # `exames_brnet`; `exames_obrigatorios` só alimenta a auditoria. No
        # workflow as duas listas são diferentes (a do BRNET é a crua, a de
        # obrigatórios é a filtrada), mas aqui o cliente manda a lista pronta:
        # ela é a própria referência da comparação.
        #
        # Sem o `await` e sem `exames_brnet` esta rota devolvia 500
        # (TypeError), desde que a assinatura do serviço mudou.
        resultado = await validacao_service.validar_exames(
            cpf=request.cpf,
            exames_obrigatorios=request.exames_obrigatorios,
            exames_enviados=request.exames_enviados,
            exames_brnet=request.exames_obrigatorios,
        )
        return resultado
    except Exception as e:
        logger.exception(f"Erro inesperado na validação: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro inesperado na validação de exames.") 