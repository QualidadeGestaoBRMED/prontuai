"use client"

import { useCallback, useEffect, useState } from "react"
import { useSession } from "next-auth/react"
import { API_ENDPOINTS } from "@/lib/config"
import { DocumentApi } from "@/types/document"

export function useDocuments() {
  const { data: session } = useSession()
  const [documents, setDocuments] = useState<DocumentApi[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const refreshIntervalMs = 2000

  const fetchDocuments = useCallback(async () => {
    setLoading(true)
    setError(null)

    try {
      const headers: Record<string, string> = {}
      if (session?.accessToken) {
        headers.Authorization = `Bearer ${session.accessToken}`
      }

      const response = await fetch(API_ENDPOINTS.DOCUMENTS, {
        headers,
        cache: "no-store",
      })
      if (!response.ok) {
        const detail = await response.text().catch(() => "Erro ao carregar documentos")
        throw new Error(detail)
      }
      const data = (await response.json()) as DocumentApi[]
      setDocuments(data)
    } catch (err) {
      const message = err instanceof Error ? err.message : "Erro ao carregar documentos"
      setError(message)
    } finally {
      setLoading(false)
    }
  }, [session?.accessToken])

  useEffect(() => {
    fetchDocuments()
  }, [fetchDocuments])

  useEffect(() => {
    const onFocus = () => fetchDocuments()
    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        fetchDocuments()
      }
    }

    window.addEventListener("focus", onFocus)
    document.addEventListener("visibilitychange", onVisibility)
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        fetchDocuments()
      }
    }, refreshIntervalMs)

    return () => {
      window.removeEventListener("focus", onFocus)
      document.removeEventListener("visibilitychange", onVisibility)
      window.clearInterval(interval)
    }
  }, [fetchDocuments, refreshIntervalMs])

  return { documents, loading, error, refresh: fetchDocuments }
}
