import { ProcessResult } from "@/types/process"
import { DocumentApi } from "@/types/document"

const toDate = (value?: string | null) => {
  if (!value) return new Date()
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? new Date() : date
}

const mapStatus = (validationStatus?: string | null): ProcessResult["status"] => {
  if (validationStatus === "validated") return "approved"
  if (validationStatus === "rejected") return "rejected"
  return "pending_review"
}

export const documentToProcessResult = (doc: DocumentApi): ProcessResult => {
  const payload = doc.result_payload || {}
  const validation = payload.validation_result || {}
  const examesFaltantes = Array.isArray(validation.exames_faltantes)
    ? validation.exames_faltantes.length
    : Array.isArray(payload.tabela_comparacao)
      ? payload.tabela_comparacao.filter((e: any) => e.status === "faltante").length
      : 0

  const examesExtras = Array.isArray(validation.exames_extras)
    ? validation.exames_extras.length
    : Array.isArray(payload.tabela_comparacao)
      ? payload.tabela_comparacao.filter((e: any) => e.status === "extra_no_ocr").length
      : 0

  return {
    id: doc.id,
    batchId: doc.id,
    filename: doc.filename,
    cpf: doc.cpf || "N/A",
    patientName: payload.patient_name || payload.patientName || "Paciente",
    uploadedAt: toDate(doc.uploaded_at),
    processedAt: toDate(doc.updated_at || doc.uploaded_at),
    status: mapStatus(doc.validation_status),
    rejectionReason: payload.erro || validation.analysis || payload.decisao_final,
    approvalReason: payload.approvalReason,
    examesFaltantes,
    examesExtras,
    result: payload,
    submittedBy: doc.uploaded_by_user_email || "-",
    reviewedBy: payload.reviewed_by,
    reviewedAt: payload.reviewed_at ? toDate(payload.reviewed_at) : undefined,
  }
}
