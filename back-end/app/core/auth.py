"""
Sistema de autenticação e autorização com JWT.
"""
from datetime import datetime, timedelta
import hashlib
import uuid
import os
from typing import Optional, List, Any
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.models.user import User, TokenData, UserRole
from app.core.database import user_db
from app.core.config import settings
from app.core.logging import set_user_context
import logging

logger = logging.getLogger(__name__)

# Configurações JWT
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = settings.JWT_EXPIRATION_HOURS * 60
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_EXPIRATION_DAYS", 30))

security = HTTPBearer(auto_error=False)


def _is_non_production() -> bool:
    return settings.APP_ENV in {"local", "dev", "development", "test", "testing"}


def _resolve_secret_key() -> str:
    configured = settings.JWT_SECRET_KEY or ""
    if configured:
        return configured
    if _is_non_production():
        fallback = os.getenv(
            "JWT_SECRET_KEY_LOCAL_FALLBACK",
            "local-dev-secret-not-for-production-use-only",
        )
        logger.warning(
            "JWT_SECRET_KEY ausente. Usando fallback local; configure segredo explícito no ambiente.",
        )
        return fallback
    return ""


SECRET_KEY = _resolve_secret_key()


def _is_weak_jwt_secret(secret: str) -> bool:
    if not secret:
        return True
    if len(secret) < settings.JWT_MIN_SECRET_LENGTH:
        return True
    bad_prefixes = (
        "dev-secret-key-change-in-production-please",
        "sua-chave-secreta-super-segura-mude-isso-em-producao",
        "changeme",
        "secret",
    )
    normalized = secret.strip().lower()
    return any(normalized.startswith(prefix) for prefix in bad_prefixes)


def assert_auth_security_configuration() -> None:
    """
    Falha rápido em ambientes não-locais quando configuração de auth está insegura.
    """
    if _is_non_production():
        return

    if _is_weak_jwt_secret(settings.JWT_SECRET_KEY):
        raise RuntimeError(
            "JWT_SECRET_KEY insegura para ambiente não-local. "
            "Configure segredo forte e com comprimento mínimo."
        )

    if settings.DEV_AUTH_BYPASS:
        raise RuntimeError("DEV_AUTH_BYPASS não pode estar ativo fora de ambiente local/teste.")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Cria um token JWT"""
    to_encode = data.copy()
    now = datetime.utcnow()
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update(
        {
            "exp": expire,
            "iat": now,
            "nbf": now,
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
        }
    )
    # Refresh tokens passam jti explícito para permitir sessão persistida.
    to_encode.setdefault("jti", str(uuid.uuid4()))
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def hash_refresh_jti(jti: str) -> str:
    """Hash SHA-256 do jti para armazenamento (nunca persistir o valor cru)."""
    return hashlib.sha256(jti.encode("utf-8")).hexdigest()


def create_refresh_token(data: dict, family_id: Optional[str] = None) -> tuple[str, str, str, datetime]:
    """Cria um refresh token JWT de longa duração (scope=refresh).

    Retorna (token, jti, family_id, expires_at) para que o chamador persista a
    sessão e faça rotação de uso único com detecção de reuso.
    """
    jti = str(uuid.uuid4())
    family_id = family_id or str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    token = create_access_token(
        {**data, "scope": "refresh", "jti": jti},
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )
    return token, jti, family_id, expires_at


def create_upload_token(user: User, expires_delta: Optional[timedelta] = None) -> str:
    """
    Cria um JWT curto e limitado ao envio direto de arquivos.

    Esse token não deve funcionar nas rotas comuns: ele é aceito apenas pelas
    dependencies específicas de upload para evitar expor o JWT principal no browser.
    """
    return create_access_token(
        {
            "sub": user.email,
            "role": user.role.value if hasattr(user.role, "value") else str(user.role),
            "name": user.name,
            "clinic_id": user.clinic_id,
            "scope": "upload",
        },
        expires_delta=expires_delta or timedelta(minutes=10),
    )


def decode_token(token: str) -> TokenData:
    """Decodifica e valida um token JWT"""
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
        )
        email: str = payload.get("sub")
        role: str = payload.get("role")
        name: str = payload.get("name")
        clinic_id: Optional[str] = payload.get("clinic_id")
        scope: Optional[str] = payload.get("scope")

        if scope == "upload":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token de upload não é válido para esta rota",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if email is None or role is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido: dados faltando",
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            parsed_role = UserRole(role)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido: role inválida",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

        return TokenData(email=email, role=parsed_role, name=name, clinic_id=clinic_id)

    except JWTError as e:
        logger.error(f"Erro ao decodificar token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )


def decode_token_claims(token: str) -> dict[str, Any]:
    """
    Decodifica um JWT válido e retorna as claims brutas.

    Usado em middlewares que precisam identificar o chamador sem aplicar as
    restrições adicionais de rota do `decode_token`, como o bloqueio de
    `scope=upload`.
    """
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
        )
    except JWTError as exc:
        logger.debug("Falha ao decodificar claims do token para uso auxiliar: %s", exc)
        raise
    return payload


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """
    Dependency para obter usuário autenticado atual.
    Valida o token JWT e retorna o usuário.
    """
    if credentials is None:
        if settings.DEV_AUTH_BYPASS:
            if not _is_non_production():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token ausente",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            dev_email = os.getenv("DEV_AUTH_EMAIL", "dev@grupobrmed.com.br")
            dev_name = os.getenv("DEV_AUTH_NAME", "Dev Bypass")
            dev_role_raw = os.getenv("DEV_AUTH_ROLE", "ADMIN")
            dev_clinic_name = os.getenv("DEV_AUTH_CLINIC", "Clinica Dev")

            try:
                existing_user = user_db.get_user_by_email(dev_email)
                if existing_user:
                    return existing_user

                # Garantir que exista ao menos uma clínica para associar ao usuário dev
                clinic_id = None
                try:
                    clinics = user_db.get_all_clinics()
                except Exception:
                    clinics = []

                if clinics:
                    clinic_id = clinics[0].id
                else:
                    try:
                        clinic = user_db.create_clinic(name=dev_clinic_name)
                        clinic_id = clinic.id
                    except Exception as clinic_error:
                        logger.warning(f"Falha ao criar clínica dev: {clinic_error}")
                        clinic_id = None

                try:
                    dev_role = UserRole(dev_role_raw)
                except Exception:
                    dev_role = UserRole.ADMIN

                created_user = user_db.create_user(
                    email=dev_email,
                    name=dev_name,
                    role=dev_role,
                    clinic_id=clinic_id
                )
                set_user_context(created_user)
                return created_user
            except Exception as e:
                logger.warning(f"Falha ao montar usuário dev no banco: {e}")
                dev_user = User(
                    id="dev-bypass",
                    email=dev_email,
                    name=dev_name,
                    role=UserRole.ADMIN,
                    is_active=True,
                    clinic_id=None
                )
                set_user_context(dev_user)
                return dev_user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token ausente",
            headers={"WWW-Authenticate": "Bearer"},
        )

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

    set_user_context(user)
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
    """Requer role ADMIN. Reservado a operações destrutivas/de sistema (exclusões, migrações)."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas administradores podem acessar este recurso"
        )
    return current_user


