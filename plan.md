# Plano: Refatoração da tela `/enviar-docs` com Persistência e Central de Notificações

**Status**: 🚧 Em Desenvolvimento - Sprints 1, 2 e Correções Críticas Concluídos
**Início**: 2025-10-29
**Última Atualização**: 2025-10-30 (23h)
**Estimativa**: 4 dias (~32 horas)

## 🔥 Correções Críticas Implementadas (2025-10-30)

### ✅ 1. Modal TypeError Fix
**Problema**: `result.result.ocr_result.exames_extraidos.map is not a function`
- Backend retorna exames como string `"HEMOGRAMA, ERITROGRAMA..."` mas código esperava array
- Modal crashava ao clicar "Ver Detalhes"

**Solução**: Função helper `getExamesArray()` em `document-details-modal.tsx` (linhas 36-44)
- Detecta automaticamente se valor é string ou array
- Converte strings separadas por vírgula em arrays
- Funciona transparentemente com ambos os formatos

**Arquivos Modificados**:
- `/front-end/components/document-details-modal.tsx`

**Build Status**: ✅ Passou

---

### ✅ 2. SSE Real-Time Streaming Fix
**Problema**: Eventos SSE chegavam todos de uma vez no final (buffer de 386 bytes com 4 eventos) em vez de progressivamente
- Backend acumulava eventos em lista e só enviava após conclusão
- Frontend recebia 30%, 40%, 60%, 70% simultaneamente aos ~24s

**Solução**: Refatoração para `asyncio.Queue` + background task em `v1_brmed.py` (linhas 76-141)
- **Queue**: Eventos colocados imediatamente quando gerados
- **Background Task**: Processamento paralelo via `asyncio.create_task()`
- **Consumer Loop**: Consome fila em tempo real com timeout de 0.5s
- Logs detalhados: `[SSE]` para rastreamento

**Arquivos Modificados**:
- `/back-end/app/api/v1_brmed.py`

**Syntax Check**: ✅ Compilação Python bem-sucedida

**Impacto**: Progresso agora aparece em tempo real durante os ~24s de processamento

---

---

## 📋 Visão Geral

Transformar `/enviar-docs` em uma aplicação com processamento rastreável, central de notificações integrada, e consulta histórica de resultados.

---

## 🎯 Objetivos

- [x] **Central de Notificações**: Aba dropdown com processos ativos e histórico ✅
- [x] **Sistema de Notificações Base**: Context API, tipos TypeScript, localStorage persistence ✅
- [x] **Notification Bell**: Sino com badge e integração no sidebar ✅
- [ ] **Barra de Processamento Minimizável**: Durante processamento ativo
- [ ] **Persistência de Processos**: Consultar resultados após conclusão
- [ ] **Tabela de Resultados**: Filtros, downloads, e integração com `/checagem`
- [ ] **UI Dinâmica**: Estados visuais claros (upload → processando → concluído → histórico)
- [ ] **Roles de Usuário**: Separar submissores de revisores

---

## 🏗️ Arquitetura de Notificações

### **Sistema de Notificações**

```
┌─────────────────────────────────────────────┐
│ Header/Navbar                               │
│                                             │
│  Logo    Menu    [🔔 3] ← Sino com badge  │
└─────────────────────────────────────────────┘
                      │
                      │ (clique)
                      ▼
          ┌───────────────────────────────┐
          │ Notification Center       │
          │                           │
          │ ▶ PROCESSOS ATIVOS (1)   │
          │   📄 documento.pdf        │
          │   ━━━━━━━━━ 65% [OCR]   │
          │   [Ver Detalhes]         │
          │                           │
          │ ▶ CONCLUÍDOS HOJE (2)    │
          │   ✅ batch-10-docs.zip   │
          │   ❌ erro-documento.pdf  │
          │   [Ver Resultados]       │
          │                           │
          │ ▶ HISTÓRICO              │
          │   📋 Ver todos →         │
          └───────────────────────────────┘
```

### **Estados da Notificação**

**1. Durante Processamento Ativo**
- **Barra no topo** (expanded) com progresso detalhado
- **Sino com badge** (número de processos ativos)
- Usuário clica "Minimizar" → barra desaparece, mas sino permanece
- Sino abre dropdown mostrando processo ativo ao vivo

