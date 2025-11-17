# Sistema de Autenticação e Autorização

## Visão Geral

O sistema implementa autenticação baseada em JWT (JSON Web Tokens) com sistema de roles para controle de acesso granular.

## Roles Disponíveis

### ADMIN
- **Permissões**: Acesso total ao sistema
- **Pode**:
  - Gerenciar usuários (criar, listar, atualizar, deletar)
  - Acessar checagem de exames
  - Enviar documentos (pendentes)
  - Todas as funcionalidades

### CHECKER
- **Permissões**: Apenas checagem de exames
- **Pode**:
  - Validar exames (`POST /v1/validacao`)
  - Ver histórico de validações
- **Não pode**:
  - Enviar documentos
  - Gerenciar usuários

### SENDER
- **Permissões**: Apenas envio de documentos
- **Pode**:
  - Processar OCR e extrair dados (`POST /v1/ocr`)
  - Enviar documentos pendentes
- **Não pode**:
  - Fazer checagem de exames
  - Gerenciar usuários

## Arquitetura de Segurança

### Back-end (FastAPI) - Fonte da Verdade
```python
# Exemplo: Endpoint protegido
@router.post("/validacao")
async def validar_exames(
    request: ValidacaoRequest,
    current_user: User = Depends(require_checker)  # ✅ Validação no back-end
):
    # Se user.role não for CHECKER ou ADMIN, retorna 403
    ...
```

### Front-end (Next.js) - Apenas UX
- Esconde/mostra botões baseado em role (experiência do usuário)
- **NÃO é responsável por segurança** (pode ser burlado)
- Todas as validações reais acontecem no back-end

## Endpoints de Autenticação

### POST /v1/auth/google
Autentica usuário via Google OAuth e retorna JWT token.

**Request:**
```json
{
  "email": "usuario@grupobrmed.com.br",
  "name": "João Silva",
  "google_id": "102938475623847562"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": "uuid-do-usuario",
    "email": "usuario@grupobrmed.com.br",
    "name": "João Silva",
    "role": "CHECKER",
    "is_active": true
  }
}
```

**Erros:**
- `403`: Email não é @grupobrmed.com.br
- `403`: Usuário não cadastrado (admin precisa criar primeiro)
- `403`: Usuário inativo

### GET /v1/auth/me
Retorna dados do usuário autenticado atual.

**Headers:**
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response:**
```json
{
  "id": "uuid",
  "email": "usuario@grupobrmed.com.br",
  "name": "João Silva",
  "role": "CHECKER",
  "is_active": true
}
```

## Endpoints de Gerenciamento de Usuários (ADMIN apenas)

### GET /v1/users
Lista todos os usuários.

**Query Params:**
- `include_inactive` (bool): Incluir usuários inativos (default: false)

**Response:**
```json
[
  {
    "id": "uuid",
    "email": "admin@grupobrmed.com.br",
    "name": "Administrador",
    "role": "ADMIN",
    "is_active": true,
    "created_at": "2025-01-01T10:00:00",
    "updated_at": "2025-01-01T10:00:00"
  }
]
```

### POST /v1/users
Cria um novo usuário.

**Request:**
```json
{
  "email": "novo@grupobrmed.com.br",
  "name": "Novo Usuário",
  "role": "CHECKER"
}
```

**Response:** Retorna o usuário criado (201 Created)

**Erros:**
- `400`: Email não é @grupobrmed.com.br
- `400`: Email já existe
- `403`: Usuário não é ADMIN

### PATCH /v1/users/{user_id}
Atualiza um usuário existente.

**Request:**
```json
{
  "role": "ADMIN",
  "is_active": true
}
```

### DELETE /v1/users/{user_id}
Desativa um usuário (soft delete).

**Response:** 204 No Content

**Erros:**
- `400`: Admin tentando desativar a si mesmo
- `404`: Usuário não encontrado

## Endpoints Protegidos

### POST /v1/validacao
**Requer**: CHECKER ou ADMIN

### POST /v1/ocr
**Requer**: SENDER ou ADMIN

### POST /v1/workflow/processar
**Requer**: SENDER ou ADMIN (herda de /ocr)

## Banco de Dados

Usa arquivo JSON simples (`data/users.json`) para armazenamento.

**Estrutura:**
```json
{
  "users": {
    "uuid-1": {
      "id": "uuid-1",
      "email": "admin@grupobrmed.com.br",
      "name": "Administrador",
      "role": "ADMIN",
      "is_active": true,
      "created_at": "2025-01-01T10:00:00",
      "updated_at": "2025-01-01T10:00:00"
    }
  }
}
```

