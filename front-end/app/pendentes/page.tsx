"use client"

import { useState, useEffect, Suspense, useCallback, useMemo } from "react"
import { useSearchParams } from "next/navigation"
import { useSession } from "next-auth/react"
import { AppSidebar } from "@/components/app-sidebar"
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import UserDropdown from "@/components/user-dropdown"
import { NotificationBell } from "@/components/notification-bell"
import { NotificationCenter } from "@/components/notification-center"
import { useNotifications } from "@/hooks/use-notifications"
import { useDocuments } from "@/hooks/use-documents"
import { documentToProcessResult } from "@/lib/document-mapper"
import { ProcessProgressBar } from "@/components/process-progress-bar"
import { ResultsTable } from "@/components/results-table"
import { DocumentDetailsModal } from "@/components/document-details-modal"
import { ProcessResult } from "@/types/process"
import { Clock, History, Loader2 } from "lucide-react"
import { RequireRole } from "@/components/require-role"
import { usePermissions } from "@/hooks/usePermissions"
import { downloadDocumentPdf } from "@/lib/document-download"

function PendentesContent() {
  const { data: session } = useSession()
  const searchParams = useSearchParams()
  const [selectedResult, setSelectedResult] = useState<ProcessResult | null>(null)
  const [detailsModalOpen, setDetailsModalOpen] = useState(false)
  const { unreadCount, activeProcess, setNotificationCenterOpen, processResults } = useNotifications()
  const { documents, loading, refreshing, hasLoaded, lastUpdatedAt } = useDocuments()
  const { user } = usePermissions()
  const isStrictSender = user?.role === "SENDER"
  const senderId = user?.id
  const senderEmail = user?.email
  const filteredDocuments = isStrictSender
    ? documents.filter((doc) => {
        if (senderId && doc.uploaded_by_user_id === senderId) return true
        if (senderEmail && doc.uploaded_by_user_email === senderEmail) return true
        return false
      })
    : documents
  const dbResults = filteredDocuments.map(documentToProcessResult)
  const baseResults = hasLoaded ? dbResults : (loading ? [] : processResults)
  const resultsToShow = isStrictSender && senderEmail
    ? baseResults.filter((result) => result.submittedBy === senderEmail)
    : baseResults
  const displayResults = useMemo(() => {
    const toTime = (value: unknown) => {
      if (!value) return 0
      if (value instanceof Date) return value.getTime()
      const parsed = new Date(String(value))
      return Number.isNaN(parsed.getTime()) ? 0 : parsed.getTime()
    }
    const getResultTimestamp = (result: ProcessResult) => {
      return Math.max(toTime(result.processedAt), toTime(result.uploadedAt))
    }
    return [...resultsToShow].sort(
      (a, b) => getResultTimestamp(b) - getResultTimestamp(a)
    )
  }, [resultsToShow])
  const pendingResults = displayResults.filter((result) => result.status !== "approved")
  const showRefreshing = refreshing && hasLoaded
  const totalPendentes = displayResults.filter((result) => result.status === "pending_review").length
  const totalAprovados = displayResults.filter((result) => result.status === "approved").length
  const totalRejeitados = displayResults.filter((result) => result.status === "rejected").length

  // Abre modal automaticamente se viewId for fornecido na URL
  useEffect(() => {
    const viewId = searchParams.get('viewId')
    if (viewId && resultsToShow.length > 0) {
      const result = resultsToShow.find(r => r.id === viewId)
      if (result) {
        setSelectedResult(result)
        setDetailsModalOpen(true)
      }
    }
  }, [searchParams, resultsToShow])

  const handleDownloadPDF = useCallback(async (result: ProcessResult) => {
    if (!result?.id) return
    try {
      await downloadDocumentPdf({
        id: result.id,
        filename: result.filename,
        accessToken: session?.accessToken,
      })
    } catch (error) {
      console.error("Falha ao baixar PDF:", error)
    }
  }, [session?.accessToken])

  return (
    <>
      <SidebarProvider>
        {activeProcess && (
          <ProcessProgressBar process={activeProcess} />
        )}
        <AppSidebar />
        <SidebarInset className="bg-sidebar group/sidebar-inset">
          <header className="flex h-16 shrink-0 items-center gap-2 px-4 md:px-6 lg:px-8 bg-sidebar text-sidebar-foreground relative before:absolute before:inset-y-3 before:-left-px before:w-px before:bg-gradient-to-b before:from-white/5 before:via-white/15 before:to-white/5 before:z-50">
            <SidebarTrigger className="-ms-2 text-sidebar-foreground hover:text-sidebar-foreground/70" />
            <div className="flex items-center gap-2">
              <History className="size-5" />
              <h1 className="text-lg font-semibold">Documentos Pendentes</h1>
            </div>
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
              {lastUpdatedAt && (
                <p className="text-xs text-muted-foreground/70 mb-2">
                  Última atualização: {lastUpdatedAt.toLocaleTimeString("pt-BR")}
                </p>
              )}
              <div className="grid grid-cols-3 gap-4 mb-4">
                <div className="bg-gradient-to-br from-yellow-50 to-yellow-100 border border-yellow-200 rounded-lg p-4 shadow-sm">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-xs font-medium text-yellow-700 uppercase tracking-wide">Pendentes</div>
                      <div className="text-3xl font-bold text-yellow-600 mt-1">
                        {totalPendentes}
                      </div>
                    </div>
                    <div className="size-12 rounded-full bg-yellow-200 flex items-center justify-center">
                      <Clock className="size-6 text-yellow-600" />
                    </div>
                  </div>
                </div>

                <div className="bg-gradient-to-br from-green-50 to-green-100 border border-green-200 rounded-lg p-4 shadow-sm">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-xs font-medium text-green-700 uppercase tracking-wide">Aprovados</div>
                      <div className="text-3xl font-bold text-green-600 mt-1">
                        {totalAprovados}
                      </div>
                    </div>
                    <div className="size-12 rounded-full bg-green-200 flex items-center justify-center">
                      <History className="size-6 text-green-600" />
                    </div>
                  </div>
                </div>

                <div className="bg-gradient-to-br from-red-50 to-red-100 border border-red-200 rounded-lg p-4 shadow-sm">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-xs font-medium text-red-700 uppercase tracking-wide">Rejeitados</div>
                      <div className="text-3xl font-bold text-red-600 mt-1">
                        {totalRejeitados}
                      </div>
                    </div>
                    <div className="size-12 rounded-full bg-red-200 flex items-center justify-center">
                      <svg className="size-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                    </div>
                  </div>
                </div>
              </div>

                {showRefreshing && (
                  <div className="mb-4 border rounded-lg bg-white p-3 flex items-center gap-2 text-muted-foreground">
                    <Loader2 className="size-4 animate-spin" />
                    <span>Atualizando documentos do banco...</span>
                    {lastUpdatedAt && (
                      <span className="text-xs text-muted-foreground/70">
                        Última atualização: {lastUpdatedAt.toLocaleTimeString("pt-BR")}
                      </span>
                    )}
                  </div>
                )}

              <div className="flex-1 min-h-0 bg-white rounded-lg p-6 shadow-sm overflow-hidden flex flex-col">
                {loading ? (
                  <div className="flex-1 flex items-center justify-center text-muted-foreground gap-3">
                    <Loader2 className="size-4 animate-spin" />
                    <span>Sincronizando documentos com o banco...</span>
                  </div>
                ) : (
                  <ResultsTable
                    results={pendingResults}
                    onViewDetails={(result) => {
                      console.log('[DEBUG] Opening modal for result:', result)
                      console.log('[DEBUG] Result exists?', !!result)
                      setSelectedResult(result)
                      setDetailsModalOpen(true)
                      console.log('[DEBUG] Modal state set to open')
                    }}
                    onDownloadPDF={(result) => {
                      handleDownloadPDF(result)
                    }}
                  />
                )}
              </div>
            </div>
          </div>
        </SidebarInset>

        <NotificationCenter />
        <DocumentDetailsModal
          open={detailsModalOpen}
          onOpenChange={setDetailsModalOpen}
          result={selectedResult}
          onDownloadPDF={selectedResult ? () => {
            handleDownloadPDF(selectedResult)
          } : undefined}
        />
      </SidebarProvider>
    </>
  )
}

export default function PendentesPage() {
  return (
    <RequireRole allowedRoles={["ADMIN", "SENDER"]}>
      <Suspense fallback={null}>
        <PendentesContent />
      </Suspense>
    </RequireRole>
  )
}
