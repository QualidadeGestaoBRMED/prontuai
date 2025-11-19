"""
Endpoints para gerenciamento de clínicas credenciadas.
Apenas administradores podem gerenciar clínicas.
"""
from fastapi import APIRouter, HTTPException, status, Depends
from typing import List
from app.core.auth import require_admin
from app.core.database import user_db
from app.models.user import User
from app.models.clinic import Clinic, ClinicCreate, ClinicUpdate
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clinics", tags=["Clínicas"])


@router.get("", response_model=List[Clinic])
async def list_clinics(
    include_inactive: bool = False,
    current_user: User = Depends(require_admin)
):
    """
    Lista todas as clínicas credenciadas.
    Apenas administradores.
    """
    try:
        clinics = user_db.get_all_clinics(include_inactive=include_inactive)
        logger.info(f"[CLINICS] Admin {current_user.email} listou {len(clinics)} clínicas")
        return clinics
    except Exception as e:
        logger.exception(f"Erro ao listar clínicas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao listar clínicas: {str(e)}"
        )


@router.get("/{clinic_id}", response_model=Clinic)
async def get_clinic(
    clinic_id: str,
    current_user: User = Depends(require_admin)
):
    """
    Obtém detalhes de uma clínica específica.
    Apenas administradores.
    """
    try:
        clinic = user_db.get_clinic_by_id(clinic_id)

        if not clinic:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Clínica não encontrada"
            )

        logger.info(f"[CLINICS] Admin {current_user.email} acessou clínica {clinic_id}")
        return clinic

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao obter clínica {clinic_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao obter clínica: {str(e)}"
        )


@router.post("", response_model=Clinic, status_code=status.HTTP_201_CREATED)
async def create_clinic(
    clinic_data: ClinicCreate,
    current_user: User = Depends(require_admin)
):
    """
    Cria uma nova clínica credenciada.
    Apenas administradores.
    """
    try:
        # Verificar se já existe clínica com este email
        existing = user_db.get_clinic_by_email(clinic_data.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Já existe uma clínica com o email {clinic_data.email}"
            )

        clinic = user_db.create_clinic(
            email=clinic_data.email,
            name=clinic_data.name
        )

        logger.info(f"[CLINICS] Admin {current_user.email} criou clínica {clinic.id} ({clinic.email})")
        return clinic

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao criar clínica: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao criar clínica: {str(e)}"
        )


@router.patch("/{clinic_id}", response_model=Clinic)
async def update_clinic(
    clinic_id: str,
    clinic_data: ClinicUpdate,
    current_user: User = Depends(require_admin)
):
    """
    Atualiza dados de uma clínica.
    Apenas administradores.
    """
    try:
        # Verificar se clínica existe
        existing = user_db.get_clinic_by_id(clinic_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Clínica não encontrada"
            )

        clinic = user_db.update_clinic(
            clinic_id=clinic_id,
            name=clinic_data.name,
            is_active=clinic_data.is_active
        )

        logger.info(f"[CLINICS] Admin {current_user.email} atualizou clínica {clinic_id}")
        return clinic

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao atualizar clínica {clinic_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao atualizar clínica: {str(e)}"
        )