**Usuário padrão:**
- Email: `admin@grupobrmed.com.br`
- Role: `ADMIN`
- Criado automaticamente na primeira execução

## Fluxo de Autenticação

1. **Login no Front-end**
   - Usuário faz login com Google OAuth (NextAuth)
   - Front-end envia email/name/google_id para `POST /v1/auth/google`

2. **Validação no Back-end**
   - Verifica se email é @grupobrmed.com.br
   - Busca usuário no banco
   - Se não existir → retorna 403 (admin deve criar primeiro)
   - Se inativo → retorna 403

3. **Geração de Token**
   - Cria JWT com payload: `{sub: email, role: ROLE, name: name}`
   - Token expira em 24h (configurável via `JWT_EXPIRATION_HOURS`)
   - Retorna token + dados do usuário

4. **Requests Subsequentes**
   - Front-end inclui token no header: `Authorization: Bearer <token>`
   - Back-end valida token em cada request
   - Verifica role do usuário para endpoints protegidos
   - Se não autorizado → retorna 403

## Variáveis de Ambiente

Adicione ao `.env`:

```bash
# JWT Secret Key (MUDE EM PRODUÇÃO!)
JWT_SECRET_KEY=sua-chave-super-secreta-mude-isso-em-producao

# Expiração do token em horas (padrão: 24)
JWT_EXPIRATION_HOURS=24
```

## Migrações Futuras

### Para PostgreSQL/MongoDB:
1. Substituir `app/core/database.py` por ORM (SQLAlchemy/Prisma)
2. Criar tabela `users` com schema equivalente
3. Manter mesma interface (`UserDatabase` class)
4. Endpoints não precisam mudar

### Adicionar Senhas:
1. Descomentar campo `hashed_password` em `UserInDB`
2. Usar `passlib` para hash bcrypt
3. Adicionar endpoint `POST /v1/auth/login` com email+senha
4. Manter Google OAuth como opção alternativa

## Testando

### 1. Criar primeiro admin:
O sistema cria automaticamente `admin@grupobrmed.com.br` no banco.

### 2. Fazer login (simular):
```bash
curl -X POST http://localhost:8000/v1/auth/google \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@grupobrmed.com.br",
    "name": "Administrador",
    "google_id": "fake-id"
  }'
```

Copie o `access_token` da resposta.

### 3. Criar novo usuário (como admin):
```bash
curl -X POST http://localhost:8000/v1/users \
  -H "Authorization: Bearer <SEU_TOKEN_AQUI>" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "checker@grupobrmed.com.br",
    "name": "João Checker",
    "role": "CHECKER"
  }'
```

### 4. Testar permissões:
```bash
# Deve funcionar (CHECKER pode validar)
curl -X POST http://localhost:8000/v1/validacao \
  -H "Authorization: Bearer <TOKEN_DO_CHECKER>" \
  -H "Content-Type: application/json" \
  -d '{...}'

# Deve retornar 403 (CHECKER não pode fazer OCR)
curl -X POST http://localhost:8000/v1/ocr \
  -H "Authorization: Bearer <TOKEN_DO_CHECKER>" \
  -F "arquivo=@documento.pdf"
```

## Segurança

### ✅ Implementado:
- JWT com expiração
- Validação de domínio de email
- Role-based access control (RBAC)
- Validação em TODOS os endpoints sensíveis
- Soft delete (usuários nunca são removidos do banco)
- Logs de auditoria (quem fez o quê)

### ⚠️ Recomendações para Produção:
- **MUDE** `JWT_SECRET_KEY` para valor aleatório forte
- Use HTTPS (obrigatório para JWT)
- Configure rate limiting (prevenir brute force)
- Adicione refresh tokens (para renovar sem re-login)
- Implemente 2FA (opcional, para maior segurança)
- Use PostgreSQL ao invés de JSON file
- Configure backup automático do banco de dados

## Troubleshooting

### Erro: "Token inválido ou expirado"
- Token expirou (24h)
- Usuário precisa fazer login novamente

### Erro: "Permissão negada. Requer uma das roles: [...]"
- Usuário não tem a role necessária
- Admin precisa atualizar role: `PATCH /v1/users/{id}`

### Erro: "Usuário não cadastrado"
- Admin ainda não criou o usuário
- Admin deve criar via `POST /v1/users`

### Erro: "Apenas emails @grupobrmed.com.br são permitidos"
- Usuário tentou logar com email de domínio diferente
- Sistema só aceita emails corporativos
