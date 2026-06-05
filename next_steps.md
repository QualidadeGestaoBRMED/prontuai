# Next Steps - ProntuAI

## Status Atual
O projeto está **funcional para desenvolvimento** mas precisa de trabalho para produção.
Identificados ~150 itens divididos em 4 prioridades.

---

## CRÍTICO (Obrigatório antes de produção)

### 1. Configurações de Segurança
- [ ] Criar arquivo `.env` no back-end (atualmente não existe, apenas `.env.example`)
- [ ] Criar arquivo `.env.local` no front-end
- [ ] Trocar JWT secret padrão em `back-end/app/core/auth.py:17`
  - Atual: `"dev-secret-key-change-in-production-please"`
  - Usar: valor aleatório seguro (>32 caracteres)
- [ ] Configurar CORS em `back-end/main.py:31`
  - Atual: aceita `*` (qualquer domínio)
  - Definir lista específica de origens permitidas
- [ ] Adicionar rate limiting nas APIs
  - Proteger contra DDoS e abuso
  - Implementar com `slowapi` ou similar

### 2. Implementações Incompletas
- [ ] Completar download de PDF
  - `front-end/app/historico/page.tsx:81,96` (TODO)
  - `front-end/app/pendentes/page.tsx:83,98` (TODO)
  - Remover `console.log("Download PDF:", result)`
- [ ] Consertar handlers de erro vazios em `back-end/app/api/v1_brmed.py`
  - Linha 34, 99, 185, 246 (4 `pass` statements que engolem erros)
  - Adicionar logging e tratamento adequado
- [ ] Configurar PostgreSQL para produção
  - Atualmente usa JSON como padrão (não escalável)
  - Definir `DATABASE_URL` em `.env`

### 3. Remover Debug
- [ ] Remover 89 `console.log` do front-end
  - Usar ferramenta de busca: `grep -r "console\." front-end/app`
  - Manter apenas em casos críticos com `console.error`
- [ ] Remover logs de debug ativos
  - `historico/page.tsx:74-78`
  - `pendentes/page.tsx:76-80`

---

## ALTA PRIORIDADE

### 4. Testes (Crítico)

#### Front-end
- [ ] Criar estrutura de testes
  - Configurar Jest + React Testing Library
  - Adicionar script `npm test`
- [ ] Testes unitários para componentes críticos
  - Upload de documentos
  - Sistema de notificações
  - Tabelas de resultados
  - Modals
- [ ] Testes E2E
  - Fluxo completo: login → upload → validação → histórico

#### Back-end
- [ ] Expandir cobertura de testes (atual ~30%, alvo 70%+)
- [ ] Adicionar testes para:
  - Endpoints API (`v1/users`, `v1/clinics`, `v1/documents`)
  - Isolamento multi-tenant
  - Autenticação/autorização
  - Casos de erro e edge cases
  - OCR e validação de serviços

### 5. Infraestrutura

- [ ] Implementar monitoramento
  - Configurar Sentry ou similar para error tracking
  - Adicionar APM (Application Performance Monitoring)
  - Setup uptime monitoring
- [ ] Sistema de logs centralizado
  - Atualmente loga apenas em filesystem
  - Migrar para ELK, CloudWatch ou similar
  - Configurar log rotation
- [ ] Backup do banco de dados
  - Estratégia de backup automático
  - Point-in-time recovery
  - Testar procedimento de restore
- [ ] Redis para job persistence
  - Atualmente in-memory (perde dados em restart)
  - Configurar Redis para async jobs
  - Documentar em `ASYNC_JOBS_API.md`
- [ ] CI/CD Pipeline
  - GitHub Actions ou similar
  - Testes automáticos em PR
  - Deploy automático em merge

### 6. Validação e Segurança

- [ ] Input sanitization
  - Validar/sanitizar todos inputs do usuário
  - Prevenir XSS em nomes de documentos e pacientes
- [ ] Validação de CPF
  - Atualmente apenas extração regex
  - Adicionar validação de checksum (dígitos verificadores)
- [ ] Validação de upload de arquivos
  - Limites de tamanho (MB)
  - Validação de tipo MIME (não apenas extensão)
  - Considerar scan de malware
- [ ] Error Boundaries no React
  - Prevenir crash completo da aplicação
  - Mostrar UI de erro amigável

---

## MÉDIA PRIORIDADE

### 7. Performance

- [ ] Cache para queries BRMED
  - Evitar chamadas repetidas e caras
  - Implementar com Redis
  - Definir TTL apropriado
- [ ] Connection pooling do banco
  - Configurar pool size adequado
  - Prevenir connection exhaustion
  - Documentar configurações
- [ ] WebSocket para notificações real-time
  - Atualmente usa polling via localStorage
  - Implementar Socket.io ou similar
  - Notificações push para checadores
- [ ] Otimização de bundle
  - Front-end: 352kB First Load (aceitável, mas pode melhorar)
  - Code splitting
  - Lazy loading de componentes
- [ ] Async processing com Celery
  - Mencionado em `proximos.txt`
  - OCR e BRMED scraping devem ser async
  - Liberar worker threads

### 8. Documentação

- [ ] README específico do projeto
  - Atualmente é boilerplate genérico do Next.js
  - Documentar: setup, env vars, arquitetura
- [ ] Documentação da API
  - Gerar OpenAPI/Swagger spec (FastAPI suporta)
  - Criar Postman collection
  - Documentar versionamento
- [ ] Guia de deployment
  - Existe `render.yaml` mas falta contexto
  - Procedimento de migração de banco
  - Estratégia de rollback
  - Setup de monitoring
- [ ] Documentação para usuários
  - Manual do usuário
  - Guia de onboarding
  - Expandir tour guiado (`tour-guiado.tsx`)

