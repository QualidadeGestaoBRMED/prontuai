"use client"

import { useState, useEffect, Suspense } from "react"
import { useSearchParams } from "next/navigation"
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
import { History, Loader2 } from "lucide-react"
import { RequireRole } from "@/components/require-role"
import { usePermissions } from "@/hooks/usePermissions"

function PendentesContent() {
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
  const showRefreshing = refreshing && hasLoaded

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

          <div className="flex-1 overflow-auto bg-[hsl(240_5%_92.16%)] md:rounded-s-3xl md:group-peer-data-[state=collapsed]/sidebar-inset:rounded-s-none transition-all ease-in-out duration-300">
            <div className="p-6 md:p-8 lg:p-12">
              <div className="space-y-4">
                <div>
                  <p className="text-sm text-muted-foreground">
                    Visualize e gerencie todos os documentos processados
                  </p>
                  {lastUpdatedAt && (
                    <p className="text-xs text-muted-foreground/70 mt-1">
                      Última atualização: {lastUpdatedAt.toLocaleTimeString("pt-BR")}
                    </p>
                  )}
                </div>

                {showRefreshing && (
                  <div className="border rounded-lg bg-white p-3 flex items-center gap-2 text-muted-foreground">
                    <Loader2 className="size-4 animate-spin" />
                    <span>Atualizando documentos do banco...</span>
                    {lastUpdatedAt && (
                      <span className="text-xs text-muted-foreground/70">
                        Última atualização: {lastUpdatedAt.toLocaleTimeString("pt-BR")}
                      </span>
                    )}
                  </div>
                )}

                {loading ? (
                  <div className="border rounded-lg bg-white p-6 flex items-center gap-3 text-muted-foreground">
                    <Loader2 className="size-4 animate-spin" />
                    <span>Sincronizando documentos com o banco...</span>
                  </div>
                ) : (
                  <ResultsTable
                    results={resultsToShow.filter(result => result.status !== 'approved')}
                    onViewDetails={(result) => {
                      console.log('[DEBUG] Opening modal for result:', result)
                      console.log('[DEBUG] Result exists?', !!result)
                      setSelectedResult(result)
                      setDetailsModalOpen(true)
                      console.log('[DEBUG] Modal state set to open')
                    }}
                    onDownloadPDF={(result) => {
                      // TODO: Implementar download de PDF
                      console.log("Download PDF:", result)
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
            // TODO: Implementar download de PDF
            console.log("Download PDF:", selectedResult)
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
