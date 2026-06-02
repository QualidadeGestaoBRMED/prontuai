"use client"

import { TriangleAlert, X } from "lucide-react"

import { Alert } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import type { MaintenanceStatusResponse } from "@/types/maintenance"

type MaintenanceBannerProps = {
  maintenance: MaintenanceStatusResponse
  onDismiss: () => void
}

export function MaintenanceBanner({ maintenance, onDismiss }: MaintenanceBannerProps) {
  const when = maintenance.eta || maintenance.starts_at || ""
  const message = [maintenance.message, when ? `Previsão: ${when}` : ""]
    .filter(Boolean)
    .join(" ")

  return (
    <div className="fixed left-0 right-0 top-3 z-[80] pointer-events-none">
      <Alert className="pointer-events-auto relative mx-auto flex w-[90%] max-w-7xl flex-row items-center justify-center gap-3 rounded-full border-amber-200 bg-amber-50/95 px-12 py-2 text-amber-950 shadow-lg shadow-amber-950/5 backdrop-blur">
        <div className="flex min-w-0 max-w-full items-center justify-center gap-2 text-center">
          <TriangleAlert className="size-4 shrink-0 text-amber-600" aria-hidden="true" />
          <Badge className="border-amber-300 bg-amber-200 text-amber-900 hover:bg-amber-200">
            Manutenção
          </Badge>
          <span className="truncate text-sm font-medium">{message}</span>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="absolute right-3 top-1/2 -translate-y-1/2 shrink-0 rounded-full text-amber-700 hover:bg-amber-100 hover:text-amber-950"
          aria-label="Fechar aviso de manutenção"
          onClick={onDismiss}
        >
          <X className="size-4" aria-hidden="true" />
        </Button>
      </Alert>
    </div>
  )
}
