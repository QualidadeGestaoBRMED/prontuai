"use client"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import Image from "next/image"
import { useEffect, useRef, useState, type MouseEvent } from "react"
import { ArrowRight, Cpu, Database, Layers, ServerCog } from "lucide-react"

const navPrimary = [
  { label: "Visão", href: "#visao" },
  { label: "Pipeline", href: "#pipeline" },
  { label: "Stack", href: "#stack" },
  { label: "Integrações", href: "#integracoes" },
  { label: "Config", href: "#config" },
  { label: "Rotas", href: "#rotas" },
]

const navSecondary = [
  { label: "Auth", href: "#auth" },
  { label: "Deploy", href: "#deploy" },
  { label: "Observabilidade", href: "#observabilidade" },
  { label: "Segurança", href: "#seguranca" },
]

const pipelineSteps = [
  {
    title: "Recepção",
    description: "Entrada de PDFs e criação do lote de processamento.",
  },
  {
    title: "OCR",
    description: "Extração de texto, identificação de exames e metadados.",
  },
  {
    title: "BRNET",
    description: "Consulta dos exames obrigatórios por CPF.",
  },
  {
    title: "IA",
    description: "Comparação inteligente e geração de justificativas.",
  },
  {
    title: "Checagem",
    description: "Revisão humana com decisão final registrada.",
  },
]

const stackFront = [
  "Next.js 15 (App Router)",
  "React 19 + TypeScript",
  "Tailwind CSS 4 + shadcn/ui",
  "NextAuth (Google OAuth)",
]

const stackBack = [
  "FastAPI (Python 3.11+)",
  "OpenAI API + FAISS",
  "Docling / AWS Textract (opcional)",
  "Gunicorn + Uvicorn workers",
]

const integracoes = [
  {
    title: "OpenAI",
    description: "Geração de análises, embeddings e validações por IA.",
  },
  {
    title: "BRNET",
    description: "Requisitos obrigatórios por CPF para comparação dos exames.",
  },
  {
    title: "OCR",
    description: "Docling como padrão e Textract como fallback opcional.",
  },
]

const envVars = [
]

const frontendRoutes = [
  {
    path: "/login",
    label: "Login",
    description: "Autenticação via Google OAuth.",
    access: "Público",
    params: "—",
    example: "/login",
  },
  {
    path: "/docs",
    label: "Guia de uso",
    description: "Documentação funcional do produto.",
    access: "Público",
    params: "—",
    example: "/docs",
  },
  {
    path: "/docs-tecnica",
    label: "Docs técnica",
    description: "Manutenção e arquitetura do sistema.",
    access: "Time interno",
    params: "—",
    example: "/docs-tecnica",
  },
  {
    path: "/anexar-prontuario",
    label: "Envio de documentos",
    description: "Upload, processamento e acompanhamento do lote.",
    access: "Clínica (Enviador) + Admin",
    params: "view=processing (abre tela de progresso)",
    example: "/anexar-prontuario?view=processing",
  },
  {
    path: "/pendentes",
    label: "Pendências",
    description: "Fila de documentos rejeitados que aguardam correção.",
    access: "Clínica (Enviador) + Admin",
    params: "—",
    example: "/pendentes",
  },
  {
    path: "/checagem",
    label: "Checagem",
    description: "Validação manual e decisão final do time interno.",
    access: "Time interno BR MED + Admin",
    params: "—",
    example: "/checagem",
  },
  {
    path: "/historico",
    label: "Histórico",
    description: "Arquivo final de processamentos concluídos.",
    access: "Admin",
    params: "—",
    example: "/historico",
  },
  {
    path: "/insights",
    label: "Insights",
    description: "Indicadores operacionais e visão de performance.",
    access: "Admin",
    params: "—",
    example: "/insights",
  },
]

