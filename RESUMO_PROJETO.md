# ProntuAI - Resumo do Projeto

## 📋 Visão Geral

**ProntuAI** é uma plataforma de validação automatizada de documentos médicos para a BRMED (empresa de saúde ocupacional). O sistema utiliza OCR e Inteligência Artificial para extrair informações de exames médicos, validá-los contra requisitos obrigatórios do sistema BRNET, e fornecer comparação inteligente usando similaridade vetorial e modelos de inteligência artificial.

---

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONT-END (Next.js 15)                   │
│  - React 19 + TypeScript                                     │
│  - Tailwind CSS 4 + shadcn/ui                                │
│  - NextAuth (Google OAuth)                                   │
│  - Sistema de notificações em tempo real                     │
└────────────────────────┬────────────────────────────────────┘
                         │ API REST
┌────────────────────────┴────────────────────────────────────┐
│                   BACK-END (FastAPI + Python)               │
│  - OCR (Docling) / Próxima implementação: AWS textract      │
│  - BRMED Scraper (Playwright) / Próxima implementação: API   │
│  - Validação de Exames (OpenAI + FAISS)                      │
│  - Vector Search para sinônimos                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 👥 Papéis de Usuário e Permissões

O sistema possui **3 papéis distintos** com acessos segregados:

### 1. 📤 **ENVIADOR** (Submitter)
**Responsabilidade**: Enviar documentos médicos para análise

**Acesso às páginas**:
- ✅ **Enviar Exames** (`/enviar-docs`) - Upload e processamento de documentos
- ✅ **Pendentes** (`/pendentes`) - Ver APENAS documentos **rejeitados pelo Revisor**

**⚠️ IMPORTANTE sobre /pendentes**:
- **APARECEM apenas**: Documentos **REJEITADOS PELO REVISOR** (humano)
- **NÃO aparecem**:
  - ✅ Documentos aprovados pela IA (vão para Checagem)
  - ❌ Documentos rejeitados pela IA (vão para Checagem)
  - ✅ Documentos aprovados pelo Revisor (finalizados)

**Resumo**: O enviador **não tem contato** com documentos aprovados. Só vê documentos que o **Revisor rejeitou** e precisa corrigir.

**Fluxo de trabalho**:
1. Faz login com email `@grupobrmed.com.br`
2. Acessa "Enviar Exames"
3. Faz upload de PDFs (arrasta ou seleciona arquivos)
4. Sistema processa automaticamente (OCR → BRNET → Validação IA)
5. Recebe notificação de processamento concluído
6. **TODOS os documentos vão para Checagem** (aprovados E rejeitados pela IA)
7. Aguarda validação do Revisor
8. **SE** o Revisor rejeitar: documento aparece em "Pendentes" com notificação
9. **SE** o Revisor aprovar: documento finalizado (enviador não vê)

**Sistema de Deduplicação**:
- ID único gerado: `hash(nome_paciente + documento_identificacao + data_exame)`
- Previne envio de documentos duplicados
- Alerta o enviador se documento já foi processado anteriormente

**Notificações recebidas**:
- 🔵 **Início**: "Iniciando processamento de 3 documento(s)"
- ✅ **Concluído (sem pendências)**: "Processamento concluído - 3 documentos enviados para revisão"
- ⚠️ **Concluído (com pendências detectadas)**: "Processamento concluído - 2 aprovados, 1 com pendências detectadas pela IA (todos enviados para revisão)"
- 🔴 **Erro**: "Erro ao processar documento: timeout OCR"
- ❌ **Rejeição pelo Revisor**: "Seu documento de João Silva foi rejeitado: Documento ilegível"
- 📋 **Duplicata detectada**: "Documento já foi enviado anteriormente em 15/12/2024"

---

### 2. 🔍 **REVISOR** (Reviewer/Validator)
**Responsabilidade**: Validar documentos processados e aprovar/rejeitar

**Acesso às páginas**:
- ✅ **Checagem** (`/checagem`) - Revisar e validar documentos pendentes

**Fluxo de trabalho**:
1. Faz login com email `@grupobrmed.com.br`
2. Acessa "Checagem"
3. Visualiza documentos que aguardam validação humana
4. Analisa detalhes:
   - Decisão da IA (aprovado/rejeitado)
   - Exames faltantes e extras
   - Informações do paciente
5. Toma decisão:
   - **Aprovar**: Documento validado e liberado
   - **Rejeitar**: Preenche motivo (ex: "Documento ilegível")
