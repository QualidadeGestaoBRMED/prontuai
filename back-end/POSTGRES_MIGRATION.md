# Migração para PostgreSQL

Este documento mapeia o que precisa ser substituído para migrar do banco JSON atual para PostgreSQL.

## 📋 Checklist de Migração

### 1. Adicionar Dependências

**Adicionar ao `requirements.txt`:**
```txt
# Database
psycopg2-binary>=2.9.0  # Driver PostgreSQL
sqlalchemy>=2.0.0       # ORM
alembic>=1.13.0         # Migrations
```

**Instalar:**
```bash
pip install psycopg2-binary sqlalchemy alembic
```

### 2. Configuração do Banco

**Adicionar ao `.env`:**
```bash
# PostgreSQL Database
DATABASE_URL=postgresql://usuario:senha@localhost:5432/prontuai
# Ou para async (recomendado com FastAPI):
# DATABASE_URL=postgresql+asyncpg://usuario:senha@localhost:5432/prontuai
```

**Atualizar `app/core/config.py`:**
```python
class Settings:
    # ... existing settings ...

    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/prontuai")
    DATABASE_POOL_SIZE = int(os.getenv("DATABASE_POOL_SIZE", 5))
    DATABASE_MAX_OVERFLOW = int(os.getenv("DATABASE_MAX_OVERFLOW", 10))
```

### 3. Criar Estrutura SQLAlchemy

**Criar `app/db/base.py`:**
```python
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Engine
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    echo=False  # Set True para debug SQL
)

# Session maker
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class para models
Base = declarative_base()

# Dependency para obter session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

**OU para Async (recomendado):**
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=settings.DATABASE_POOL_SIZE
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
```

### 4. Criar Model SQLAlchemy

**Criar `app/db/models.py`:**
```python
from sqlalchemy import Column, String, Boolean, DateTime, Enum as SQLEnum
from sqlalchemy.sql import func
import uuid
from app.db.base import Base
from app.models.user import UserRole

class UserModel(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRole), nullable=False, default=UserRole.CHECKER)
    is_active = Column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Indexes
    __table_args__ = (
        {'comment': 'Tabela de usuários do sistema'},
    )
```

### 5. Substituir `app/core/database.py`

**ANTES (JSON file):**
```python
# app/core/database.py - ARQUIVO ATUAL
class UserDatabase:
    def __init__(self):
        self._ensure_db_exists()

    def _read_db(self) -> Dict:
        with open(DB_PATH, 'r') as f:
            return json.load(f)
    # ...
```

**DEPOIS (SQLAlchemy):**
```python
# app/core/database.py - NOVA VERSÃO
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List, Optional
from app.db.models import UserModel
from app.models.user import User, UserRole
import logging

logger = logging.getLogger(__name__)

class UserDatabase:
    """Gerenciador de usuários usando PostgreSQL"""

    def get_user_by_email(self, db: Session, email: str) -> Optional[User]:
        """Busca usuário por email"""
        stmt = select(UserModel).where(UserModel.email == email)
        db_user = db.execute(stmt).scalar_one_or_none()

        if db_user:
            return User.model_validate(db_user)
        return None

    def get_user_by_id(self, db: Session, user_id: str) -> Optional[User]:
        """Busca usuário por ID"""
        stmt = select(UserModel).where(UserModel.id == user_id)
        db_user = db.execute(stmt).scalar_one_or_none()

        if db_user:
            return User.model_validate(db_user)
        return None

    def list_users(self, db: Session, include_inactive: bool = False) -> List[User]:
        """Lista todos os usuários"""
        stmt = select(UserModel)
        if not include_inactive:
            stmt = stmt.where(UserModel.is_active == True)

        stmt = stmt.order_by(UserModel.created_at.desc())
        results = db.execute(stmt).scalars().all()

        return [User.model_validate(user) for user in results]

    def create_user(self, db: Session, email: str, name: str, role: UserRole) -> User:
        """Cria um novo usuário"""
        # Verificar se já existe
        if self.get_user_by_email(db, email):
            raise ValueError(f"Usuário com email {email} já existe")

        db_user = UserModel(
            email=email,
            name=name,
            role=role,
            is_active=True
        )

        db.add(db_user)
        db.commit()
        db.refresh(db_user)

        logger.info(f"Usuário criado: {email} com role {role.value}")
        return User.model_validate(db_user)

    def update_user(self, db: Session, user_id: str,
                   name: Optional[str] = None,
                   role: Optional[UserRole] = None,
                   is_active: Optional[bool] = None) -> User:
        """Atualiza um usuário existente"""
        stmt = select(UserModel).where(UserModel.id == user_id)
        db_user = db.execute(stmt).scalar_one_or_none()

        if not db_user:
            raise ValueError(f"Usuário com ID {user_id} não encontrado")

        if name is not None:
            db_user.name = name
        if role is not None:
            db_user.role = role
        if is_active is not None:
            db_user.is_active = is_active

        db.commit()
        db.refresh(db_user)

        logger.info(f"Usuário atualizado: {db_user.email}")
        return User.model_validate(db_user)

    def delete_user(self, db: Session, user_id: str) -> bool:
        """Deleta um usuário (soft delete)"""
        return self.update_user(db, user_id, is_active=False) is not None

# Instância global
user_db = UserDatabase()
```

