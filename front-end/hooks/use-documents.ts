"use client"

// DEPRECATED: hook legado que carrega TODA a coleção de documentos.
// Usado somente por /historico enquanto não migra para useDocumentsPaged
// com uma queue "historico" no backend. Não use em telas novas — prefira
// `useDocumentsPaged({ queue: ... })` para evitar fetches O(N).

import { useCallback, useEffect, useRef, useState } from "react"
import { useSession } from "next-auth/react"
import { API_ENDPOINTS } from "@/lib/config"
import { DocumentApi } from "@/types/document"
import { authFetch } from "@/lib/auth-fetch"

type FetchOptions = {
  silent?: boolean
  clear?: boolean
  showIndicator?: boolean
}

export function useDocuments() {
  const { data: session } = useSession()
  const [documents, setDocuments] = useState<DocumentApi[]>([])
  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasLoaded, setHasLoaded] = useState(false)
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null)
  const refreshIntervalMs = 3000
  const refreshIndicatorDelayMs = 700
  const refreshIndicatorCooldownMs = 12000
  const inFlightRef = useRef(false)
  const refreshTimerRef = useRef<number | null>(null)
  const lastUpdatedAtRef = useRef<Date | null>(null)

  const fetchDocuments = useCallback(async (options?: FetchOptions) => {
    const silent = options?.silent ?? false
    const clear = options?.clear ?? false
    const showIndicator = options?.showIndicator ?? silent
    if (inFlightRef.current) return
    inFlightRef.current = true
    if (!silent) {
      setLoading(true)
      if (clear) {
        setDocuments([])
      }
    } else {
      if (showIndicator) {
        const now = Date.now()
        const lastUpdated = lastUpdatedAtRef.current?.getTime() ?? 0
        const canShowIndicator = now - lastUpdated > refreshIndicatorCooldownMs
        if (canShowIndicator) {
          if (refreshTimerRef.current) {
            window.clearTimeout(refreshTimerRef.current)
          }
          refreshTimerRef.current = window.setTimeout(() => {
            setRefreshing(true)
          }, refreshIndicatorDelayMs)
        }
      }
    }
    setError(null)

    try {
      const headers: Record<string, string> = {}
      headers["Cache-Control"] = "no-cache"
      headers.Pragma = "no-cache"

      const url = new URL(API_ENDPOINTS.DOCUMENTS, window.location.origin)
      url.searchParams.set("compact", "true")
      url.searchParams.set("cache_seconds", "10")
      url.searchParams.set("stale_seconds", "120")

      const response = await authFetch(url.toString(), {
        headers,
        cache: "no-store",
      })
      if (!response.ok) {
        const detail = await response.text().catch(() => "Erro ao carregar documentos")
        throw new Error(detail)
      }
      const data = (await response.json()) as DocumentApi[]
      setDocuments(data)
      setHasLoaded(true)
      const updatedAt = new Date()
      lastUpdatedAtRef.current = updatedAt
      setLastUpdatedAt(updatedAt)
    } catch (err) {
      const message = err instanceof Error ? err.message : "Erro ao carregar documentos"
      setError(message)
    } finally {
      if (refreshTimerRef.current) {
        window.clearTimeout(refreshTimerRef.current)
        refreshTimerRef.current = null
      }
      if (!silent) {
        setLoading(false)
      } else {
        setRefreshing(false)
      }
      inFlightRef.current = false
    }
  }, [session?.user?.email])

  useEffect(() => {
    fetchDocuments()
  }, [fetchDocuments])

  useEffect(() => {
    const onFocus = () => fetchDocuments({ silent: true, showIndicator: false })
    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        fetchDocuments({ silent: true, showIndicator: false })
      }
    }

    window.addEventListener("focus", onFocus)
    document.addEventListener("visibilitychange", onVisibility)
    const interval = window.setInterval(() => {
      fetchDocuments({ silent: true, showIndicator: false })
    }, refreshIntervalMs)

    return () => {
      window.removeEventListener("focus", onFocus)
      document.removeEventListener("visibilitychange", onVisibility)
      window.clearInterval(interval)
    }
  }, [fetchDocuments, refreshIntervalMs])

  useEffect(() => {
    const onManualRefresh = (event: Event) => {
      const detail = (event as CustomEvent)?.detail as FetchOptions | undefined
      fetchDocuments({
        silent: detail?.silent ?? true,
        clear: detail?.clear ?? false,
        showIndicator: detail?.showIndicator ?? true,
      })
    }

    window.addEventListener("documents:refresh", onManualRefresh as EventListener)
    return () => {
      window.removeEventListener("documents:refresh", onManualRefresh as EventListener)
    }
  }, [fetchDocuments])

  return { documents, loading, refreshing, hasLoaded, lastUpdatedAt, error, refresh: fetchDocuments }
}
