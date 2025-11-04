"use client"

import { format } from "date-fns"
import { ptBR } from "date-fns/locale"
import { CheckIcon, XIcon } from "lucide-react"
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
import type { DocumentoChecagem } from "@/types/checagem"

interface DocumentDetailsModalChecagemProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  documento: DocumentoChecagem | null
  onAprovar: (id: string) => void
  onRejeitar: (id: string, motivo: string) => void
}

export function DocumentDetailsModalChecagem({
  open,
  onOpenChange,
  documento,
  onAprovar,
  onRejeitar,
}: DocumentDetailsModalChecagemProps) {
  const [motivo, setMotivo] = useState("")
  const [showRejectDialog, setShowRejectDialog] = useState(false)
  const [showApproveDialog, setShowApproveDialog] = useState(false)

  if (!documento) return null

  const getStatusBadge = (doc: DocumentoChecagem) => {
    const decisaoIA = doc.decisaoIA

    // Show badge indicating AI decision
    if (decisaoIA === 'approved') {
      return (
        <Badge variant="outline" className="bg-green-100 text-green-700 border-green-300">
          Aprovado pela IA
        </Badge>
      )
    } else if (decisaoIA === 'rejected') {
      return (
        <Badge variant="outline" className="bg-orange-100 text-orange-700 border-orange-300">
          Rejeitado pela IA
        </Badge>
      )
    }

    // Fallback for already reviewed documents
    const styles = {
      pendente: "bg-yellow-400/20 text-yellow-700 border-yellow-400/50",
      aprovado: "bg-green-400/20 text-green-700 border-green-400/50",
      rejeitado: "bg-red-400/20 text-red-700 border-red-400/50",
    }[doc.status]

    return (
      <Badge variant="outline" className={`capitalize ${styles}`}>
        {doc.status}
      </Badge>
    )
  }

  const handleAprovar = () => {
    onAprovar(documento.id)
    setShowApproveDialog(false)
    onOpenChange(false)
  }

  const handleRejeitar = () => {
    if (motivo.trim()) {
      onRejeitar(documento.id, motivo)
      setMotivo("")
      setShowRejectDialog(false)
      onOpenChange(false)
    }
  }

  const isPending = documento.status === "pendente"

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-7xl max-h-[90vh] p-4">
          <DialogHeader>
            <div className="flex items-start justify-between">
              <div className="space-y-1">
                <DialogTitle className="text-2xl">
                  Detalhes do Documento
                </DialogTitle>
                <DialogDescription>CPF: {documento.cpf}</DialogDescription>
              </div>
              {getStatusBadge(documento)}
            </div>
          </DialogHeader>

          <ScrollArea className="max-h-[calc(90vh-12rem)] pr-2">
            <div className="space-y-6">
              {/* Basic Information */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">CPF</p>
                  <p className="font-medium font-mono">{documento.cpf}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Paciente</p>
                  <p className="font-medium">{documento.paciente}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Data de Upload</p>
                  <p className="text-sm">
                    {format(new Date(documento.dataUpload), "dd/MM/yyyy 'às' HH:mm", {
                      locale: ptBR,
                    })}
                  </p>
                </div>
                {documento.dataProcessamento && (
                  <div>
                    <p className="text-sm text-muted-foreground">
                      Data de Processamento
                    </p>
                    <p className="text-sm">
                      {format(new Date(documento.dataProcessamento), "dd/MM/yyyy 'às' HH:mm", {
                        locale: ptBR,
                      })}
                    </p>
                  </div>
                )}
              </div>

              <Separator />

              {/* Summary Counters */}
              <div className="grid grid-cols-2 gap-4">
                <div className="text-center p-4 border rounded-lg bg-muted/30">
                  <p className="text-2xl font-bold text-red-600">
                    {documento.examesFaltantes}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    Exames Faltantes
                  </p>
                </div>
                <div className="text-center p-4 border rounded-lg bg-muted/30">
                  <p className="text-2xl font-bold text-blue-600">
                    {documento.examesExtras}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    Exames Extras
                  </p>
                </div>
              </div>

              {/* Rejection Reason (if exists) */}
              {documento.motivoRejeicao && (
                <div className="p-4 border border-red-200 rounded-lg bg-red-50">
                  <h4 className="font-semibold text-red-900 mb-2">
                    Motivo da Rejeição
                  </h4>
                  <p className="text-sm text-red-700">{documento.motivoRejeicao}</p>
                </div>
              )}

              {/* AI Decision Information */}
              {documento.decisaoIA && (
                <>
                  <Separator />
                  <div className="p-4 border rounded-lg bg-muted/30">
                    <h4 className="font-semibold mb-2">Decisão da Inteligência Artificial</h4>
                    <p className="text-sm text-muted-foreground">
                      {documento.decisaoIA === 'approved'
                        ? 'Este documento foi aprovado pela IA. Por favor, revise os detalhes e confirme a aprovação ou rejeite se encontrar inconsistências.'
                        : 'Este documento foi rejeitado pela IA devido a exames faltantes. Por favor, revise os detalhes e tome a decisão final.'}
                    </p>
                  </div>
                </>
              )}
            </div>
          </ScrollArea>

          {/* Footer Actions */}
          <div className="flex items-center justify-between pt-4 border-t">
            <div className="text-sm text-muted-foreground">
              {isPending ? 'Aguardando sua revisão' : 'Documento já foi revisado'}
            </div>
            <div className="flex gap-2">
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
              Tem certeza que deseja aprovar o documento do paciente{" "}
              <strong>{documento.paciente}</strong> (CPF: {documento.cpf})?
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
              <strong>{documento.paciente}</strong> (CPF: {documento.cpf}).
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