### 6. Atualizar Endpoints para Usar Session

**ANTES:**
```python
# app/api/v1/users.py - VERSÃO ATUAL
@router.get("", response_model=List[User])
async def list_users(
    include_inactive: bool = False,
    admin: User = Depends(require_admin)
):
    users = user_db.list_users(include_inactive=include_inactive)
    return users
```

**DEPOIS:**
```python
# app/api/v1/users.py - NOVA VERSÃO
from app.db.base import get_db
from sqlalchemy.orm import Session

@router.get("", response_model=List[User])
async def list_users(
    include_inactive: bool = False,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)  # ← Adicionar isso em TODOS os endpoints
):
    users = user_db.list_users(db, include_inactive=include_inactive)
    return users
```

**Padrão para TODOS os endpoints de usuários:**
```python
async def meu_endpoint(
    ...,
    current_user: User = Depends(get_current_user),  # Auth
    db: Session = Depends(get_db)  # Database session
):
    # Sempre passar db como primeiro parâmetro para user_db
    result = user_db.metodo(db, ...)
```

### 7. Inicialização do Banco

**Criar `app/db/init_db.py`:**
```python
from app.db.base import engine, Base
from app.db.models import UserModel
from sqlalchemy.orm import Session
from app.core.database import user_db
from app.models.user import UserRole
import logging

logger = logging.getLogger(__name__)

def init_db():
    """
    Cria todas as tabelas e insere admin padrão se necessário.
    Executar apenas uma vez no startup.
    """
    # Criar todas as tabelas
    Base.metadata.create_all(bind=engine)
    logger.info("Tabelas do banco de dados criadas")

    # Criar admin padrão se não existir
    from app.db.base import SessionLocal
    db = SessionLocal()
    try:
        admin = user_db.get_user_by_email(db, "admin@grupobrmed.com.br")
        if not admin:
            user_db.create_user(
                db,
                email="admin@grupobrmed.com.br",
                name="Administrador",
                role=UserRole.ADMIN
            )
            logger.info("Admin padrão criado")
    finally:
        db.close()
```

**Atualizar `main.py`:**
```python
from app.db.init_db import init_db

app = FastAPI(...)

@app.on_event("startup")
async def startup_event():
    """Executar ao iniciar aplicação"""
    init_db()

# ... resto do código
```

### 8. Migrations com Alembic

**Inicializar Alembic:**
```bash
cd back-end
alembic init alembic
```

**Configurar `alembic/env.py`:**
```python
from app.db.base import Base
from app.db.models import UserModel  # Importar TODOS os models
from app.core.config import settings

# ...

target_metadata = Base.metadata

# ...

def run_migrations_offline():
    url = settings.DATABASE_URL
    # ...

def run_migrations_online():
    connectable = create_engine(settings.DATABASE_URL)
    # ...
```

**Criar primeira migration:**
```bash
alembic revision --autogenerate -m "Create users table"
alembic upgrade head
```

**Para aplicar migrations em produção:**
```bash
# Antes de subir o app
alembic upgrade head
```

### 9. Testar Migração

