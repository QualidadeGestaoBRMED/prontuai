"use client"

import { Suspense, useMemo, useState } from "react"
import { useSearchParams } from "next/navigation"
import { useSession } from "next-auth/react"
import { AppSidebar } from "@/components/app-sidebar"
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import UserDropdown from "@/components/user-dropdown"
import { DocumentUploadZone } from "@/components/document-upload-zone"
import { DocumentBatchProcessor, DocumentProcessingResult } from "@/components/document-batch-processor"
// import { ChatSidebar } from "@/components/chat-sidebar"
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
import { generateResultPDF } from "@/lib/pdf-generator"

type PageState = "upload" | "processing" | "completed"

export default function Page() {
  return (
    <Suspense fallback={<PageLoading />}>
      <PageContent />
    </Suspense>
  )
}

function PageLoading() {
  return (
    <div className="flex items-center justify-center h-screen bg-sidebar">
      <div className="animate-pulse text-sidebar-foreground">Carregando...</div>
    </div>
  )
}

function PageContent() {
  const searchParams = useSearchParams()
  const autoOpenUpload = searchParams.get("reenviar") === "1"
  const [pageState, setPageState] = useState<PageState>("upload")
  const [filesToProcess, setFilesToProcess] = useState<FileWithPreview[]>([])
  // const [chatInitialMessage, setChatInitialMessage] = useState<string>()
  const [selectedResult, setSelectedResult] = useState<ProcessResult | null>(null)
  const [detailsModalOpen, setDetailsModalOpen] = useState(false)
  const { unreadCount, activeProcess, setNotificationCenterOpen, processResults, progressBarMinimized, showProgressBar } = useNotifications()
  const { data: session } = useSession()
  const userEmail = session?.user?.email?.toLowerCase()

  const filteredResults = useMemo(() => {
    if (!userEmail) return processResults
    return processResults.filter((result) =>
      (result.submittedBy || "").toLowerCase() === userEmail
    )
  }, [processResults, userEmail])

  const sortedResults = useMemo(() => {
    const list = [...filteredResults]
    const toTime = (value: unknown) => {
      if (!value) return 0
      if (value instanceof Date) return value.getTime()
      const parsed = new Date(String(value))
      return Number.isNaN(parsed.getTime()) ? 0 : parsed.getTime()
    }
    list.sort((a, b) => {
      const timeA = toTime(a.processedAt) || toTime(a.uploadedAt)
      const timeB = toTime(b.processedAt) || toTime(b.uploadedAt)
      return timeB - timeA
    })
    return list
  }, [filteredResults])

  // Don't auto-navigate to results - let user control the state

  const handleProcessFiles = (files: FileWithPreview[]) => {
    setFilesToProcess(files)
    setPageState("processing")
    // setChatInitialMessage(
    //   `Recebi ${files.length} ${files.length === 1 ? "documento" : "documentos"}! Iniciando processamento...`
    // )
  }

  const handleProcessingComplete = (completedResults: DocumentProcessingResult[]) => {
    setPageState("completed")
    // setChatInitialMessage(
    //   `Processamento concluído! ${completedResults.length} ${completedResults.length === 1 ? "documento processado" : "documentos processados"}.`
    // )
  }

  const handleStartOver = () => {
    setPageState("upload")
    setFilesToProcess([])
    // setChatInitialMessage(undefined)
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
            <h1 className="text-lg font-semibold">Anexar Prontuário</h1>
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
                  <DocumentUploadZone onProcessFiles={handleProcessFiles} autoOpen={autoOpenUpload} />
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
                    submittedBy={session?.user?.email || undefined}
                  />
                </div>
              )}

              {pageState === "completed" && (
                <div className="space-y-6 animate-in fade-in duration-500">
                  <div className="flex items-center justify-between">
                    <div>
                      <h2 className="text-2xl font-bold">Resultados de Processamento</h2>
                      <p className="text-sm text-muted-foreground mt-1">
                        {sortedResults.length} {sortedResults.length === 1 ? "documento processado" : "documentos processados"}
                      </p>
                    </div>
                    <Button onClick={handleStartOver} variant="outline" className="gap-2">
                      <ArrowLeft className="size-4" />
                      Novo Envio
                    </Button>
                  </div>

                  {/* Estatísticas compactas */}
                  <div className="grid grid-cols-3 gap-4">
                    <div className="bg-gradient-to-br from-green-50 to-green-100 border border-green-200 rounded-lg p-4 shadow-sm">
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="text-xs font-medium text-green-700 uppercase tracking-wide">Aprovados</div>
                          <div className="text-3xl font-bold text-green-600 mt-1">
                            {sortedResults.filter((r) => r.status === "approved" && r.reviewedBy).length}
                          </div>
                        </div>
                        <div className="size-12 rounded-full bg-green-200 flex items-center justify-center">
                          <svg className="size-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                          </svg>
                        </div>
                      </div>
                    </div>

                    <div className="bg-gradient-to-br from-amber-50 to-amber-100 border border-amber-200 rounded-lg p-4 shadow-sm">
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="text-xs font-medium text-amber-700 uppercase tracking-wide">Aguardando Revisão</div>
                          <div className="text-3xl font-bold text-amber-600 mt-1">
                            {sortedResults.filter((r) => (r.status === "approved" || r.status === "pending_review") && !r.reviewedBy).length}
                          </div>
                        </div>
                        <div className="size-12 rounded-full bg-amber-200 flex items-center justify-center">
                          <svg className="size-6 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                          </svg>
                        </div>
                      </div>
                    </div>

                    <div className="bg-gradient-to-br from-red-50 to-red-100 border border-red-200 rounded-lg p-4 shadow-sm">
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="text-xs font-medium text-red-700 uppercase tracking-wide">Rejeitados</div>
                          <div className="text-3xl font-bold text-red-600 mt-1">
                            {sortedResults.filter((r) => r.status === "rejected" && r.reviewedBy).length}
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

                  <ResultsTable
                    results={sortedResults}
                    onViewDetails={(result) => {
                      setSelectedResult(result)
                      setDetailsModalOpen(true)
                    }}
                    onDownloadPDF={(result) => {
                      generateResultPDF(result)
                    }}
                  />
                </div>
              )}
            </div>
          </div>

          {/* FAQ removido temporariamente (manter para retorno futuro). */}
          {/* <div className="w-96 shrink-0 border-l">
            <ChatSidebar initialMessage={chatInitialMessage} />
          </div> */}
        </div>
      </SidebarInset>
      <NotificationCenter />
      <DocumentDetailsModal
        open={detailsModalOpen}
        onOpenChange={setDetailsModalOpen}
        result={selectedResult}
        onDownloadPDF={selectedResult ? () => {
          generateResultPDF(selectedResult)
        } : undefined}
      />
    </SidebarProvider>
  )
}
