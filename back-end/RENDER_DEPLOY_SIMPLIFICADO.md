# Deploy no Render - Guia Simplificado

## 🎉 **AUTO-MIGRAÇÃO ATIVADA!**

A migração do banco de dados agora é **100% AUTOMÁTICA**!

Quando você fizer o deploy, o sistema vai:
1. ✅ Detectar se a migração é necessária
2. ✅ Executar a migração SQL automaticamente
3. ✅ Migrar os dados existentes (usuários → clínica padrão)
4. ✅ Iniciar normalmente

**Você NÃO precisa fazer NADA manualmente!** 🚀

---

## 📋 **Passos para Deploy**

### 1️⃣ **Verificar Variáveis de Ambiente**

No painel do Render, confirme que estas variáveis estão configuradas:

- ✅ `DATABASE_URL` - URL do PostgreSQL
- ✅ `JWT_SECRET_KEY` - Chave secreta
- ✅ `GOOGLE_CLIENT_ID` - Google OAuth
- ✅ `GOOGLE_CLIENT_SECRET` - Google OAuth

### 2️⃣ **Fazer Deploy**

É só fazer o push! 🚀

```bash
git add .
git commit -m "feat: add multi-tenant support with auto-migration"
git push origin main
```

### 3️⃣ **Acompanhar Logs**

No Render, abra os logs e você verá:

```
🚀 Iniciando aplicação...
============================================================
VERIFICANDO MIGRAÇÕES DO BANCO DE DADOS
============================================================
⚠️  Migração necessária: coluna clinic_id não existe
🔄 Executando migração do banco de dados...
Executando SQL de migração...
✅ Migração executada com sucesso!
🔄 Migrando dados existentes...
✓ Clínica padrão criada: [UUID]
  ✓ SENDER user@example.com associado à clínica padrão
✅ Migração de dados concluída: X SENDERs migrados
============================================================
✅ AUTO-MIGRAÇÃO CONCLUÍDA COM SUCESSO
============================================================
```

Se a migração já foi executada antes, você verá:

```
============================================================
VERIFICANDO MIGRAÇÕES DO BANCO DE DADOS
============================================================
✓ Banco de dados já migrado (clinic_id existe)
Nenhuma migração necessária - banco já atualizado
```

### 4️⃣ **Verificar que está Online**

Acesse:

1. **Root:** https://prontuai-backend.onrender.com/
   ```json
   {
     "service": "ProntuAI Backend API",
     "version": "2.0.0",
     "status": "online"
   }
   ```

2. **Health:** https://prontuai-backend.onrender.com/health
   ```json
   {
     "status": "healthy",
     "service": "prontuai-backend"
   }
   ```

3. **Docs:** https://prontuai-backend.onrender.com/docs
   - Deve mostrar todos os novos endpoints

---

## 🔧 **Endpoints Admin (Opcional)**

Se a auto-migração falhar por algum motivo, você pode executar manualmente via API:

### **GET /v1/admin/status** (Verificar Status)

```bash
curl -H "Authorization: Bearer <admin-token>" \
  https://prontuai-backend.onrender.com/v1/admin/status
```

Resposta:
```json
{
  "status": "online",
  "database": {
    "migrations_needed": false,
    "migrations_status": "up-to-date"
  },
  "statistics": {
    "users": 4,
    "clinics": 1,
    "documents": 0
  }
}
```

### **POST /v1/admin/migrate** (Forçar Migração)

```bash
curl -X POST \
  -H "Authorization: Bearer <admin-token>" \
  https://prontuai-backend.onrender.com/v1/admin/migrate
```

Resposta:
```json
{
  "status": "success",
  "message": "Migração executada com sucesso!",
  "migrations_executed": true,
  "sql_migration": true,
  "data_migration": true
}
```

---

## ✅ **Checklist Pós-Deploy**

- [ ] Logs mostram "AUTO-MIGRAÇÃO CONCLUÍDA COM SUCESSO"
- [ ] Endpoint `/` retorna status "online"
- [ ] Endpoint `/health` retorna "healthy"
- [ ] Swagger Docs acessível em `/docs`
- [ ] Novos endpoints visíveis: `/v1/clinics`, `/v1/documents`, `/v1/admin`
- [ ] Front-end consegue listar clínicas (admin)
- [ ] Front-end consegue criar nova clínica (admin)

---

## 🎯 **Testando Sistema Multi-Tenant**

### 1. **Criar Nova Clínica (via Admin)**

No front-end:
1. Login como ADMIN
2. Sidebar → "Gerenciar Clínicas"
3. Criar nova clínica com email único

### 2. **Criar Usuário SENDER para a Clínica**

1. Sidebar → "Gerenciar Usuários"
2. Criar usuário com role "SENDER"
3. Sistema associa automaticamente à clínica

### 3. **Testar Isolamento**

1. Login como SENDER da Clínica A
2. Enviar documento → aparece na lista
3. Login como SENDER da Clínica B
4. Lista de documentos vazia (não vê da Clínica A) ✅

### 4. **Testar CHECKER (Global)**

1. Login como CHECKER
2. Vê documentos de TODAS as clínicas ✅

---

## 🆘 **Problemas?**

### "Migração falhou"
1. Verifique logs do Render
2. Use endpoint `/v1/admin/status` para ver o problema
3. Tente `/v1/admin/migrate` para re-executar

### "404 na rota /"
- Código antigo ainda no ar
- Aguarde redeploy completar

### "Column clinic_id does not exist"
- Auto-migração não executou
- Verifique logs de erro
- Use `/v1/admin/migrate` manualmente

---

## 🎊 **Pronto!**

Seu sistema multi-tenant está no ar! 🚀

Agora cada clínica credenciada pode:
- ✅ Fazer login com seu próprio email
- ✅ Ver apenas seus documentos
- ✅ Enviar documentos isoladamente

E o BRMED pode:
- ✅ Ver todos os documentos (CHECKER)
- ✅ Gerenciar clínicas e usuários (ADMIN)