**2. Processamento Concluído**
- Barra desaparece automaticamente após 5s
- **Badge no sino fica vermelho** (notificação não lida)
- Dropdown mostra "Concluídos Hoje" com novo item
- Usuário clica para ver → marca como lida

**3. Sem Processos Ativos**
- Sino sem badge (ou badge "0")
- Dropdown mostra apenas histórico

---

## 📦 Componentes a Criar/Modificar

### **✅ = Concluído | 🔄 = Em Progresso | ⏳ = Pendente**

### **1. Notification Center** ⏳
**Arquivo**: `/front-end/components/notification-center.tsx`

**Estrutura de Dados**:
```typescript
interface Notification {
  id: string
  type: 'process_started' | 'process_completed' | 'process_error' | 'review_action'
  title: string
  message: string
  timestamp: Date
  read: boolean
  actionUrl?: string
  metadata?: {
    processId?: string
    batchId?: string
    documentCount?: number
    status?: string
  }
}
```

**Features**:
- Sheet/Dropdown do shadcn que abre ao clicar no sino
- Seções expansíveis: Ativos / Concluídos Hoje / Histórico
- Processos ativos mostram progresso em tempo real
- Notificações concluídas com ações: [Ver Resultados] [Baixar]
- Badge de não lidas
- Botão "Marcar todas como lidas"
- Auto-refresh a cada 5s quando aberto

**Tipos de Notificação**:
- 🔵 Processo iniciado: "Processando 10 documentos..."
- ✅ Processo concluído com sucesso: "10 documentos aprovados!"
- ⚠️ Processo concluído com pendências: "8 aprovados, 2 para revisão"
- ❌ Processo com erro: "Falha no processamento de documento.pdf"
- 👤 Ação de revisão: "Seu documento foi aprovado por maria@grupobrmed.com.br"

---

### **2. Notification Bell Icon** ⏳
**Arquivo**: `/front-end/components/notification-bell.tsx`

**Localização**: AppSidebar ou Header

```tsx
<NotificationBell
  unreadCount={3}
  hasActiveProcess={true}
  onClick={() => setNotificationCenterOpen(true)}
/>
```

**Estados Visuais**:
- Badge vermelho com número de não lidas
- Ícone pulsando quando há processo ativo
- Animação ao receber nova notificação

---

### **3. Process Progress Bar** ⏳
**Arquivo**: `/front-end/components/process-progress-bar.tsx`

**Quando mostrar**:
- Apenas quando há processo ativo E usuário não minimizou
- Posição: Topo da página (abaixo do header)

**Layout**:
```
┌──────────────────────────────────────────────────────────────┐
│ 🔄 Processando lote #123 (5 documentos)                      │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 60% - Validando exames   │
│ Documento atual: prontuario-joao-silva.pdf (3/5)             │
│                                  [Minimizar] [Ver Detalhes]  │
└──────────────────────────────────────────────────────────────┘
```

**Persistência**:
- Estado salvo em `localStorage.activeProgressBar`
- Se usuário minimizar: `{shown: false, processId: '123'}`
- Se voltar à página `/enviar-docs`: pode reaparecer

---

### **4. Context Global de Notificações** ⏳
**Arquivo**: `/front-end/hooks/use-notifications.tsx`

```typescript
interface NotificationContext {
  // Notificações
  notifications: Notification[]
  unreadCount: number
  addNotification: (notification: Omit<Notification, 'id' | 'timestamp'>) => void
  markAsRead: (id: string) => void
  markAllAsRead: () => void
  clearHistory: () => void

  // Processos ativos
  activeProcesses: ProcessNotification[]
  startProcess: (batchId: string, files: File[]) => void
  updateProcess: (processId: string, update: Partial<ProcessNotification>) => void
  completeProcess: (processId: string, results: ProcessResult[]) => void

  // UI State
  notificationCenterOpen: boolean
  setNotificationCenterOpen: (open: boolean) => void
  progressBarMinimized: boolean
  minimizeProgressBar: () => void
  showProgressBar: () => void
}
```

**Persistência**:
- `localStorage.notifications` → últimos 30 dias
- `localStorage.activeProcess` → processo atual
- `localStorage.progressBarState` → minimizado ou não

---

