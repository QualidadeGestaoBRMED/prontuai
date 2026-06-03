"use client"

import { useEffect } from "react"
import { SessionProvider, signOut } from "next-auth/react"
import { toast } from "sonner"
import { NotificationProvider } from "@/hooks/use-notifications"
import { MaintenanceWrapper } from "@/components/maintenance/maintenance-wrapper"

function AuthGuard({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    let fired = false
    const handle = () => {
      if (fired) return
      fired = true
      toast.error("Sessão expirada. Faça login novamente.", { duration: 4000 })
      signOut({ callbackUrl: "/login" })
    }
    window.addEventListener("auth:unauthorized", handle)
    return () => window.removeEventListener("auth:unauthorized", handle)
  }, [])

  return <>{children}</>
}

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider>
      <AuthGuard>
        <MaintenanceWrapper>
          <NotificationProvider>
            {children}
          </NotificationProvider>
        </MaintenanceWrapper>
      </AuthGuard>
    </SessionProvider>
  )
}
