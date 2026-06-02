"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { usePathname } from "next/navigation"

import { API_ENDPOINTS } from "@/lib/config"
import type { MaintenanceStatusResponse } from "@/types/maintenance"
import { MaintenanceBanner } from "@/components/maintenance/maintenance-banner"
import { MaintenancePage } from "@/components/maintenance/maintenance-page"

const EMPTY_MAINTENANCE: MaintenanceStatusResponse = {
  status: "none",
  message: "",
  eta: "",
}

const DISMISSED_KEY = "dismissedMaintenanceVersion"
const POLL_INTERVAL_MS = 60_000
const ACTIVE_BYPASS_PATHS = ["/login", "/auth/error", "/admin/ops-manutencao"]

export function MaintenanceWrapper({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const [maintenance, setMaintenance] = useState<MaintenanceStatusResponse>(EMPTY_MAINTENANCE)
  const [dismissedVersion, setDismissedVersion] = useState<string | null>(null)

  const fetchStatus = useCallback(async () => {
    try {
      const response = await fetch(API_ENDPOINTS.MAINTENANCE_STATUS, {
        cache: "no-store",
      })
      if (!response.ok) return
      const payload = (await response.json()) as MaintenanceStatusResponse
      setMaintenance(payload)
    } catch {
      setMaintenance(EMPTY_MAINTENANCE)
    }
  }, [])

  useEffect(() => {
    if (typeof window === "undefined") return
    setDismissedVersion(window.localStorage.getItem(DISMISSED_KEY))
  }, [])

  useEffect(() => {
    fetchStatus()
    const interval = window.setInterval(fetchStatus, POLL_INTERVAL_MS)
    return () => window.clearInterval(interval)
  }, [fetchStatus])

  const maintenanceVersion = maintenance.version || maintenance.id || null
  const canBypassActive = useMemo(
    () => ACTIVE_BYPASS_PATHS.some((path) => pathname === path || pathname?.startsWith(`${path}/`)),
    [pathname],
  )
  const showScheduledBanner =
    maintenance.status === "scheduled" &&
    Boolean(maintenanceVersion) &&
    dismissedVersion !== maintenanceVersion

  const dismissBanner = () => {
    if (!maintenanceVersion) return
    window.localStorage.setItem(DISMISSED_KEY, maintenanceVersion)
    setDismissedVersion(maintenanceVersion)
  }

  if (maintenance.status === "active" && !canBypassActive) {
    return <MaintenancePage maintenance={maintenance} />
  }

  return (
    <>
      {showScheduledBanner && (
        <MaintenanceBanner maintenance={maintenance} onDismiss={dismissBanner} />
      )}
      {children}
    </>
  )
}