6. Sistema notifica automaticamente o enviador original

**Notificações recebidas**:
- 📬 Novos documentos aguardando revisão
- 🔔 Documentos com alta prioridade

**Estatísticas visíveis**:
- 🟡 Pendentes - Aguardando revisão
- 🟢 Aprovados - Já revisados positivamente
- 🔴 Rejeitados - Já revisados negativamente

---

### 3. 👑 **ADMIN** (Administrador)
**Responsabilidade**: Gestão completa do sistema + acesso a insights

**Acesso às páginas**:
- ✅ **Enviar Exames** (`/enviar-docs`)
- ✅ **Pendentes** (`/pendentes`) - Visualizar TODOS os documentos
- ✅ **Checagem** (`/checagem`)
- ✅ **Insights** (`/insights`) - Analytics e base de conhecimento
- ✅ **Histórico** (`/historico`) - Arquivo completo de processamentos

**Capacidades extras**:
- Visualizar documentos de todos os usuários
- Acesso ao sistema de FAQ/Insights (RAG-based Q&A)
- Análise de métricas e estatísticas
- Gestão de configurações do sistema

---

## 🔄 Fluxo Completo de um Documento

```
1. 📤 ENVIADOR faz upload de PDF
   ↓
2. 🔎 SISTEMA verifica duplicatas
   └─ ID único: hash(nome + doc + data_exame)
   ├─ Se JÁ EXISTE → 🔔 Notifica: "Documento já enviado em 15/12/2024"
   └─ Se NOVO → Continua processamento
   ↓
3. 🤖 SISTEMA processa automaticamente
   │
   ├─ 📄 OCR: Extrai texto do documento (Docling)
   │  └─ Identifica: CPF, Nomes dos exames, assinaturas, data
   │
   ├─ 🌐 Consulta sistema BRNET
   │  └─ Obtém: Lista de exames obrigatórios para o CPF
   │
   └─ ✅ VALIDAÇÃO IA: Compara exames encontrados vs. obrigatórios
      ├─ Vector search no FAISS (sinônimos médicos)
      ├─ Comparação via IA
      └─ Resultado: Lista de exames faltantes/extras + status IA
   ↓
4. 🎯 DECISÃO DA IA (apenas sugestão)
   │
   ├─ ✅ APROVADO pela IA (todos exames OK)
   └─ ⚠️ REJEITADO pela IA (faltam exames ou discrepâncias)
   │
   ↓
5. 🔔 NOTIFICAÇÃO ao ENVIADOR
   ├─ Sem pendências: "Processamento concluído - 3 documentos enviados para revisão"
   └─ Com pendências: "Processamento concluído - 2 aprovados, 1 com pendências pela IA (todos enviados para revisão)"
   ↓
6. 📋 TODOS os documentos vão para /CHECAGEM
   (Aprovados E Rejeitados pela IA)
   │
   └─ Enviador NÃO vê esses documentos
      (Não aparecem em /pendentes)
   ↓
7. 👤 REVISOR valida em /checagem
   │
   ├─ Vê decisão da IA como referência:
   │  • Badge "Aprovado pela IA" (verde)
   │  • Badge "Rejeitado pela IA" (amarelo)
   │
   ├─ Analisa documento e exames
   │
   └─ Toma DECISÃO FINAL (independente da IA):
      │
      ├─ ✅ APROVAR
      │  └─ 🟢 APROVADO FINAL
      │     └─ Enviador NÃO é notificado
      │        └─ 📊 Documento arquivado
      │           └─ Fim do fluxo
      │
      └─ ❌ REJEITAR (com motivo obrigatório)
         └─ 🔴 Documento vai para /PENDENTES do enviador
            └─ 🔔 Notifica: "Seu documento de João Silva foi rejeitado: Documento ilegível"
               └─ Enviador vê em /pendentes e pode:
                  • Corrigir documento
                  • Reenviar (ciclo reinicia no passo 1)
```

### ⚠️ IMPORTANTE: Entendendo o Fluxo Real

**O que o ENVIADOR vê**:
- ❌ **Apenas documentos REJEITADOS PELO REVISOR** em /pendentes
- ✅ **NÃO vê** documentos aprovados (pela IA ou pelo Revisor)
- ⚠️ **NÃO vê** documentos rejeitados pela IA (estes vão direto para Checagem)

