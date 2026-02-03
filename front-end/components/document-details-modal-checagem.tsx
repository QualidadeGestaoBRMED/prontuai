"use client"

import { format } from "date-fns"
import { ptBR } from "date-fns/locale"
import { CheckIcon, XIcon, Download, Loader2 } from "lucide-react"
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
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { ProcessResult } from "@/types/process"
import ExamesComparativoTable from "@/components/exames-comparativo-table"
import { cn } from "@/lib/utils"

interface DocumentDetailsModalChecagemProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  result: ProcessResult | null
  onAprovar: (id: string, approvalReason: string) => void
  onRejeitar: (id: string, motivo: string) => void
  onViewDocument?: () => void
  documentUrl?: string | null
  documentLoading?: boolean
}

export function DocumentDetailsModalChecagem({
  open,
  onOpenChange,
  result,
  onAprovar,
  onRejeitar,
  onViewDocument,
  documentUrl,
  documentLoading,
}: DocumentDetailsModalChecagemProps) {
  const [motivo, setMotivo] = useState("")
  const [showRejectDialog, setShowRejectDialog] = useState(false)
  const [showApproveDialog, setShowApproveDialog] = useState(false)

  if (!result) return null
  const showPreview = Boolean(documentUrl || documentLoading)
  const previewSrc = documentUrl
    ? (documentUrl.includes("#")
        ? `${documentUrl}&toolbar=0&navpanes=0&scrollbar=0`
        : `${documentUrl}#toolbar=0&navpanes=0&scrollbar=0`)
    : ""
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
          Rejeitado pelo Revisor
        </Badge>
      )
    }

    // Fallback
    return <Badge variant="secondary">{status}</Badge>
  }

  const handleAprovar = () => {
    onAprovar(result.id, "")
    setShowApproveDialog(false)
    onOpenChange(false)
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
        <DialogContent
          className={cn(
            "p-4",
            showPreview
              ? "!w-[96vw] !h-[94svh] !max-w-[96vw] !max-h-[94svh] rounded-2xl"
              : "max-h-[90vh] max-w-4xl"
          )}
        >
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

          {showPreview ? (
            <div className="flex flex-col gap-4 lg:grid lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
              <ScrollArea className="h-[70vh] pr-2">
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

              <div className="flex flex-col gap-3">
                <div className="flex items-center justify-between">
                  <h4 className="font-semibold">Documento</h4>
                  {documentUrl && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => window.open(documentUrl, "_blank", "noopener,noreferrer")}
                    >
                      Abrir em nova aba
                    </Button>
                  )}
                </div>
                <div className="h-[70vh] rounded-lg border bg-muted/20 overflow-hidden">
                  {documentUrl ? (
                    <iframe
                      title={`Documento ${result.filename}`}
                      src={previewSrc}
                      className="h-full w-full"
                    />
                  ) : (
                    <div className="h-full flex items-center justify-center text-sm text-muted-foreground px-6 text-center">
                      <div className="flex items-center gap-2">
                        <Loader2 className="size-4 animate-spin" />
                        Carregando documento...
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : (
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
          )}

          {/* Footer Actions */}
          <div className="flex items-center justify-between pt-4 border-t">
            {onViewDocument && (
              <div className="flex gap-2">
                {onViewDocument && (
                  <Button variant="outline" size="sm" onClick={onViewDocument} disabled={documentLoading}>
                    {documentLoading ? (
                      <Loader2 className="size-4 mr-2 animate-spin" />
                    ) : (
                      <Download className="size-4 mr-2" />
                    )}
                    {documentUrl ? "Recarregar documento" : "Visualizar documento"}
                  </Button>
                )}
              </div>
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
              Confirme a aprovação do documento do paciente{" "}
              <strong>{result.patientName}</strong> (CPF: {result.cpf}).
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleAprovar}
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
