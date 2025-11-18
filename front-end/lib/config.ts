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

  // FAQ/Chat
  FAQ: `${API_URL}/v1/faq`,

  // Documents
  PROCESS_DOCUMENT_STREAM: `${API_URL}/v1/processar-documento-stream`,
} as const;