const apiRouteGroups = [
  {
    title: "Auth",
    items: [
      {
        method: "POST",
        path: "/v1/auth/google",
        description: "Login via Google OAuth.",
        auth: "Público",
        headers: "Content-Type: application/json",
        body: "email, name, google_id",
        query: "—",
        response: "access_token, token_type, user",
        example: `POST /v1/auth/google
{
  "email": "usuario@grupobrmed.com.br",
  "name": "João Silva",
  "google_id": "google-123"
}`,
        exampleResponse: `{
  "access_token": "...",
  "token_type": "bearer",
  "user": {
    "id": "user-123",
    "email": "usuario@grupobrmed.com.br",
    "name": "João Silva",
    "role": "CHECKER",
    "clinic_id": null,
    "is_active": true
  }
}`,
      },
      {
        method: "GET",
        path: "/v1/auth/me",
        description: "Retorna o usuário autenticado.",
        auth: "Bearer",
        headers: "Authorization: Bearer <token>",
        body: "—",
        query: "—",
        response: "User atual",
        example: `GET /v1/auth/me
Authorization: Bearer <token>`,
        exampleResponse: `{
  "id": "user-123",
  "email": "usuario@grupobrmed.com.br",
  "name": "João Silva",
  "role": "CHECKER",
  "clinic_id": null,
  "is_active": true
}`,
      },
      {
        method: "POST",
        path: "/v1/auth/verify",
        description: "Valida token JWT.",
        auth: "Bearer",
        headers: "Authorization: Bearer <token>",
        body: "—",
        query: "—",
        response: "valid, user",
        example: `POST /v1/auth/verify
Authorization: Bearer <token>`,
        exampleResponse: `{
  "valid": true,
  "user": {
    "id": "user-123",
    "email": "usuario@grupobrmed.com.br",
    "role": "CHECKER"
  }
}`,
      },
    ],
  },
  {
    title: "Users",
    items: [
      {
        method: "GET",
        path: "/v1/users",
        description: "Lista usuários.",
        auth: "Bearer (ADMIN)",
        headers: "Authorization: Bearer <token>",
        body: "—",
        query: "include_inactive?: boolean",
        response: "Array de users",
        example: `GET /v1/users?include_inactive=true
Authorization: Bearer <token>`,
        exampleResponse: `[
  {
    "id": "user-123",
    "email": "usuario@grupobrmed.com.br",
    "name": "João Silva",
    "role": "CHECKER",
    "clinic_id": null,
    "is_active": true
  }
]`,
      },
      {
        method: "POST",
        path: "/v1/users",
        description: "Cria usuário.",
        auth: "Bearer (ADMIN)",
        headers: "Authorization: Bearer <token>",
        body: "email, name, role, clinic_id?",
        query: "—",
        response: "User criado",
        example: `POST /v1/users
Authorization: Bearer <token>
{
  "email": "novo@grupobrmed.com.br",
  "name": "Novo Usuário",
  "role": "SENDER",
  "clinic_id": "clinic-123"
}`,
        exampleResponse: `{
  "id": "user-456",
  "email": "novo@grupobrmed.com.br",
  "name": "Novo Usuário",
  "role": "SENDER",
  "clinic_id": "clinic-123",
  "is_active": true
}`,
      },
      {
        method: "GET",
        path: "/v1/users/{user_id}",
        description: "Detalhe do usuário.",
        auth: "Bearer (ADMIN)",
        headers: "Authorization: Bearer <token>",
        body: "—",
        query: "—",
        response: "User",
        example: `GET /v1/users/123
Authorization: Bearer <token>`,
        exampleResponse: `{
  "id": "user-123",
  "email": "usuario@grupobrmed.com.br",
  "name": "João Silva",
  "role": "CHECKER",
  "clinic_id": null,
  "is_active": true
}`,
      },
      {
        method: "PATCH",
        path: "/v1/users/{user_id}",
        description: "Atualiza usuário.",
        auth: "Bearer (ADMIN)",
        headers: "Authorization: Bearer <token>",
        body: "name?, role?, is_active?, clinic_id?",
        query: "—",
        response: "User atualizado",
        example: `PATCH /v1/users/123
Authorization: Bearer <token>
{
  "role": "ADMIN",
  "is_active": true
}`,
        exampleResponse: `{
  "id": "user-123",
  "email": "usuario@grupobrmed.com.br",
  "role": "ADMIN",
  "is_active": true
}`,
      },
      {
        method: "DELETE",
        path: "/v1/users/{user_id}",
        description: "Desativa usuário (soft delete).",
        auth: "Bearer (ADMIN)",
        headers: "Authorization: Bearer <token>",
        body: "—",
        query: "—",
        response: "204 No Content",
        example: `DELETE /v1/users/123
Authorization: Bearer <token>`,
        exampleResponse: "204 No Content",
      },
      {
        method: "GET",
        path: "/v1/users/email/{email}",
        description: "Busca por email.",
        auth: "Bearer (ADMIN)",
        headers: "Authorization: Bearer <token>",
        body: "—",
        query: "—",
        response: "User",
        example: `GET /v1/users/email/usuario@empresa.com
Authorization: Bearer <token>`,
        exampleResponse: `{
  "id": "user-123",
  "email": "usuario@empresa.com",
  "name": "Usuário",
  "role": "CHECKER"
}`,
      },
    ],
  },
  {
    title: "Clinics",
    items: [
      {
        method: "GET",
        path: "/v1/clinics/test-auth",
        description: "Teste de autenticação.",
        auth: "Bearer (ADMIN)",
        headers: "Authorization: Bearer <token>",
        body: "—",
        query: "—",
        response: "authenticated, user",
        example: `GET /v1/clinics/test-auth
Authorization: Bearer <token>`,
        exampleResponse: `{
  "authenticated": true,
  "user": {
    "email": "admin@grupobrmed.com.br",
    "role": "ADMIN"
  }
}`,
      },
      {
        method: "POST",
        path: "/v1/clinics/test-create",
        description: "Teste rápido de criação.",
        auth: "Bearer (ADMIN)",
        headers: "Authorization: Bearer <token>",
        body: "—",
        query: "name",
        response: "success, clinic_id",
        example: `POST /v1/clinics/test-create?name=Clinica+Teste
Authorization: Bearer <token>`,
        exampleResponse: `{
  "success": true,
  "clinic_id": "clinic-123"
}`,
      },
      {
        method: "GET",
        path: "/v1/clinics",
        description: "Lista clínicas.",
        auth: "Bearer (ADMIN)",
        headers: "Authorization: Bearer <token>",
        body: "—",
        query: "include_inactive?: boolean",
        response: "Array de clinics",
        example: `GET /v1/clinics?include_inactive=true
Authorization: Bearer <token>`,
        exampleResponse: `[
  {
    "id": "clinic-123",
    "name": "Clínica Exemplo",
    "cnpj": "12.345.678/0001-90",
    "is_active": true
  }
]`,
      },
      {
        method: "GET",
        path: "/v1/clinics/{clinic_id}",
        description: "Detalhe da clínica.",
        auth: "Bearer (ADMIN)",
        headers: "Authorization: Bearer <token>",
        body: "—",
        query: "—",
        response: "Clinic",
        example: `GET /v1/clinics/123
Authorization: Bearer <token>`,
        exampleResponse: `{
  "id": "clinic-123",
  "name": "Clínica Exemplo",
  "city": "São Paulo",
  "state": "SP",
  "is_active": true
}`,
      },
      {
        method: "POST",
        path: "/v1/clinics",
        description: "Cria clínica.",
        auth: "Bearer (ADMIN)",
        headers: "Authorization: Bearer <token>",
        body: "name, cnpj?, phone?, address?, city?, state?",
        query: "—",
        response: "Clinic criada",
        example: `POST /v1/clinics
Authorization: Bearer <token>
{
  "name": "Clínica Exemplo",
  "cnpj": "12.345.678/0001-90",
  "phone": "(11) 99999-9999",
  "city": "São Paulo",
  "state": "SP"
}`,
        exampleResponse: `{
  "id": "clinic-123",
  "name": "Clínica Exemplo",
  "cnpj": "12.345.678/0001-90",
  "is_active": true
}`,
      },
      {
        method: "PATCH",
        path: "/v1/clinics/{clinic_id}",
        description: "Atualiza clínica.",
        auth: "Bearer (ADMIN)",
        headers: "Authorization: Bearer <token>",
        body: "name?, cnpj?, phone?, address?, city?, state?, is_active?",
        query: "—",
        response: "Clinic atualizada",
        example: `PATCH /v1/clinics/123
Authorization: Bearer <token>
{
  "phone": "(11) 98888-8888",
  "is_active": true
}`,
        exampleResponse: `{
  "id": "clinic-123",
  "name": "Clínica Exemplo",
  "phone": "(11) 98888-8888",
  "is_active": true
}`,
      },
    ],
  },
  {
    title: "Documents",
    items: [
      {
        method: "GET",
        path: "/v1/documents",
        description: "Lista documentos (compact/cache).",
        auth: "Bearer",
        headers: "Authorization: Bearer <token>",
        body: "—",
        query: "compact?, cache_seconds?, stale_seconds?",
        response: "Array de documents (compact)",
        example: `GET /v1/documents?compact=true&cache_seconds=10&stale_seconds=120
Authorization: Bearer <token>`,
        exampleResponse: `[
  {
    "id": "doc-123",
    "filename": "aso.pdf",
    "cpf": "12345678901",
    "validation_status": "pending",
    "uploaded_at": "2026-02-09T10:00:00Z"
  }
]`,
      },
      {
        method: "GET",
        path: "/v1/documents/{document_id}",
        description: "Detalhe do documento.",
        auth: "Bearer",
        headers: "Authorization: Bearer <token>",
        body: "—",
        query: "—",
        response: "Document completo",
        example: `GET /v1/documents/123
Authorization: Bearer <token>`,
        exampleResponse: `{
  "id": "doc-123",
  "filename": "aso.pdf",
  "cpf": "12345678901",
  "validation_status": "validated",
  "exams_found": ["Hemograma"],
  "run_id": "run-123"
}`,
      },
      {
        method: "GET",
        path: "/v1/documents/{document_id}/view",
        description: "Preview do arquivo.",
        auth: "Bearer",
        headers: "Authorization: Bearer <token>",
        body: "—",
        query: "—",
        response: "Arquivo (PDF)",
        example: `GET /v1/documents/123/view
Authorization: Bearer <token>`,
        exampleResponse: "PDF stream (Content-Type: application/pdf)",
      },
      {
        method: "PATCH",
        path: "/v1/documents/{document_id}",
        description: "Atualiza status/metadata.",
        auth: "Bearer",
        headers: "Authorization: Bearer <token>",
        body: "validation_status, exams_*, result_payload?",
        query: "—",
        response: "Document atualizado",
        example: `PATCH /v1/documents/123
Authorization: Bearer <token>
{
  "validation_status": "validated",
  "approval_reason": "Exames completos"
}`,
        exampleResponse: `{
  "id": "doc-123",
  "validation_status": "validated",
  "approval_reason": "Exames completos"
}`,
      },
    ],
  },
  {
    title: "Processamento",
    items: [
      {
        method: "POST",
        path: "/v1/processar-documento",
        description: "Processamento completo (OCR + BRMED + validação).",
        auth: "Bearer (SENDER)",
        headers: "Content-Type: multipart/form-data",
        body: "arquivo (PDF), exames_obrigatorios (JSON string)",
        query: "—",
        response: "Resultado completo + document_id",
        example: `POST /v1/processar-documento
Authorization: Bearer <token>
FormData:
  arquivo=@aso.pdf
  exames_obrigatorios=["Hemograma","Glicemia"]`,
        exampleResponse: `{
  "status": "success",
  "document_id": "doc-123",
  "cpf_processado": "12345678901",
  "validation_result": {
    "exames_faltantes": []
  }
}`,
      },
      {
        method: "POST",
        path: "/v1/processar-documento-stream",
        description: "Processamento com SSE (progresso em tempo real).",
        auth: "Sem auth explícita",
        headers: "Accept: text/event-stream",
        body: "arquivo (PDF), exames_obrigatorios (JSON string)",
        query: "—",
        response: "SSE { progress, step, message }",
        example: `POST /v1/processar-documento-stream
FormData:
  arquivo=@aso.pdf
  exames_obrigatorios=["Hemograma","Glicemia"]`,
        exampleResponse: `data: {"progress":20,"step":"ocr","message":"OCR em andamento..."}\n\ndata: {"progress":90,"step":"validacao","message":"Validação concluída"}\n`,
      },
      {
        method: "POST",
        path: "/v1/processar-documento-async",
        description: "Processamento assíncrono (retorna job_id).",
        auth: "Bearer (SENDER)",
        headers: "Content-Type: multipart/form-data",
        body: "arquivo (PDF), exames_obrigatorios (JSON string)",
        query: "—",
        response: "job_id, status, poll_url",
        example: `POST /v1/processar-documento-async
Authorization: Bearer <token>
FormData:
  arquivo=@aso.pdf
  exames_obrigatorios=["Hemograma","Glicemia"]`,
        exampleResponse: `{
  "job_id": "job-123",
  "status": "pending",
  "poll_url": "/v1/jobs/job-123"
}`,
      },
      {
        method: "POST",
        path: "/v1/consultar-brmed",
        description: "Consulta de exames BRMED por CPF.",
        auth: "Sem auth explícita",
        headers: "Content-Type: application/json",
        body: "cpf",
        query: "—",
        response: "exames_obrigatorios",
        example: `POST /v1/consultar-brmed
{
  "cpf": "12345678901"
}`,
        exampleResponse: `{
  "exames_obrigatorios": ["Hemograma","Glicemia"]
}`,
      },
      {
        method: "POST",
        path: "/v1/ocr",
        description: "OCR isolado.",
        auth: "Bearer (SENDER)",
        headers: "Content-Type: multipart/form-data",
        body: "arquivo (PDF)",
        query: "—",
        response: "cpf, exames, markdown",
        example: `POST /v1/ocr
Authorization: Bearer <token>
FormData:
  arquivo=@aso.pdf`,
        exampleResponse: `{
  "cpf": "12345678901",
  "exames": ["Hemograma","Glicemia"],
  "markdown_content": "# Laudo..."
}`,
      },
      {
        method: "POST",
        path: "/v1/validacao",
        description: "Validação isolada.",
        auth: "Bearer (CHECKER)",
        headers: "Content-Type: application/json",
        body: "cpf, exames_obrigatorios[], exames_enviados[]",
        query: "—",
        response: "status_liberado, exames_faltantes, analise",
        example: `POST /v1/validacao
Authorization: Bearer <token>
{
  "cpf": "12345678901",
  "exames_obrigatorios": ["Hemograma","Glicemia"],
  "exames_enviados": ["Hemograma"]
}`,
        exampleResponse: `{
  "status_liberado": false,
  "exames_faltantes": ["Glicemia"],
  "mensagem": "Faltam exames obrigatórios"
}`,
      },
    ],
  },
  {
    title: "Jobs",
    items: [
      {
        method: "GET",
        path: "/v1/jobs",
        description: "Lista jobs.",
        auth: "Público",
        headers: "—",
        body: "—",
        query: "status_filter?, limit?",
        response: "total, jobs[]",
        example: `GET /v1/jobs?status_filter=in_progress&limit=20`,
        exampleResponse: `{
  "total": 1,
  "jobs": [
    { "job_id": "job-123", "status": "in_progress", "progress": 40 }
  ]
}`,
      },
      {
        method: "GET",
        path: "/v1/jobs/{job_id}",
        description: "Status do job.",
        auth: "Público",
        headers: "—",
        body: "—",
        query: "—",
        response: "job_id, status, progress, result?",
        example: `GET /v1/jobs/job-123`,
        exampleResponse: `{
  "job_id": "job-123",
  "status": "in_progress",
  "progress": 40,
  "current_step": "ocr",
  "message": "OCR em andamento"
}`,
      },
      {
        method: "DELETE",
        path: "/v1/jobs/{job_id}",
        description: "Cancela job.",
        auth: "Público",
        headers: "—",
        body: "—",
        query: "—",
        response: "job_id, status=cancelled",
        example: `DELETE /v1/jobs/job-123`,
        exampleResponse: `{
  "job_id": "job-123",
  "status": "cancelled",
  "message": "Job marcado como cancelado"
}`,
      },
    ],
  },
  {
    title: "Notifications",
    items: [
      {
        method: "GET",
        path: "/v1/notifications",
        description: "Lista notificações.",
        auth: "Bearer",
        headers: "Authorization: Bearer <token>",
        body: "—",
        query: "include_read?, limit?",
        response: "Array de notifications",
        example: `GET /v1/notifications?include_read=false&limit=50
Authorization: Bearer <token>`,
        exampleResponse: `[
  {
    "id": "notif-123",
    "type": "process_started",
    "title": "Processamento iniciado",
    "message": "Iniciando processamento de 1 documento(s)",
    "read": false
  }
]`,
      },
      {
        method: "POST",
        path: "/v1/notifications",
        description: "Cria notificação.",
        auth: "Bearer",
        headers: "Authorization: Bearer <token>",
        body: "type, title, message, document_id?, action_url?, metadata?",
        query: "—",
        response: "Notification criada",
        example: `POST /v1/notifications
Authorization: Bearer <token>
{
  "type": "document_rejected",
  "title": "Documento rejeitado",
  "message": "Motivo: Documento ilegível",
  "document_id": "doc-123"
}`,
        exampleResponse: `{
  "id": "notif-456",
  "type": "document_rejected",
  "title": "Documento rejeitado",
  "message": "Motivo: Documento ilegível",
  "read": false
}`,
      },
      {
        method: "POST",
        path: "/v1/notifications/{notification_id}/read",
        description: "Marca como lida.",
        auth: "Bearer",
        headers: "Authorization: Bearer <token>",
        body: "—",
        query: "—",
        response: "Notification atualizada",
        example: `POST /v1/notifications/123/read
Authorization: Bearer <token>`,
        exampleResponse: `{
  "id": "notif-123",
  "read": true
}`,
      },
      {
        method: "POST",
        path: "/v1/notifications/read-all",
        description: "Marca todas como lidas.",
        auth: "Bearer",
        headers: "Authorization: Bearer <token>",
        body: "—",
        query: "—",
        response: "updated",
        example: `POST /v1/notifications/read-all
Authorization: Bearer <token>`,
        exampleResponse: `{
  "updated": 12
}`,
      },
      {
        method: "DELETE",
        path: "/v1/notifications",
        description: "Limpa notificações.",
        auth: "Bearer",
        headers: "Authorization: Bearer <token>",
        body: "—",
        query: "—",
        response: "deleted",
        example: `DELETE /v1/notifications
Authorization: Bearer <token>`,
        exampleResponse: `{
  "deleted": 12
}`,
      },
    ],
  },
  {
    title: "Audit & Admin",
    items: [
      {
        method: "GET",
        path: "/v1/audit-logs",
        description: "Logs de auditoria.",
        auth: "Bearer (ADMIN)",
        headers: "Authorization: Bearer <token>",
        body: "—",
        query: "limit?, user_id?, user_email?, action?, request_id?, since?",
        response: "Array de audit logs",
        example: `GET /v1/audit-logs?limit=200&action=documents.update
Authorization: Bearer <token>`,
        exampleResponse: `[
  {
    "id": "audit-123",
    "action": "documents.update",
    "user_email": "admin@grupobrmed.com.br",
    "path": "/v1/documents/123",
    "status_code": 200
  }
]`,
      },
      {
        method: "GET",
        path: "/v1/admin/status",
        description: "Status do backend.",
        auth: "Bearer (ADMIN)",
        headers: "Authorization: Bearer <token>",
        body: "—",
        query: "—",
        response: "status, database, statistics",
        example: `GET /v1/admin/status
Authorization: Bearer <token>`,
        exampleResponse: `{
  "status": "online",
  "database": { "migrations_needed": false },
  "statistics": { "users": 12, "clinics": 4, "documents": 120 }
}`,
      },
      {
        method: "POST",
        path: "/v1/admin/migrate",
        description: "Migração administrativa.",
        auth: "Bearer (ADMIN)",
        headers: "Authorization: Bearer <token>",
        body: "—",
        query: "—",
        response: "status, migrations_executed",
        example: `POST /v1/admin/migrate
Authorization: Bearer <token>`,
        exampleResponse: `{
  "status": "success",
  "migrations_executed": true,
  "migration_files": ["001_add_multi_tenant.sql"]
}`,
      },
    ],
  },
]