**O que o REVISOR vê**:
- 📋 **TODOS os documentos processados** em /checagem
- 🟢 Documentos aprovados pela IA (como referência)
- ⚠️ Documentos rejeitados pela IA (como referência)
- 👤 **Decisão final é sempre do REVISOR** (pode aprovar ou rejeitar independente da IA)

**Resumo**: A IA apenas **sugere**, o Revisor **decide**, e o Enviador só vê **rejeições finais** para corrigir.

---

## 🔔 Sistema de Notificações

### Arquitetura
- **Baseado em Contexto React** + localStorage
- **Persistência**: Notificações sobrevivem a refresh/fechamento do navegador
- **Retenção**: Até 30 dias ou máximo de 100 notificações
- **Deduplicação**: Evita notificações duplicadas em 5 segundos

### Componentes Visuais

#### 1. **Sino de Notificações** (header, canto superior direito)
```
📍 Estado Normal:
   • Badge com número não lido (ex: "3")
   • Clique abre painel lateral

🔄 Durante Processamento:
   • Badge pulsa/anima
   • Indicador visual de atividade

✅ Após Conclusão:
   • Badge atualizado com nova contagem
   • Link "Ver Resultados" disponível
```

#### 2. **Barra de Progresso** (topo da tela)
```
⏳ Exibida durante processamento:
   • Porcentagem: 0% → 100%
   • Etapa atual: "Upload" → "OCR" → "BR NET" → "Validação" → "Completo"
   • Mensagem dinâmica: "Extraindo exames via OCR..."
   • Minimizável (continua visível na central)
```

#### 3. **Central de Notificações** (painel lateral)
```
📂 Seções:

├─ 🔄 PROCESSO ATIVO (se houver)
│   ├─ Spinner animado
│   ├─ Mensagem da etapa atual
│   ├─ Barra de progresso
│   └─ Botão "Ver Detalhes"
│
├─ 📅 CONCLUÍDO HOJE
│   └─ Notificações de hoje agrupadas
│       • Processamentos finalizados
│       • Aprovações/rejeições
│       • Erros
│
└─ 📜 HISTÓRICO
    └─ Notificações antigas (até 30 dias)
        • Lidas e não lidas
        • Organizadas por data relativa
```

### Tipos de Notificações por Papel

#### 📤 **Enviador recebe**:
| Tipo | Quando | Mensagem Exemplo |
|------|--------|------------------|
| 🔵 Início | Upload começa | "Iniciando processamento de 3 documento(s)" |
| ✅ Concluído (limpo) | Todos aprovados pela IA | "Processamento concluído - 3 documentos enviados para revisão" |
| ⚠️ Concluído (pendências) | Alguns rejeitados pela IA | "Processamento concluído - 2 aprovados, 1 com pendências pela IA (todos enviados para revisão)" |
| 🔴 Erro | Falha técnica | "Erro ao processar documento: timeout OCR" |
| 📋 Duplicata | Documento já enviado | "Documento já foi enviado anteriormente em 15/12/2024" |
| ❌ Rejeição pelo Revisor | Revisor rejeita | "Seu documento de João Silva foi rejeitado: Documento ilegível" |

**Nota**: Enviadores **NÃO recebem** notificação quando o Revisor aprova (fluxo transparente para documentos aprovados).

#### 🔍 **Revisor recebe**:
| Tipo | Quando | Mensagem Exemplo |
|------|--------|------------------|
| 📬 Novo documento | Documento processado | "3 novos documentos aguardando revisão" |
| ⚠️ Alta prioridade | Urgente | "Documento urgente para revisão: CPF 123.456.789-00" |

#### 👑 **Admin recebe**:
- Todas as notificações acima +
- Notificações de sistema (erros, alertas)

---

## 📊 Páginas e Funcionalidades

| Página | Rota | Acesso | Descrição |
|--------|------|--------|-----------|
| **Login** | `/login` | Todos (público) | Autenticação via Google OAuth |
| **Enviar Exames** | `/enviar-docs` | Enviador, Admin | Upload de documentos, processamento em lote, resultados em tempo real |
| **Pendentes** | `/pendentes` | Enviador (seus docs), Admin (todos) | Visualização de documentos processados, filtros, detalhes |
| **Checagem** | `/checagem` | Revisor, Admin | Validação manual, aprovação/rejeição com justificativa |
| **Histórico** | `/historico` | Admin | Arquivo completo de todos os processamentos |

---

## 🔐 Autenticação e Segurança

