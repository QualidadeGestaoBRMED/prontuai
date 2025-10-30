// Types for document processing and results

export type ProcessStatus = 'processing' | 'completed' | 'error'
export type ProcessStep = 'upload' | 'ocr' | 'brmed' | 'validation' | 'completed'
export type DocumentStatus = 'pending' | 'processing' | 'completed' | 'error'
export type ResultStatus = 'approved' | 'rejected' | 'pending_review'

// Individual document within a batch
export interface ProcessDocument {
  filename: string
  status: DocumentStatus
  progress: number  // 0-100
  error?: string
}

// Active process notification (shows in progress bar and notification center)
export interface ProcessNotification {
  id: string
  batchId: string
  filename: string  // Se único documento, ou nome do lote
  documentCount: number
  status: ProcessStatus
  progress: number  // 0-100
  currentStep: ProcessStep
  stepMessage: string  // Ex: "Validando exames..."
  startedAt: Date
  completedAt?: Date
  documents: ProcessDocument[]
  error?: string
}

// Result of a completed process
export interface ProcessResult {
  id: string
  batchId: string  // Agrupa documentos do mesmo upload
  filename: string
  cpf: string
  patientName: string
  uploadedAt: Date
  processedAt: Date
  status: ResultStatus
  rejectionReason?: string
  examesFaltantes: number
  examesExtras: number
  result: DocumentProcessingResult  // From backend
  submittedBy: string  // Email do usuário (vem do NextAuth)
  reviewedBy?: string
  reviewedAt?: Date
}

// Backend response structure (from existing API)
export interface DocumentProcessingResult {
  cpf: string
  patient_name?: string
  ocr_result?: {
    text: string
    exames_extraidos: string[]
  }
  brmed_result?: {
    exames_obrigatorios: string[]
    empresa?: string
  }
  validation_result?: {
    exames_faltantes: string[]
    exames_extras: string[]
    analysis?: string
    similarity_scores?: Record<string, number>
  }
  status: 'success' | 'partial' | 'error'
  error?: string
}

// State for progress bar UI
export interface ProgressBarState {
  minimized: boolean
  processId: string | null
}

// Helper type for creating new process
export type CreateProcessInput = Pick<ProcessNotification, 'batchId' | 'filename' | 'documentCount'>
