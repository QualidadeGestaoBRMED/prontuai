import type { TabelaComparacaoItem } from "@/types/process"

export type ProcessingStage = "upload" | "ocr" | "brnet" | "validation" | "completed"

export interface DocumentProcessingResult {
  cpf_processado: string
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