async def require_management(current_user: User = Depends(get_current_user)) -> User:
    """Requer role ADMIN ou MANAGER (gestão administrativa sem operações destrutivas)."""
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas administradores ou gestores podem acessar este recurso"
        )
    return current_user


async def require_exam_catalog(current_user: User = Depends(get_current_user)) -> User:
    """
    Requer ADMIN ou CURATOR.

    Deliberadamente **não** inclui MANAGER: o catálogo de exames define o que o
    motor reconhece em cada prontuário, e essa curadoria foi separada da gestão
    administrativa. Por isso não usa `require_management`.
    """
    if current_user.role not in [UserRole.ADMIN, UserRole.CURATOR]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas administradores ou curadores podem acessar o catálogo de exames"
        )
    return current_user


async def get_current_upload_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """
    Valida token curto de upload direto.

    Usado para evitar que arquivos grandes passem pelo proxy server-side do Next.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de upload ausente",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
        )
    except JWTError as e:
        logger.error(f"Erro ao decodificar token de upload: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de upload inválido ou expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scope = payload.get("scope")
    if scope != "upload":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token não autorizado para upload direto",
            headers={"WWW-Authenticate": "Bearer"},
        )

    email: str = payload.get("sub")
    role: str = payload.get("role")
    if not email or not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de upload inválido: dados faltando",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = user_db.get_user_by_email(email)
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

    set_user_context(user)
    return user


async def require_checker(current_user: User = Depends(get_current_user)) -> User:
    """Requer role CHECKER, ADMIN ou MANAGER"""
    if current_user.role not in [UserRole.CHECKER, UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas checadores ou administradores podem acessar este recurso"
        )
    return current_user


async def require_sender(current_user: User = Depends(get_current_user)) -> User:
    """Requer role SENDER, ADMIN ou MANAGER"""
    if current_user.role not in [UserRole.SENDER, UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas enviadores ou administradores podem acessar este recurso"
        )
    return current_user


async def require_upload_sender(current_user: User = Depends(get_current_upload_user)) -> User:
    """Requer token curto de upload para role SENDER, ADMIN ou MANAGER."""
    if current_user.role not in [UserRole.SENDER, UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas enviadores ou administradores podem enviar documentos"
        )
    return current_user
