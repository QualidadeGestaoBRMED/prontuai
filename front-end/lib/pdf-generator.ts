import jsPDF from "jspdf"
import { ProcessResult } from "@/types/process"
import { format } from "date-fns"
import { ptBR } from "date-fns/locale"

export function generateResultPDF(result: ProcessResult): void {
  const doc = new jsPDF()
  const pageWidth = doc.internal.pageSize.getWidth()
  const margin = 20
  const contentWidth = pageWidth - 2 * margin
  let yPosition = margin

  // Helper function to add text with word wrap
  const addText = (text: string, fontSize: number = 10, isBold: boolean = false) => {
    doc.setFontSize(fontSize)
    if (isBold) {
      doc.setFont("helvetica", "bold")
    } else {
      doc.setFont("helvetica", "normal")
    }
    const lines = doc.splitTextToSize(text, contentWidth)

    // Check if we need a new page
    if (yPosition + (lines.length * fontSize * 0.5) > doc.internal.pageSize.getHeight() - margin) {
      doc.addPage()
      yPosition = margin
    }

    doc.text(lines, margin, yPosition)
    yPosition += lines.length * fontSize * 0.5 + 3
  }

  const addSpace = (space: number = 5) => {
    yPosition += space
  }

  const addDivider = () => {
    doc.setDrawColor(200, 200, 200)
    doc.line(margin, yPosition, pageWidth - margin, yPosition)
    yPosition += 8
  }

  // Header
  doc.setFillColor(59, 130, 246) // Blue
  doc.rect(0, 0, pageWidth, 40, "F")
  doc.setTextColor(255, 255, 255)
  addText("BRMED - Relatório de Processamento", 18, true)
  doc.setTextColor(255, 255, 255)
  addText(result.filename, 12)
  doc.setTextColor(0, 0, 0)
  addSpace(5)

  // Status Badge
  const statusText = result.status === "approved" ? "APROVADO" :
                     result.status === "rejected" ? "REJEITADO" : "PENDENTE"
  const statusColor = result.status === "approved" ? [34, 197, 94] :
                      result.status === "rejected" ? [239, 68, 68] : [251, 191, 36]

  doc.setFillColor(statusColor[0], statusColor[1], statusColor[2])
  doc.setTextColor(255, 255, 255)
  const statusWidth = doc.getTextWidth(statusText) + 10
  doc.roundedRect(pageWidth - margin - statusWidth, yPosition - 8, statusWidth, 10, 3, 3, "F")
  doc.text(statusText, pageWidth - margin - statusWidth + 5, yPosition - 2)
  doc.setTextColor(0, 0, 0)
  addSpace(10)

  // Basic Information Section
  addText("Informações Básicas", 14, true)
  addSpace(3)

  addText(`CPF: ${result.cpf}`, 10)
  addText(`Paciente: ${result.patientName}`, 10)
  addText(`Data de Upload: ${format(result.uploadedAt, "dd/MM/yyyy 'às' HH:mm", { locale: ptBR })}`, 10)
  addText(`Data de Processamento: ${format(result.processedAt, "dd/MM/yyyy 'às' HH:mm", { locale: ptBR })}`, 10)
  addText(`Enviado por: ${result.submittedBy}`, 10)

  if (result.reviewedBy) {
    addText(`Revisado por: ${result.reviewedBy}`, 10)
    if (result.reviewedAt) {
      addText(`Data de Revisão: ${format(result.reviewedAt, "dd/MM/yyyy 'às' HH:mm", { locale: ptBR })}`, 10)
    }
  }

  addSpace(5)
  addDivider()

  // Summary Section
  addText("Resumo de Exames", 14, true)
  addSpace(3)

  const examCount = Array.isArray(result.result.ocr_result?.exames_extraidos) ? result.result.ocr_result.exames_extraidos.length : 0
  const requiredCount = Array.isArray(result.result.brmed_result?.exames_obrigatorios) ? result.result.brmed_result.exames_obrigatorios.length : 0

  addText(`Exames Encontrados no Documento: ${examCount}`, 10)
  addText(`Exames Obrigatórios (BRMED): ${requiredCount}`, 10)
  addText(`Exames Faltantes: ${result.examesFaltantes}`, 10, result.examesFaltantes > 0)
  addText(`Exames Extras: ${result.examesExtras}`, 10)

  addSpace(5)
  addDivider()

  // Rejection Reason (if applicable)
  if (result.status === "rejected" && result.rejectionReason) {
    doc.setFillColor(254, 226, 226)
    doc.roundedRect(margin - 5, yPosition - 5, contentWidth + 10, 30, 3, 3, "F")
    addText("Motivo da Rejeição", 12, true)
    addText(result.rejectionReason, 10)
    addSpace(5)
    addDivider()
  }

  // Analysis Section
  if (result.result.validation_result?.analysis) {
    addText("Análise de Validação", 14, true)
    addSpace(3)
    addText(result.result.validation_result.analysis, 10)
    addSpace(5)
    addDivider()
  }

  // Detailed Comparison
  addText("Comparação Detalhada de Exames", 14, true)
  addSpace(5)

  // Exames Extraídos
  addText("Exames Encontrados no Documento:", 12, true)
  addSpace(2)
  if (Array.isArray(result.result.ocr_result?.exames_extraidos) && result.result.ocr_result.exames_extraidos.length > 0) {
    result.result.ocr_result.exames_extraidos.forEach((exame, index) => {
      addText(`${index + 1}. ${exame}`, 9)
    })
  } else {
    addText("Nenhum exame extraído", 9)
  }
  addSpace(5)

  // Exames Obrigatórios
  addText("Exames Obrigatórios (BRMED):", 12, true)
  addSpace(2)
  if (Array.isArray(result.result.brmed_result?.exames_obrigatorios) && result.result.brmed_result.exames_obrigatorios.length > 0) {
    result.result.brmed_result.exames_obrigatorios.forEach((exame, index) => {
      addText(`${index + 1}. ${exame}`, 9)
    })
  } else {
    addText("Nenhum exame obrigatório", 9)
  }
  addSpace(5)

  // Exames Faltantes
  if (result.result.validation_result?.exames_faltantes && result.result.validation_result.exames_faltantes.length > 0) {
    doc.setTextColor(220, 38, 38)
    addText("Exames Faltantes:", 12, true)
    doc.setTextColor(0, 0, 0)
    addSpace(2)
    result.result.validation_result.exames_faltantes.forEach((exame, index) => {
      doc.setTextColor(185, 28, 28)
      addText(`${index + 1}. ${exame}`, 9)
      doc.setTextColor(0, 0, 0)
    })
    addSpace(5)
  }

  // Exames Extras
  if (result.result.validation_result?.exames_extras && result.result.validation_result.exames_extras.length > 0) {
    doc.setTextColor(37, 99, 235)
    addText("Exames Extras no Documento:", 12, true)
    doc.setTextColor(0, 0, 0)
    addSpace(2)
    result.result.validation_result.exames_extras.forEach((exame, index) => {
      doc.setTextColor(29, 78, 216)
      addText(`${index + 1}. ${exame}`, 9)
      doc.setTextColor(0, 0, 0)
    })
  }

  // Footer
  const pageCount = doc.getNumberOfPages()
  for (let i = 1; i <= pageCount; i++) {
    doc.setPage(i)
    doc.setFontSize(8)
    doc.setTextColor(150, 150, 150)
    doc.text(
      `Página ${i} de ${pageCount} - Gerado em ${format(new Date(), "dd/MM/yyyy 'às' HH:mm", { locale: ptBR })}`,
      pageWidth / 2,
      doc.internal.pageSize.getHeight() - 10,
      { align: "center" }
    )
  }

  // Download
  const fileName = `resultado-${result.cpf}-${format(new Date(), "yyyy-MM-dd-HHmmss")}.pdf`
  doc.save(fileName)
}
