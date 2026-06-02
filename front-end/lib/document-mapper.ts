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

const isPresentString = (value: unknown): value is string =>
  typeof value === "string" && value.trim() !== "" && value !== "Não encontrado"

const asStringArray = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : []

export const documentToProcessResult = (doc: DocumentApi): ProcessResult => {
  const payload = doc.result_payload || {}
  const validation = payload.validation_result || {}
  const cpfPersistido = isPresentString(doc.cpf) ? doc.cpf : null
  const cpfProcessado = isPresentString(payload.cpf_processado) ? payload.cpf_processado : null
  const identificadorConsulta = isPresentString(payload.identificador_consulta) ? payload.identificador_consulta : null
  const displayIdentifier = cpfPersistido || cpfProcessado || identificadorConsulta || "N/A"
  const examesOcr =
    asStringArray(payload.ocr_result?.exames_extraidos).length > 0
      ? asStringArray(payload.ocr_result?.exames_extraidos)
      : asStringArray(payload.exames_ocr).length > 0
        ? asStringArray(payload.exames_ocr)
        : asStringArray(doc.exams_ocr).length > 0
          ? asStringArray(doc.exams_ocr)
          : asStringArray(doc.exams_found)
  const examesBrnet =
    asStringArray(payload.brmed_result?.exames_obrigatorios).length > 0
      ? asStringArray(payload.brmed_result?.exames_obrigatorios)
      : asStringArray(payload.exames_brnet).length > 0
        ? asStringArray(payload.exames_brnet)
        : asStringArray(doc.exams_brnet)
  const patientName =
    isPresentString(payload.patient_name)
      ? payload.patient_name
      : isPresentString(payload.patientName)
        ? payload.patientName
        : "Não identificado"
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
  const normalizedPayload = {
    ...payload,
    cpf: isPresentString(payload.cpf) ? payload.cpf : displayIdentifier,
    cpf_processado: cpfProcessado || displayIdentifier,
    identificador_consulta: identificadorConsulta || displayIdentifier,
    patient_name: patientName,
    ocr_result: {
      ...(payload.ocr_result || {}),
      text: payload.ocr_result?.text || "",
      exames_extraidos: examesOcr,
    },
    brmed_result: {
      ...(payload.brmed_result || {}),
      exames_obrigatorios: examesBrnet,
    },
  }

  return {
    id: doc.id,
    batchId: doc.id,
    filename: doc.filename,
    cpf: displayIdentifier,
    patientName,
    uploadedAt: toDate(doc.uploaded_at),
    processedAt: toDate(doc.updated_at || doc.uploaded_at),
    status: mapStatus(doc.validation_status),
    rejectionReason: payload.rejectionReason || doc.rejection_reason || payload.erro || validation.analysis || payload.decisao_final,
    approvalReason: payload.approvalReason || doc.approval_reason,
    examesFaltantes,
    examesExtras,
    result: normalizedPayload,
    submittedBy: doc.uploaded_by_user_email || "-",
    reviewedBy: payload.reviewed_by || doc.reviewed_by || undefined,
    reviewedAt: payload.reviewed_at
      ? toDate(payload.reviewed_at)
      : doc.reviewed_at
        ? toDate(doc.reviewed_at)
        : undefined,
  }
}
