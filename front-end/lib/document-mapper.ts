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
  const cpfPersistido = typeof doc.cpf === "string" && doc.cpf.trim() && doc.cpf !== "Não encontrado" ? doc.cpf : null
  const cpfProcessado =
    typeof payload.cpf_processado === "string" && payload.cpf_processado.trim() && payload.cpf_processado !== "Não encontrado"
      ? payload.cpf_processado
      : null
  const identificadorConsulta =
    typeof payload.identificador_consulta === "string" && payload.identificador_consulta.trim()
      ? payload.identificador_consulta
      : null
  const displayIdentifier = cpfPersistido || cpfProcessado || identificadorConsulta || "N/A"
  const tabelaComparacao = Array.isArray(payload.tabela_comparacao)
    ? (payload.tabela_comparacao as Array<{ status?: string }>)
    : []
  const examesFaltantes = Array.isArray(validation.exames_faltantes)
    ? validation.exames_faltantes.length
    : tabelaComparacao.length > 0
      ? tabelaComparacao.filter((e) => e.status === "faltante").length
      : 0

  const examesExtras = Array.isArray(validation.exames_extras)
    ? validation.exames_extras.length
    : tabelaComparacao.length > 0
      ? tabelaComparacao.filter((e) => e.status === "extra_no_ocr").length
      : 0

  return {
    id: doc.id,
    batchId: doc.id,
    filename: doc.filename,
    cpf: displayIdentifier,
    patientName: payload.patient_name || payload.patientName || "Paciente",
    uploadedAt: toDate(doc.uploaded_at),
    processedAt: toDate(doc.updated_at || doc.uploaded_at),
    status: mapStatus(doc.validation_status),
    rejectionReason: payload.rejectionReason || doc.rejection_reason || payload.erro || validation.analysis || payload.decisao_final,
    approvalReason: payload.approvalReason || doc.approval_reason,
    examesFaltantes,
    examesExtras,
    result: payload,
    submittedBy: doc.uploaded_by_user_email || "-",
    reviewedBy: payload.reviewed_by || doc.reviewed_by || undefined,
    reviewedAt: payload.reviewed_at
      ? toDate(payload.reviewed_at)
      : doc.reviewed_at
        ? toDate(doc.reviewed_at)
        : undefined,
  }
}