**Script de teste `scripts/test_postgres.py`:**
```python
from app.db.base import SessionLocal
from app.core.database import user_db
from app.models.user import UserRole

def test_crud():
    db = SessionLocal()
    try:
        # Create
        user = user_db.create_user(
            db,
            email="test@grupobrmed.com.br",
            name="Test User",
            role=UserRole.CHECKER
        )
        print(f"✅ Created: {user}")

        # Read
        found = user_db.get_user_by_email(db, "test@grupobrmed.com.br")
        print(f"✅ Found: {found}")

        # Update
        updated = user_db.update_user(db, user.id, role=UserRole.ADMIN)
        print(f"✅ Updated: {updated}")

        # List
        users = user_db.list_users(db)
        print(f"✅ Total users: {len(users)}")

        # Delete
        user_db.delete_user(db, user.id)
        print(f"✅ Deleted (soft): {user.id}")

    finally:
        db.close()

if __name__ == "__main__":
    test_crud()
```

### 10. Docker Compose com PostgreSQL

**Adicionar ao `docker-compose.prod.yml`:**
```yaml
services:
  postgres:
    image: postgres:16-alpine
    container_name: prontuai-postgres
    environment:
      POSTGRES_DB: prontuai
      POSTGRES_USER: ${DB_USER:-prontuai}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U prontuai"]
      interval: 10s
      timeout: 5s
      retries: 5

  prontuai-backend:
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      - DATABASE_URL=postgresql://${DB_USER:-prontuai}:${DB_PASSWORD}@postgres:5432/prontuai
      # ... outras envs

volumes:
  postgres_data:
```

**Adicionar ao `.env`:**
```bash
# PostgreSQL
DB_USER=prontuai
DB_PASSWORD=sua-senha-super-segura-aqui
```

## 📊 Comparação: JSON vs PostgreSQL

| Aspecto | JSON File (Atual) | PostgreSQL (Migração) |
|---------|-------------------|----------------------|
| **Concorrência** | ❌ Lock de arquivo | ✅ ACID transactions |
| **Performance** | ❌ Leitura total do arquivo | ✅ Queries indexadas |
| **Escalabilidade** | ❌ Limitado | ✅ Milhões de registros |
| **Backup** | ⚠️ Manual (git) | ✅ pg_dump automático |
| **Complexidade** | ✅ Simples (zero setup) | ⚠️ Requer servidor DB |
| **Produção** | ❌ Não recomendado | ✅ Pronto para produção |

## 🚀 Plano de Migração Gradual

### Fase 1: Setup Paralelo (Sem Breaking Changes)
1. Adicionar PostgreSQL ao docker-compose
2. Criar models SQLAlchemy
3. Testar CRUD com script de teste
4. **Sistema continua usando JSON**

### Fase 2: Feature Flag
```python
# app/core/config.py
USE_POSTGRES = os.getenv("USE_POSTGRES", "false").lower() == "true"

# app/core/database.py
if settings.USE_POSTGRES:
    from app.core.database_postgres import user_db
else:
    from app.core.database_json import user_db
```

### Fase 3: Migração de Dados
```python
# scripts/migrate_json_to_postgres.py
import json
from app.db.base import SessionLocal
from app.core.database import user_db as pg_db
from app.models.user import UserRole

def migrate():
    # Ler JSON atual
    with open('data/users.json') as f:
        data = json.load(f)

    db = SessionLocal()
    try:
        for user_data in data['users'].values():
            pg_db.create_user(
                db,
                email=user_data['email'],
                name=user_data['name'],
                role=UserRole(user_data['role'])
            )
        print(f"✅ Migrated {len(data['users'])} users")
    finally:
        db.close()
```

### Fase 4: Switch Completo
1. Set `USE_POSTGRES=true`
2. Rodar migrations
3. Rodar script de migração
4. Testar em staging
5. Deploy em produção
6. Remover código JSON após 1 semana de estabilidade

## ⚠️ Avisos Importantes

1. **Não delete** `data/users.json` imediatamente - mantenha como backup
2. **Teste** a migração em ambiente local primeiro
3. **Backup** do banco PostgreSQL antes de cada deploy
4. **Monitore** logs após migração para detectar problemas
5. **Rollback plan**: Se der problema, voltar para `USE_POSTGRES=false`

## 📝 Checklist de Produção

- [ ] PostgreSQL configurado na AWS RDS ou similar
- [ ] Backup automático habilitado
- [ ] Connection pooling configurado
- [ ] SSL/TLS para conexões de banco
- [ ] Migrations rodando automaticamente no CI/CD
- [ ] Monitoring (CloudWatch, DataDog, etc)
- [ ] Script de rollback testado
