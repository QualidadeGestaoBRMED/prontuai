"use client"

import { useState } from "react"
import { AppSidebar } from "@/components/app-sidebar"
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import UserDropdown from "@/components/user-dropdown"
import { DocumentUploadZone } from "@/components/document-upload-zone"
import { DocumentBatchProcessor, DocumentProcessingResult } from "@/components/document-batch-processor"
import { ChatSidebar } from "@/components/chat-sidebar"
import { FileWithPreview } from "@/hooks/use-file-upload"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { ArrowLeft, Bell } from "lucide-react"
import { cn } from "@/lib/utils"
import { NotificationBell } from "@/components/notification-bell"
import { NotificationCenter } from "@/components/notification-center"
import { useNotifications } from "@/hooks/use-notifications"
import { ProcessProgressBar } from "@/components/process-progress-bar"
import { ResultsTable } from "@/components/results-table"
import { DocumentDetailsModal } from "@/components/document-details-modal"
import { ProcessResult } from "@/types/process"

type PageState = "upload" | "processing" | "completed"

export default function Page() {
  const [pageState, setPageState] = useState<PageState>("upload")
  const [filesToProcess, setFilesToProcess] = useState<FileWithPreview[]>([])
  const [chatInitialMessage, setChatInitialMessage] = useState<string>()
  const [selectedResult, setSelectedResult] = useState<ProcessResult | null>(null)
  const [detailsModalOpen, setDetailsModalOpen] = useState(false)
  const { unreadCount, activeProcess, setNotificationCenterOpen, processResults, progressBarMinimized, showProgressBar } = useNotifications()

  // Don't auto-navigate to results - let user control the state

  const handleProcessFiles = (files: FileWithPreview[]) => {
    setFilesToProcess(files)
    setPageState("processing")
    setChatInitialMessage(
      `Recebi ${files.length} ${files.length === 1 ? "documento" : "documentos"}! Iniciando processamento...`
    )
  }

  const handleProcessingComplete = (completedResults: DocumentProcessingResult[]) => {
    setPageState("completed")
    setChatInitialMessage(
      `Processamento concluído! ${completedResults.length} ${completedResults.length === 1 ? "documento processado" : "documentos processados"}.`
    )
  }

  const handleStartOver = () => {
    setPageState("upload")
    setFilesToProcess([])
    setChatInitialMessage(undefined)
  }

  return (
    <SidebarProvider>
      {activeProcess && (
        <ProcessProgressBar
          process={activeProcess}
        />
      )}
      <AppSidebar />
      <SidebarInset className="bg-sidebar group/sidebar-inset">
        <header className="flex h-16 shrink-0 items-center gap-2 px-4 md:px-6 lg:px-8 bg-sidebar text-sidebar-foreground relative before:absolute before:inset-y-3 before:-left-px before:w-px before:bg-gradient-to-b before:from-white/5 before:via-white/15 before:to-white/5 before:z-50">
          <SidebarTrigger className="-ms-2 text-sidebar-foreground hover:text-sidebar-foreground/70" />
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold">Enviar Documentos</h1>
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

        <div className="flex h-[calc(100svh-4rem)] bg-[hsl(240_5%_92.16%)] md:rounded-s-3xl md:group-peer-data-[state=collapsed]/sidebar-inset:rounded-s-none transition-all ease-in-out duration-300">
          {/* Main Content Area */}
          <div className="flex-1 overflow-auto">
            <div
              className={cn(
                "h-full p-6 md:p-8 lg:p-12 transition-all duration-500",
                pageState === "upload" && "flex items-center justify-center"
              )}
            >
              {pageState === "upload" && (
                <div className="w-full max-w-4xl mx-auto space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
                  <div className="text-center space-y-2 mb-8">
                    <h2 className="text-3xl font-bold">Bem-vindo!</h2>
                    <p className="text-muted-foreground">
                      Faça upload dos documentos médicos para validação automática
                    </p>
                  </div>
                  <DocumentUploadZone onProcessFiles={handleProcessFiles} />
                </div>
              )}

              {pageState === "processing" && (
                <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-500">
                  <div className="flex items-center justify-between">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={handleStartOver}
                      className="gap-2"
                    >
                      <ArrowLeft className="size-4" />
                      Voltar
                    </Button>
                  </div>

                  {/* Hint card when progress bar is minimized */}
                  {progressBarMinimized && activeProcess && (
                    <Card className="p-6 border-2 border-dashed">
                      <div className="flex flex-col items-center text-center space-y-4">
                        <div className="size-12 rounded-full bg-primary/10 flex items-center justify-center">
                          <Bell className="size-6 text-primary animate-pulse" />
                        </div>
                        <div>
                          <h3 className="font-semibold text-lg mb-2">
                            Processamento em Andamento
                          </h3>
                          <p className="text-sm text-muted-foreground mb-4">
                            Acompanhe o progresso em tempo real pelo sino de notificações no topo da página
                          </p>
                          <Button onClick={showProgressBar} variant="outline" size="sm">
                            Ver Progresso Aqui
                          </Button>
                        </div>
                      </div>
                    </Card>
                  )}

                  <DocumentBatchProcessor
                    files={filesToProcess}
                    onComplete={handleProcessingComplete}
                  />
                </div>
              )}

              {pageState === "completed" && (
                <div className="space-y-6 animate-in fade-in duration-500">
                  <div className="flex items-center justify-between">
                    <div>
                      <h2 className="text-2xl font-bold">Resultados de Processamento</h2>
                      <p className="text-sm text-muted-foreground mt-1">
                        {processResults.length} {processResults.length === 1 ? "documento processado" : "documentos processados"}
                      </p>
                    </div>
                    <Button onClick={handleStartOver} variant="outline" className="gap-2">
                      <ArrowLeft className="size-4" />
                      Novo Envio
                    </Button>
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
                      // Download JSON
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
              )}
            </div>
          </div>

          {/* Chat Sidebar */}
          <div className="w-96 shrink-0 border-l">
            <ChatSidebar initialMessage={chatInitialMessage} />
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
