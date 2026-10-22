"use client"

import { useState, useEffect, Suspense, useMemo, useCallback, useRef } from "react"
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
import { useDocumentsPaged } from "@/hooks/use-documents-paged"
import { useClinicOptions } from "@/hooks/use-clinic-options"
import { documentToProcessResult } from "@/lib/document-mapper"
import { ProcessProgressBar } from "@/components/process-progress-bar"
import { ResultsTable } from "@/components/results-table"
import { DocumentDetailsModal } from "@/components/document-details-modal"
import { ProcessResult } from "@/types/process"
import { History, Loader2 } from "lucide-react"
import { downloadDocumentPdf } from "@/lib/document-download"
import { DocumentoArquivadoError } from "@/lib/document-archive"
import { authFetch } from "@/lib/auth-fetch"
import { API_ENDPOINTS } from "@/lib/config"
import { DocumentApi } from "@/types/document"
import { toast } from "sonner"

function HistoricoContent() {
  const searchParams = useSearchParams()
  const [selectedResult, setSelectedResult] = useState<ProcessResult | null>(null)
  const [detailsModalOpen, setDetailsModalOpen] = useState(false)
  const { unreadCount, activeProcess, setNotificationCenterOpen } = useNotifications()
  // Paginação server-side, como Pendentes e Checagem já fazem.
  //
  // Antes esta tela usava `useDocuments()`, que baixa a coleção INTEIRA: medido
  // no dev com 11.188 documentos, `GET /v1/documents?compact=true` devolve
  // 69 MB em 7,2s — e o hook repetia isso a cada 30s e a cada foco da janela,
  // atravessando o proxy do Next nas duas pontas. A ordenação, a busca, o
  // filtro de status e o de clínica passam todos a rodar no banco, que é onde
  // eles enxergam todas as páginas e não só a que está na tela.
  const {
    documents,
    loading,
    refreshing,
    page,
    setPage,
    totalPages,
    totalItems,
    search,
    setSearch,
    statusFilter,
    setStatusFilter,
    clinicFilter,
    setClinicFilter,
    refresh,
  } = useDocumentsPaged({
    queue: "historico",
    pageSize: 10,
    refreshIntervalMs: 0,
  })
  const {
    options: clinicOptions,
    loading: clinicOptionsLoading,
    enabled: canFilterByClinic,
  } = useClinicOptions()
  // Precisa ser memoizado: sem isso o array nasce novo a cada render, o efeito
  // do `viewId` — que depende dele — dispara em todo render. Como
  // `setSelectedResult` recebia um objeto novo toda vez, o React não conseguia
  // descartar a atualização e a página entrava em loop infinito (React #185).
  // É o mesmo cuidado que `pendentes/page.tsx` já tinha.
  const sortedResults = useMemo(() => documents.map(documentToProcessResult), [documents])
  const showRefreshing = refreshing

  // Spinner só no PRIMEIRO carregamento, como a Checagem já fazia. Condicionar
  // à lista vazia (`sortedResults.length === 0`) parecia equivalente e não é:
  // toda busca sem resultado troca a tabela pelo spinner, desmontando o campo
  // de busca junto — o foco e o texto digitado se perdem no meio da digitação.
  const [carregouUmaVez, setCarregouUmaVez] = useState(false)
  useEffect(() => {
    if (!loading) setCarregouUmaVez(true)
  }, [loading])

  useEffect(() => {
    if (!canFilterByClinic) setClinicFilter("all")
  }, [canFilterByClinic, setClinicFilter])

  // Auto-abre o modal quando a URL traz `?viewId=<id do documento>`.
  //
  // A lista é paginada (10 por página), então o documento quase nunca está na
  // página carregada. Antes o efeito só procurava em `sortedResults` e, sem
  // achar, não fazia nada: o link só abria os 10 documentos mais recentes.
  // Fora da página, o documento vem de `GET /v1/documents/{id}`, que já
  // aplica a regra de clínica do SENDER no back-end.
  //
  // Abre uma vez por id. Sem essa trava o modal reabria sozinho a cada
  // atualização da lista depois de fechado, e reatribuir o resultado a cada
  // render levava ao loop infinito (React #185) que a memoização acima evita.
  const viewIdAberto = useRef<string | null>(null)
  useEffect(() => {
    const viewId = searchParams.get('viewId')
    if (!viewId || viewIdAberto.current === viewId) return
    const daPagina = sortedResults.find(r => r.id === viewId)
    if (daPagina) {
      viewIdAberto.current = viewId
      setSelectedResult(daPagina)
      setDetailsModalOpen(true)
      return
    }
    if (loading) return
    viewIdAberto.current = viewId
    void (async () => {
      try {
        const response = await authFetch(`${API_ENDPOINTS.DOCUMENTS}/${encodeURIComponent(viewId)}`)
        if (!response.ok) {
          toast.error(
            response.status === 404
              ? "Documento não encontrado."
              : response.status === 403
                ? "Você não tem permissão para abrir este documento."
                : "Não foi possível abrir o documento."
          )
          return
        }
        const doc = (await response.json()) as DocumentApi
        setSelectedResult(documentToProcessResult(doc))
        setDetailsModalOpen(true)
      } catch (error) {
        console.error("Falha ao abrir documento do link:", error)
        toast.error("Não foi possível abrir o documento.")
      }
    })()
  }, [searchParams, sortedResults, loading])

  const handleDownloadPDF = useCallback(async (result: ProcessResult) => {
    if (!result?.id) return
    try {
      await downloadDocumentPdf({
        id: result.id,
        filename: result.filename,
      })
    } catch (error) {
      console.error("Falha ao baixar PDF:", error)
      // Antes este catch era silencioso: a falha só aparecia no console.
      // Com o arquivamento, "não abre" passou a ser um caso normal e o
      // usuário precisa saber o que fazer.
      if (error instanceof DocumentoArquivadoError) {
        toast.info(error.message, { duration: 10000 })
      } else {
        toast.error("Não foi possível baixar o documento.")
      }
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
                </div>
              )}

              {loading && !carregouUmaVez ? (
                <div className="border rounded-lg bg-white p-6 flex items-center gap-3 text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" />
                  <span>Sincronizando documentos com o banco...</span>
                </div>
                ) : (
                  <ResultsTable
                    results={sortedResults}
                    serverMode
                    searchQuery={search}
                    onSearchQueryChange={setSearch}
                    statusFilter={statusFilter}
                    onStatusFilterChange={setStatusFilter}
                    clinicFilter={clinicFilter}
                    onClinicFilterChange={setClinicFilter}
                    clinicOptions={clinicOptions}
                    clinicOptionsLoading={clinicOptionsLoading}
                    showClinicFilter={canFilterByClinic}
                    currentPage={page}
                    totalPages={totalPages}
                    totalItems={totalItems}
                    pageSize={10}
                    onPageChange={setPage}
                    onViewDetails={(result) => {
                      setSelectedResult(result)
                      setDetailsModalOpen(true)
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
        onComplemento={() => refresh()}
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
