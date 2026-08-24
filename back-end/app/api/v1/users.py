"""
Endpoints de gerenciamento de usuários (ADMIN e MANAGER).

MANAGER pode listar, criar e editar usuários, mas não pode desativar (delete)
nem criar/promover usuários ADMIN.
"""
from fastapi import APIRouter, HTTPException, status, Depends
from typing import List
from app.core.auth import require_admin, require_management
from app.core.database import user_db
from app.core import metrics
from app.models.user import User, UserCreate, UserUpdate, UserRole
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["Usuários"])


def _assert_manager_cannot_touch_admin(actor: User, target_role: UserRole | None):
    """Impede escalada de privilégio: MANAGER só atribui roles CHECKER/SENDER."""
    if actor.role == UserRole.MANAGER and target_role in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Gestores só podem atribuir as roles CHECKER e SENDER"
        )


@router.get("", response_model=List[User])
async def list_users(
    include_inactive: bool = False,
    admin: User = Depends(require_management)
):
    """
    Lista todos os usuários (ADMIN/MANAGER).

    - **include_inactive**: Se True, inclui usuários inativos
    """
    users = user_db.list_users(include_inactive=include_inactive)
    logger.info(f"Admin {admin.email} listou {len(users)} usuários")
    return users


@router.post("", response_model=User, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_create: UserCreate,
    admin: User = Depends(require_management)
):
    """
    Cria um novo usuário (ADMIN/MANAGER; MANAGER só cria CHECKER/SENDER).

    - Para role SENDER: clinic_id é OBRIGATÓRIO (deve escolher de uma clínica existente)
    - Para role CHECKER/ADMIN/MANAGER: clinic_id deve ser NULL
    """
    _assert_manager_cannot_touch_admin(admin, user_create.role)
    try:
        clinic_id = user_create.clinic_id
        clinic_name = None

        # Validar clinic_id para SENDER
        if user_create.role == UserRole.SENDER:
            if not clinic_id:
                raise ValueError("clinic_id é obrigatório para usuários SENDER. Crie uma clínica primeiro.")

            # Verificar se clínica existe
            clinic = user_db.get_clinic_by_id(clinic_id)
            if not clinic:
                raise ValueError(f"Clínica com ID {clinic_id} não encontrada")
            clinic_name = clinic.name

            logger.info(f"Criando usuário SENDER {user_create.email} para clínica {clinic.name} ({clinic_id})")

        # CHECKER, ADMIN e MANAGER não devem ter clinic_id
        if user_create.role in [UserRole.CHECKER, UserRole.ADMIN, UserRole.MANAGER]:
            clinic_id = None

        user = user_db.create_user(
            email=user_create.email,
            name=user_create.name,
            role=user_create.role,
            clinic_id=clinic_id
        )
        logger.info(f"Admin {admin.email} criou usuário {user.email} com role {user.role.value} (clinic_id: {clinic_id})")
        metrics.USUARIOS_CRIADOS.add(
            1,
            {
                "role": user.role.value,
                "clinica_id": clinic_id or "sem_clinica",
                "clinica_nome": clinic_name or "sem_clinica",
            },
        )
        return user

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{user_id}", response_model=User)
async def get_user(
    user_id: str,
    admin: User = Depends(require_management)
):
    """
    Busca um usuário por ID (ADMIN/MANAGER).
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
    admin: User = Depends(require_management)
):
    """
    Atualiza um usuário existente (ADMIN/MANAGER; MANAGER não pode alterar ADMIN).

    Pode atualizar:
    - **name**: Nome do usuário
    - **role**: Role (ADMIN, MANAGER, CHECKER, SENDER)
    - **is_active**: Status ativo/inativo
    - **clinic_id**: Clínica associada (apenas para SENDER)
    """
    _assert_manager_cannot_touch_admin(admin, user_update.role)
    if admin.role == UserRole.MANAGER:
        target = user_db.get_user_by_id(user_id)
        if target and target.role == UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Gestores não podem alterar usuários ADMIN"
            )

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
    admin: User = Depends(require_management)
):
    """
    Busca um usuário por email (ADMIN/MANAGER).
    """
    user = user_db.get_user_by_email(email)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado"
        )

    return user
