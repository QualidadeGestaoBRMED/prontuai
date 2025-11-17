# Sistema de Roles e Autenticação - Implementação Completa

## ✅ BACK-END CONCLUÍDO

### Arquivos Criados

1. **`app/models/user.py`** - Modelos Pydantic
   - `UserRole` enum (ADMIN, CHECKER, SENDER)
   - `User`, `UserCreate`, `UserUpdate`, `UserInDB`, `TokenData`

2. **`app/core/database.py`** - Banco de dados JSON
   - CRUD completo de usuários
   - Admin padrão: `admin@grupobrmed.com.br`
   - Arquivo: `data/users.json`

3. **`app/core/auth.py`** - Autenticação JWT
   - `create_access_token()` - Gera JWT
   - `decode_token()` - Valida JWT
   - `get_current_user()` - Dependency para auth
   - `require_admin()`, `require_checker()`, `require_sender()` - Decorators

4. **`app/api/v1/auth.py`** - Endpoints de autenticação
   - `POST /v1/auth/google` - Login via Google OAuth
   - `GET /v1/auth/me` - Usuário atual
   - `POST /v1/auth/verify` - Verificar token

5. **`app/api/v1/users.py`** - Endpoints de usuários (ADMIN only)
   - `GET /v1/users` - Listar usuários
   - `POST /v1/users` - Criar usuário
   - `GET /v1/users/{id}` - Buscar por ID
   - `PATCH /v1/users/{id}` - Atualizar usuário
   - `DELETE /v1/users/{id}` - Desativar usuário (soft delete)

6. **Endpoints Protegidos**
   - `POST /v1/validacao` → Requer CHECKER ou ADMIN
   - `POST /v1/ocr` → Requer SENDER ou ADMIN

### Dependências Adicionadas ao requirements.txt

```txt
python-jose[cryptography]>=3.3.0  # JWT tokens
passlib[bcrypt]>=1.7.4  # Hashing (futuro)
email-validator>=2.0.0  # Validação de email
```

### Variáveis de Ambiente (.env)

```bash
# JWT Authentication
JWT_SECRET_KEY=sua-chave-super-secreta-mude-em-producao
JWT_EXPIRATION_HOURS=24
```

### Estrutura do Banco (data/users.json)

```json
{
  "users": {
    "uuid-123": {
      "id": "uuid-123",
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

## 🎯 Fluxo de Autenticação

```
┌──────────┐       1. Google OAuth        ┌─────────────┐
│          │ ────────────────────────────> │             │
│  Front   │                               │   NextAuth  │
│   -end   │ <──────────────────────────── │             │
│          │       2. email/name/id        └─────────────┘
└────┬─────┘
     │
     │ 3. POST /v1/auth/google
     │    {email, name, google_id}
     ▼
┌─────────────────────────────────────────────────────┐
│              Back-end (FastAPI)                      │
│                                                      │
│  1. Valida domínio @grupobrmed.com.br               │
│  2. Busca usuário no banco                          │
│  3. Verifica se está ativo                          │
│  4. Gera JWT com {email, role, name}                │
│  5. Retorna {access_token, user}                    │
└─────────────────────────────────────────────────────┘
     │
     │ 4. JWT Token
     ▼
┌──────────┐
│  Front   │  Armazena token
│  -end    │  Usa em todas as requests
└──────────┘  Header: Authorization: Bearer <token>
```

## 🔒 Matriz de Permissões

| Endpoint | ADMIN | CHECKER | SENDER |
|----------|-------|---------|--------|
| `POST /v1/auth/google` | ✅ | ✅ | ✅ |
| `GET /v1/auth/me` | ✅ | ✅ | ✅ |
| `POST /v1/validacao` | ✅ | ✅ | ❌ |
| `POST /v1/ocr` | ✅ | ❌ | ✅ |
| `POST /v1/workflow/processar` | ✅ | ❌ | ✅ |
| `GET /v1/users` | ✅ | ❌ | ❌ |
| `POST /v1/users` | ✅ | ❌ | ❌ |
| `PATCH /v1/users/{id}` | ✅ | ❌ | ❌ |
| `DELETE /v1/users/{id}` | ✅ | ❌ | ❌ |
| `POST /v1/brmed` | ✅ | ✅ | ✅ |
| `POST /v1/faq` | ✅ | ✅ | ✅ |

## 📖 Documentação Criada

1. **AUTH_SETUP.md** - Guia completo de autenticação
   - Como funciona o sistema
   - Todos os endpoints
   - Exemplos de uso com curl
   - Troubleshooting

2. **POSTGRES_MIGRATION.md** - Migração para PostgreSQL
   - Passo a passo completo
   - Código SQLAlchemy pronto
   - Plano de migração gradual
   - Docker Compose com PostgreSQL

3. **SISTEMA_ROLES_COMPLETO.md** (este arquivo)
   - Visão geral da implementação
   - O que falta fazer no front-end

## 🚀 Testando o Sistema

### 1. Iniciar o servidor

```bash
cd back-end
source venv/bin/activate
uvicorn main:app --reload
```

### 2. Login como admin (simular)

```bash
curl -X POST http://localhost:8000/v1/auth/google \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@grupobrmed.com.br",
    "name": "Administrador",
    "google_id": "fake-google-id"
  }'
