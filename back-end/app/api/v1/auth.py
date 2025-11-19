"""
Endpoints de autenticação e autorização.
"""
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, EmailStr
from app.core.auth import create_access_token, get_current_user
from app.core.database import user_db
from app.models.user import User
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Autenticação"])


class GoogleAuthRequest(BaseModel):
    """Request de autenticação via Google"""
    email: EmailStr
    name: str
    google_id: str


class TokenResponse(BaseModel):
    """Response com token de acesso"""
    access_token: str
    token_type: str = "bearer"
    user: User


@router.post("/google", response_model=TokenResponse)
async def google_auth(auth_request: GoogleAuthRequest):
    """
    Autentica usuário via Google OAuth.
    Se usuário não existir, retorna erro (admin deve criar primeiro).
    """
    # Buscar usuário no banco
    user = user_db.get_user_by_email(auth_request.email)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário não cadastrado. Contate o administrador para obter acesso."
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário inativo. Contate o administrador."
        )

    # Criar token JWT com clinic_id (se usuário for SENDER)
    token_data = {
        "sub": user.email,
        "role": user.role.value,
        "name": user.name
    }

    if user.clinic_id:
        token_data["clinic_id"] = user.clinic_id

    access_token = create_access_token(data=token_data)

    logger.info(f"Usuário autenticado: {user.email} (role: {user.role.value}, clinic_id: {user.clinic_id})")

    return TokenResponse(
        access_token=access_token,
        user=user
    )


@router.get("/me", response_model=User)
async def get_me(current_user: User = Depends(get_current_user)):
    """
    Retorna dados do usuário autenticado atual.
    """
    return current_user


@router.post("/verify")
async def verify_token(current_user: User = Depends(get_current_user)):
    """
    Verifica se o token é válido.
    """
    return {
        "valid": True,
        "user": current_user
    }
