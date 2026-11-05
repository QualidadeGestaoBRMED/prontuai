"use client"

import { format } from "date-fns"
import { ptBR } from "date-fns/locale"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { ScrollArea } from "@/components/ui/scroll-area"
import { ProcessResult, TabelaComparacaoItem } from "@/types/process"
import ExamesComparativoTable from "@/components/exames-comparativo-table"
import { Archive, Download } from "lucide-react"
import { useRouter } from "next/navigation"
import { CLASSE_TAG_REENVIO, rotuloReenvio } from "@/lib/reenvio"

interface DocumentDetailsModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  result: ProcessResult | null
  onDownloadPDF?: () => void
}

/**
 * Os exames da comparação nas duas partes da Checagem: os **previstos no BR NET**
 * e, numa seção à parte e fechada, os que vieram **além do previsto**. Antes era
 * uma tabela só ("Comparação Detalhada"), com o "Extra no OCR" no meio da grade
 * do BR NET — o mesmo pedido de padronização que a Checagem já atendeu.
 */
function ExamesPorPrevisao({ tabela }: { tabela: TabelaComparacaoItem[] }) {
  const previstos = tabela.filter((item) => item.status !== "extra_no_ocr")
  const alem = tabela.filter((item) => item.status === "extra_no_ocr")
  return (
    <div>
      <h4 className="font-semibold mb-3">Exames previstos no BR NET</h4>
      {previstos.length > 0 && (
        <div className="mb-4">
          <ExamesComparativoTable tabela={previstos} />
        </div>
      )}
      {alem.length > 0 && (
        <details className="mb-6 rounded-lg border">
          <summary className="cursor-pointer px-3 py-2 text-sm font-medium">
            Exames além do previsto no BR NET ({alem.length})
            <span className="block text-xs font-normal text-muted-foreground">
              Vieram no prontuário, mas não estão previstos no BR NET para este atendimento.
            </span>
          </summary>
          <div className="border-t px-1 pb-1">
            <ExamesComparativoTable tabela={alem} rotuloColunaExame="Exame no prontuário" rotuloExtra="Além do previsto" />
          </div>
        </details>
      )}
    </div>
  )
}

