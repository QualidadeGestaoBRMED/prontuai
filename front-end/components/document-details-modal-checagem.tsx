"use client"

import { format } from "date-fns"
import { ptBR } from "date-fns/locale"
import { CheckIcon, XIcon, Download } from "lucide-react"
import { useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { ProcessResult } from "@/types/process"
import ExamesComparativoTable from "@/components/exames-comparativo-table"

interface DocumentDetailsModalChecagemProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  result: ProcessResult | null
  onAprovar: (id: string, approvalReason: string) => void
  onRejeitar: (id: string, motivo: string) => void
  onDownloadPDF?: () => void
}

export function DocumentDetailsModalChecagem({
  open,
  onOpenChange,
  result,
  onAprovar,
  onRejeitar,
  onDownloadPDF,
}: DocumentDetailsModalChecagemProps) {
  const [motivo, setMotivo] = useState("")
  const [approvalReason, setApprovalReason] = useState("")
  const [showRejectDialog, setShowRejectDialog] = useState(false)
  const [showApproveDialog, setShowApproveDialog] = useState(false)

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

    // Fallback
    return <Badge variant="secondary">{status}</Badge>
  }

  const handleAprovar = () => {
    if (approvalReason.trim()) {
      onAprovar(result.id, approvalReason)
      setApprovalReason("")
      setShowApproveDialog(false)
      onOpenChange(false)
    }
  }

  const handleRejeitar = () => {
    if (motivo.trim()) {
      onRejeitar(result.id, motivo)
      setMotivo("")
      setShowRejectDialog(false)
      onOpenChange(false)
    }
  }

  const isPending = !result.reviewedBy

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-7xl max-h-[90vh] p-4">
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
                      {result.result.validation_result?.analysis}
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

              {/* Detailed Comparison Table */}
              <div>
                <h4 className="font-semibold mb-3">Comparação Detalhada</h4>

                {Array.isArray(result.result.tabela_comparacao) && result.result.tabela_comparacao.length > 0 && (
                  <div className="mb-6">
                    <ExamesComparativoTable tabela={result.result.tabela_comparacao} />
                  </div>
                )}
              </div>
            </div>
          </ScrollArea>

          {/* Footer Actions */}
          <div className="flex items-center justify-between pt-4 border-t">
            {onDownloadPDF && (
              <Button variant="outline" size="sm" onClick={onDownloadPDF}>
                <Download className="size-4 mr-2" />
                Download PDF
              </Button>
            )}
            <div className="flex gap-2 ml-auto">
              {isPending && (
                <>
                  <Button
                    variant="outline"
                    onClick={() => setShowRejectDialog(true)}
                    className="text-red-600 hover:text-red-700 hover:bg-red-50"
                  >
                    <XIcon className="size-4 mr-2" />
                    Rejeitar
                  </Button>
                  <Button
                    onClick={() => setShowApproveDialog(true)}
                    className="bg-green-600 hover:bg-green-700"
                  >
                    <CheckIcon className="size-4 mr-2" />
                    Aprovar
                  </Button>
                </>
              )}
              <Button variant="ghost" onClick={() => onOpenChange(false)}>
                Fechar
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Approve Confirmation Dialog */}
      <AlertDialog open={showApproveDialog} onOpenChange={setShowApproveDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Confirmar aprovação</AlertDialogTitle>
            <AlertDialogDescription className="text-foreground">
              Informe a justificativa para aprovar o documento do paciente{" "}
              <strong>{result.patientName}</strong> (CPF: {result.cpf}).
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-2 py-4">
            <Label htmlFor="approvalReason" className="text-foreground">Justificativa da aprovação</Label>
            <Textarea
              id="approvalReason"
              placeholder="Ex: Exames equivalentes foram aceitos, documentação complementar validada, etc."
              value={approvalReason}
              onChange={(e) => setApprovalReason(e.target.value)}
              rows={4}
            />
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setApprovalReason("")}>
              Cancelar
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleAprovar}
              disabled={!approvalReason.trim()}
              className="bg-green-600 hover:bg-green-700"
            >
              Aprovar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Reject Confirmation Dialog */}
      <AlertDialog open={showRejectDialog} onOpenChange={setShowRejectDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Rejeitar documento</AlertDialogTitle>
            <AlertDialogDescription className="text-foreground">
              Informe o motivo da rejeição do documento do paciente{" "}
              <strong>{result.patientName}</strong> (CPF: {result.cpf}).
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-2 py-4">
            <Label htmlFor="motivo" className="text-foreground">Motivo da rejeição</Label>
            <Textarea
              id="motivo"
              placeholder="Ex: Documento ilegível, exames faltantes, etc."
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
              rows={4}
            />
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setMotivo("")}>
              Cancelar
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleRejeitar}
              disabled={!motivo.trim()}
              className="bg-red-600 hover:bg-red-700"
            >
              Rejeitar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
