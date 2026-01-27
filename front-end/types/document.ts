export type DocumentApi = {
  id: string
  clinic_id: string
  uploaded_by_user_id: string
  uploaded_by_user_email?: string | null
  filename: string
  cpf?: string | null
  uploaded_at?: string | null
  exams_found?: string[] | null
  validation_status?: "pending" | "validated" | "rejected" | string
  ocr_markdown?: string | null
  run_id?: string | null
  result_payload?: any
  confidence_score?: number | null
  quality_score?: number | null
  mandatory_coverage?: number | null
  created_at?: string | null
  updated_at?: string | null
}
