"""
Endpoints para gerenciamento de clínicas credenciadas.
Apenas administradores podem gerenciar clínicas.
"""
from fastapi import APIRouter, HTTPException, status, Depends
from typing import List
from app.core.auth import require_management, get_current_user
from app.core.database import user_db
from app.models.user import User, UserRole
from app.models.clinic import Clinic, ClinicCreate, ClinicUpdate
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clinics", tags=["Clínicas"])


@router.get("/test-auth")
async def test_auth(current_user: User = Depends(require_management)):
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
    name: str,
    current_user: User = Depends(require_management)
):
    """Endpoint de teste simplificado para criar clínica"""
    try:
        logger.info(f"[TEST] Recebido: name={name}")
        logger.info(f"[TEST] User: {current_user.email} ({current_user.role})")
        logger.info(f"[TEST] user_db type: {type(user_db).__name__}")

        if not hasattr(user_db, 'create_clinic'):
            return {"error": "user_db não tem método create_clinic"}

        clinic = user_db.create_clinic(name=name)
        return {"success": True, "clinic_id": clinic.id}

    except Exception as e:
        logger.exception(f"[TEST] Erro: {e}")
        return {"error": str(e)}


@router.get("", response_model=List[Clinic])
async def list_clinics(
    include_inactive: bool = False,
    current_user: User = Depends(require_management)
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


@router.get("/options")
async def list_clinic_options(current_user: User = Depends(get_current_user)):
    """
    Lista enxuta (id + nome) das clínicas ativas para preencher filtros/combobox.
    Disponível a ADMIN, MANAGER e CHECKER — não expõe CNPJ, telefone ou endereço.
    """
    try:
        if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER, UserRole.CHECKER]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Sem permissão para listar opções de clínicas",
            )
        clinics = user_db.get_all_clinics(include_inactive=False)
        options = sorted(
            ({"id": c.id, "name": c.name} for c in clinics),
            key=lambda option: (option["name"] or "").lower(),
        )
        return options
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao listar opções de clínicas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar opções de clínicas"
        )


@router.get("/{clinic_id}", response_model=Clinic)
async def get_clinic(
    clinic_id: str,
    current_user: User = Depends(require_management)
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
    current_user: User = Depends(require_management)
):
    """
    Cria uma nova clínica credenciada.
    Apenas administradores.

    A clínica é identificada por ID (UUID). Usuários SENDER são associados a ela posteriormente.
    """
    try:
        logger.info(f"[CLINICS] Tentativa de criação: name={clinic_data.name}, cnpj={clinic_data.cnpj}")
        logger.info(f"[CLINICS] Admin autenticado: {current_user.email}")

        # Verificar se user_db tem os métodos necessários
        if not hasattr(user_db, 'create_clinic'):
            logger.error("[CLINICS] user_db não tem método create_clinic - usando JSON database?")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Banco de dados não configurado corretamente. DATABASE_URL deve estar configurado."
            )

        clinic = user_db.create_clinic(
            name=clinic_data.name,
            cnpj=clinic_data.cnpj,
            phone=clinic_data.phone,
            address=clinic_data.address,
            city=clinic_data.city,
            state=clinic_data.state
        )

        logger.info(f"[CLINICS] Admin {current_user.email} criou clínica {clinic.id} ({clinic.name})")
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
    current_user: User = Depends(require_management)
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
            cnpj=clinic_data.cnpj,
            phone=clinic_data.phone,
            address=clinic_data.address,
            city=clinic_data.city,
            state=clinic_data.state,
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
