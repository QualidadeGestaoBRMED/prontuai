"use client"

import { useState, useEffect, Suspense, useMemo, useCallback } from "react"
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
import { useClinicOptions } from "@/hooks/use-clinic-options"
import { documentToProcessResult } from "@/lib/document-mapper"
import { ProcessProgressBar } from "@/components/process-progress-bar"
import { ResultsTable } from "@/components/results-table"
import { DocumentDetailsModal } from "@/components/document-details-modal"
import { ProcessResult } from "@/types/process"
import { History, Loader2 } from "lucide-react"
import { downloadDocumentPdf } from "@/lib/document-download"

function HistoricoContent() {
  const searchParams = useSearchParams()
  const [selectedResult, setSelectedResult] = useState<ProcessResult | null>(null)
  const [detailsModalOpen, setDetailsModalOpen] = useState(false)
  const { unreadCount, activeProcess, setNotificationCenterOpen, processResults } = useNotifications()
  const { documents, loading, refreshing, hasLoaded, lastUpdatedAt } = useDocuments()
  const {
    options: clinicOptions,
    loading: clinicOptionsLoading,
    enabled: canFilterByClinic,
  } = useClinicOptions()
  const dbResults = documents.map(documentToProcessResult)
  const sortedResults = useMemo(() => {
    const baseResults = hasLoaded ? dbResults : (loading ? [] : processResults)
    const list = [...baseResults]
    const toTime = (value: unknown) => {
      if (!value) return 0
      if (value instanceof Date) return value.getTime()
      const parsed = new Date(String(value))
      return Number.isNaN(parsed.getTime()) ? 0 : parsed.getTime()
    }
    list.sort((a, b) => toTime(b.uploadedAt) - toTime(a.uploadedAt))
    return list
  }, [hasLoaded, dbResults, loading, processResults])
  const showRefreshing = refreshing && hasLoaded

  // Auto-abre modal se viewId for fornecido na URL
  useEffect(() => {
    const viewId = searchParams.get('viewId')
    if (viewId && sortedResults.length > 0) {
      const result = sortedResults.find(r => r.id === viewId)
      if (result) {
        setSelectedResult(result)
        setDetailsModalOpen(true)
      }
    }
  }, [searchParams, sortedResults])

  const handleDownloadPDF = useCallback(async (result: ProcessResult) => {
    if (!result?.id) return
    try {
      await downloadDocumentPdf({
        id: result.id,
        filename: result.filename,
      })
    } catch (error) {
      console.error("Falha ao baixar PDF:", error)
    }
  }, [])

  return (
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
            <h1 className="text-lg font-semibold">Histórico de Processamentos</h1>
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

              {loading && !hasLoaded ? (
                <div className="border rounded-lg bg-white p-6 flex items-center gap-3 text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" />
                  <span>Sincronizando documentos com o banco...</span>
                </div>
                ) : (
                  <ResultsTable
                    results={sortedResults}
                    clinicOptions={clinicOptions}
                    clinicOptionsLoading={clinicOptionsLoading}
                    showClinicFilter={canFilterByClinic}
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
  )
}

export default function HistoricoPage() {
  return (
    <Suspense fallback={<div>Carregando...</div>}>
      <HistoricoContent />
    </Suspense>
  )
}
