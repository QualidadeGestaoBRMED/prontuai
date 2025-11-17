"""
Sistema de autenticação e autorização com JWT.
"""
from datetime import datetime, timedelta
from typing import Optional, List
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.models.user import User, TokenData, UserRole
from app.core.database import user_db
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# Configurações JWT
SECRET_KEY = settings.JWT_SECRET_KEY if hasattr(settings, 'JWT_SECRET_KEY') else "sua-chave-secreta-super-segura-mude-isso-em-producao"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 horas

security = HTTPBearer()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Cria um token JWT"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> TokenData:
    """Decodifica e valida um token JWT"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        role: str = payload.get("role")
        name: str = payload.get("name")

        if email is None or role is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido: dados faltando",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return TokenData(email=email, role=UserRole(role), name=name)

    except JWTError as e:
        logger.error(f"Erro ao decodificar token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """
    Dependency para obter usuário autenticado atual.
    Valida o token JWT e retorna o usuário.
    """
    token = credentials.credentials
    token_data = decode_token(token)

    # Buscar usuário no banco
    user = user_db.get_user_by_email(token_data.email)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário inativo"
        )

    return user


def require_roles(allowed_roles: List[UserRole]):
    """
    Dependency factory para verificar se usuário tem uma das roles permitidas.

    Uso:
        @app.get("/admin")
        async def admin_only(user: User = Depends(require_roles([UserRole.ADMIN]))):
            return {"message": "Admin area"}
    """
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permissão negada. Requer uma das roles: {[r.value for r in allowed_roles]}"
            )
        return current_user

    return role_checker


# Helpers específicos para cada role
async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Requer role ADMIN"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas administradores podem acessar este recurso"
        )
    return current_user


async def require_checker(current_user: User = Depends(get_current_user)) -> User:
    """Requer role CHECKER ou ADMIN"""
    if current_user.role not in [UserRole.CHECKER, UserRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas checadores ou administradores podem acessar este recurso"
        )
    return current_user


async def require_sender(current_user: User = Depends(get_current_user)) -> User:
    """Requer role SENDER ou ADMIN"""
    if current_user.role not in [UserRole.SENDER, UserRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas enviadores ou administradores podem acessar este recurso"
        )
    return current_user