const deployNotes = [
  "Serviço backend em Render com runtime Python.",
  "Build: pip install + requirements.txt.",
  "Start: gunicorn main:app com Uvicorn workers.",
  "Região padrão: Oregon.",
]

const authNotes = [
  "Front-end com NextAuth e Google OAuth corporativo.",
  "Backend com JWT para sessões e validações.",
]

const observabilityNotes = [
  "Logs automáticos com timestamp para auditoria.",
  "Histórico de decisões e justificativas por documento.",
  "Trilha de auditoria com usuário, data e ação.",
]

const securityNotes = [
  "Criptografia em trânsito (HTTPS/TLS).",
  "Criptografia em repouso (AES-256).",
  "Acesso granular por perfis e ações.",
  "Retenção e backup conforme requisitos legais.",
]

export default function DocsTecnicaPage() {
  const headerRef = useRef<HTMLElement | null>(null)
  const [headerHidden, setHeaderHidden] = useState(false)
  const [routeView, setRouteView] = useState<"front" | "api">("front")
  const sectionHighlight =
    "scroll-mt-24 transition-all duration-[1700ms] ease-out data-[highlight=true]:rounded-2xl data-[highlight=true]:bg-secondary/4 data-[highlight=true]:shadow-[0_18px_40px_-30px_rgba(0,120,145,0.35)]"

  const handleNavClick = (href: string) => (event: MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault()
    const target = document.querySelector(href)
    if (!target) return
    target.scrollIntoView({ behavior: "smooth", block: "center" })
    if (target instanceof HTMLElement) {
      target.dataset.highlight = "true"
      window.setTimeout(() => {
        target.dataset.highlight = "false"
      }, 2200)
    }
    if (window.history.replaceState) {
      window.history.replaceState(null, "", href)
    }
  }

  useEffect(() => {
    const node = headerRef.current
    if (!node) return
    const observer = new IntersectionObserver(
      ([entry]) => setHeaderHidden(!entry.isIntersecting),
      { threshold: 0.1 }
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  return (
    <div className="min-h-screen bg-[#EEF1F4] text-foreground">
      <div className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0">
          <div className="absolute -right-36 -top-36 h-96 w-96 rounded-full bg-[radial-gradient(circle_at_center,rgba(0,120,145,0.28),transparent_65%)]" />
          <div className="absolute -left-24 top-28 h-80 w-80 rounded-full bg-[radial-gradient(circle_at_center,rgba(25,59,79,0.2),transparent_65%)]" />
          <div className="absolute inset-0 bg-[linear-gradient(120deg,rgba(0,120,145,0.08),rgba(25,59,79,0.08),rgba(0,120,145,0.04))]" />
        </div>

        <header
          ref={headerRef}
          className="relative border-b border-primary/10 bg-gradient-to-r from-primary via-[#0f566f] to-secondary text-white"
        >
          <div className="mx-auto w-full max-w-[90rem] px-4 py-8 sm:px-6 xl:px-8 2xl:px-10">
            <div className="grid items-center gap-10 lg:gap-14 lg:grid-cols-[minmax(0,220px)_minmax(0,1fr)]">
              <div className="flex items-center gap-5 xl:-ml-4 2xl:-ml-8">
                <div className="relative h-12 w-36">
                  <Image src="/logo.png" alt="ProntuAI" fill className="object-contain" priority />
                </div>
                <Badge className="ml-1 border border-white/30 bg-white/10 text-white">Documentação técnica</Badge>
              </div>
              <div className="flex justify-start lg:justify-end">
                <a
                  href="/login"
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 rounded-md bg-white/15 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-white/25"
                >
                  Acessar ProntuAI
                  <ArrowRight className="size-4" />
                </a>
              </div>
            </div>
          </div>
        </header>
      </div>

      <main className="mx-auto w-full max-w-[90rem] px-4 py-12 sm:px-6 xl:px-8 2xl:px-10">
        <div className="grid items-start gap-10 lg:gap-14 lg:grid-cols-[minmax(0,220px)_minmax(0,1fr)]">
          <aside
            className={`min-w-0 space-y-4 lg:sticky lg:h-fit xl:-ml-4 2xl:-ml-8 ${
              headerHidden ? "lg:top-1/2 lg:-translate-y-1/2" : "lg:top-24"
            }`}
          >
            <div className="rounded-xl border border-primary/15 bg-card/90 p-4">
              <p className="text-xs font-bold uppercase tracking-[0.08em] text-secondary">Seções principais</p>
              <nav className="mt-3 flex flex-col gap-2 text-sm">
                {navPrimary.map((item) => (
                  <a
                    key={item.href}
                    href={item.href}
                    className="rounded-lg border border-transparent px-2 py-1 text-muted-foreground transition-colors hover:border-primary/20 hover:bg-primary/5 hover:text-foreground"
                    onClick={handleNavClick(item.href)}
                  >
                    {item.label}
                  </a>
                ))}
              </nav>
            </div>
            <div className="rounded-xl border border-primary/15 bg-card/90 p-4">
              <p className="text-xs font-bold uppercase tracking-[0.08em] text-secondary">Qualidade e governança</p>
              <nav className="mt-3 flex flex-col gap-2 text-sm">
                {navSecondary.map((item) => (
                  <a
                    key={item.href}
                    href={item.href}
                    className="rounded-lg border border-transparent px-2 py-1 text-muted-foreground transition-colors hover:border-primary/20 hover:bg-primary/5 hover:text-foreground"
                    onClick={handleNavClick(item.href)}
                  >
                    {item.label}
                  </a>
                ))}
              </nav>
            </div>
          </aside>

          <div className="min-w-0 flex flex-col gap-20">
            <section className={`space-y-6 ${sectionHighlight}`} id="visao">
              <div className="space-y-4">
                <Badge
                  variant="outline"
                  className="px-3 py-1 text-xs font-bold uppercase tracking-[0.08em] text-secondary"
                >
                  Visão técnica
                </Badge>
                <h1 className="text-3xl font-semibold text-foreground md:text-4xl">
                  Documentação técnica do Prontu<span className="font-bold text-cyan-800">AI</span> | (EM CONSTRUÇÃO)
                </h1>
              </div>
              <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
                <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
                <CardContent className="space-y-3 text-sm text-muted-foreground">
                  <p>
                    Este guia técnico descreve a arquitetura, integrações e configurações do ProntuAI,
                    servindo como referência para desenvolvimento, suporte e operação.
                  </p>
                </CardContent>
              </Card>
            </section>

            <section className={`space-y-6 ${sectionHighlight}`} id="pipeline">
              <div className="space-y-4">
                <Badge
                  variant="outline"
                  className="px-3 py-1 text-xs font-bold uppercase tracking-[0.08em] text-secondary"
                >
                  Pipeline técnico
                </Badge>
                <h2 className="text-2xl font-semibold text-foreground">Fluxo de processamento</h2>
              </div>
              <div className="grid gap-6 lg:grid-cols-3">
                {pipelineSteps.map((step) => (
                  <Card key={step.title} className="relative overflow-hidden border border-primary/15 bg-card/90">
                    <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2 text-base">
                        <Layers className="size-4 text-secondary" />
                        {step.title}
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="text-sm text-muted-foreground">{step.description}</CardContent>
                  </Card>
                ))}
              </div>
            </section>

            <section className={`space-y-6 ${sectionHighlight}`} id="stack">
              <div className="space-y-4">
                <Badge
                  variant="outline"
                  className="px-3 py-1 text-xs font-bold uppercase tracking-[0.08em] text-secondary"
                >
                  Stack principal
                </Badge>
                <h2 className="text-2xl font-semibold text-foreground">Tecnologias</h2>
              </div>
              <div className="grid gap-6 lg:grid-cols-2">
                <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
                  <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <Cpu className="size-4 text-secondary" />
                      Front-end
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm text-muted-foreground">
                    {stackFront.map((item) => (
                      <p key={item}>{item}</p>
                    ))}
                  </CardContent>
                </Card>
                <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
                  <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-secondary via-primary to-secondary" />
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <ServerCog className="size-4 text-secondary" />
                      Back-end
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm text-muted-foreground">
                    {stackBack.map((item) => (
                      <p key={item}>{item}</p>
                    ))}
                  </CardContent>
                </Card>
              </div>
            </section>

            <section className={`space-y-6 ${sectionHighlight}`} id="integracoes">
              <div className="space-y-4">
                <Badge
                  variant="outline"
                  className="px-3 py-1 text-xs font-bold uppercase tracking-[0.08em] text-secondary"
                >
                  Integrações
                </Badge>
                <h2 className="text-2xl font-semibold text-foreground">Serviços externos</h2>
              </div>
              <div className="grid gap-6 lg:grid-cols-3">
                {integracoes.map((item) => (
                  <Card key={item.title} className="relative overflow-hidden border border-primary/15 bg-card/90">
                    <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2 text-base">
                        <Database className="size-4 text-secondary" />
                        {item.title}
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="text-sm text-muted-foreground">{item.description}</CardContent>
                  </Card>
                ))}
              </div>
            </section>

            <section className={`space-y-6 ${sectionHighlight}`} id="rotas">
              <div className="space-y-4">
                <Badge
                  variant="outline"
                  className="px-3 py-1 text-xs font-bold uppercase tracking-[0.08em] text-secondary"
                >
                  Rotas
                </Badge>
                <h2 className="text-2xl font-semibold text-foreground">Rotas principais (Front e API)</h2>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-sm text-muted-foreground">
                  Alterne entre a visão de navegação do produto e os endpoints principais da API.
                </p>
                <div className="inline-flex rounded-full border border-primary/15 bg-white/70 p-1 text-sm font-semibold">
                  <button
                    type="button"
                    onClick={() => setRouteView("front")}
                    className={`rounded-full px-4 py-1 transition-colors ${
                      routeView === "front"
                        ? "bg-secondary text-white shadow-sm"
                        : "text-secondary/70 hover:text-secondary"
                    }`}
                  >
                    Front-end
                  </button>
                  <button
                    type="button"
                    onClick={() => setRouteView("api")}
                    className={`rounded-full px-4 py-1 transition-colors ${
                      routeView === "api"
                        ? "bg-secondary text-white shadow-sm"
                        : "text-secondary/70 hover:text-secondary"
                    }`}
                  >
                    API
                  </button>
                </div>
              </div>
              <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
                <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
                <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <CardTitle className="text-base">
                    {routeView === "front" ? "Interface (Front-end)" : "API (Back-end)"}
                  </CardTitle>
                  <span className="text-sm font-semibold uppercase tracking-[0.16em] text-secondary">
                    {routeView === "front" ? "Navegação" : "Endpoints"}
                  </span>
                </CardHeader>
                <CardContent className="space-y-4 text-sm text-muted-foreground">
                  {routeView === "front" ? (
                    <div className="space-y-4">
                      {frontendRoutes.map((item) => (
                        <div key={item.path} className="rounded-2xl border border-primary/10 bg-white/70 p-4">
                          <div className="flex flex-wrap items-center justify-between gap-3">
                            <div className="space-y-1">
                              <p className="text-sm font-semibold text-foreground">{item.path}</p>
                              <p className="text-[12px] uppercase tracking-[0.12em] text-secondary">{item.label}</p>
                            </div>
                            <Badge
                              variant="secondary"
                              className="h-5 px-3 text-[11px] font-semibold uppercase tracking-[0.14em]"
                            >
                              {item.access}
                            </Badge>
                          </div>
                          <p className="mt-2 text-sm text-muted-foreground">{item.description}</p>
                          <div className="mt-3 grid gap-3 text-sm text-muted-foreground sm:grid-cols-2">
                            <div className="space-y-1">
                              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-secondary">
                                Parâmetros
                              </p>
                              <p className="text-foreground/80">{item.params}</p>
                            </div>
                            <div className="space-y-1">
                              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-secondary">
                                Exemplo
                              </p>
                              <p className="text-foreground/80">{item.example}</p>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="space-y-6">
                      {apiRouteGroups.map((group, index) => (
                        <div
                          key={group.title}
                          className={`space-y-3 ${index === 0 ? "" : "border-t border-primary/10 pt-4"}`}
                        >
                          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-secondary">
                            {group.title}
                          </p>
                          <div className="space-y-3">
                            {group.items.map((item) => (
                              <div
                                key={`${item.method}-${item.path}`}
                                className="rounded-2xl border border-primary/10 bg-white/70 p-4"
                              >
                                <div className="flex items-start gap-3">
                                  <Badge
                                    variant="secondary"
                                    className="h-5 min-w-[56px] justify-center text-[11px] uppercase tracking-[0.14em]"
                                  >
                                    {item.method}
                                  </Badge>
                                  <div className="flex-1 space-y-2">
                                    <div>
                                      <p className="text-sm font-semibold text-foreground">{item.path}</p>
                                      <p className="text-sm text-muted-foreground">{item.description}</p>
                                    </div>
                                    <div className="grid gap-3 text-sm text-muted-foreground sm:grid-cols-2 lg:grid-cols-4">
                                      <div className="space-y-1">
                                        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-secondary">
                                          Auth
                                        </p>
                                        <p className="text-foreground/80">{item.auth}</p>
                                      </div>
                                      <div className="space-y-1">
                                        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-secondary">
                                          Headers
                                        </p>
                                        <p className="text-foreground/80">{item.headers ?? "—"}</p>
                                      </div>
                                      <div className="space-y-1">
                                        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-secondary">
                                          Query
                                        </p>
                                        <p className="text-foreground/80">{item.query}</p>
                                      </div>
                                      <div className="space-y-1">
                                        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-secondary">
                                          Body
                                        </p>
                                        <p className="text-foreground/80">{item.body}</p>
                                      </div>
                                    </div>
                                    <div className="space-y-1 text-sm text-muted-foreground">
                                      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-secondary">
                                        Response
                                      </p>
                                      <p className="text-foreground/80">{item.response ?? "—"}</p>
                                    </div>
                                    <div className="space-y-2 text-sm text-muted-foreground">
                                      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-secondary">
                                        Exemplo (request)
                                      </p>
                                      <pre className="whitespace-pre-wrap rounded-lg border border-primary/10 bg-white/80 p-3 text-[12px] text-foreground/80">
                                        {item.example ?? "—"}
                                      </pre>
                                    </div>
                                    <div className="space-y-2 text-sm text-muted-foreground">
                                      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-secondary">
                                        Exemplo (response)
                                      </p>
                                      <pre className="whitespace-pre-wrap rounded-lg border border-primary/10 bg-white/80 p-3 text-[12px] text-foreground/80">
                                        {item.exampleResponse ?? "—"}
                                      </pre>
                                    </div>
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </section>

            <section className={`space-y-6 ${sectionHighlight}`} id="auth">
              <div className="space-y-4">
                <Badge
                  variant="outline"
                  className="px-3 py-1 text-xs font-bold uppercase tracking-[0.08em] text-secondary"
                >
                  Auth
                </Badge>
                <h2 className="text-2xl font-semibold text-foreground">Autenticação e autorização</h2>
              </div>
              <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
                <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
                <CardContent className="space-y-2 text-sm text-muted-foreground">
                  {authNotes.map((item) => (
                    <p key={item}>{item}</p>
                  ))}
                </CardContent>
              </Card>
            </section>

            <section className={`space-y-6 ${sectionHighlight}`} id="deploy">
              <div className="space-y-4">
                <Badge
                  variant="outline"
                  className="px-3 py-1 text-xs font-bold uppercase tracking-[0.08em] text-secondary"
                >
                  Deploy
                </Badge>
                <h2 className="text-2xl font-semibold text-foreground">Deploy e runtime</h2>
              </div>
              <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
                <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-secondary via-primary to-secondary" />
                <CardContent className="space-y-2 text-sm text-muted-foreground">
                  {deployNotes.map((item) => (
                    <p key={item}>{item}</p>
                  ))}
                </CardContent>
              </Card>
            </section>

            <section className={`space-y-6 ${sectionHighlight}`} id="observabilidade">
              <div className="space-y-4">
                <Badge
                  variant="outline"
                  className="px-3 py-1 text-xs font-bold uppercase tracking-[0.08em] text-secondary"
                >
                  Observabilidade
                </Badge>
                <h2 className="text-2xl font-semibold text-foreground">Logs e auditoria</h2>
              </div>
              <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
                <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
                <CardContent className="space-y-2 text-sm text-muted-foreground">
                  {observabilityNotes.map((item) => (
                    <p key={item}>{item}</p>
                  ))}
                </CardContent>
              </Card>
            </section>

            <section className={`space-y-6 ${sectionHighlight}`} id="seguranca">
              <div className="space-y-4">
                <Badge
                  variant="outline"
                  className="px-3 py-1 text-xs font-bold uppercase tracking-[0.08em] text-secondary"
                >
                  Segurança
                </Badge>
                <h2 className="text-2xl font-semibold text-foreground">Boas práticas</h2>
              </div>
              <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
                <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-secondary via-primary to-secondary" />
                <CardContent className="space-y-2 text-sm text-muted-foreground">
                  {securityNotes.map((item) => (
                    <p key={item}>{item}</p>
                  ))}
                </CardContent>
              </Card>
            </section>
          </div>
        </div>
      </main>

      <footer className="border-t border-primary/10 bg-gradient-to-r from-primary via-[#0f566f] to-secondary text-white">
        <div className="mx-auto flex w-full max-w-[90rem] flex-wrap items-center justify-between gap-4 px-4 py-6 sm:px-6">
          <div className="flex items-center gap-3">
            <div className="relative h-8 w-24">
              <Image src="/logo.png" alt="ProntuAI" fill className="object-contain" />
            </div>
            <span className="text-xs uppercase tracking-[0.2em] text-white/70">Documentação técnica</span>
          </div>
          <div className="text-xs text-white/70">Prontu<span className="text-cyan-200">AI</span> · BR MED</div>
        </div>
      </footer>
    </div>
  )
}