### Google OAuth (NextAuth)
```
✅ Permitido: @grupobrmed.com.br
❌ Bloqueado: Outros domínios
```

### Middleware de Proteção
- Todas as rotas protegidas exceto `/login` e `/api/auth/*`
- Redirecionamento automático para login se não autenticado
- Verificação de papel do usuário em cada página
- Bloqueio de acesso não autorizado

### Segregação de Dados
- **Enviadores**: Veem apenas documentos que enviaram
- **Revisores**: Veem apenas documentos pendentes de revisão
- **Admins**: Acesso completo a todos os dados

---

## 🔬 Tecnologias Utilizadas

### Front-end
- **Framework**: Next.js 15 (App Router)
- **UI Library**: React 19 + TypeScript
- **Styling**: Tailwind CSS 4
- **Component Library**: shadcn/ui (23 componentes)
- **Autenticação**: NextAuth com Google OAuth
- **State Management**: Context API + localStorage
- **Date Handling**: date-fns (pt-BR)
- **Notifications**: Sonner (toast)
- **Forms**: React Hook Form + Zod

### Back-end
- **Framework**: FastAPI (Python 3.11+)
- **OCR**: Docling (conversão para Markdown)
- **Web Scraping**: Playwright (BRNET automation)
- **AI/ML**: OpenAI API (GPT-4 + embeddings)
- **Vector Search**: FAISS (GPU-accelerated)
- **Retry Logic**: Tenacity
- **Logging**: Custom logging module

### Infraestrutura
- **Dev Environment**: uvicorn (backend) + Next.js dev server
- **Storage**: localStorage (front-end), filesystem (back-end)
- **API**: REST (JSON)

---

## 📈 Estatísticas e Métricas (Visíveis no Sistema)

### Dashboard da Checagem
```
┌─────────────────┬─────────────────┬─────────────────┐
│  🟡 PENDENTES   │  🟢 APROVADOS   │  🔴 REJEITADOS  │
│                 │                 │                 │
│       23        │       156       │       12        │
│                 │                 │                 │
│ Aguardando      │ Validados       │ Recusados       │
│ revisão humana  │ positivamente   │ por revisor     │
└─────────────────┴─────────────────┴─────────────────┘
```

### Página Enviar Exames (pós-processamento)
```
┌─────────────────┬─────────────────┬─────────────────┐
│  ✅ APROVADOS   │  ⏳ AGUARDANDO  │  ❌ REJEITADOS  │
│                 │     REVISÃO     │                 │
│        5        │        2        │        1        │
│                 │                 │                 │
│ Aprovados       │ Pendentes de    │ Rejeitados      │
│ pela IA         │ validação       │ pela IA         │
└─────────────────┴─────────────────┴─────────────────┘
```

---

## 🎯 Estados do Documento (State Machine)

```
📤 ENVIADO pelo usuário
   ↓
⏳ PROCESSANDO
   ├─ Upload (0-20%)
   ├─ OCR (20-50%)
   ├─ BR NET Query (50-75%)
   └─ Validação (75-100%)
   ↓
🤖 DECISÃO DA IA
   ├─ ✅ approved (AI)
   │   └─ Requer validação humana → 🟡 PENDENTE REVISÃO
   │
   └─ ⚠️ rejected (AI)
       └─ Requer revisão humana → 🟡 PENDENTE REVISÃO
   ↓
👤 REVISÃO HUMANA
   ├─ ✅ Aprovar → 🟢 APROVADO (final)
   └─ ❌ Rejeitar → 🔴 REJEITADO (final)
   ↓
📊 ARQUIVADO em Pendentes/Histórico
```

### Status Possíveis

| Status | Cor | Significado | Visível em |
|--------|-----|-------------|-----------|
| `processing` | 🔵 Azul | Processando | Enviar Exames |
| `approved` (AI) | 🟢 Verde claro | Aprovado pela IA, aguarda humano | Checagem |
| `rejected` (AI) | 🔴 Vermelho claro | Rejeitado pela IA, aguarda humano | Checagem |
| `pending_review` | 🟡 Amarelo | Aguardando revisão | Checagem |
| `approved` (final) | 🟢 Verde | Aprovado definitivo | Pendentes, Histórico |
| `rejected` (final) | 🔴 Vermelho | Rejeitado definitivo | Pendentes, Histórico |
| `error` | ⚫ Cinza | Erro no processamento | Todas |


**Última atualização**: 2025-01-06
**Versão do Sistema**: v1.0
