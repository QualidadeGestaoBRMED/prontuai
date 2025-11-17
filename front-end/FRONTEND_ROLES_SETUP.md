# Sistema de Roles - Front-end Implementação

## ✅ Implementação Completa

### Arquivos Criados/Modificados

1. **`.env.local.example`** - Template de variáveis de ambiente
   - `NEXT_PUBLIC_API_URL` - URL do back-end
   - `NEXTAUTH_SECRET` - Chave secreta do NextAuth

2. **`app/api/auth/[...nextauth]/route.ts`** - Integração com back-end
   - Chama `POST /v1/auth/google` após Google OAuth
   - Obtém JWT do back-end
   - Armazena token e dados do usuário na session

3. **`types/next-auth.d.ts`** - Types do NextAuth
   - Adiciona `accessToken` à session
   - Adiciona `role` e `is_active` ao user
   - Suporte a JWT types

4. **`hooks/usePermissions.ts`** - Hook de permissões
   - `isAdmin`, `isChecker`, `isSender`
   - `canManageUsers`, `canValidateExams`, `canSendDocuments`
   - `isLoading`, `isAuthenticated`

5. **`components/require-role.tsx`** - Guard de rota
   - Protege componentes baseado em roles
   - Redireciona para login se não autenticado
   - Mostra mensagem de acesso negado se não autorizado

6. **`app/checagem/page.tsx`** - Protegido com RequireRole
   - Requer: ADMIN ou CHECKER

7. **`app/pendentes/page.tsx`** - Protegido com RequireRole
   - Requer: ADMIN ou SENDER

8. **`app/admin/users/page.tsx`** - Painel admin (NOVO)
   - Requer: Apenas ADMIN
   - Lista usuários
   - Criar novo usuário
   - Editar usuário (nome, role)
   - Ativar/desativar usuário

## 🚀 Como Usar

### 1. Configurar Variáveis de Ambiente

Crie `.env.local`:

```bash
# Copiar do .env.local.example
cp .env.local.example .env.local

# Editar e preencher
nano .env.local
```

Valores necessários:
```bash
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=qualquer-string-aleatoria-aqui
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 2. Iniciar Desenvolvimento

```bash
npm install  # Se necessário
npm run dev
```

### 3. Fluxo de Autenticação

```
1. Usuário clica em "Login with Google"
2. Google OAuth retorna email/name/id
3. NextAuth chama back-end: POST /v1/auth/google
4. Back-end valida e retorna JWT + dados do usuário
5. NextAuth armazena na session
6. Front-end usa session.user.role para controlar acesso
```

## 🔐 Usando Permissões

### Opção 1: Hook usePermissions

```tsx
import { usePermissions } from "@/hooks/usePermissions";

export function MyComponent() {
  const { canManageUsers, canValidateExams, isAdmin } = usePermissions();

  return (
    <div>
      {canManageUsers && <AdminButton />}
      {canValidateExams && <ValidationPanel />}
      {isAdmin && <SuperSecretFeature />}
    </div>
  );
}
```

### Opção 2: Componente RequireRole

```tsx
import { RequireRole } from "@/components/require-role";

export function ProtectedPage() {
  return (
    <RequireRole allowedRoles={["ADMIN", "CHECKER"]}>
      <div>Conteúdo protegido</div>
    </RequireRole>
  );
}
```

### Opção 3: useSession Diretamente

```tsx
import { useSession } from "next-auth/react";

export function MyComponent() {
  const { data: session } = useSession();
  const userRole = session?.user?.role;

  if (userRole === "ADMIN") {
    return <AdminView />;
  }

  return <RegularView />;
}
```

## 🎯 Matriz de Acesso

| Página/Recurso | ADMIN | CHECKER | SENDER |
|----------------|-------|---------|--------|
| `/checagem` | ✅ | ✅ | ❌ |
| `/pendentes` | ✅ | ❌ | ✅ |
| `/admin/users` | ✅ | ❌ | ❌ |
| `/historico` | ✅ | ✅ | ✅ |
| `/chat` | ✅ | ✅ | ✅ |
| `/insights` | ✅ | ✅ | ✅ |

## 📊 Painel Admin

Acesse: `http://localhost:3000/admin/users`

**Funcionalidades:**
- ✅ Listar todos os usuários
- ✅ Criar novo usuário
  - Email (@grupobrmed.com.br obrigatório)
  - Nome
  - Role (ADMIN, CHECKER, SENDER)
- ✅ Editar usuário
  - Alterar nome
  - Alterar role
- ✅ Ativar/desativar usuário

**UI Features:**
- Tabela responsiva
- Badges coloridos por role
- Badges de status ativo/inativo
- Modais para criar/editar
- Toast notifications (Sonner)
- Loading states

