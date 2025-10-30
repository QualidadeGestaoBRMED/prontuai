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
import { ProcessProgressBar } from "@/components/process-progress-bar"
import { ResultsTable } from "@/components/results-table"
import { DocumentDetailsModal } from "@/components/document-details-modal"
import { ProcessResult } from "@/types/process"
import { History } from "lucide-react"

function HistoricoContent() {
  const searchParams = useSearchParams()
  const [selectedResult, setSelectedResult] = useState<ProcessResult | null>(null)
  const [detailsModalOpen, setDetailsModalOpen] = useState(false)
  const { unreadCount, activeProcess, setNotificationCenterOpen, processResults } = useNotifications()

  // Auto-open modal if viewId is provided in URL
  useEffect(() => {
    const viewId = searchParams.get('viewId')
    if (viewId && processResults.length > 0) {
      const result = processResults.find(r => r.id === viewId)
      if (result) {
        setSelectedResult(result)
        setDetailsModalOpen(true)
      }
    }
  }, [searchParams, processResults])

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

              <ResultsTable
                results={processResults}
                onViewDetails={(result) => {
                  console.log('[DEBUG] Opening modal for result:', result)
                  console.log('[DEBUG] Result exists?', !!result)
                  setSelectedResult(result)
                  setDetailsModalOpen(true)
                  console.log('[DEBUG] Modal state set to open')
                }}
                onDownloadPDF={(result) => {
                  // TODO: Implement PDF download
                  console.log("Download PDF:", result)
                }}
                onDownloadJSON={(result) => {
                  const dataStr = JSON.stringify(result, null, 2)
                  const dataBlob = new Blob([dataStr], { type: "application/json" })
                  const url = URL.createObjectURL(dataBlob)
                  const link = document.createElement("a")
                  link.href = url
                  link.download = `resultado-${result.cpf}-${Date.now()}.json`
                  document.body.appendChild(link)
                  link.click()
                  document.body.removeChild(link)
                  URL.revokeObjectURL(url)
                }}
              />
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
          // TODO: Implement PDF download
          console.log("Download PDF:", selectedResult)
        } : undefined}
        onDownloadJSON={selectedResult ? () => {
          const dataStr = JSON.stringify(selectedResult, null, 2)
          const dataBlob = new Blob([dataStr], { type: "application/json" })
          const url = URL.createObjectURL(dataBlob)
          const link = document.createElement("a")
          link.href = url
          link.download = `resultado-${selectedResult.cpf}-${Date.now()}.json`
          document.body.appendChild(link)
          link.click()
          document.body.removeChild(link)
          URL.revokeObjectURL(url)
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