### **5. Página `/enviar-docs` Refatorada** ⏳
**Arquivo**: `/front-end/app/enviar-docs/page.tsx`

**Estados Visuais**:

#### **A. Estado Inicial (SEM processo ativo)**
```
┌─────────────────────────────────────┐
│ 📤 Enviar Documentos               │
│                                     │
│  ┌──────────────────────────────┐  │
│  │  Arraste arquivos aqui       │  │
│  │  ou clique para selecionar   │  │
│  │  (Máximo 10 arquivos)        │  │
│  └──────────────────────────────┘  │
│                                     │
│  [Botão: Processar Documentos]     │
│                                     │
│  💡 Dica: Acompanhe o progresso    │
│     pelo sino de notificações ↗    │
└─────────────────────────────────────┘
```

#### **B. Durante Processamento (COM processo ativo)**

**Se barra NÃO minimizada**:
```
┌──────────────────────────────────────────────┐
│ [BARRA DE PROGRESSO NO TOPO]                │
└──────────────────────────────────────────────┘

┌─────────────────────────────────────┐
│ ⏳ Processamento em Andamento      │
│                                     │
│  "Seu lote está sendo processado"  │
│                                     │
│  [Stepper Vertical]                 │
│  ✅ 1. Upload concluído            │
│  🔄 2. OCR em andamento (60%)      │
│  ⏸  3. Consulta BRMED              │
│  ⏸  4. Validação                   │
│  ⏸  5. Finalização                 │
│                                     │
│  📄 Documentos:                    │
│  ✅ doc1.pdf (concluído)           │
│  🔄 doc2.pdf (processando)         │
│  ⏳ doc3.pdf (aguardando)          │
└─────────────────────────────────────┘
```

**Se barra minimizada**:
```
┌─────────────────────────────────────┐
│ ⏳ Processamento em Andamento      │
│                                     │
│  "Acompanhe o progresso pelo       │
│   sino de notificações no topo"    │
│                                     │
│  [Botão: Ver Progresso Aqui]       │
│                                     │
│  (ou continue navegando...)         │
└─────────────────────────────────────┘
```

#### **C. Após Conclusão (SEM processo ativo + tem histórico)**
```
┌─────────────────────────────────────┐
│ 📂 Resultados de Processamento     │
│                                     │
│  Filtros: [CPF] [Status] [Data]    │
│  [Exportar CSV] [Novo Lote]        │
│                                     │
│  ┌─────────────────────────────┐   │
│  │ Tabela de Documentos        │   │
│  │ CPF | Paciente | Status     │   │
│  │ Download | Ver Detalhes     │   │
│  └─────────────────────────────┘   │
└─────────────────────────────────────┘
```

---

### **6. Tabela de Resultados** ⏳
**Arquivo**: `/front-end/components/results-table.tsx`

**Colunas**:
- CPF (formatado)
- Nome do Paciente
- Data de Upload
- Status (badge colorido: ✅ Aprovado | ⚠️ Pendente | ❌ Rejeitado)
- Exames Faltantes (contador)
- Exames Extras (contador)
- Ações: [Download PDF] [Download JSON] [Ver Detalhes]

**Filtros**:
- Busca por CPF
- Dropdown de Status
- Range de datas

**Integração com `/checagem`**:
- Documentos com status "rejeitado" aparecem automaticamente em `/checagem`
- Botão "Enviar para Revisão" cria entrada na fila de checagem

---

### **7. Modal de Detalhes do Resultado** ⏳
**Arquivo**: `/front-end/components/result-detail-modal.tsx`

**Conteúdo**:
- Visualização completa do resultado
- Tabela de comparação de exames
- Análise GPT
- Logs de processamento
- Botões de ação (Aprovar/Rejeitar/Reprocessar)

---

## 🗄️ Estrutura de Dados

### **Notificações**

```typescript
// /front-end/types/notification.ts
type NotificationType =
  | 'process_started'
  | 'process_completed'
  | 'process_error'
  | 'review_approved'
  | 'review_rejected'
  | 'system_message'

interface Notification {
  id: string
  type: NotificationType
  title: string
  message: string
  timestamp: Date
  read: boolean
  actionUrl?: string  // Para navegação direta
  actionLabel?: string  // Ex: "Ver Resultados", "Baixar PDF"
  metadata?: {
    processId?: string
    batchId?: string
    documentId?: string
    cpf?: string
    reviewerEmail?: string
  }
  icon?: React.ReactNode  // Customizado por tipo
  variant?: 'default' | 'success' | 'error' | 'warning'
}
```