## 🔧 Personalizações

### Adicionar Nova Role

1. **Back-end:** Adicionar em `app/models/user.py`
```python
class UserRole(str, Enum):
    ADMIN = "ADMIN"
    CHECKER = "CHECKER"
    SENDER = "SENDER"
    VIEWER = "VIEWER"  # ← Nova role
```

2. **Front-end:** Atualizar types
```typescript
// types/next-auth.d.ts
role: "ADMIN" | "CHECKER" | "SENDER" | "VIEWER";

// hooks/usePermissions.ts
export type UserRole = "ADMIN" | "CHECKER" | "SENDER" | "VIEWER";
```

3. **Front-end:** Adicionar permissões
```typescript
// hooks/usePermissions.ts
const isViewer = role === "VIEWER";
const canViewOnly = role === "VIEWER" || role === "ADMIN";
```

### Proteger Nova Página

```tsx
// app/nova-pagina/page.tsx
import { RequireRole } from "@/components/require-role";

export default function NovaPagina() {
  return (
    <RequireRole allowedRoles={["ADMIN"]}>
      <div>Conteúdo protegido</div>
    </RequireRole>
  );
}
```

### Customizar Mensagem de Acesso Negado

```tsx
<RequireRole
  allowedRoles={["ADMIN"]}
  fallback={
    <div>Você precisa ser administrador para acessar esta página.</div>
  }
>
  <AdminContent />
</RequireRole>
```

## 🧪 Testando

### 1. Testar Login

```bash
# Iniciar back-end
cd ../back-end
source venv/bin/activate
uvicorn main:app --reload

# Iniciar front-end (outro terminal)
cd front-end
npm run dev
```

Acesse: `http://localhost:3000/login`

### 2. Testar Permissões

**Como ADMIN:**
1. Login com `admin@grupobrmed.com.br`
2. Acesse `/admin/users` (deve funcionar)
3. Acesse `/checagem` (deve funcionar)
4. Acesse `/pendentes` (deve funcionar)

**Como CHECKER:**
1. Criar usuário checker via painel admin
2. Logout e login como checker
3. Acesse `/checagem` (deve funcionar)
4. Acesse `/pendentes` (deve mostrar "Acesso Negado")
5. Acesse `/admin/users` (deve mostrar "Acesso Negado")

**Como SENDER:**
1. Criar usuário sender via painel admin
2. Logout e login como sender
3. Acesse `/pendentes` (deve funcionar)
4. Acesse `/checagem` (deve mostrar "Acesso Negado")

### 3. Testar API Calls

Todas as chamadas ao back-end devem incluir o token:

```typescript
const response = await fetch(`${API_URL}/v1/validacao`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${session.accessToken}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({...})
});
```

## ⚠️ Troubleshooting

### "Acesso Negado" mesmo sendo admin

1. Verificar se fez login após criar usuário no back-end
2. Limpar cache do navegador
3. Fazer logout e login novamente
4. Verificar se `session.user.role` está correto (DevTools → Application → Storage)

### Token JWT expirado

Token expira em 24h. Faça logout e login novamente.

### Erro "Usuário não cadastrado"

O admin precisa criar o usuário no back-end primeiro (`POST /v1/users`).
Não basta ter conta Google, precisa estar no banco de usuários.

### API retorna 403 mesmo com token

1. Verificar se token está no header: `Authorization: Bearer <token>`
2. Verificar se usuário tem a role necessária
3. Verificar logs do back-end: `tail -f logs/app.log`

### Environment variables não carregam

1. Arquivo deve ser `.env.local` (não `.env`)
2. Reiniciar servidor Next.js após criar/editar `.env.local`
3. Variáveis client-side devem ter prefixo `NEXT_PUBLIC_`

## 📝 Próximos Passos

### Melhorias Sugeridas

1. **Refresh Token**
   - Implementar refresh automático do JWT
   - Evitar que usuário precise fazer login a cada 24h

2. **Auditoria**
   - Registrar quem criou/editou usuários
   - Histórico de mudanças de permissões

3. **Bulk Actions**
   - Desativar múltiplos usuários de uma vez
   - Alterar role de múltiplos usuários

4. **Filtros e Busca**
   - Buscar usuários por email/nome
   - Filtrar por role
   - Filtrar por status (ativo/inativo)

5. **Paginação**
   - Implementar quando houver muitos usuários
   - Backend já suporta, falta frontend

6. **2FA (Opcional)**
   - Autenticação de dois fatores para admins
   - Requer SMS/TOTP

## 🔗 Links Úteis

- [NextAuth.js Docs](https://next-auth.js.org/)
- [Back-end AUTH_SETUP.md](../back-end/AUTH_SETUP.md)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [JWT.io](https://jwt.io/) - Decodificar tokens para debug