### 9. Autenticação e Autorização

- [ ] RBAC completo
  - Role-based access control existe mas enforcement mínimo
  - Audit logging de tentativas de acesso
- [ ] Refresh tokens
  - JWT tokens sem mecanismo de refresh
  - Adicionar estratégia de revogação
- [ ] Múltiplos providers de auth
  - Atualmente apenas Google OAuth
  - Adicionar fallback (email/password?)
  - Considerar 2FA
- [ ] Restrição de domínio (opcional)
  - Originalmente restrito a `@grupobrmed.com.br`
  - Avaliar se quer reativar para segurança

---

## BAIXA PRIORIDADE (Melhorias Futuras)

### 10. Features Phase 2

- [ ] Migrar localStorage para backend API
  - Planejado mas não implementado (ver `plan.md`)
  - Notificações persistentes no banco
  - REST API CRUD endpoints
- [ ] Analytics avançado
  - Dashboard de métricas
  - Relatórios de uso
  - KPIs de validação
- [ ] Dark mode
  - UI/UX melhoria
  - Preferência do usuário
- [ ] Acessibilidade (WCAG 2.1 AA)
  - Screen reader support
  - Keyboard navigation
  - Contraste de cores
- [ ] Internacionalização (i18n)
  - Suporte multi-idioma
  - Português + Inglês?
- [ ] Bulk actions
  - Validação em lote
  - Upload múltiplo
  - Exportação em massa

---

## Arquivos Que Precisam de Atenção Imediata

### Front-end
1. `/front-end/app/historico/page.tsx` - Completar PDF download
2. `/front-end/app/pendentes/page.tsx` - Completar PDF download
3. Criar `.env.local` com todas variáveis necessárias
4. Remover todos `console.log` statements
5. Adicionar Error Boundaries

### Back-end
1. `/back-end/.env` - Criar a partir de `.env.example` com valores seguros
2. `/back-end/app/api/v1_brmed.py` - Consertar exception handlers vazios
3. `/back-end/app/core/auth.py` - Trocar default JWT secret
4. `/back-end/main.py` - Configurar CORS adequadamente
5. Adicionar rate limiting middleware
6. Completar cobertura de testes

---

## Variáveis de Ambiente Necessárias

### Back-end `.env`
```bash
# OpenAI (Obrigatório)
OPENAI_API_KEY=sk-proj-xxxxx

# BRMED Scraping (Obrigatório)
BRMED_USERNAME=seu_usuario
BRMED_PASSWORD=sua_senha

# JWT (Obrigatório - TROCAR!)
JWT_SECRET_KEY=gerar-valor-aleatorio-seguro-aqui-32-chars-minimo

# Database (Recomendado para produção)
DATABASE_URL=postgresql://user:pass@host:5432/dbname

# AWS Textract (Opcional)
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=us-east-1
AWS_S3_BUCKET=
USE_TEXTRACT=false

# Redis (Recomendado para produção)
REDIS_URL=redis://localhost:6379

# CORS (Produção)
ALLOWED_ORIGINS=https://seu-dominio.com,https://www.seu-dominio.com
```

### Front-end `.env.local`
```bash
# NextAuth
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=mesmo-valor-do-jwt-secret-key-do-backend

# Google OAuth
GOOGLE_CLIENT_ID=seu-client-id
GOOGLE_CLIENT_SECRET=seu-client-secret

# API
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Cronograma Recomendado

### Semana 1: Segurança e Configuração
- Criar arquivos `.env`
- Trocar JWT secret
- Configurar CORS
- Adicionar rate limiting
- **Resultado:** Sistema seguro para deploy

### Semana 2: Completar Features e Error Handling
- Implementar download de PDF
- Consertar error handlers vazios
- Remover console.logs
- Adicionar Error Boundaries
- **Resultado:** Features completas e robustas

### Semana 3: Testes e Validação
- Escrever testes unitários (alvo 70% coverage)
- Testes de integração
- Setup CI/CD
- Adicionar validação de inputs
- **Resultado:** Código testado e confiável

### Semana 4: Infraestrutura e Performance
- Configurar PostgreSQL corretamente
- Implementar Redis para jobs
- Setup monitoramento (Sentry)
- Configurar backups
- Logs centralizados
- **Resultado:** Sistema production-ready

---

## Prioridade de Ação Imediata (Começar Hoje)

1. **Criar `.env` files** (15 min)
   - Copiar `.env.example` para `.env`
   - Preencher valores reais
   - Nunca commitar no git

2. **Trocar JWT secret** (5 min)
   - Gerar: `openssl rand -hex 32`
   - Substituir em `back-end/app/core/auth.py`

3. **Configurar CORS** (10 min)
   - Definir lista de domínios permitidos
   - Remover wildcard `*`

4. **Implementar download de PDF** (1-2h)
   - Remover TODOs em historico e pendentes
   - Testar funcionalidade

5. **Consertar error handlers** (30 min)
   - Substituir `pass` por logging adequado
   - Retornar erros apropriados

---

## Métricas de Sucesso

- [ ] **Segurança:** Nenhuma credencial hardcoded ou padrão
- [ ] **Testes:** Cobertura >70% back-end, >60% front-end
- [ ] **Performance:** API responde <500ms p95
- [ ] **Uptime:** >99.9% com monitoramento ativo
- [ ] **Documentação:** README completo + API docs
- [ ] **Deploy:** CI/CD automatizado com rollback

---

## Notas

- **Total de issues identificados:** ~150
- **Análise completa em:** `agentId: aab7660`
- **Status atual:** Funcional para dev, não production-ready
- **Tempo estimado para production:** 3-4 semanas (1 dev full-time)

---

**Última atualização:** 2026-01-08
**Próxima revisão:** Após completar itens CRÍTICOS
