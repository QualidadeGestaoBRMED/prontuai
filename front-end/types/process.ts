// Tipos para processamento de documentos e resultados

export type ProcessStatus = 'processing' | 'completed' | 'error'
export type ProcessStep = 'upload' | 'ocr' | 'brmed' | 'validation' | 'completed'
export type DocumentStatus = 'pending' | 'processing' | 'completed' | 'error'
export type ResultStatus = 'approved' | 'rejected' | 'pending_review'
export type TabelaComparacaoItem = {
  exame: string
  status: "encontrado" | "faltante" | "parcialmente_encontrado" | "extra_no_ocr"
  justificativa: string
}

export type FieldCheck = {
  field: string
  label: string
  found: boolean
  evidence: string[]
}

export type MatchConfidence = {
  exame: string
  status: "encontrado" | "faltante" | "parcialmente_encontrado" | "extra_no_ocr"
  match_type: "exato" | "similar" | "parcial" | "inferido" | "ausente" | "extra" | "invalido"
  ocr_match: string | null
  evidence: string[]
  justificativa?: string
}

export type AnalysisDetails = {
  quality: {
    score: number
    total_chars: number
    total_lines: number
    alpha_ratio: number
    digit_ratio: number
    unique_line_ratio: number
  }
  field_checks: FieldCheck[]
  match_confidence: MatchConfidence[]
}

// Documento individual dentro de um lote
export interface ProcessDocument {
  filename: string
  status: DocumentStatus
  progress: number  // 0-100
  error?: string
}

// Notificação de processo ativo (mostra na barra de progresso e centro de notificações)
export interface ProcessNotification {
  id: string
  batchId: string
  filename: string  // Se único documento, ou nome do lote
  documentCount: number
  originPath?: string
  status: ProcessStatus
  progress: number  // 0-100
  currentStep: ProcessStep
  stepMessage: string  // Ex: "Validando exames..."
  startedAt: Date
  completedAt?: Date
  documents: ProcessDocument[]
  error?: string
}

// Resultado de um processo concluído
export interface ProcessResult {
  id: string
  batchId: string  // Agrupa documentos do mesmo upload
  filename: string
  clinicId?: string
  clinicName?: string
  cpf: string
  patientName: string
  uploadedAt: Date
  processedAt: Date
  status: ResultStatus
  rejectionReason?: string
  approvalReason?: string  // Justificativa para aprovação manual (quando IA rejeitou)
  examesFaltantes: number
  examesExtras: number
  result: DocumentProcessingResult  // Do backend
  submittedBy: string  // Email do usuário (vem do NextAuth)
  reviewedBy?: string
  reviewedAt?: Date
}

// Estrutura de resposta do backend (da API existente)
export interface DocumentProcessingResult {
  cpf: string
  cpf_processado?: string
  passaporte_processado?: string | null
  cnpj_processado?: string | null
  tipo_identificador_consulta?: "cpf" | "passaporte" | string
  identificador_consulta?: string | null
  fonte_exames_obrigatorios?: string | null
  patient_name?: string
  document_id?: string
  ocr_result?: {
    text: string
    exames_extraidos: string[]
  }
  brmed_result?: {
    exames_obrigatorios: string[]
    empresa?: string
    source?: string | null
    pedido_exame_id?: number | string | null
    tipo_pedido_exame?: string | null
    data_previsao_liberacao?: string | null
    atendimento_realizado_em?: string | null
  }
  tabela_comparacao?: TabelaComparacaoItem[]
  analysis_details?: AnalysisDetails
  validation_result?: {
    exames_faltantes: string[]
    exames_extras: string[]
    analysis?: string
    similarity_scores?: Record<string, number>
  }
  status: 'success' | 'partial' | 'error'
  error?: string
  erro?: string
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

// Estado para UI da barra de progresso
export interface ProgressBarState {
  minimized: boolean
  processId: string | null
}

// Tipo auxiliar para criar novo processo
export type CreateProcessInput = Pick<
  ProcessNotification,
  'batchId' | 'filename' | 'documentCount' | 'originPath'
>
