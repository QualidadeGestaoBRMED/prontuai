# Deploy no Render - Guia Completo

## 🚨 **IMPORTANTE: Migração do Banco de Dados**

Antes de fazer o deploy da nova versão com sistema multi-tenant, é necessário executar as migrações do banco de dados.

## 📋 **Passos para Deploy**

### 1. **Configurar Variáveis de Ambiente no Render**

Certifique-se de que as seguintes variáveis estão configuradas no painel do Render:

- `DATABASE_URL` - URL do PostgreSQL
- `JWT_SECRET_KEY` - Chave secreta para JWT
- `GOOGLE_CLIENT_ID` - ID do cliente Google OAuth
- `GOOGLE_CLIENT_SECRET` - Secret do Google OAuth
- `NEXT_PUBLIC_API_URL` (front-end) - URL da API

### 2. **Executar Migração SQL**

**ANTES** de fazer o deploy do código novo, você precisa executar a migração SQL no banco de dados.

#### Opção A: Via Shell do Render

1. Acesse o dashboard do Render
2. Vá em "Shell" do serviço back-end
3. Execute:

```bash
python run_migration.py
```

#### Opção B: Localmente (Conectando ao Banco de Produção)

1. Configure `DATABASE_URL` localmente com a URL do banco de produção:

```bash
export DATABASE_URL="postgresql://user:password@host:port/database"
```

2. Execute a migração:

```bash
python run_migration.py
```

#### Opção C: SQL Direto no Banco

Se preferir, execute o SQL diretamente:

```sql
-- Conteúdo do arquivo migrations/001_add_multi_tenant.sql
```

### 3. **Migrar Dados Existentes**

Após executar a migração SQL, migre os usuários existentes:

```bash
python migrate_existing_data.py
```

Isso vai:
- Criar clínica padrão "Grupo BRMED - Legado"
- Associar usuários SENDER à clínica padrão
- Manter CHECKER/ADMIN sem clínica

### 4. **Fazer Deploy do Código**

Agora pode fazer o deploy normalmente:

```bash
git add .
git commit -m "feat: add multi-tenant support"
git push origin main
```

O Render vai detectar o push e fazer o redeploy automaticamente.

### 5. **Verificar Deploy**

Após o deploy, acesse:

1. **Root endpoint:** https://prontuai-backend.onrender.com/
   - Deve retornar: `{"service": "ProntuAI Backend API", "status": "online", ...}`

2. **Health check:** https://prontuai-backend.onrender.com/health
   - Deve retornar: `{"status": "healthy", ...}`

3. **API Docs:** https://prontuai-backend.onrender.com/docs
   - Deve mostrar a documentação Swagger com novos endpoints

4. **Testar endpoints:**
   - GET `/v1/clinics` (com token ADMIN)
   - GET `/v1/documents` (com token SENDER/CHECKER)

## 🔧 **Troubleshooting**

### Erro: "column users.clinic_id does not exist"

❌ **Causa:** Migração SQL não foi executada

✅ **Solução:** Execute `python run_migration.py`

### Erro: "Clinic with email ... already exists"

❌ **Causa:** Tentando criar clínica que já existe

✅ **Solução:** Normal se já executou `migrate_existing_data.py` antes

### Aplicação retorna 404 em "/"

❌ **Causa:** Versão antiga do código sem rota raiz

✅ **Solução:** Faça deploy da versão atualizada do `main.py`

## 📝 **Checklist de Deploy**

- [ ] Variáveis de ambiente configuradas no Render
- [ ] Migração SQL executada (`python run_migration.py`)
- [ ] Dados migrados (`python migrate_existing_data.py`)
- [ ] Código commitado e pushed para repositório
- [ ] Deploy completado no Render
- [ ] Endpoint `/` retorna status online
- [ ] Endpoint `/health` retorna healthy
- [ ] Swagger Docs acessível em `/docs`
- [ ] Novos endpoints `/v1/clinics` e `/v1/documents` funcionando
- [ ] Front-end atualizado e apontando para API correta

## 🎯 **Validação Final**

Execute estes comandos para validar:

```bash
# 1. Verificar API online
curl https://prontuai-backend.onrender.com/

# 2. Health check
curl https://prontuai-backend.onrender.com/health

# 3. Listar clínicas (com token admin)
curl -H "Authorization: Bearer <admin-token>" https://prontuai-backend.onrender.com/v1/clinics

# 4. Listar documentos (com token qualquer)
curl -H "Authorization: Bearer <token>" https://prontuai-backend.onrender.com/v1/documents
```

Se todos retornarem respostas válidas (não 404/500), o deploy foi bem-sucedido! 🎉
