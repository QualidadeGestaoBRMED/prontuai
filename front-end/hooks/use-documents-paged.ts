"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useSession } from "next-auth/react"
import { API_ENDPOINTS } from "@/lib/config"
import { authFetch } from "@/lib/auth-fetch"
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

  const fetchPage = useCallback(
    async (silent = false) => {
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

        const response = await authFetch(url.toString(), { cache: "no-store" })
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
        const message = err instanceof Error ? err.message : "Erro ao carregar documentos paginados"
        setError(message)
      } finally {
        setLoading(false)
        if (!silent) setRefreshing(false)
      }
    },
    [session?.user?.email, queue, page, pageSize, compact, search, statusFilter, clinicFilter],
  )

  useEffect(() => {
    fetchPage(false)
  }, [fetchPage])

  useEffect(() => {
    if (refreshIntervalMs <= 0) return
    const interval = window.setInterval(() => {
      fetchPage(true)
    }, refreshIntervalMs)
    return () => window.clearInterval(interval)
  }, [fetchPage, refreshIntervalMs])

  useEffect(() => {
    setPage(1)
  }, [queue, search, statusFilter, clinicFilter, pageSize])

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
    setSearch,
    statusFilter,
    setStatusFilter,
    clinicFilter,
    setClinicFilter,
    summaryCounts,
    refresh: fetchPage,
  }
}
