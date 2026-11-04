"use client"

import { AppSidebar } from "@/components/app-sidebar"
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar"
import UserDropdown from "@/components/user-dropdown"
import { useNotifications } from "@/hooks/use-notifications"
import { NotificationBell } from "@/components/notification-bell"
import { NotificationCenter } from "@/components/notification-center"
import { PainelChecagem } from "@/components/painel-checagem"
import { RequireRole } from "@/components/require-role"

export default function Page() {
  const { unreadCount, activeProcess, setNotificationCenterOpen } = useNotifications()

  return (
    <RequireRole allowedRoles={["ADMIN", "MANAGER", "CHECKER", "CURATOR"]}>
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset className="bg-sidebar group/sidebar-inset">
          <header className="flex h-16 shrink-0 items-center gap-2 px-4 md:px-6 lg:px-8 bg-sidebar text-sidebar-foreground relative before:absolute before:inset-y-3 before:-left-px before:w-px before:bg-gradient-to-b before:from-white/5 before:via-white/15 before:to-white/5 before:z-50">
            <SidebarTrigger className="-ms-2 text-sidebar-foreground hover:text-sidebar-foreground/70" />
            <h1 className="text-lg font-semibold">Checagem de Documentos</h1>
            <div className="flex items-center gap-2 ml-auto">
              <NotificationBell
                unreadCount={unreadCount}
                hasActiveProcess={!!activeProcess}
                onClick={() => setNotificationCenterOpen(true)}
              />
              <UserDropdown />
            </div>
          </header>

          <div className="flex flex-col h-[calc(100svh-4rem)] bg-[hsl(240_5%_92.16%)] md:rounded-s-3xl md:group-peer-data-[state=collapsed]/sidebar-inset:rounded-s-none transition-all ease-in-out duration-300">
            <div className="flex-1 min-h-0 flex flex-col p-4 md:p-6 lg:p-8 overflow-hidden">
              <PainelChecagem />
            </div>
          </div>
        </SidebarInset>
        <NotificationCenter />
      </SidebarProvider>
    </RequireRole>
  )
}
