/**
 * Tipos para o sistema de jobs assíncronos
 */

import { DocumentProcessingResult } from "@/types/document-processing"

/**
 * Status possíveis de um job
 */
export type JobStatus = "pending" | "in_progress" | "completed" | "failed" | "cancelled"

/**
 * Etapas do processamento
 */
export type JobStep = "pending" | "upload" | "ocr" | "brmed" | "validacao" | "concluido" | "erro"

/**
 * Resposta da criação de um job
 */
export interface CreateJobResponse {
  job_id: string
  status: JobStatus
  message: string
  poll_url: string
}

/**
 * Status detalhado de um job
 */
export interface Job {
  job_id: string
  job_type: string
  status: JobStatus
  progress: number // 0-100
  current_step: JobStep
  message: string
  created_at: string
  started_at: string | null
  completed_at: string | null
  result: DocumentProcessingResult | null
  error: string | null
  metadata: JobMetadata
}

/**
 * Metadados do job
 */
export interface JobMetadata {
  filename: string
  file_size: string
  num_exames_obrigatorios: number
}

/**
 * Resposta da listagem de jobs
 */
export interface ListJobsResponse {
  total: number
  jobs: Job[]
}

/**
 * Opções de polling
 */
export interface PollingOptions {
  /**
   * Intervalo entre polls em milissegundos
   * @default 2000
   */
  interval?: number

  /**
   * Timeout máximo em milissegundos
   * @default 300000 (5 minutos)
   */
  timeout?: number

  /**
   * Callback executado a cada atualização de progresso
   */
  onProgress?: (job: Job) => void

  /**
   * Callback executado quando o job completa
   */
  onComplete?: (result: DocumentProcessingResult) => void

  /**
   * Callback executado quando ocorre erro
   */
  onError?: (error: string) => void
}
