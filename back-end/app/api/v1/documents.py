"""
Endpoints para gerenciamento de documentos.
"""
from fastapi import APIRouter, HTTPException, status, Depends
from typing import List
from app.core.auth import get_current_user, require_admin
from app.core.database import user_db
from app.models.user import User, UserRole
from app.models.document import Document
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documentos"])


@router.get("", response_model=List[Document])
async def list_documents(current_user: User = Depends(get_current_user)):
    """
    Lista documentos processados.

    - SENDER: retorna apenas documentos da própria clínica
    - CHECKER/ADMIN: retorna documentos de todas as clínicas
    """
    try:
        if current_user.role in [UserRole.CHECKER, UserRole.ADMIN]:
            # Checkers e Admins veem tudo
            documents = user_db.get_all_documents()
            logger.info(f"[DOCUMENTS] {current_user.role.value} {current_user.email} listou {len(documents)} documentos (todas clínicas)")
        else:
            # SENDER vê apenas da própria clínica
            if not current_user.clinic_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Usuário SENDER deve estar associado a uma clínica"
                )
            documents = user_db.get_documents_by_clinic(current_user.clinic_id)
            logger.info(f"[DOCUMENTS] SENDER {current_user.email} listou {len(documents)} documentos (clinic_id: {current_user.clinic_id})")

        return documents
    except Exception as e:
        logger.exception(f"Erro ao listar documentos: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao listar documentos: {str(e)}"
        )


@router.get("/{document_id}", response_model=Document)
async def get_document(document_id: str, current_user: User = Depends(get_current_user)):
    """
    Obtém detalhes de um documento específico.

    - SENDER: apenas se o documento pertencer à sua clínica
    - CHECKER/ADMIN: qualquer documento
    """
    try:
        document = user_db.get_document_by_id(document_id)

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Documento não encontrado"
            )

        # Verificar permissão
        if current_user.role == UserRole.SENDER:
            if not current_user.clinic_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Usuário SENDER deve estar associado a uma clínica"
                )
            if document.clinic_id != current_user.clinic_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Você não tem permissão para acessar este documento"
                )

        logger.info(f"[DOCUMENTS] {current_user.email} acessou documento {document_id}")
        return document

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao obter documento {document_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao obter documento: {str(e)}"
        )
