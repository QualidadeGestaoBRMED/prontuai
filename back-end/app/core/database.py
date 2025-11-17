"""
Sistema de armazenamento de usuários com suporte a múltiplos backends.
Suporta JSON file (desenvolvimento) e PostgreSQL (produção).
"""
import json
import os
from typing import Dict, List, Optional, Protocol
from datetime import datetime
import uuid
from app.models.user import User, UserInDB, UserRole, UserUpdate
import logging

logger = logging.getLogger(__name__)


class UserDatabaseProtocol(Protocol):
    """Protocol defining the interface for user database implementations."""

    def get_user_by_email(self, email: str) -> Optional[User]: ...
    def get_user_by_id(self, user_id: str) -> Optional[User]: ...
    def get_all_users(self) -> List[User]: ...
    def create_user(self, email: str, name: str, role: UserRole = UserRole.CHECKER) -> User: ...
    def update_user(self, user_id: str, update: UserUpdate) -> User: ...
    def delete_user(self, user_id: str) -> bool: ...

# Caminho do arquivo de banco de dados
DB_PATH = os.path.join(os.path.dirname(__file__), "../../data/users.json")


class UserDatabase:
    """Gerenciador simples de banco de dados de usuários"""

    def __init__(self):
        self._ensure_db_exists()

    def _ensure_db_exists(self):
        """Garante que o arquivo de banco existe com estrutura inicial"""
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

        if not os.path.exists(DB_PATH):
            # Criar banco inicial com usuário admin padrão
            initial_data = {
                "users": {
                    str(uuid.uuid4()): {
                        "id": str(uuid.uuid4()),
                        "email": "gabriel.rodrigues@grupobrmed.com.br",
                        "name": "Gabriel Rodrigues",
                        "role": UserRole.ADMIN.value,
                        "is_active": True,
                        "created_at": datetime.now().isoformat(),
                        "updated_at": datetime.now().isoformat()
                    }
                }
            }
            self._write_db(initial_data)
            logger.info("Banco de dados de usuários criado com admin padrão")

    def _read_db(self) -> Dict:
        """Lê o banco de dados"""
        try:
            with open(DB_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Erro ao ler banco de dados: {e}")
            return {"users": {}}

    def _write_db(self, data: Dict):
        """Escreve no banco de dados"""
        try:
            with open(DB_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erro ao escrever no banco de dados: {e}")
            raise

    def get_user_by_email(self, email: str) -> Optional[UserInDB]:
        """Busca usuário por email"""
        db = self._read_db()
        for user_data in db.get("users", {}).values():
            if user_data.get("email") == email:
                return UserInDB(**user_data)
        return None

    def get_user_by_id(self, user_id: str) -> Optional[UserInDB]:
        """Busca usuário por ID"""
        db = self._read_db()
        user_data = db.get("users", {}).get(user_id)
        if user_data:
            return UserInDB(**user_data)
        return None

    def list_users(self, include_inactive: bool = False) -> List[User]:
        """Lista todos os usuários"""
        db = self._read_db()
        users = []
        for user_data in db.get("users", {}).values():
            if include_inactive or user_data.get("is_active", True):
                users.append(User(**user_data))
        return sorted(users, key=lambda u: u.created_at or "", reverse=True)

    def create_user(self, email: str, name: str, role: UserRole) -> User:
        """Cria um novo usuário"""
        db = self._read_db()

        # Verificar se email já existe
        if self.get_user_by_email(email):
            raise ValueError(f"Usuário com email {email} já existe")

        user_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        user_data = {
            "id": user_id,
            "email": email,
            "name": name,
            "role": role.value,
            "is_active": True,
            "created_at": now,
            "updated_at": now
        }

        db["users"][user_id] = user_data
        self._write_db(db)

        logger.info(f"Usuário criado: {email} com role {role.value}")
        return User(**user_data)

    def update_user(self, user_id: str, update: UserUpdate) -> User:
        """Atualiza um usuário existente"""
        db = self._read_db()

        if user_id not in db.get("users", {}):
            raise ValueError(f"Usuário com ID {user_id} não encontrado")

        user_data = db["users"][user_id]

        if update.name is not None:
            user_data["name"] = update.name
        if update.role is not None:
            user_data["role"] = update.role.value
        if update.is_active is not None:
            user_data["is_active"] = update.is_active

        user_data["updated_at"] = datetime.now().isoformat()

        db["users"][user_id] = user_data
        self._write_db(db)

        logger.info(f"Usuário atualizado: {user_data['email']}")
        return User(**user_data)

    def delete_user(self, user_id: str) -> bool:
        """Deleta um usuário (soft delete - apenas marca como inativo)"""
        update = UserUpdate(is_active=False)
        return self.update_user(user_id, update) is not None


def get_user_database() -> UserDatabaseProtocol:
    """
    Factory function to get the appropriate database implementation.

    Uses DATABASE_URL environment variable to decide:
    - If DATABASE_URL is set: PostgreSQL
    - Otherwise: JSON file (development)
    """
    database_url = os.getenv("DATABASE_URL")

    if database_url:
        logger.info("Using PostgreSQL database")
        from app.core.database_postgres import PostgresUserDatabase
        return PostgresUserDatabase(database_url)
    else:
        logger.info("Using JSON file database (development mode)")
        return UserDatabase()


# Instância global
user_db = get_user_database()