```

**Resposta:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "email": "admin@grupobrmed.com.br",
    "name": "Administrador",
    "role": "ADMIN",
    "is_active": true
  }
}
```

Copie o `access_token`.

### 3. Criar novo usuário (como admin)

```bash
TOKEN="cole-o-token-aqui"

curl -X POST http://localhost:8000/v1/users \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "checker@grupobrmed.com.br",
    "name": "João Checker",
    "role": "CHECKER"
  }'
```

### 4. Listar usuários

```bash
curl http://localhost:8000/v1/users \
  -H "Authorization: Bearer $TOKEN"
```

### 5. Testar permissões

```bash
# Login como checker
curl -X POST http://localhost:8000/v1/auth/google \
  -H "Content-Type: application/json" \
  -d '{
    "email": "checker@grupobrmed.com.br",
    "name": "João Checker",
    "google_id": "fake-id-2"
  }'

CHECKER_TOKEN="token-do-checker"

# Deve FUNCIONAR (CHECKER pode validar)
curl -X POST http://localhost:8000/v1/validacao \
  -H "Authorization: Bearer $CHECKER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "cpf": "12345678901",
    "exames_obrigatorios": ["Hemograma"],
    "exames_enviados": ["Hemograma Completo"]
  }'

# Deve retornar 403 (CHECKER não pode gerenciar usuários)
curl http://localhost:8000/v1/users \
  -H "Authorization: Bearer $CHECKER_TOKEN"
```

## 📋 TO-DO: FRONT-END

### 1. Integrar NextAuth com Back-end

**Arquivo:** `front-end/app/api/auth/[...nextauth]/route.ts`

```typescript
import NextAuth from "next-auth";
import GoogleProvider from "next-auth/providers/google";

const authOptions = {
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID as string,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET as string,
    }),
  ],
  pages: {
    signIn: "/login",
  },
  callbacks: {
    async signIn({ profile }: { profile?: Profile }) {
      // Validar domínio
      if (!profile?.email?.endsWith("@grupobrmed.com.br")) {
        return false;
      }

      // Chamar back-end para obter JWT
      try {
        const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/v1/auth/google`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email: profile.email,
            name: profile.name,
            google_id: profile.sub
          })
        });

        if (!response.ok) {
          console.error('Auth failed:', await response.text());
          return false;
        }

        const data = await response.json();

        // Armazenar token e user data
        // (será acessível em jwt e session callbacks)
        return data;

      } catch (error) {
        console.error('Auth error:', error);
        return false;
      }
    },

    async jwt({ token, user, account }) {
      // Primeiro login: adicionar dados do back-end ao token
      if (account && user) {
        token.accessToken = user.access_token;
        token.user = user.user;
      }
      return token;
    },

    async session({ session, token }) {
      // Adicionar dados do token à session (acessível no client)
      session.accessToken = token.accessToken;
      session.user = token.user;
      return session;
    }
  }
};

const handler = NextAuth(authOptions);
export { handler as GET, handler as POST };
```

### 2. Atualizar types do NextAuth

**Arquivo:** `front-end/types/next-auth.d.ts`

```typescript
import NextAuth from "next-auth";

declare module "next-auth" {
  interface Session {
    accessToken: string;
    user: {
      id: string;
      name: string;
      email: string;
      image: string;
      role: "ADMIN" | "CHECKER" | "SENDER";
      is_active: boolean;
    };
  }

  interface User {
    access_token: string;
    user: {
      id: string;
      email: string;
      name: string;
      role: "ADMIN" | "CHECKER" | "SENDER";
      is_active: boolean;
    };
  }
}
```

### 3. Hook de Permissões

**Criar:** `front-end/hooks/usePermissions.ts`

```typescript
import { useSession } from "next-auth/react";

