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


@router.get("/test-auth")
async def test_auth(current_user: User = Depends(require_admin)):
    """Endpoint de teste para verificar autenticação admin"""
    return {
        "authenticated": True,
        "user": {
            "email": current_user.email,
            "name": current_user.name,
            "role": current_user.role,
            "clinic_id": current_user.clinic_id
        }
    }


@router.post("/test-create")
async def test_create(
    email: str,
    name: str,
    current_user: User = Depends(require_admin)
):
    """Endpoint de teste simplificado para criar clínica"""
    try:
        logger.info(f"[TEST] Recebido: email={email}, name={name}")
        logger.info(f"[TEST] User: {current_user.email} ({current_user.role})")
        logger.info(f"[TEST] user_db type: {type(user_db).__name__}")
        logger.info(f"[TEST] Has get_clinic_by_email: {hasattr(user_db, 'get_clinic_by_email')}")

        if not hasattr(user_db, 'create_clinic'):
            return {"error": "user_db não tem método create_clinic"}

        clinic = user_db.create_clinic(email=email, name=name)
        return {"success": True, "clinic_id": clinic.id}

    except Exception as e:
        logger.exception(f"[TEST] Erro: {e}")
        return {"error": str(e)}


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
        logger.info(f"[CLINICS] Tentativa de criação: email={clinic_data.email}, name={clinic_data.name}")
        logger.info(f"[CLINICS] Admin autenticado: {current_user.email}")

        # Verificar se user_db tem os métodos necessários
        if not hasattr(user_db, 'get_clinic_by_email'):
            logger.error("[CLINICS] user_db não tem método get_clinic_by_email - usando JSON database?")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Banco de dados não configurado corretamente. DATABASE_URL deve estar configurado."
            )

        # Verificar se já existe clínica com este email
        existing = user_db.get_clinic_by_email(clinic_data.email)
        if existing:
            logger.warning(f"[CLINICS] Clínica com email {clinic_data.email} já existe")
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
        logger.exception(f"[CLINICS] Erro ao criar clínica: {e}")
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
