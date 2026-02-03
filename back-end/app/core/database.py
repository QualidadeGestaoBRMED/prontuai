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
from app.models.notification import Notification, NotificationCreate
from app.models.audit_log import AuditLog, AuditLogCreate
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
    def create_notification(self, data: NotificationCreate) -> Notification: ...
    def list_notifications(self, clinic_id: Optional[str] = None, limit: int = 100, include_read: bool = True) -> List[Notification]: ...
    def mark_notification_read(self, notification_id: str) -> Optional[Notification]: ...
    def mark_all_notifications_read(self, clinic_id: Optional[str] = None) -> int: ...
    def clear_notifications(self, clinic_id: Optional[str] = None) -> int: ...
    def create_audit_log(self, data: AuditLogCreate) -> AuditLog: ...
    def list_audit_logs(
        self,
        limit: int = 200,
        user_id: Optional[str] = None,
        user_email: Optional[str] = None,
        action: Optional[str] = None,
        request_id: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> List[AuditLog]: ...

# Caminho do arquivo de banco de dados
DB_PATH = os.path.join(os.path.dirname(__file__), "../../data/users.json")
NOTIFICATIONS_PATH = os.path.join(os.path.dirname(__file__), "../../data/notifications.json")
AUDIT_LOGS_PATH = os.path.join(os.path.dirname(__file__), "../../data/audit_logs.json")


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

        if not os.path.exists(NOTIFICATIONS_PATH):
            with open(NOTIFICATIONS_PATH, 'w', encoding='utf-8') as f:
                json.dump({"notifications": []}, f, indent=2, ensure_ascii=False)
        if not os.path.exists(AUDIT_LOGS_PATH):
            with open(AUDIT_LOGS_PATH, 'w', encoding='utf-8') as f:
                json.dump({"audit_logs": []}, f, indent=2, ensure_ascii=False)

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

    def _read_notifications(self) -> Dict:
        try:
            with open(NOTIFICATIONS_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Erro ao ler notificações: {e}")
            return {"notifications": []}

    def _write_notifications(self, data: Dict) -> None:
        try:
            with open(NOTIFICATIONS_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erro ao escrever notificações: {e}")
            raise

    def _read_audit_logs(self) -> Dict:
        try:
            with open(AUDIT_LOGS_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Erro ao ler audit logs: {e}")
            return {"audit_logs": []}

    def _write_audit_logs(self, data: Dict) -> None:
        try:
            with open(AUDIT_LOGS_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erro ao escrever audit logs: {e}")
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
        existing = self.get_user_by_email(email)
        if existing:
            if getattr(existing, "is_active", True):
                raise ValueError(f"Usuário com email {email} já existe")
            # Reativa usuário inativo
            for user_id, user_data in db.get("users", {}).items():
                if user_data.get("email") == email:
                    now = datetime.now().isoformat()
                    user_data["name"] = name
                    user_data["role"] = role.value
                    user_data["is_active"] = True
                    user_data["updated_at"] = now
                    db["users"][user_id] = user_data
                    self._write_db(db)
                    logger.info(f"Usuário reativado: {email} com role {role.value}")
                    return User(**user_data)
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

    # =============== NOTIFICAÇÕES (JSON) ===============

    def create_notification(self, data: NotificationCreate) -> Notification:
        db = self._read_notifications()
        notif_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        notif = {
            "id": notif_id,
            "clinic_id": data.clinic_id,
            "document_id": data.document_id,
            "type": data.type,
            "title": data.title,
            "message": data.message,
            "variant": data.variant,
            "action_url": data.action_url,
            "action_label": data.action_label,
            "metadata": data.metadata,
            "read": False,
            "created_at": now
        }
        db["notifications"].append(notif)
        self._write_notifications(db)
        return Notification(**notif)

    def list_notifications(self, clinic_id: Optional[str] = None, limit: int = 100, include_read: bool = True) -> List[Notification]:
        db = self._read_notifications()
        items = db.get("notifications", [])
        if clinic_id:
            items = [n for n in items if n.get("clinic_id") == clinic_id]
        if not include_read:
            items = [n for n in items if not n.get("read", False)]
        items = sorted(items, key=lambda n: n.get("created_at", ""), reverse=True)[:limit]
        return [Notification(**n) for n in items]

    def mark_notification_read(self, notification_id: str) -> Optional[Notification]:
        db = self._read_notifications()
        for n in db.get("notifications", []):
            if n.get("id") == notification_id:
                n["read"] = True
                self._write_notifications(db)
                return Notification(**n)
        return None

    def mark_all_notifications_read(self, clinic_id: Optional[str] = None) -> int:
        db = self._read_notifications()
        count = 0
        for n in db.get("notifications", []):
            if clinic_id and n.get("clinic_id") != clinic_id:
                continue
            if not n.get("read", False):
                n["read"] = True
                count += 1
        self._write_notifications(db)
        return count

    def clear_notifications(self, clinic_id: Optional[str] = None) -> int:
        # Preserve histórico: apenas marca como lidas
        db = self._read_notifications()
        count = 0
        for n in db.get("notifications", []):
            if clinic_id and n.get("clinic_id") != clinic_id:
                continue
            if not n.get("read", False):
                n["read"] = True
                count += 1
        self._write_notifications(db)
        return count

    # =============== AUDIT LOG METHODS ===============

    def create_audit_log(self, data: AuditLogCreate) -> AuditLog:
        db = self._read_audit_logs()
        now = datetime.now().isoformat()
        entry = {
            "id": str(uuid.uuid4()),
            "user_id": data.user_id,
            "user_email": data.user_email,
            "user_role": data.user_role,
            "action": data.action,
            "resource": data.resource,
            "resource_id": data.resource_id,
            "method": data.method,
            "path": data.path,
            "status_code": data.status_code,
            "ip": data.ip,
            "user_agent": data.user_agent,
            "request_id": data.request_id,
            "metadata": data.metadata,
            "created_at": now,
        }
        db["audit_logs"].append(entry)
        self._write_audit_logs(db)
        return AuditLog(**entry)

    def list_audit_logs(
        self,
        limit: int = 200,
        user_id: Optional[str] = None,
        user_email: Optional[str] = None,
        action: Optional[str] = None,
        request_id: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> List[AuditLog]:
        db = self._read_audit_logs()
        logs = db.get("audit_logs", [])
        filtered = []
        normalized_email = user_email.strip().lower() if user_email else ""
        normalized_action = action.strip().lower() if action else ""
        normalized_request = request_id.strip().lower() if request_id else ""
        for entry in logs:
            if user_id and entry.get("user_id") != user_id:
                continue
            if normalized_email:
                entry_email = (entry.get("user_email") or "").lower()
                if normalized_email not in entry_email:
                    continue
            if normalized_action:
                entry_action = (entry.get("action") or "").lower()
                if normalized_action not in entry_action:
                    continue
            if normalized_request:
                entry_request = (entry.get("request_id") or "").lower()
                if normalized_request not in entry_request:
                    continue
            if since:
                try:
                    entry_dt = datetime.fromisoformat(entry.get("created_at"))
                    if entry_dt < since:
                        continue
                except Exception:
                    pass
            filtered.append(entry)
        filtered = list(reversed(filtered))[:limit]
        return [AuditLog(**entry) for entry in filtered]


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
