import type { TabelaComparacaoItem } from "@/types/process"

export type ProcessingStage = "upload" | "ocr" | "brnet" | "validation" | "completed"

export interface DocumentProcessingResult {
  status?: "success" | "partial" | "error"
  cpf_processado: string
  passaporte_processado?: string | null
  cnpj_processado?: string | null
  tipo_identificador_consulta?: "cpf" | "passaporte" | string
  identificador_consulta?: string | null
  fonte_exames_obrigatorios?: string | null
  patient_name?: string
  document_id?: string
  exames_ocr: string[]
  exames_brnet: string[]
  tabela_comparacao: TabelaComparacaoItem[]
  analise_comparacao: string
  decisao_final: string
  analysis_details?: {
    quality?: {
      score: number
      total_chars: number
      total_lines: number
      alpha_ratio: number
      digit_ratio: number
      unique_line_ratio: number
    }
    field_checks?: {
      field: string
      label: string
      found: boolean
      evidence: string[]
    }[]
    match_confidence?: {
      exame: string
      status: "encontrado" | "faltante" | "parcialmente_encontrado" | "extra_no_ocr"
      match_type: "exato" | "similar" | "parcial" | "inferido" | "ausente" | "extra" | "invalido"
      ocr_match: string | null
      evidence: string[]
      justificativa?: string
    }[]
  }
  erro?: string
  error?: string
  error_type?: string
  error_code?: string
  error_source?: string | null
  error_http_status?: number | null
  business_error?: {
    code?: string
    type?: string
    message?: string
    source?: string | null
    http_status?: number | null
    retryable?: boolean
    trace_id?: string
  } | null
}

export interface ProcessingDocumentState {
  id: string
  file?: File
  fileName: string
  fileSize: number
  stage: ProcessingStage
  progress: number
  displayProgress: number
  statusMessage: string
  result?: DocumentProcessingResult
  error?: string
  jobId?: string
  lastUpdatedAt?: Date
}
