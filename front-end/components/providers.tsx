"use client"

import { SessionProvider } from "next-auth/react"
import { NotificationProvider } from "@/hooks/use-notifications"
import { MaintenanceWrapper } from "@/components/maintenance/maintenance-wrapper"

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider>
      <MaintenanceWrapper>
        <NotificationProvider>
          {children}
        </NotificationProvider>
      </MaintenanceWrapper>
    </SessionProvider>
  )
}
