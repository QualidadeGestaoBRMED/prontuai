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
from app.models.clinic import Clinic, ClinicCreate, ClinicUpdate
import logging

logger = logging.getLogger(__name__)


class UserDatabaseProtocol(Protocol):
    """Protocolo definindo a interface para implementações de banco de dados de usuários."""

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
                },
                "clinics": {}
            }
            self._write_db(initial_data)
            logger.info("Banco de dados de usuários criado com admin padrão")

    def _read_db(self) -> Dict:
        """Lê o banco de dados"""
        try:
            with open(DB_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Garantir que "clinics" existe
                if "clinics" not in data:
                    data["clinics"] = {}
                return data
        except Exception as e:
            logger.error(f"Erro ao ler banco de dados: {e}")
            return {"users": {}, "clinics": {}}

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

    def get_all_users(self) -> List[User]:
        """Retorna todos os usuários (alias para list_users)"""
        return self.list_users(include_inactive=True)

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
        """Deleta um usuário (exclusão suave - apenas marca como inativo)"""
        update = UserUpdate(is_active=False)
        return self.update_user(user_id, update) is not None

    # =============== CLINIC METHODS ===============

    def get_clinic_by_id(self, clinic_id: str) -> Optional[Clinic]:
        """Busca clínica por ID"""
        db = self._read_db()
        clinic_data = db.get("clinics", {}).get(clinic_id)
        if clinic_data:
            return Clinic(**clinic_data)
        return None

    def get_clinic_by_name(self, name: str) -> Optional[Clinic]:
        """Busca clínica por nome"""
        db = self._read_db()
        for clinic_data in db.get("clinics", {}).values():
            if clinic_data.get("name") == name:
                return Clinic(**clinic_data)
        return None

    def get_all_clinics(self, include_inactive: bool = False) -> List[Clinic]:
        """Lista todas as clínicas"""
        db = self._read_db()
        clinics = []
        for clinic_data in db.get("clinics", {}).values():
            if include_inactive or clinic_data.get("is_active", True):
                clinics.append(Clinic(**clinic_data))
        return sorted(clinics, key=lambda c: c.created_at or "", reverse=True)

    def create_clinic(
        self,
        name: str,
        cnpj: Optional[str] = None,
        phone: Optional[str] = None,
        address: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None
    ) -> Clinic:
        """Cria uma nova clínica"""
        db = self._read_db()

        clinic_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        clinic_data = {
            "id": clinic_id,
            "name": name,
            "cnpj": cnpj,
            "phone": phone,
            "address": address,
            "city": city,
            "state": state,
            "is_active": True,
            "created_at": now,
            "updated_at": now
        }

        db["clinics"][clinic_id] = clinic_data
        self._write_db(db)

        logger.info(f"Clínica criada: {name} ({clinic_id})")
        return Clinic(**clinic_data)

    def update_clinic(
        self,
        clinic_id: str,
        name: Optional[str] = None,
        cnpj: Optional[str] = None,
        phone: Optional[str] = None,
        address: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> Clinic:
        """Atualiza uma clínica existente"""
        db = self._read_db()

        if clinic_id not in db.get("clinics", {}):
            raise ValueError(f"Clínica com ID {clinic_id} não encontrada")

        clinic_data = db["clinics"][clinic_id]

        if name is not None:
            clinic_data["name"] = name
        if cnpj is not None:
            clinic_data["cnpj"] = cnpj
        if phone is not None:
            clinic_data["phone"] = phone
        if address is not None:
            clinic_data["address"] = address
        if city is not None:
            clinic_data["city"] = city
        if state is not None:
            clinic_data["state"] = state
        if is_active is not None:
            clinic_data["is_active"] = is_active

        clinic_data["updated_at"] = datetime.now().isoformat()

        db["clinics"][clinic_id] = clinic_data
        self._write_db(db)

        logger.info(f"Clínica atualizada: {clinic_data['name']}")
        return Clinic(**clinic_data)


def get_user_database() -> UserDatabaseProtocol:
    """
    Função factory para obter a implementação apropriada do banco de dados.

    Usa a variável de ambiente DATABASE_URL para decidir:
    - Se DATABASE_URL está definida: PostgreSQL
    - Caso contrário: Arquivo JSON (desenvolvimento)
    """
    database_url = os.getenv("DATABASE_URL")

    if database_url:
        logger.info("Usando banco de dados PostgreSQL")
        from app.core.database_postgres import PostgresUserDatabase
        return PostgresUserDatabase(database_url)
    else:
        logger.info("Usando banco de dados em arquivo JSON (modo desenvolvimento)")
        return UserDatabase()


# Instância global
user_db = get_user_database()
