export type DocumentApi = {
  id: string
  clinic_id: string
  uploaded_by_user_id: string
  uploaded_by_user_email?: string | null
  filename: string
  cpf?: string | null
  uploaded_at?: string | null
  exams_found?: string[] | null
  exams_ocr?: string[] | null
  exams_brnet?: string[] | null
  validation_status?: "pending" | "validated" | "rejected" | string
  ocr_markdown?: string | null
  run_id?: string | null
  result_payload?: any
  reviewed_by?: string | null
  reviewed_at?: string | null
  approval_reason?: string | null
  rejection_reason?: string | null
  confidence_score?: number | null
  quality_score?: number | null
  mandatory_coverage?: number | null
  created_at?: string | null
  updated_at?: string | null
}

export type DocumentQueue = "pendentes" | "checagem"

export type DocumentSummaryCounts = {
  approved: number
  rejected: number
  pending_review: number
  total: number
}

export type PaginatedDocumentsResponse = {
  items: DocumentApi[]
  page: number
  page_size: number
  total_items: number
  total_pages: number
  has_next: boolean
  summary_counts: DocumentSummaryCounts
}