### **Processo Ativo**

```typescript
interface ProcessNotification {
  id: string
  batchId: string
  filename: string  // Se único documento, ou nome do lote
  documentCount: number
  status: 'processing' | 'completed' | 'error'
  progress: number  // 0-100
  currentStep: 'upload' | 'ocr' | 'brmed' | 'validation' | 'completed'
  stepMessage: string  // Ex: "Validando exames..."
  startedAt: Date
  completedAt?: Date
  documents: {
    filename: string
    status: 'pending' | 'processing' | 'completed' | 'error'
    progress: number
  }[]
}
```

### **Resultado de Processo**

```typescript
interface ProcessResult {
  id: string
  batchId: string  // Agrupa documentos do mesmo upload
  filename: string
  cpf: string
  patientName: string
  uploadedAt: Date
  processedAt: Date
  status: 'approved' | 'rejected' | 'pending_review'
  rejectionReason?: string
  examesFaltantes: number
  examesExtras: number
  result: DocumentProcessingResult  // Tipo existente
  submittedBy: string  // Email do usuário (vem do NextAuth)
  reviewedBy?: string
  reviewedAt?: Date
}
```

### **localStorage Keys**

```typescript
// Notificações (últimos 30 dias, máx 100)
'notifications': Notification[]

// Processo ativo (só 1 por vez)
'active_process': ProcessNotification | null

// Histórico de resultados
'process_results': ProcessResult[]

// Estado da UI
'notification_center_preferences': {
  lastOpenedAt: Date
  autoMarkAsReadOnClick: boolean
}

'progress_bar_state': {
  minimized: boolean
  processId: string
}
```

---

## 🎨 Componentes shadcn/ui Necessários

### **A Instalar**

```bash
# Já instalados (verificar):
- button
- card
- badge
- progress
- dialog

# A instalar:
pnpm dlx shadcn@latest add sheet       # Notification Center dropdown
pnpm dlx shadcn@latest add scroll-area # Scroll da lista de notificações
pnpm dlx shadcn@latest add separator   # Divisores entre seções
pnpm dlx shadcn@latest add avatar      # Ícones de revisores
pnpm dlx shadcn@latest add toast       # Toasts para ações rápidas
pnpm dlx shadcn@latest add calendar    # Filtro de data (histórico)
pnpm dlx shadcn@latest add popover     # Filter popovers
pnpm dlx shadcn@latest add select      # Status dropdown
pnpm dlx shadcn@latest add pagination  # Results table pagination
```

---

## 📝 Tarefas Detalhadas

### **FASE 1: Frontend com Mock Data**

#### **Sprint 1: Foundation (6h)** ✅ CONCLUÍDO

- [x] **1.1 - Instalar shadcn components** (30min) ✅
  - sheet, scroll-area, separator, avatar, sonner, calendar, popover, select, pagination

- [x] **1.2 - Criar tipos TypeScript** (1h) ✅
  - `/front-end/types/notification.ts`
  - `/front-end/types/process.ts`
  - Interfaces para Notification, ProcessNotification, ProcessResult

- [x] **1.3 - Context de Notificações** (3h) ✅
  - `/front-end/hooks/use-notifications.tsx`
  - Gerenciar notificações + processos ativos
  - Funções de CRUD no localStorage
  - Auto-cleanup de notificações antigas (>30 dias)
  - Integração com localStorage

- [x] **1.4 - Dados Mock** (1.5h) ✅
  - `/front-end/lib/mock-notifications.ts`
  - Gerador de notificações fake
  - Simular chegada de notificações (setTimeout)
  - 20+ exemplos de diferentes tipos
  - Mock de processos históricos

---

#### **Sprint 2: Notification System (8h)** ✅ CONCLUÍDO

- [x] **2.1 - Notification Bell Component** (2h) ✅
  - `/front-end/components/notification-bell.tsx`
  - Ícone com badge no header/sidebar
  - Animação de pulso quando processo ativo
  - Animação ao receber nova notificação
  - Badge vermelho para não lidas