export function DocumentDetailsModal({
  open,
  onOpenChange,
  result,
  onDownloadPDF,
}: DocumentDetailsModalProps) {
  const router = useRouter()
  if (!result) return null

  const getStatusBadge = (result: ProcessResult) => {
    const { status, reviewedBy } = result

    // Approved by human (final approval)
    if (status === "approved" && reviewedBy) {
      return (
        <Badge variant="default" className="bg-green-500 hover:bg-green-600">
          Aprovado por Revisor
        </Badge>
      )
    }

    // Approved by AI, awaiting human validation
    if (status === "approved" && !reviewedBy) {
      return (
        <Badge variant="secondary" className="bg-amber-100 text-amber-700 hover:bg-amber-200">
          Aprovado pela IA - Aguardando Validação Humana
        </Badge>
      )
    }

    // Rejected by AI, awaiting human review
    if (status === "pending_review") {
      return (
        <Badge variant="secondary" className="bg-orange-100 text-orange-700 hover:bg-orange-200">
          Rejeitado pela IA - Aguardando Revisão Humana
        </Badge>
      )
    }

    // Rejected by human (final rejection)
    if (status === "rejected" && reviewedBy) {
      return (
        <Badge variant="destructive">
          Documentos Incompletos - Reenviar
        </Badge>
      )
    }

    // Reenvio de prontuário já liberado ou em revisão: não volta para a revisão
    if (status === "resubmission") {
      return (
        <Badge variant="outline" className={CLASSE_TAG_REENVIO}>
          {rotuloReenvio(result.result.reenvio)}
        </Badge>
      )
    }

    // Fallback
    return <Badge variant="secondary">{status}</Badge>
  }

  const canResend = result.status === "pending_review" || result.status === "rejected"
  const highlightLiberacao = (text?: string | null) => {
    if (!text) return null
    const phrase = "Liberação concedida"
    const lower = text.toLowerCase()
    const idx = lower.indexOf(phrase.toLowerCase())
    if (idx === -1) return text
    const before = text.slice(0, idx)
    const match = text.slice(idx, idx + phrase.length)
    const after = text.slice(idx + phrase.length)
    return (
      <>
        {before}
        <span className="font-semibold text-emerald-700">{match}</span>
        {after}
      </>
    )
  }

  const handleReenviar = () => {
    const params = new URLSearchParams()
    params.set("reenviar", "1")
    if (result.cpf) params.set("cpf", result.cpf)
    if (result.filename) params.set("filename", result.filename)
    router.push(`/anexar-prontuario?${params.toString()}`)
    onOpenChange(false)
  }

  // No disco e no Drive o arquivo se chama `<id do documento>_<nome>`; o aviso
  // mostra só o nome. O prefixo é o que impede colisão no Drive: cerca de 6%
  // dos arquivados dividem o nome com outro documento.
  const nomeArquivado = result.storageFilename?.replace(
    /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}_/i,
    "",
  )

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[90vw] max-w-6xl max-h-[90vh] p-4">
        <DialogHeader className="pr-8">
          <div className="space-y-1">
            <DialogTitle className="text-2xl">
              Detalhes do Documento
            </DialogTitle>
            <DialogDescription>{result.filename}</DialogDescription>
          </div>
          <div className="absolute top-4 right-12">
            {getStatusBadge(result)}
          </div>
        </DialogHeader>

        <ScrollArea className="max-h-[calc(90vh-12rem)] pr-2">
          <div className="space-y-6">
            {/* Basic Information */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">CPF</p>
                <p className="font-medium font-mono">{result.cpf}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Paciente</p>
                <p className="font-medium">{result.patientName}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Data de Upload</p>
                <p className="text-sm">
                  {format(result.uploadedAt, "dd/MM/yyyy 'às' HH:mm", {
                    locale: ptBR,
                  })}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">
                  Data de Processamento
                </p>
                <p className="text-sm">
                  {format(result.processedAt, "dd/MM/yyyy 'às' HH:mm", {
                    locale: ptBR,
                  })}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Enviado por</p>
                <p className="text-sm">{result.submittedBy}</p>
              </div>
              {result.archivedAt && (
                <div className="col-span-2 rounded-lg border bg-muted/30 p-3">
                  <p className="flex items-center gap-2 text-sm font-medium text-foreground">
                    <Archive className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                    Arquivado em{" "}
                    {format(result.archivedAt, "dd/MM/yyyy", { locale: ptBR })}
                  </p>
                  <p className="mt-1 text-xs text-foreground/80">
                    O PDF não está mais disponível para visualização. Para recuperá-lo, entre em
                    contato com o setor de Qualidade e Gestão e informe o arquivo abaixo:
                  </p>
                  {nomeArquivado && (
                    <p className="mt-2 break-all rounded border bg-background px-2 py-1 font-mono text-xs text-foreground">
                      {nomeArquivado}
                    </p>
                  )}
                </div>
              )}
              {result.reviewedBy && (
                <div>
                  <p className="text-sm text-muted-foreground">Revisado por</p>
                  <p className="text-sm">{result.reviewedBy}</p>
                  {result.reviewedAt && (
                    <p className="text-xs text-muted-foreground">
                      {format(result.reviewedAt, "dd/MM/yyyy 'às' HH:mm", {
                        locale: ptBR,
                      })}
                    </p>
                  )}
                </div>
              )}
            </div>

            <Separator />

            {/* Summary Counters */}
            <div className="grid grid-cols-3 gap-4">
              <div className="text-center p-4 border rounded-lg bg-muted/30">
                <p className="text-2xl font-bold">
                  {Array.isArray(result.result.ocr_result?.exames_extraidos) ? result.result.ocr_result.exames_extraidos.length : 0}
                </p>
                <p className="text-sm text-muted-foreground">
                  Exames no Documento
                </p>
              </div>
              <div className="text-center p-4 border rounded-lg bg-muted/30">
                <p className="text-2xl font-bold">
                  {Array.isArray(result.result.brmed_result?.exames_obrigatorios) ? result.result.brmed_result.exames_obrigatorios.length : 0}
                </p>
                <p className="text-sm text-muted-foreground">
                  Exames Obrigatórios
                </p>
              </div>
              <div className="text-center p-4 border rounded-lg bg-muted/30">
                <p className="text-2xl font-bold text-red-600">
                  {result.examesFaltantes}
                </p>
                <p className="text-sm text-muted-foreground">
                  Exames Faltantes
                </p>
              </div>
            </div>


            {/* Rejection Reason (if rejected) */}
            {result.status === "rejected" && result.rejectionReason && (
              <div className="p-4 border border-red-200 rounded-lg bg-red-50">
                <h4 className="font-semibold text-red-900 mb-2">
                  Motivo da Rejeição
                </h4>
                <p className="text-sm text-red-700">{result.rejectionReason}</p>
              </div>
            )}

            {/* Analysis */}
            {result.result.validation_result?.analysis && (
              <>
                <Separator />
                <div>
                  <h4 className="font-semibold mb-3">Análise de Validação</h4>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    {highlightLiberacao(result.result.validation_result?.analysis)}
                  </p>
                </div>
              </>
            )}

            {/* Checklist de Campos */}
            {result.result.analysis_details?.field_checks?.length ? (
              <>
                <Separator />
                <div>
                  <h4 className="font-semibold mb-3">Checklist de Campos</h4>
                  <div className="grid grid-cols-2 gap-2">
                    {result.result.analysis_details.field_checks.map((item) => (
                      <div
                        key={item.field}
                        className="flex items-center justify-between rounded border px-3 py-2"
                      >
                        <span className="text-sm">{item.label}</span>
                        <Badge
                          variant="secondary"
                          className={item.found ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-600"}
                        >
                          {item.found ? "Encontrado" : "Não encontrado"}
                        </Badge>
                      </div>
                    ))}
                  </div>

                  <details className="mt-3">
                    <summary className="text-sm text-muted-foreground cursor-pointer">
                      Evidências (trechos do OCR onde o campo aparece)
                    </summary>
                    <div className="mt-2 space-y-2">
                      {result.result.analysis_details.field_checks.map((item) => (
                        item.evidence?.length ? (
                          <div key={`${item.field}-evidence`} className="text-sm">
                            <p className="font-medium">{item.label}</p>
                            <ul className="text-muted-foreground list-disc ml-5">
                              {item.evidence.map((line, idx) => (
                                <li key={`${item.field}-${idx}`}>{line}</li>
                              ))}
                            </ul>
                          </div>
                        ) : null
                      ))}
                    </div>
                  </details>
                </div>
              </>
            ) : null}

            <Separator />

            {/* Exames previstos no BR NET e, à parte, os além do previsto — como na Checagem */}
            <ExamesPorPrevisao
              tabela={Array.isArray(result.result.tabela_comparacao) ? result.result.tabela_comparacao : []}
            />
          </div>
        </ScrollArea>

        {/* Footer Actions */}
        <div className="flex items-center justify-between pt-4 border-t">
          {(canResend || onDownloadPDF) && (
            <div className="flex gap-2">
              {onDownloadPDF && (
                <Button variant="outline" size="sm" onClick={onDownloadPDF}>
                  <Download className="size-4 mr-2" />
                  Download PDF
                </Button>
              )}
            </div>
          )}
          <div className="flex items-center gap-2 ml-auto">
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              Fechar
            </Button>
            {canResend && (
              <Button
                size="sm"
                onClick={handleReenviar}
                className="bg-primary text-primary-foreground hover:bg-primary/90"
              >
                Reenviar ASO completo novamente
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
