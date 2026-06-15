"""
Endpoints de gerenciamento de usuários (apenas ADMIN).
"""
from fastapi import APIRouter, HTTPException, status, Depends
from typing import List
from app.core.auth import require_admin
from app.core.database import user_db
from app.models.user import User, UserCreate, UserUpdate, UserRole
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["Usuários"])


@router.get("", response_model=List[User])
async def list_users(
    include_inactive: bool = False,
    admin: User = Depends(require_admin)
):
    """
    Lista todos os usuários (apenas ADMIN).

    - **include_inactive**: Se True, inclui usuários inativos
    """
    users = user_db.list_users(include_inactive=include_inactive)
    logger.info(f"Admin {admin.email} listou {len(users)} usuários")
    return users


@router.post("", response_model=User, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_create: UserCreate,
    admin: User = Depends(require_admin)
):
    """
    Cria um novo usuário (apenas ADMIN).

    - Para role SENDER/BOTH: clinic_id é OBRIGATÓRIO (deve escolher de uma clínica existente)
    - Para role CHECKER/ADMIN: clinic_id deve ser NULL
    """
    try:
        clinic_id = user_create.clinic_id

        # Validar clinic_id para roles que exigem clínica
        if user_create.role.requires_clinic:
            if not clinic_id:
                raise ValueError(f"clinic_id é obrigatório para usuários {user_create.role.value}. Crie uma clínica primeiro.")

            # Verificar se clínica existe
            clinic = user_db.get_clinic_by_id(clinic_id)
            if not clinic:
                raise ValueError(f"Clínica com ID {clinic_id} não encontrada")

            logger.info(f"Criando usuário {user_create.role.value} {user_create.email} para clínica {clinic.name} ({clinic_id})")

        # CHECKER e ADMIN não devem ter clinic_id
        if not user_create.role.requires_clinic:
            clinic_id = None

        user = user_db.create_user(
            email=user_create.email,
            name=user_create.name,
            role=user_create.role,
            clinic_id=clinic_id
        )
        logger.info(f"Admin {admin.email} criou usuário {user.email} com role {user.role.value} (clinic_id: {clinic_id})")
        return user

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{user_id}", response_model=User)
async def get_user(
    user_id: str,
    admin: User = Depends(require_admin)
):
    """
    Busca um usuário por ID (apenas ADMIN).
    """
    user = user_db.get_user_by_id(user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado"
        )

    return user


@router.patch("/{user_id}", response_model=User)
async def update_user(
    user_id: str,
    user_update: UserUpdate,
    admin: User = Depends(require_admin)
):
    """
    Atualiza um usuário existente (apenas ADMIN).

    Pode atualizar:
    - **name**: Nome do usuário
    - **role**: Role (ADMIN, CHECKER, SENDER, BOTH)
    - **is_active**: Status ativo/inativo
    - **clinic_id**: Clínica associada (apenas para SENDER/BOTH)
    """
    try:
        user = user_db.update_user(
            user_id=user_id,
            name=user_update.name,
            role=user_update.role,
            is_active=user_update.is_active,
            clinic_id=user_update.clinic_id
        )
        logger.info(f"Admin {admin.email} atualizou usuário {user.email}")
        return user

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    admin: User = Depends(require_admin)
):
    """
    Desativa um usuário (soft delete, apenas ADMIN).
    O usuário não é removido do banco, apenas marcado como inativo.
    """
    # Não permitir admin desativar a si mesmo
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Você não pode desativar sua própria conta"
        )

    try:
        user_db.delete_user(user_id)
        logger.info(f"Admin {admin.email} desativou usuário {user_id}")
        return None

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get("/email/{email}", response_model=User)
async def get_user_by_email(
    email: str,
    admin: User = Depends(require_admin)
):
    """
    Busca um usuário por email (apenas ADMIN).
    """
    user = user_db.get_user_by_email(email)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado"
        )

    return user
