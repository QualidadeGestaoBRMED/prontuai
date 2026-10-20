"use client"

import { useEffect, useState } from "react"
import { API_ENDPOINTS } from "@/lib/config"
import { authFetch } from "@/lib/auth-fetch"
import { usePermissions, type UserRole } from "@/hooks/usePermissions"

export type ClinicOption = {
  id: string
  name: string
}

const LEEM_TODAS_AS_CLINICAS: UserRole[] = ["ADMIN", "MANAGER", "CHECKER", "CURATOR"]

export function useClinicOptions() {
  const { roles } = usePermissions()
  // O filtro de clínica é para quem enxerga todas — espelho de
  // GLOBAL_READ_ROLES no back. Não basta "qualquer cargo além do SENDER": o
  // Enviador + Visualizador não lê outras clínicas e levaria 403.
  const enabled = roles.some((r) => LEEM_TODAS_AS_CLINICAS.includes(r))
  const [options, setOptions] = useState<ClinicOption[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!enabled) {
      setOptions([])
      setError(null)
      return
    }

    let cancelled = false
    async function loadOptions() {
      setLoading(true)
      setError(null)
      try {
        const response = await authFetch(API_ENDPOINTS.CLINIC_OPTIONS, { cache: "no-store" })
        if (!response.ok) throw new Error("Erro ao carregar clínicas")
        const data = (await response.json()) as ClinicOption[]
        if (!cancelled) setOptions(data)
      } catch (err) {
        const message = err instanceof Error ? err.message : "Erro ao carregar clínicas"
        if (!cancelled) setError(message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    loadOptions()
    return () => {
      cancelled = true
    }
  }, [enabled])

  return { options, loading, error, enabled }
}
