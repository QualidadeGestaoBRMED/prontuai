/**
 * Configuração centralizada da aplicação
 */

// URL base da API - usa variável de ambiente ou fallback para localhost
export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Endpoints da API
export const API_ENDPOINTS = {
  // Auth
  AUTH_GOOGLE: `${API_URL}/v1/auth/google`,

  // Users
  USERS: `${API_URL}/v1/users`,
  USER_BY_ID: (id: string) => `${API_URL}/v1/users/${id}`,

  // Clinics
  CLINICS: `${API_URL}/v1/clinics`,
  CLINIC_BY_ID: (id: string) => `${API_URL}/v1/clinics/${id}`,

  // FAQ/Chat
  FAQ: `${API_URL}/v1/faq`,

  // Documents (Legacy - pode dar timeout)
  PROCESS_DOCUMENT_STREAM: `${API_URL}/v1/processar-documento-stream`,

  // Documents (Async - recomendado)
  PROCESS_DOCUMENT_ASYNC: `${API_URL}/v1/processar-documento-async`,

  // Jobs
  JOB_STATUS: (jobId: string) => `${API_URL}/v1/jobs/${jobId}`,
  JOBS_LIST: `${API_URL}/v1/jobs`,
  CANCEL_JOB: (jobId: string) => `${API_URL}/v1/jobs/${jobId}`,
} as const;