- [x] **2.2 - Notification Center Dropdown** (4h) ✅
  - `/front-end/components/notification-center.tsx`
  - Sheet do shadcn com 3 seções
  - Seção "Processos Ativos" com progresso ao vivo
  - Seção "Concluídos Hoje" agrupados por data
  - Seção "Histórico" com link para ver todos
  - Botões de ação (Ver Resultados, Marcar como lida)
  - Scroll area para lista longa
  - Estados vazios para cada seção

- [x] **2.3 - Integração com Layout** (1h) ✅
  - Adicionar `<NotificationBell />` no AppSidebar
  - Provider do NotificationContext no layout root
  - Posicionamento correto

- [x] **2.4 - Testes Iniciais** (1h) ✅
  - Build passa com sucesso
  - Componentes integrados sem erros de lint/type
  - Estrutura pronta para integração com dados reais

---

#### **Sprint 3: Progress Bar + enviar-docs (8h)**

- [ ] **3.1 - Process Progress Bar** (3h)
  - `/front-end/components/process-progress-bar.tsx`
  - Barra no topo com progresso detalhado
  - Botão minimizar (salva estado no localStorage)
  - Stepper horizontal com etapas
  - Lista de documentos individual com status
  - Mostrar tempo decorrido
  - Auto-hide ao concluir (após 5s)

- [ ] **3.2 - Refatorar `/enviar-docs/page.tsx`** (4h)
  - 3 estados visuais (upload / processing / results)
  - Estado "upload": zona de upload existente
  - Estado "processing": mostrar progresso + dica da notificação
  - Estado "results": tabela de resultados
  - Integração com notification context
  - Mostrar/esconder progress bar baseado no estado
  - Desabilitar upload durante processo ativo
  - Botão "Ver Progresso Aqui" quando barra minimizada

- [ ] **3.3 - Conectar com SSE do Backend** (1h)
  - Manter lógica existente de `document-batch-processor.tsx`
  - Adicionar hooks para atualizar notification context
  - Emitir notificações em eventos chave (início, conclusão, erro)
  - Atualizar progresso em tempo real

---

#### **Sprint 4: Results Table + Details (8h)**

- [ ] **4.1 - Tabela de Resultados** (3h)
  - `/front-end/components/results-table.tsx`
  - Tabela com shadcn Table
  - Colunas: CPF, Paciente, Data, Status, Exames, Ações
  - Badge colorido para status
  - Botões de ação por linha
  - Paginação client-side
  - Estados vazios

- [ ] **4.2 - Filtros da Tabela** (2h)
  - Busca por CPF (input)
  - Dropdown de Status (select)
  - Range de datas (calendar + popover)
  - Botão "Limpar Filtros"
  - Filtros aplicados em tempo real

- [ ] **4.3 - Modal de Detalhes** (2h)
  - `/front-end/components/result-detail-modal.tsx`
  - Visualização completa do resultado
  - Tabela de comparação de exames
  - Análise GPT formatada
  - Seção de logs (se houver)
  - Botões: Fechar, Baixar PDF, Baixar JSON
  - Botão "Enviar para Checagem" (se rejeitado)

- [ ] **4.4 - Download de Resultados** (1h)
  - Função para gerar PDF client-side (jsPDF ou similar)
  - Download JSON direto (Blob)
  - Exportar CSV da tabela filtrada

---

#### **Sprint 5: Integração e Polish (6h)**

- [ ] **5.1 - Integração com `/checagem`** (2h)
  - Compartilhar `process_results` do localStorage
  - Filtrar apenas documentos "pending_review" em `/checagem`
  - Botão em `/checagem` para aprovar/rejeitar atualiza status
  - Criar notificação ao submissor quando revisor age

- [ ] **5.2 - Notificações de Sistema** (1h)
  - Toast ao iniciar processamento
  - Toast ao concluir processamento
  - Toast ao marcar todas como lidas
  - Toast ao baixar arquivos

- [ ] **5.3 - Animações e Transições** (1h)
  - Progress bar slide in/out
  - Notification center fade in
  - Badge pulse animation
  - Smooth transitions entre estados da página

- [ ] **5.4 - Responsividade** (1h)
  - Testar em mobile
  - Ajustar notification center para telas pequenas
  - Progress bar responsiva

