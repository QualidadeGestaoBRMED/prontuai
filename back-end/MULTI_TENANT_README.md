# Sistema Multi-Tenant - Clínicas Credenciadas BRMED

## Visão Geral

O sistema foi reestruturado para suportar múltiplas clínicas credenciadas, onde:

- **Cada clínica** é identificada por um e-mail único
- **Usuários SENDER** pertencem a uma clínica e veem apenas documentos da própria clínica
- **Usuários CHECKER** e **ADMIN** veem documentos de todas as clínicas (acesso global)
- Documentos processados são rastreados no banco de dados

## Estrutura do Banco de Dados

### Novas Tabelas

#### `clinics`
- `id` - Identificador único (UUID)
- `email` - Email da clínica (único)
- `name` - Nome da clínica
- `is_active` - Status ativo/inativo
- `created_at`, `updated_at` - Timestamps

#### `documents`
- `id` - Identificador único
- `clinic_id` - Clínica que enviou o documento
- `uploaded_by_user_id` - Usuário que fez upload
- `filename` - Nome do arquivo
- `cpf` - CPF extraído
- `uploaded_at` - Data de upload
- `exams_found` - Array de exames encontrados
- `validation_status` - Status (`pending`, `validated`, `rejected`)
- `ocr_markdown` - Resultado do OCR
- `created_at`, `updated_at` - Timestamps

### Modificações em Tabelas Existentes

#### `users`
- **Nova coluna:** `clinic_id` - Foreign key para `clinics` (NULL para CHECKER/ADMIN)

## Migração de Banco de Dados

### 1. Executar Migração SQL

```bash
python run_migration.py
```

Este script cria:
- Tabela `clinics`
- Tabela `documents`
- Adiciona coluna `clinic_id` em `users`

### 2. Migrar Dados Existentes

```bash
python migrate_existing_data.py
```

Este script:
- Cria clínica padrão "Grupo BRMED - Legado"
- Associa todos os usuários SENDER à clínica padrão
- Mantém CHECKER/ADMIN sem clínica (acesso global)

## Novos Endpoints

### Clínicas (Admin apenas)

#### GET `/v1/clinics`
Lista todas as clínicas credenciadas.

**Headers:** `Authorization: Bearer <token>`

**Query params:**
- `include_inactive` (opcional): incluir clínicas inativas

#### POST `/v1/clinics`
Cria nova clínica.

**Headers:** `Authorization: Bearer <token>`

**Body:**
```json
{
  "email": "clinica@example.com",
  "name": "Clínica Exemplo"
}
```

#### PATCH `/v1/clinics/{clinic_id}`
Atualiza clínica.

**Body:**
```json
{
  "name": "Novo Nome",
  "is_active": true
}
```

### Documentos

#### GET `/v1/documents`
Lista documentos processados.

**Comportamento por role:**
- **SENDER:** retorna apenas documentos da própria clínica
- **CHECKER/ADMIN:** retorna todos os documentos

**Headers:** `Authorization: Bearer <token>`

#### GET `/v1/documents/{document_id}`
Obtém detalhes de um documento.

**Permissões:**
- SENDER: apenas se pertencer à sua clínica
- CHECKER/ADMIN: qualquer documento

### Upload de Documentos

#### POST `/v1/processar-documento`
Processa documento (OCR + validação).

**Mudanças:**
- Agora requer autenticação (role SENDER)
- Salva metadados do documento na tabela `documents`
- Inclui `clinic_id` automaticamente do usuário autenticado

**Headers:** `Authorization: Bearer <token>`

**Body:**
```json
{
  "arquivo": "<file>",
  "exames_obrigatorios": "[\"Hemograma\", \"Glicemia\"]"
}
```

**Response:**
```json
{
  "ocr": { ... },
  "brmed": { ... },
  "validacao": { ... },
  "document_id": "uuid-do-documento"
}
```

## Criação de Usuários

### Comportamento Atualizado

Ao criar um usuário SENDER via `/v1/users`:

1. **Se `clinic_id` não fornecido:**
   - Verifica se já existe clínica com o email do usuário
   - Se sim, usa essa clínica
   - Se não, cria nova clínica automaticamente

2. **Para CHECKER/ADMIN:**
   - `clinic_id` sempre NULL (acesso global)

**Exemplo:**
```bash
POST /v1/users
{
  "email": "novaclinica@example.com",
  "name": "Clínica Nova",
  "role": "SENDER"
}
```

Resultado:
- Cria usuário SENDER
- Cria clínica com email `novaclinica@example.com`
- Associa usuário à clínica automaticamente

## Autenticação

### Token JWT

O token JWT agora inclui `clinic_id`:

```json
{
  "sub": "usuario@example.com",
  "role": "SENDER",
  "name": "Nome do Usuário",
  "clinic_id": "uuid-da-clinica",  // NULL para CHECKER/ADMIN
  "exp": 1234567890
}
```

### Validação de Email

- **Removida** a validação de domínio `@grupobrmed.com.br`
- Agora aceita qualquer email válido
- Usuários devem ser criados via `/v1/users` (apenas ADMIN)

## Fluxo de Uso

### 1. Admin cria clínica credenciada

```bash
POST /v1/users
{
  "email": "clinica1@example.com",
  "name": "Clínica 1",
  "role": "SENDER"
}
```

### 2. Clínica faz login

```bash
POST /v1/auth/google
{
  "email": "clinica1@example.com",
  "name": "Clínica 1",
  "google_id": "..."
}
```

### 3. Clínica envia documento

```bash
POST /v1/processar-documento
Authorization: Bearer <token>

{
  "arquivo": ...,
  "exames_obrigatorios": "[...]"
}
```

### 4. Clínica lista seus documentos

```bash
GET /v1/documents
Authorization: Bearer <token>
```

Retorna apenas documentos da clínica.

### 5. Checker vê todos os documentos

```bash
GET /v1/documents
Authorization: Bearer <checker-token>
```

Retorna documentos de TODAS as clínicas.

## Segurança

### Isolamento de Dados

- **SENDER:** Queries filtradas por `clinic_id` do token
- **CHECKER/ADMIN:** Sem filtro (acesso global)

### Foreign Keys

- `documents.clinic_id` → `clinics.id`
- `documents.uploaded_by_user_id` → `users.id`
- `users.clinic_id` → `clinics.id`

## Logs

O sistema registra:
- Criação de clínicas
- Associação de usuários a clínicas
- Upload de documentos com `clinic_id`
- Acesso a documentos (com verificação de permissão)

## Troubleshooting

### Erro: "column users.clinic_id does not exist"

Execute a migração SQL:
```bash
python run_migration.py
```

### Erro: "UserDatabase object has no attribute get_clinic_by_email"

Verifique se `DATABASE_URL` está configurado no `.env`:
```bash
echo $DATABASE_URL
```

### Usuários sem clínica

Execute o script de migração:
```bash
python migrate_existing_data.py
```
