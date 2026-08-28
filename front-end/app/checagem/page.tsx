"use client"

import { useEffect, useMemo, useState } from "react"
import { AppSidebar } from "@/components/app-sidebar"
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar"
import UserDropdown from "@/components/user-dropdown"
import { CheckagemTable } from "@/components/checagem-table"
import type { DocumentoChecagem } from "@/types/checagem"
import { toast } from "sonner"
import { useNotifications } from "@/hooks/use-notifications"
import { NotificationBell } from "@/components/notification-bell"
import { NotificationCenter } from "@/components/notification-center"
import { useSession } from "next-auth/react"
import { ProcessResult } from "@/types/process"
import { DocumentDetailsModalChecagem } from "@/components/document-details-modal-checagem"
import { RequireRole } from "@/components/require-role"
import { useDocumentsPaged } from "@/hooks/use-documents-paged"
import { useReviewTimer } from "@/hooks/use-review-timer"
import { useClinicOptions } from "@/hooks/use-clinic-options"
import { documentToProcessResult } from "@/lib/document-mapper"
import { API_ENDPOINTS } from "@/lib/config"
import { Loader2 } from "lucide-react"
import { authFetch } from "@/lib/auth-fetch"

export default function Page() {
  const [documentos, setDocumentos] = useState<DocumentoChecagem[]>([])
  const [selectedResult, setSelectedResult] = useState<ProcessResult | null>(null)
  const [documentPreviewUrl, setDocumentPreviewUrl] = useState<string | null>(null)
  const [documentPreviewLoading, setDocumentPreviewLoading] = useState(false)
  const { updateProcessResultStatus, addNotification, unreadCount, activeProcess, setNotificationCenterOpen } =
    useNotifications()
  const {
    documents,
    loading,
    error,
    page,
    setPage,
    totalPages,
    search,
    setSearch,
    statusFilter,
    setStatusFilter,
    clinicFilter,
    setClinicFilter,
    summaryCounts,
    refresh,
  } = useDocumentsPaged({
    queue: "checagem",
    pageSize: 10,
    refreshIntervalMs: 0,
  })
  const sessionData = useSession()
  const session = sessionData?.data || null
  // Cronometragem da revisão: sobe junto do PATCH da decisão, sem UI e sem
  // requisição extra. Ver docs/tempo-de-revisao-desenho.md.
  const reviewTimer = useReviewTimer()
  const {
    options: clinicOptions,
    loading: clinicOptionsLoading,
    error: clinicOptionsError,
    enabled: canFilterByClinic,
  } = useClinicOptions()

  useEffect(() => {
    if (!canFilterByClinic) setClinicFilter("all")
  }, [canFilterByClinic, setClinicFilter])

  useEffect(() => {
    if (clinicOptionsError) toast.error("Não foi possível carregar o filtro de clínicas.")
  }, [clinicOptionsError])

  // Spinner só no primeiro carregamento: desmontar a tabela em refetches de busca
  // perderia o texto digitado nos filtros (que vivem no estado interno da tabela).
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false)
  useEffect(() => {
    if (!loading) setHasLoadedOnce(true)
  }, [loading])
  const dbResults = useMemo(() => documents.map(documentToProcessResult), [documents])

  useEffect(() => {
    const pendingDocs: DocumentoChecagem[] = dbResults.map((result) => ({
      id: result.id,
      clinicName: result.clinicName,
      cpf: result.cpf,
      paciente: result.patientName,
      dataUpload: new Date(result.uploadedAt).toISOString(),
      dataPrevisaoLiberacao: result.result.brmed_result?.data_previsao_liberacao || undefined,
      status:
        result.status === "pending_review"
          ? ("pendente" as const)
          : result.status === "rejected"
            ? ("rejeitado" as const)
            : ("aprovado" as const),
      dataProcessamento: result.reviewedAt ? new Date(result.reviewedAt).toISOString() : undefined,
      motivoRejeicao: result.rejectionReason,
      examesFaltantes: result.examesFaltantes,
      examesExtras: result.examesExtras,
      decisaoIA:
        result.reviewedBy
          ? undefined
          : (result.status as "approved" | "rejected" | "pending_review") === "pending_review"
            ? "rejected"
            : (result.status as "approved" | "rejected"),
      submittedBy: result.submittedBy,
    }))

    setDocumentos(pendingDocs)
  }, [dbResults])

  const handleViewDocument = async (result: ProcessResult) => {
    if (documentPreviewLoading) return
    setDocumentPreviewLoading(true)
    try {
      const response = await authFetch(API_ENDPOINTS.DOCUMENT_VIEW(result.id))
      if (!response.ok) {
        toast.error("Não foi possível abrir o documento.")
        setDocumentPreviewLoading(false)
        return
      }
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      setDocumentPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev)
        return url
      })
    } catch (error) {
      console.error("[CHECAGEM] Falha ao carregar o documento", error)
      toast.error("Falha ao carregar o documento.")
    } finally {
      setDocumentPreviewLoading(false)
    }
  }

  const handleAprovar = async (id: string, approvalReason: string) => {
    const reviewTiming = reviewTimer.encerrar(id)
    const result = dbResults.find((r) => r.id === id)
    const approvalReasonValue = approvalReason?.trim() || ""
    const approvalReasonNormalized = approvalReasonValue.length ? approvalReasonValue : undefined

    updateProcessResultStatus(id, "approved", session?.user?.email || "revisor@grupobrmed.com.br", undefined, approvalReasonNormalized)

    const headers: Record<string, string> = { "Content-Type": "application/json" }

    try {
      const response = await authFetch(`${API_ENDPOINTS.DOCUMENTS}/${id}`, {
        method: "PATCH",
        headers,
        body: JSON.stringify({
          validation_status: "validated",
          approval_reason: approvalReasonNormalized,
          ...(reviewTiming ? { review_timing: reviewTiming } : {}),
          result_payload: {
            ...(result?.result || {}),
            reviewed_by: session?.user?.email || "revisor@grupobrmed.com.br",
            reviewed_at: new Date().toISOString(),
            approvalReason: approvalReasonNormalized,
          },
        }),
      })
      const text = await response.text().catch(() => "")
      console.info("[CHECAGEM] Resposta aprovação", { status: response.status, ok: response.ok, body: text })
      await refresh(true)
    } catch (error) {
      console.error("[CHECAGEM] Falha ao aprovar documento", error)
    }

    if (result) {
      const reviewerName = session?.user?.name || "um revisor"
      const mensagemJustificativa = approvalReasonNormalized ? ` Justificativa: ${approvalReasonNormalized}` : ""
      addNotification({
        type: "review_approved",
        title: "Documento Aprovado",
        message: `Seu documento do paciente ${result.patientName} foi aprovado por ${reviewerName}.${mensagemJustificativa}`,
        read: false,
        metadata: {
          documentId: id,
          cpf: result.cpf,
          reviewerEmail: session?.user?.email || "revisor@grupobrmed.com.br",
          approvalReason: approvalReasonNormalized,
        },
        variant: "success",
      })
    }

    toast.success("Documento aprovado")
  }

  const handleRejeitar = async (id: string, motivo: string) => {
    const reviewTiming = reviewTimer.encerrar(id)
    const result = dbResults.find((r) => r.id === id)
    updateProcessResultStatus(id, "rejected", session?.user?.email || "revisor@grupobrmed.com.br", motivo)

    const headers: Record<string, string> = { "Content-Type": "application/json" }

    try {
      const response = await authFetch(`${API_ENDPOINTS.DOCUMENTS}/${id}`, {
        method: "PATCH",
        headers,
        body: JSON.stringify({
          validation_status: "rejected",
          ...(reviewTiming ? { review_timing: reviewTiming } : {}),
          result_payload: {
            ...(result?.result || {}),
            reviewed_by: session?.user?.email || "revisor@grupobrmed.com.br",
            reviewed_at: new Date().toISOString(),
            rejectionReason: motivo,
          },
        }),
      })
      const text = await response.text().catch(() => "")
      console.info("[CHECAGEM] Resposta rejeição", { status: response.status, ok: response.ok, body: text })
      await refresh(true)
    } catch (error) {
      console.error("[CHECAGEM] Falha ao rejeitar documento", error)
    }

    if (result) {
      addNotification({
        type: "review_rejected",
        title: "Documento Rejeitado",
        message: `Seu documento do paciente ${result.patientName} foi rejeitado: ${motivo}`,
        read: false,
        metadata: {
          documentId: id,
          cpf: result.cpf,
          reviewerEmail: session?.user?.email || "revisor@grupobrmed.com.br",
        },
        variant: "error",
      })
    }

    toast.error("Documento rejeitado")
  }

  const handleViewDetails = (id: string) => {
    const result = dbResults.find((r) => r.id === id)
    if (result) {
      setDocumentPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev)
        return null
      })
      setSelectedResult(result)
      reviewTimer.abrir(id)
    }
  }

  return (
    <RequireRole allowedRoles={["ADMIN", "MANAGER", "CHECKER"]}>
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset className="bg-sidebar group/sidebar-inset">
          <header className="flex h-16 shrink-0 items-center gap-2 px-4 md:px-6 lg:px-8 bg-sidebar text-sidebar-foreground relative before:absolute before:inset-y-3 before:-left-px before:w-px before:bg-gradient-to-b before:from-white/5 before:via-white/15 before:to-white/5 before:z-50">
            <SidebarTrigger className="-ms-2 text-sidebar-foreground hover:text-sidebar-foreground/70" />
            <h1 className="text-lg font-semibold">Checagem de Documentos</h1>
            <div className="flex items-center gap-2 ml-auto">
              <NotificationBell
                unreadCount={unreadCount}
                hasActiveProcess={!!activeProcess}
                onClick={() => setNotificationCenterOpen(true)}
              />
              <UserDropdown />
            </div>
          </header>

          <div className="flex flex-col h-[calc(100svh-4rem)] bg-[hsl(240_5%_92.16%)] md:rounded-s-3xl md:group-peer-data-[state=collapsed]/sidebar-inset:rounded-s-none transition-all ease-in-out duration-300">
            <div className="flex-1 min-h-0 flex flex-col p-4 md:p-6 lg:p-8 overflow-hidden">
              <div className="grid grid-cols-3 gap-4 mb-4">
                <div className="bg-gradient-to-br from-yellow-50 to-yellow-100 border border-yellow-200 rounded-lg p-4 shadow-sm">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-xs font-medium text-yellow-700 uppercase tracking-wide">Pendentes</div>
                      <div className="text-3xl font-bold text-yellow-600 mt-1">{summaryCounts.pending_review}</div>
                    </div>
                    <div className="size-12 rounded-full bg-yellow-200 flex items-center justify-center">
                      <svg className="size-6 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                    </div>
                  </div>
                </div>

                <div className="bg-gradient-to-br from-green-50 to-green-100 border border-green-200 rounded-lg p-4 shadow-sm">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-xs font-medium text-green-700 uppercase tracking-wide">Aprovados</div>
                      <div className="text-3xl font-bold text-green-600 mt-1">{summaryCounts.approved}</div>
                    </div>
                    <div className="size-12 rounded-full bg-green-200 flex items-center justify-center">
                      <svg className="size-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                    </div>
                  </div>
                </div>

                <div className="bg-gradient-to-br from-red-50 to-red-100 border border-red-200 rounded-lg p-4 shadow-sm">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-xs font-medium text-red-700 uppercase tracking-wide">Rejeitados</div>
                      <div className="text-3xl font-bold text-red-600 mt-1">{summaryCounts.rejected}</div>
                    </div>
                    <div className="size-12 rounded-full bg-red-200 flex items-center justify-center">
                      <svg className="size-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                    </div>
                  </div>
                </div>
              </div>

              {!!error && (
                <div className="mb-4 border rounded-lg bg-red-50 border-red-200 p-3 text-red-700 text-sm">
                  Falha ao carregar documentos da checagem: {error}
                </div>
              )}

              <div className="flex-1 min-h-0 bg-white rounded-lg p-6 shadow-sm overflow-hidden flex flex-col">
                {loading && !hasLoadedOnce ? (
                  <div className="flex-1 flex items-center justify-center text-muted-foreground gap-3">
                    <Loader2 className="size-4 animate-spin" />
                    <span>Sincronizando documentos com o banco...</span>
                  </div>
                ) : (
                  <CheckagemTable
                    documentos={documentos}
                    onAprovar={handleAprovar}
                    onRejeitar={handleRejeitar}
                    onViewDetails={handleViewDetails}
                    serverPagination={{
                      page,
                      totalPages,
                      onPageChange: setPage,
                    }}
                    serverSearch={{
                      value: search,
                      onChange: setSearch,
                    }}
                    serverStatus={{
                      value: statusFilter,
                      onChange: setStatusFilter,
                    }}
                    serverClinic={
                      canFilterByClinic
                        ? {
                            value: clinicFilter,
                            onChange: setClinicFilter,
                            options: clinicOptions,
                            loading: clinicOptionsLoading,
                          }
                        : undefined
                    }
                  />
                )}
              </div>
            </div>
          </div>
        </SidebarInset>
        <NotificationCenter />
        <DocumentDetailsModalChecagem
          open={!!selectedResult}
          onOpenChange={(open) => {
            if (!open) {
              // Depois de uma decisão o encerrar() já levou o acumulador; aqui
              // só importa o caso de fechar a tela sem decidir.
              if (selectedResult) reviewTimer.fechar(selectedResult.id)
              setSelectedResult(null)
              setDocumentPreviewUrl((prev) => {
                if (prev) URL.revokeObjectURL(prev)
                return null
              })
            }
          }}
          result={selectedResult}
          onAprovar={handleAprovar}
          onRejeitar={handleRejeitar}
          onViewDocument={selectedResult ? () => handleViewDocument(selectedResult) : undefined}
          onAbrirPdfExterno={
            selectedResult ? () => reviewTimer.registrarPdfExterno(selectedResult.id) : undefined
          }
          documentUrl={documentPreviewUrl}
          documentLoading={documentPreviewLoading}
        />
      </SidebarProvider>
    </RequireRole>
  )
}
