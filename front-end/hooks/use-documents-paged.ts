"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useSession } from "next-auth/react"
import { API_ENDPOINTS } from "@/lib/config"
import { authFetch } from "@/lib/auth-fetch"
import { useVisibleInterval } from "@/hooks/use-visible-interval"
import { DocumentApi, DocumentQueue, DocumentSummaryCounts, PaginatedDocumentsResponse } from "@/types/document"

type UseDocumentsPagedOptions = {
  queue: DocumentQueue
  pageSize?: number
  compact?: boolean
  refreshIntervalMs?: number
}

export function useDocumentsPaged(options: UseDocumentsPagedOptions) {
  const { queue, pageSize = 10, compact = true, refreshIntervalMs = 7000 } = options
  const { data: session } = useSession()

  const [documents, setDocuments] = useState<DocumentApi[]>([])
  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [totalItems, setTotalItems] = useState(0)
  const [hasNext, setHasNext] = useState(false)
  const [search, setSearch] = useState("")
  const [statusFilter, setStatusFilter] = useState<"all" | "approved" | "rejected" | "pending_review">("all")
  const [clinicFilter, setClinicFilter] = useState("all")
  const [summaryCounts, setSummaryCounts] = useState<DocumentSummaryCounts>({
    approved: 0,
    rejected: 0,
    pending_review: 0,
    total: 0,
  })
  const documentsSignatureRef = useRef<string>("")
  const paginationSignatureRef = useRef<string>("")
  const summarySignatureRef = useRef<string>("")
  // Aborta a requisição anterior quando os parâmetros mudam. Sem isto, digitar
  // na busca deixa várias chamadas em voo e quem responder por último vence —
  // que não é necessariamente a última digitada. O efeito na tela é a lista
  // "voltar" para um resultado antigo sozinha.
  const abortRef = useRef<AbortController | null>(null)

  const fetchPage = useCallback(
    async (silent = false) => {
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      if (!silent) setLoading(true)
      setError(null)

      try {
        const url = new URL(API_ENDPOINTS.DOCUMENTS_PAGED, window.location.origin)
        url.searchParams.set("queue", queue)
        url.searchParams.set("page", String(page))
        url.searchParams.set("page_size", String(pageSize))
        url.searchParams.set("compact", String(compact))
        url.searchParams.set("sort_by", "uploaded_at")
        url.searchParams.set("sort_dir", "desc")
        if (search.trim()) url.searchParams.set("search", search.trim())
        if (statusFilter !== "all") url.searchParams.set("status_filter", statusFilter)
        if (clinicFilter !== "all") url.searchParams.set("clinic_id", clinicFilter)

        const response = await authFetch(url.toString(), {
          cache: "no-store",
          signal: controller.signal,
        })
        if (!response.ok) {
          const detail = await response.text().catch(() => "Erro ao carregar documentos paginados")
          throw new Error(detail)
        }
        const data = (await response.json()) as PaginatedDocumentsResponse
        const nextItems = data.items || []
        const nextItemsSignature = JSON.stringify(nextItems)
        if (nextItemsSignature !== documentsSignatureRef.current) {
          documentsSignatureRef.current = nextItemsSignature
          setDocuments(nextItems)
        }

        const nextPaginationSignature = `${data.total_pages || 1}|${data.total_items || 0}|${Boolean(data.has_next)}`
        if (nextPaginationSignature !== paginationSignatureRef.current) {
          paginationSignatureRef.current = nextPaginationSignature
          setTotalPages(data.total_pages || 1)
          setTotalItems(data.total_items || 0)
          setHasNext(Boolean(data.has_next))
        }

        const nextSummary =
          data.summary_counts || {
            approved: 0,
            rejected: 0,
            pending_review: 0,
            total: 0,
          }
        const nextSummarySignature = `${nextSummary.approved}|${nextSummary.rejected}|${nextSummary.pending_review}|${nextSummary.total}`
        if (nextSummarySignature !== summarySignatureRef.current) {
          summarySignatureRef.current = nextSummarySignature
          setSummaryCounts(nextSummary)
        }
      } catch (err) {
        // Aborto é o fluxo normal de "os parâmetros mudaram": mostrar erro aqui
        // faria a tela piscar uma mensagem vermelha a cada tecla digitada.
        if (controller.signal.aborted) return
        const message = err instanceof Error ? err.message : "Erro ao carregar documentos paginados"
        setError(message)
      } finally {
        // A chamada que já foi substituída não mexe mais no estado de
        // carregamento: quem manda é a que está em voo.
        if (abortRef.current === controller) {
          setLoading(false)
          if (!silent) setRefreshing(false)
        }
      }
    },
    [session?.user?.email, queue, page, pageSize, compact, search, statusFilter, clinicFilter],
  )

  useEffect(() => {
    fetchPage(false)
  }, [fetchPage])

  useEffect(() => () => abortRef.current?.abort(), [])

  const refreshSilently = useCallback(() => {
    fetchPage(true)
  }, [fetchPage])

  useVisibleInterval(refreshSilently, refreshIntervalMs)

  // Clicar no item já ativo da sidebar recarrega a lista (`app-sidebar.tsx`).
  // O listener morava no hook legado `useDocuments`, que só o Histórico usava —
  // em Pendentes e Checagem o evento era disparado e ninguém ouvia. Aqui ele
  // vale para as três telas.
  useEffect(() => {
    const aoPedirRefresh = () => refreshSilently()
    window.addEventListener("documents:refresh", aoPedirRefresh)
    return () => window.removeEventListener("documents:refresh", aoPedirRefresh)
  }, [refreshSilently])

  // Trocar de filtro volta para a página 1 — senão a página 4 de um filtro vira
  // a página 4 (quase sempre vazia) do filtro novo.
  //
  // O reset vai JUNTO com o filtro, no mesmo setter, e não num `useEffect`
  // separado: no efeito, o React já teria renderizado com {filtro novo, página
  // antiga} e disparado uma busca que seria descartada no render seguinte. Aqui
  // os dois `set` entram no mesmo lote e sai uma requisição só.
  // `setSearch`/`setStatusFilter`/`setClinicFilter`/`setPage` vêm do `useState`
  // e são estáveis, então `[]` como dependência está correto.
  const aplicarSearch = useCallback((valor: string) => {
    setSearch(valor)
    setPage(1)
  }, [])

  const aplicarStatusFilter = useCallback(
    (valor: "all" | "approved" | "rejected" | "pending_review") => {
      setStatusFilter(valor)
      setPage(1)
    },
    [],
  )

  const aplicarClinicFilter = useCallback((valor: string) => {
    setClinicFilter(valor)
    setPage(1)
  }, [])

  // `queue` e `pageSize` vêm das opções do hook, não de um setter daqui.
  useEffect(() => {
    setPage(1)
  }, [queue, pageSize])

  return {
    documents,
    loading,
    refreshing,
    error,
    page,
    setPage,
    totalPages,
    totalItems,
    hasNext,
    search,
    setSearch: aplicarSearch,
    statusFilter,
    setStatusFilter: aplicarStatusFilter,
    clinicFilter,
    setClinicFilter: aplicarClinicFilter,
    summaryCounts,
    refresh: fetchPage,
  }
}
