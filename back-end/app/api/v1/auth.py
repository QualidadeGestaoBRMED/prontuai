"""
Endpoints de autenticação e autorização.
"""
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, EmailStr
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from app.core.auth import (
    create_access_token,
    create_refresh_token,
    get_current_user,
    hash_refresh_jti,
    SECRET_KEY,
    ALGORITHM,
)
from jose import JWTError, jwt as jose_jwt
from app.core.config import settings
from app.core.database import user_db
from app.models.user import User
from datetime import datetime
from typing import Optional
import logging
import os

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Autenticação"])


class GoogleAuthRequest(BaseModel):
    """Request de autenticação via Google"""
    id_token: str
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    google_id: Optional[str] = None


class TokenResponse(BaseModel):
    """Response com token de acesso"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: User


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


@router.post("/google", response_model=TokenResponse)
async def google_auth(auth_request: GoogleAuthRequest):
    """
    Autentica usuário via Google OAuth.
    Se usuário não existir, retorna erro (admin deve criar primeiro).
    """
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configuração de autenticação Google inválida no servidor."
        )

    # Validação criptográfica do token Google
    try:
        token_info = google_id_token.verify_oauth2_token(
            auth_request.id_token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
    except Exception as exc:
        logger.warning("Falha ao validar id_token Google: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token Google inválido."
        ) from exc

    email = token_info.get("email")
    email_verified = token_info.get("email_verified")
    google_sub = token_info.get("sub")
    if not email or email_verified is not True or not google_sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token Google sem claims obrigatórias."
        )

    if auth_request.email and str(auth_request.email).lower() != str(email).lower():
        logger.warning("Email no payload diverge do id_token Google. Ignorando payload do cliente.")

    # Buscar usuário no banco usando somente o email validado no token
    user = user_db.get_user_by_email(email)

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
    refresh_token, refresh_jti, family_id, refresh_expires_at = create_refresh_token(data=token_data)
    user_db.create_refresh_session(
        jti_hash=hash_refresh_jti(refresh_jti),
        user_email=user.email,
        family_id=family_id,
        expires_at=refresh_expires_at,
    )

    logger.info(
        "Usuário autenticado: %s (role: %s, clinic_id: %s, google_sub: %s)",
        user.email,
        user.role.value,
        user.clinic_id,
        google_sub,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=user
    )


# Reuso de um token rotacionado há poucos segundos costuma ser corrida benigna
# (duas abas renovando juntas), não roubo; nesse caso só nega sem derrubar a família.
REFRESH_REUSE_GRACE_SECONDS = int(os.getenv("REFRESH_REUSE_GRACE_SECONDS", "30"))


def _handle_refresh_reuse(session_row: dict) -> None:
    """Trata reuso de um refresh token já rotacionado/revogado.

    Dentro da janela de graça (rotação recente e legítima), apenas nega a
    requisição. Fora dela, presume roubo e revoga a família inteira.
    """
    revoked_at = session_row.get("revoked_at")
    was_rotated = session_row.get("replaced_by_jti_hash") is not None
    age_seconds = (
        (datetime.utcnow() - revoked_at).total_seconds() if revoked_at is not None else None
    )
    if was_rotated and age_seconds is not None and age_seconds <= REFRESH_REUSE_GRACE_SECONDS:
        logger.info(
            "Refresh token rotacionado em corrida recente; negando sem revogar família.",
            extra={"family_id": session_row["family_id"]},
        )
    else:
        revoked = user_db.revoke_refresh_family(session_row["family_id"])
        logger.warning(
            "Reuso de refresh token detectado; família revogada.",
            extra={"family_id": session_row["family_id"], "sessions_revoked": revoked},
        )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sessão inválida. Faça login novamente.",
    )


def _decode_refresh_payload(refresh_token: str) -> dict:
    """Valida assinatura/expiração e scope de um refresh token."""
    try:
        payload = jose_jwt.decode(
            refresh_token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
        )
    except JWTError as exc:
        logger.warning("Refresh token inválido ou expirado: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido ou expirado",
        ) from exc

    if payload.get("scope") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token não é um refresh token",
        )
    return payload


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token(body: RefreshRequest):
    """Renova o access token usando um refresh token válido.

    Rotação de uso único: cada refresh token só pode ser usado uma vez.
    Reuso de um token já rotacionado indica roubo e revoga a família
    inteira de tokens (todas as rotações derivadas do mesmo login).
    """
    payload = _decode_refresh_payload(body.refresh_token)

    jti = str(payload.get("jti") or "")
    if not jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido ou expirado",
        )

    session_row = user_db.get_refresh_session(hash_refresh_jti(jti))
    if session_row is None:
        # Token assinado mas sem sessão persistida: emitido antes da rotação
        # de uso único existir, ou de uma família já purgada. Exige novo login.
        logger.warning("Refresh token sem sessão registrada; exigindo novo login.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão expirada. Faça login novamente.",
        )

    if session_row["revoked_at"] is not None:
        _handle_refresh_reuse(session_row)

    email: str = payload.get("sub", "")
    user = user_db.get_user_by_email(email)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado ou inativo",
        )

    token_data = {"sub": user.email, "role": user.role.value, "name": user.name}
    if user.clinic_id:
        token_data["clinic_id"] = user.clinic_id

    new_refresh_token, new_jti, family_id, new_expires_at = create_refresh_token(
        data=token_data, family_id=session_row["family_id"]
    )
    rotated = user_db.rotate_refresh_session(
        old_jti_hash=session_row["jti_hash"],
        new_jti_hash=hash_refresh_jti(new_jti),
        user_email=user.email,
        family_id=family_id,
        expires_at=new_expires_at,
    )
    if not rotated:
        # Outra requisição rotacionou este mesmo token em corrida.
        refreshed_row = user_db.get_refresh_session(session_row["jti_hash"]) or session_row
        _handle_refresh_reuse(refreshed_row)

    logger.info("Token renovado para: %s", user.email)

    return RefreshResponse(
        access_token=create_access_token(data=token_data),
        refresh_token=new_refresh_token,
    )


@router.post("/logout")
async def logout(body: RefreshRequest):
    """Revoga a sessão de refresh token (e toda a família de rotação)."""
    payload = _decode_refresh_payload(body.refresh_token)
    jti = str(payload.get("jti") or "")
    if jti:
        session_row = user_db.get_refresh_session(hash_refresh_jti(jti))
        if session_row is not None:
            revoked = user_db.revoke_refresh_family(session_row["family_id"])
            logger.info(
                "Logout: família de refresh tokens revogada.",
                extra={"family_id": session_row["family_id"], "sessions_revoked": revoked},
            )
    return {"success": True}


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
