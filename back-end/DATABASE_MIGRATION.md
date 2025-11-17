# Migração de Banco de Dados - JSON para PostgreSQL

## Arquitetura Atual

O sistema suporta **dois backends de banco de dados** através de um factory pattern:

1. **JSON File** (desenvolvimento/local)
   - Arquivo: `data/users.json`
   - Usado quando `DATABASE_URL` não está definida
   - Simples e sem dependências

2. **PostgreSQL** (produção)
   - Implementação: `app/core/database_postgres.py`
   - Usado quando `DATABASE_URL` está definida
   - Escalável e robusto

## Como Funciona

O arquivo `app/core/database.py` contém:
- `UserDatabaseProtocol`: Interface que ambas implementações seguem
- `UserDatabase`: Implementação JSON (original)
- `PostgresUserDatabase`: Implementação PostgreSQL (nova)
- `get_user_database()`: Factory que escolhe automaticamente

```python
# Automático baseado em DATABASE_URL
from app.core.database import user_db

# user_db será JSON ou PostgreSQL dependendo do ambiente
users = user_db.get_all_users()
```

## Setup PostgreSQL com Neon

### 1. Criar database no Neon

```bash
npx neonctl@latest init
```

Isso vai criar um projeto e retornar a `DATABASE_URL`.

### 2. Adicionar DATABASE_URL no Render

No dashboard do Render, vá em **Environment** e adicione:

```
DATABASE_URL=postgresql://user:password@host/database?sslmode=require
```

**IMPORTANTE**: Neon usa `postgresql://` mas SQLAlchemy 2.0 precisa de `postgresql+psycopg2://`.
O código já faz essa conversão automaticamente em `database_postgres.py`.

### 3. Deploy

Após adicionar `DATABASE_URL`, faça redeploy:
- O sistema vai detectar automaticamente
- As tabelas serão criadas no primeiro acesso
- Um usuário admin padrão será criado: `admin@grupobrmed.com.br`

## Migração de Dados (Opcional)

Se você já tem usuários no JSON e quer migrar para PostgreSQL:

```python
# scripts/migrate_json_to_postgres.py
import json
import os
from app.core.database_postgres import PostgresUserDatabase

# Load JSON data
with open('data/users.json', 'r') as f:
    data = json.load(f)

# Connect to Postgres
db = PostgresUserDatabase(os.getenv('DATABASE_URL'))

# Migrate users
for user_id, user_data in data['users'].items():
    try:
        db.create_user(
            email=user_data['email'],
            name=user_data['name'],
            role=user_data['role']
        )
        print(f"✅ Migrated: {user_data['email']}")
    except ValueError as e:
        print(f"⚠️  Skipped: {user_data['email']} - {e}")
```

Execute:
```bash
python scripts/migrate_json_to_postgres.py
```

## Desenvolvimento Local

### Opção 1: Continuar com JSON
Não defina `DATABASE_URL` no `.env` local

### Opção 2: Usar PostgreSQL local

Instalar PostgreSQL:
```bash
sudo apt install postgresql
sudo systemctl start postgresql
```

Criar database:
```bash
sudo -u postgres createuser prontuai_user
sudo -u postgres createdb prontuai_db -O prontuai_user
sudo -u postgres psql -c "ALTER USER prontuai_user PASSWORD 'dev_password';"
```

Adicionar ao `.env`:
```
DATABASE_URL=postgresql://prontuai_user:dev_password@localhost/prontuai_db
```

### Opção 3: Usar Neon também no desenvolvimento

Crie um database separado para dev e adicione ao `.env`:
```
DATABASE_URL=postgresql://user:password@ep-xxx.neon.tech/prontuai_dev?sslmode=require
```

## Verificar Qual Database Está Sendo Usado

Ao iniciar a aplicação, verifique os logs:

```bash
# JSON
INFO: Using JSON file database (development mode)

# PostgreSQL
INFO: Using PostgreSQL database
```

## Estrutura da Tabela PostgreSQL

```sql
CREATE TABLE users (
    id VARCHAR PRIMARY KEY,
    email VARCHAR UNIQUE NOT NULL,
    name VARCHAR NOT NULL,
    role VARCHAR NOT NULL,  -- ENUM: 'ADMIN', 'CHECKER', 'SENDER'
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);
```

## Rollback para JSON

Se precisar voltar para JSON:

1. Remova `DATABASE_URL` do Render
2. Redeploy
3. O sistema volta automaticamente para JSON

## Troubleshooting

### Erro: "psycopg2.OperationalError: FATAL: password authentication failed"
- Verifique se `DATABASE_URL` está correta
- Teste conexão: `psql $DATABASE_URL`

### Erro: "relation 'users' does not exist"
- As tabelas são criadas automaticamente no primeiro acesso
- Se persistir, verifique permissões do usuário no banco

### Performance lenta
- PostgreSQL no Neon Free tier pode ter cold starts
- Considere upgrade para plano pago se necessário
- Adicione índices se fizer muitas queries por campos específicos

## Próximos Passos (Futuro)

- [ ] Async database com asyncpg
- [ ] Migrations com Alembic
- [ ] Connection pooling
- [ ] Read replicas para escalabilidade
- [ ] Backup automático
