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
import { ProcessResult } from "@/types/process"
import { Download } from "lucide-react"

interface DocumentDetailsModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  result: ProcessResult | null
  onDownloadPDF?: () => void
  onDownloadJSON?: () => void
}

export function DocumentDetailsModal({
  open,
  onOpenChange,
  result,
  onDownloadPDF,
  onDownloadJSON,
}: DocumentDetailsModalProps) {
  if (!result) return null

  const getStatusBadge = (status: ProcessResult["status"]) => {
    switch (status) {
      case "approved":
        return (
          <Badge variant="default" className="bg-green-500 hover:bg-green-600">
            ✓ Aprovado
          </Badge>
        )
      case "rejected":
        return <Badge variant="destructive">✗ Rejeitado</Badge>
      case "pending_review":
        return (
          <Badge
            variant="secondary"
            className="bg-amber-100 text-amber-700 hover:bg-amber-200"
          >
            ⚠ Pendente de Revisão
          </Badge>
        )
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh]">
        <DialogHeader>
          <div className="flex items-start justify-between">
            <div className="space-y-1">
              <DialogTitle className="text-2xl">
                Detalhes do Documento
              </DialogTitle>
              <DialogDescription>{result.filename}</DialogDescription>
            </div>
            {getStatusBadge(result.status)}
          </div>
        </DialogHeader>

        <ScrollArea className="max-h-[calc(90vh-12rem)] pr-4">
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
                  {result.result.ocr_result?.exames_extraidos.length || 0}
                </p>
                <p className="text-sm text-muted-foreground">
                  Exames no Documento
                </p>
              </div>
              <div className="text-center p-4 border rounded-lg bg-muted/30">
                <p className="text-2xl font-bold">
                  {result.result.brmed_result?.exames_obrigatorios.length || 0}
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

            <Separator />

            {/* Detailed Comparison Table */}
            <div>
              <h4 className="font-semibold mb-3">Comparação Detalhada</h4>

              {/* Exames Extraídos (OCR) */}
              <div className="mb-4">
                <h5 className="text-sm font-medium text-muted-foreground mb-2">
                  Exames Encontrados no Documento ({result.result.ocr_result?.exames_extraidos.length || 0})
                </h5>
                <div className="space-y-2">
                  {(!result.result.ocr_result?.exames_extraidos || result.result.ocr_result.exames_extraidos.length === 0) ? (
                    <p className="text-sm text-muted-foreground italic">
                      Nenhum exame extraído
                    </p>
                  ) : (
                    <div className="grid grid-cols-2 gap-2">
                      {result.result.ocr_result.exames_extraidos.map(
                        (exame, i) => (
                          <div
                            key={i}
                            className="text-sm p-2 rounded border bg-blue-50 border-blue-200"
                          >
                            {exame}
                          </div>
                        )
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* Exames Obrigatórios (BRMED) */}
              <div className="mb-4">
                <h5 className="text-sm font-medium text-muted-foreground mb-2">
                  Exames Obrigatórios (BRMED) ({result.result.brmed_result?.exames_obrigatorios.length || 0})
                </h5>
                <div className="space-y-2">
                  {(!result.result.brmed_result?.exames_obrigatorios || result.result.brmed_result.exames_obrigatorios.length === 0) ? (
                    <p className="text-sm text-muted-foreground italic">
                      Nenhum exame obrigatório
                    </p>
                  ) : (
                    <div className="grid grid-cols-2 gap-2">
                      {result.result.brmed_result.exames_obrigatorios.map(
                        (exame, i) => (
                          <div
                            key={i}
                            className="text-sm p-2 rounded border bg-purple-50 border-purple-200"
                          >
                            {exame}
                          </div>
                        )
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* Exames Faltantes */}
              {(result.result.validation_result?.exames_faltantes?.length || 0) > 0 && (
                <div className="mb-4">
                  <h5 className="text-sm font-medium text-red-600 mb-2">
                    Exames Faltantes ({result.result.validation_result?.exames_faltantes?.length || 0})
                  </h5>
                  <div className="space-y-2">
                    <div className="grid grid-cols-2 gap-2">
                      {result.result.validation_result?.exames_faltantes?.map(
                        (exame, i) => (
                          <div
                            key={i}
                            className="text-sm p-2 rounded border bg-red-50 border-red-200 text-red-900"
                          >
                            {exame}
                          </div>
                        )
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* Exames Extras */}
              {(result.result.validation_result?.exames_extras?.length || 0) > 0 && (
                <div>
                  <h5 className="text-sm font-medium text-blue-600 mb-2">
                    Exames Extras no Documento ({result.result.validation_result?.exames_extras?.length || 0})
                  </h5>
                  <div className="space-y-2">
                    <div className="grid grid-cols-2 gap-2">
                      {result.result.validation_result?.exames_extras?.map(
                        (exame, i) => (
                          <div
                            key={i}
                            className="text-sm p-2 rounded border bg-blue-50 border-blue-200 text-blue-900"
                          >
                            {exame}
                          </div>
                        )
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </ScrollArea>

        {/* Footer Actions */}
        <div className="flex items-center justify-between pt-4 border-t">
          <div className="flex gap-2">
            {onDownloadPDF && (
              <Button variant="outline" size="sm" onClick={onDownloadPDF}>
                <Download className="size-4 mr-2" />
                Download PDF
              </Button>
            )}
            {onDownloadJSON && (
              <Button variant="outline" size="sm" onClick={onDownloadJSON}>
                <Download className="size-4 mr-2" />
                Download JSON
              </Button>
            )}
          </div>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Fechar
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