- [ ] **5.5 - Testes Completos de UX** (1h)
  - Cenário 1: Upload → Processar → Navegar → Ver notificação
  - Cenário 2: Múltiplas notificações acumuladas
  - Cenário 3: Minimizar barra e reabrir
  - Cenário 4: Filtrar resultados
  - Cenário 5: Download de resultados

---

### **FASE 2: Backend Real (Preparação para Futuro)**

#### **Sprint 6: Database Setup (3h)**

- [ ] **6.1 - Instalar Dependências** (30min)
  ```bash
  # No back-end
  pip install sqlalchemy alembic psycopg2-binary asyncpg
  ```

- [ ] **6.2 - Setup SQLAlchemy** (1h)
  - `/back-end/app/database/session.py` - Session factory
  - `/back-end/app/database/base.py` - Declarative base
  - Configuração de conexão no `.env`

- [ ] **6.3 - Criar Modelos** (1.5h)
  - `/back-end/app/models/user.py`
  - `/back-end/app/models/batch.py`
  - `/back-end/app/models/document.py`
  - `/back-end/app/models/notification.py`
  - `/back-end/app/models/review.py`
  - Relacionamentos e índices

---

#### **Sprint 7: Endpoints de Notificações (5h)**

- [ ] **7.1 - WebSocket Setup** (2h)
  - `/back-end/app/api/websocket.py`
  - Endpoint: `ws://localhost:8000/ws/notifications/{user_email}`
  - Gerenciar conexões por usuário
  - Broadcast de eventos

- [ ] **7.2 - Endpoints REST** (2h)
  - `/back-end/app/api/v1_notifications.py`
  - `GET /v1/notifications` - Listar com filtros
  - `POST /v1/notifications/{id}/mark-read` - Marcar como lida
  - `POST /v1/notifications/mark-all-read` - Todas como lidas
  - `DELETE /v1/notifications/{id}` - Remover

- [ ] **7.3 - Integrar com Workflow** (1h)
  - Modificar `/back-end/app/services/workflow_service.py`
  - Emitir eventos WebSocket durante processamento
  - Criar notificações no banco ao concluir

---

#### **Sprint 8: Endpoints de Documentos (2h)**

- [ ] **8.1 - CRUD de Documentos** (1h)
  - `/back-end/app/crud/document.py`
  - Funções de criação, leitura, atualização

- [ ] **8.2 - Endpoints REST** (1h)
  - `/back-end/app/api/v1_documents.py`
  - `GET /v1/documents` - Listar com filtros e paginação
  - `GET /v1/documents/{id}` - Detalhes
  - `GET /v1/batches` - Listar lotes
  - `POST /v1/documents/{id}/review` - Aprovar/rejeitar

---

## ⏱️ Estimativa Total

| Fase | Sprints | Tempo |
|------|---------|-------|
| **Fase 1 (Mock)** | Sprints 1-5 | 36h |
| **Fase 2 (Backend)** | Sprints 6-8 | 10h |
| **Total** | 8 sprints | 46h (~6 dias) |

---

## 🎯 Critérios de Sucesso

### **Fase 1 (Mock)**

- [x] Plano aprovado e documentado ✅
- [x] Sistema de tipos TypeScript completo ✅
- [x] Context API para notificações implementado ✅
- [x] LocalStorage persistence configurado ✅
- [x] Sino mostra badge com número de não lidas ✅
- [x] Dropdown abre com 3 seções (ativos, recentes, histórico) ✅
- [x] Componentes seguem padrões shadcn/ui ✅
- [ ] Processos ativos mostram progresso em tempo real (aguardando Sprint 3)
- [ ] Notificações de conclusão aparecem automaticamente (aguardando Sprint 3)
- [ ] Clicar em "Ver Resultados" navega corretamente (aguardando Sprint 3)
- [ ] Badge atualiza ao marcar como lida (implementado, aguardando teste real)
- [ ] Barra de progresso pode ser minimizada (aguardando Sprint 3)
- [ ] Estado persiste entre sessões (localStorage) ✅
- [ ] Funciona navegando entre páginas ✅
- [ ] Notificações antigas são limpas automaticamente (>30 dias) ✅
- [ ] Tabela de resultados com filtros funciona (aguardando Sprint 4)
- [ ] Download de PDF e JSON funciona (aguardando Sprint 4)
- [ ] Integração com `/checagem` funciona (aguardando Sprint 5)