export function usePermissions() {
  const { data: session } = useSession();

  const user = session?.user;
  const role = user?.role;

  return {
    user,
    role,
    isAdmin: role === "ADMIN",
    isChecker: role === "CHECKER" || role === "ADMIN",
    isSender: role === "SENDER" || role === "ADMIN",
    canManageUsers: role === "ADMIN",
    canValidateExams: role === "CHECKER" || role === "ADMIN",
    canSendDocuments: role === "SENDER" || role === "ADMIN",
  };
}
```

### 4. Guard de Rota

**Criar:** `front-end/components/require-role.tsx`

```typescript
"use client";

import { useSession } from "next-auth/react";
import { redirect } from "next/navigation";
import { ReactNode } from "react";

interface RequireRoleProps {
  children: ReactNode;
  allowedRoles: Array<"ADMIN" | "CHECKER" | "SENDER">;
  fallback?: ReactNode;
}

export function RequireRole({ children, allowedRoles, fallback }: RequireRoleProps) {
  const { data: session, status } = useSession();

  if (status === "loading") {
    return <div>Carregando...</div>;
  }

  if (status === "unauthenticated") {
    redirect("/login");
  }

  const userRole = session?.user?.role;

  if (!userRole || !allowedRoles.includes(userRole)) {
    if (fallback) {
      return <>{fallback}</>;
    }
    return (
      <div className="p-8 text-center">
        <h1 className="text-2xl font-bold text-red-600">Acesso Negado</h1>
        <p>Você não tem permissão para acessar esta página.</p>
      </div>
    );
  }

  return <>{children}</>;
}
```

### 5. Painel Admin

**Criar:** `front-end/app/admin/users/page.tsx`

```typescript
"use client";

import { RequireRole } from "@/components/require-role";
import { useSession } from "next-auth/react";
import { useState, useEffect } from "react";

export default function UsersAdminPage() {
  const { data: session } = useSession();
  const [users, setUsers] = useState([]);

  useEffect(() => {
    if (session?.accessToken) {
      fetch(`${process.env.NEXT_PUBLIC_API_URL}/v1/users`, {
        headers: {
          'Authorization': `Bearer ${session.accessToken}`
        }
      })
      .then(res => res.json())
      .then(setUsers);
    }
  }, [session]);

  return (
    <RequireRole allowedRoles={["ADMIN"]}>
      <div className="p-8">
        <h1 className="text-3xl font-bold mb-6">Gerenciar Usuários</h1>

        {/* Tabela de usuários */}
        {/* Botão para criar usuário */}
        {/* Modal de edição */}
      </div>
    </RequireRole>
  );
}
```

### 6. Proteger Páginas Existentes

**Atualizar:** `front-end/app/checagem/page.tsx`

```typescript
import { RequireRole } from "@/components/require-role";

export default function CheckoutPage() {
  return (
    <RequireRole allowedRoles={["ADMIN", "CHECKER"]}>
      {/* Conteúdo existente */}
    </RequireRole>
  );
}
```

**Atualizar:** `front-end/app/pendentes/page.tsx`

```typescript
import { RequireRole } from "@/components/require-role";

export default function PendentesPage() {
  return (
    <RequireRole allowedRoles={["ADMIN", "SENDER"]}>
      {/* Conteúdo existente */}
    </RequireRole>
  );
}
```

### 7. Navbar com Role

**Atualizar navbar para mostrar apenas links permitidos:**

```typescript
import { usePermissions } from "@/hooks/usePermissions";

export function Navbar() {
  const { canValidateExams, canSendDocuments, canManageUsers } = usePermissions();

  return (
    <nav>
      {canValidateExams && <Link href="/checagem">Checagem</Link>}
      {canSendDocuments && <Link href="/pendentes">Pendentes</Link>}
      {canManageUsers && <Link href="/admin/users">Usuários</Link>}
    </nav>
  );
}
```

## ⚡ Próximos Passos

1. [ ] Commit do back-end
2. [ ] Implementar integração NextAuth
3. [ ] Criar hook usePermissions
4. [ ] Criar componente RequireRole
5. [ ] Proteger páginas existentes
6. [ ] Criar painel admin de usuários
7. [ ] Testar fluxo completo
8. [ ] Deploy

## 🔐 Segurança

### ✅ Implementado (Back-end)
- JWT com expiração (24h)
- Validação de domínio de email
- RBAC (Role-Based Access Control)
- Proteção em todos os endpoints sensíveis
- Soft delete (auditoria)
- Logs de auditoria

### ⚠️ Recomendações Produção
- HTTPS obrigatório
- Mudar `JWT_SECRET_KEY`
- Rate limiting
- Refresh tokens
- 2FA (opcional)
- PostgreSQL ao invés de JSON
- Backup automático
