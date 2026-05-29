/**
 * Configuração centralizada da aplicação
 */

// URL base da API de backend (uso server-side)
export const API_URL = process.env.BACKEND_API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Base do proxy interno (uso client-side para evitar expor token JWT no browser)
export const API_PROXY_BASE = process.env.NEXT_PUBLIC_API_PROXY_BASE || "/api/proxy";

// Endpoints da API
export const API_ENDPOINTS = {
  // Auth
  AUTH_GOOGLE: `${API_URL}/v1/auth/google`,

  // Users
  USERS: `${API_PROXY_BASE}/v1/users`,
  USER_BY_ID: (id: string) => `${API_PROXY_BASE}/v1/users/${id}`,

  // Clinics
  CLINICS: `${API_PROXY_BASE}/v1/clinics`,
  CLINIC_BY_ID: (id: string) => `${API_PROXY_BASE}/v1/clinics/${id}`,

  // Documents (Legacy - pode dar timeout)
  PROCESS_DOCUMENT_STREAM: `${API_PROXY_BASE}/v1/processar-documento-stream`,

  // Documents (Async - recomendado)
  PROCESS_DOCUMENT_ASYNC: `${API_PROXY_BASE}/v1/processar-documento-async`,

  // Documents list
  DOCUMENTS: `${API_PROXY_BASE}/v1/documents`,
  DOCUMENTS_PAGED: `${API_PROXY_BASE}/v1/documents/paged`,
  DOCUMENT_VIEW: (id: string) => `${API_PROXY_BASE}/v1/documents/${id}/view`,

  // Notifications
  NOTIFICATIONS: `${API_PROXY_BASE}/v1/notifications`,
  NOTIFICATION_READ: (id: string) => `${API_PROXY_BASE}/v1/notifications/${id}/read`,
  NOTIFICATIONS_READ_ALL: `${API_PROXY_BASE}/v1/notifications/read-all`,
  NOTIFICATIONS_CLEAR: `${API_PROXY_BASE}/v1/notifications`,

  // Jobs
  JOB_STATUS: (jobId: string) => `${API_PROXY_BASE}/v1/jobs/${jobId}`,
  JOBS_LIST: `${API_PROXY_BASE}/v1/jobs`,
  CANCEL_JOB: (jobId: string) => `${API_PROXY_BASE}/v1/jobs/${jobId}`,

  // Audit Logs
  AUDIT_LOGS: `${API_PROXY_BASE}/v1/audit-logs`,
} as const;