### **Fase 2 (Backend)**

- [ ] WebSocket conecta e recebe eventos
- [ ] Notificações são salvas no banco
- [ ] Endpoints REST funcionam
- [ ] Frontend substitui localStorage por API calls

---

## 🔄 Fluxos de UX Documentados

### **Cenário 1: Primeiro Upload com Notificações**

1. ✅ Usuário acessa `/enviar-docs`
2. ✅ Seleciona 5 documentos
3. ✅ Clica "Processar Documentos"
4. ⏳ **Barra de progresso aparece no topo** (expanded)
5. ⏳ **Sino mostra badge "1"** (processo ativo)
6. ⏳ **Nova notificação**: "🔵 Iniciando processamento de 5 documentos"
7. ⏳ Página muda para estado "Processamento em Andamento"
8. ⏳ Usuário clica "Minimizar" na barra
9. ⏳ Barra desaparece, sino continua com badge
10. ⏳ Usuário navega para `/insights`
11. ⏳ Sino permanece visível com badge
12. ⏳ **Processamento conclui** (usuário ainda em /insights)
13. ⏳ **Badge muda para vermelho** (não lida)
14. ⏳ **Nova notificação**: "✅ 5 documentos processados com sucesso!"
15. ⏳ Usuário clica no sino
16. ⏳ Dropdown abre com notificação de conclusão
17. ⏳ Clica "Ver Resultados" → redireciona para `/enviar-docs`
18. ⏳ Notificação marcada como lida automaticamente

### **Cenário 2: Múltiplas Notificações Acumuladas**

1. ⏳ Usuário processa lote pela manhã (não vê conclusão)
2. ⏳ Durante o dia, 2 documentos são revisados por admin
3. ⏳ À tarde, usuário loga novamente
4. ⏳ **Sino mostra badge "3"** (vermelho)
5. ⏳ Clica no sino
6. ⏳ Vê:
   - ✅ Lote matinal concluído (9h)
   - 👤 Documento aprovado (11h30)
   - 👤 Documento rejeitado (14h15)
7. ⏳ Clica "Ver Resultados" no primeiro
8. ⏳ Vai para `/enviar-docs`, vê tabela atualizada
9. ⏳ Badge agora mostra "2" (marcou 1 como lida)

### **Cenário 3: Processo Ativo + Navegar entre Páginas**

1. ⏳ Inicia processamento em `/enviar-docs`
2. ⏳ Barra de progresso no topo (65%)
3. ⏳ Usuário navega para `/documentacao`
4. ⏳ **Barra some automaticamente** (auto-minimize)
5. ⏳ **Sino pulsa** (indicando processo ativo)
6. ⏳ Clica no sino
7. ⏳ Dropdown mostra processo ativo com progresso ao vivo
8. ⏳ Clica "Ver Progresso Completo"
9. ⏳ Redireciona para `/enviar-docs`
10. ⏳ Barra reaparece no topo

---

## 📚 Referências Técnicas

### **Documentação**
- Next.js 15: https://nextjs.org/docs
- shadcn/ui: https://ui.shadcn.com
- Tailwind CSS 4: https://tailwindcss.com/docs
- FastAPI WebSocket: https://fastapi.tiangolo.com/advanced/websockets/
- SQLAlchemy: https://docs.sqlalchemy.org

### **Componentes Inspiração**
- Notification Center: Linear, GitHub
- Progress Bar: Vercel Deploy, Railway
- Toast: shadcn/ui Toast component

---

## 🚀 Próximos Passos Imediatos

1. **Começar Sprint 1**
   - Instalar shadcn components
   - Criar tipos TypeScript
   - Implementar Context de Notificações

2. **Validar com Usuário**
   - Mostrar protótipo de Notification Center
   - Confirmar UI/UX antes de continuar

3. **Documentar Progresso**
   - Atualizar este plan.md conforme conclusão
   - Marcar checkboxes das tarefas concluídas

---

**Última Atualização**: 2025-10-30
**Responsável**: Claude Code
**Status Atual**: Sprints 1 e 2 concluídos com sucesso - Próximo: Sprint 3
