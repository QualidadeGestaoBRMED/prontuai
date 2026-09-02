'use client'

import * as React from "react";
import Image from "next/image";
import Link from "next/link";
import { usePermissions } from "@/hooks/usePermissions";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import {
  RiUploadLine,
  RiCheckDoubleLine,
  RiHistoryLine,
  RiUserSettingsLine,
  RiHospitalLine,
  RiShieldCheckLine,
  RiFileSearchLine,
  RiTestTubeLine,
} from "@remixicon/react";
import { CentroAjudaDialog } from "@/components/centro-ajuda-dialog";
import { TourGuiado } from "@/components/tour-guiado";

// This is sample data.
const data = {
  teams: [
    {
      name: "BRMED",
      logo: "https://raw.githubusercontent.com/origin-space/origin-images/refs/heads/main/exp2/logo-01_upxvqe.png",
    },
    {
      name: "Acme Corp.",
      logo: "https://raw.githubusercontent.com/origin-space/origin-images/refs/heads/main/exp2/logo-01_upxvqe.png",
    },
    {
      name: "Evil Corp.",
      logo: "https://raw.githubusercontent.com/origin-space/origin-images/refs/heads/main/exp2/logo-01_upxvqe.png",
    },
  ],
  navMain: [
    {
      title: "Menu Principal",
      url: "#",
      items: [
        {
          title: "Anexar Prontuário",
          url: "/anexar-prontuario",
          icon: RiUploadLine,
          isActive: false,
          roles: ["ADMIN", "SENDER"],
        },
        {
          title: "Pendentes",
          url: "/pendentes",
          icon: RiHistoryLine,
          roles: ["ADMIN", "SENDER"],
        },
        {
          title: "Histórico",
          url: "/historico",
          icon: RiFileSearchLine,
          roles: ["ADMIN", "SENDER"],
        },
        {
          title: "Checagem",
          url: "/checagem",
          icon: RiCheckDoubleLine,
          roles: ["ADMIN", "CHECKER"],
        },
      ],
    },
  ],
};

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const { isAdmin, isManagement, role } = usePermissions();
  const documentsRoutes = new Set(["/pendentes", "/historico", "/checagem"]);
  const handleDocumentsRefresh = (url?: string) => {
    if (!url || !documentsRoutes.has(url)) return;
    if (typeof window === "undefined") return;
    window.dispatchEvent(
      new CustomEvent("documents:refresh", {
        detail: { silent: true, showIndicator: true },
      })
    );
  };
  const visibleItems = data.navMain[0]?.items.filter((item) => {
    if (isManagement) return true;
    if (!role) return false;
    if (!item.roles || item.roles.length === 0) return true;
    return item.roles.includes(role);
  });

  return (
    <Sidebar {...props} className="dark !border-none" data-tour="sidebar-completa">
      <SidebarHeader>
        <div className="h-22 w-48 relative flex items-center justify-center ml-5" data-tour="sidebar">
          <Image
            src="/logo.png"
            alt="Logo"
            fill
            className="object-contain"
            priority
          />
        </div>
      </SidebarHeader>
      <SidebarContent>
        {visibleItems && visibleItems.length > 0 && (
          <SidebarGroup>
            <SidebarGroupLabel className="uppercase text-sidebar-foreground/50">
              {data.navMain[0]?.title}
            </SidebarGroupLabel>
            <SidebarGroupContent className="px-2">
              <SidebarMenu>
                {visibleItems.map((item) => (
                  <SidebarMenuItem key={item.title}>
                    <SidebarMenuButton
                      asChild
                      className="group/menu-button font-medium gap-3 h-9 rounded-md data-[active=true]:hover:bg-transparent data-[active=true]:bg-gradient-to-b data-[active=true]:from-sidebar-primary data-[active=true]:to-sidebar-primary/70 data-[active=true]:shadow-[0_1px_2px_0_rgb(0_0_0/.05),inset_0_1px_0_0_rgb(255_255_255/.12)] [&>svg]:size-auto"
                      isActive={item.isActive}
                    >
                      <Link
                        href={item.url}
                        data-tour={item.title.toLowerCase()}
                        onClick={() => handleDocumentsRefresh(item.url)}
                      >
                        {item.icon && (
                          <item.icon
                            className="text-sidebar-foreground/50 group-data-[active=true]/menu-button:text-sidebar-foreground"
                            size={22}
                            aria-hidden="true"
                          />
                        )}
                        <span>{item.title}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        )}

        {/* Admin Section - Apenas para administradores */}
        {isManagement && (
          <SidebarGroup>
            <SidebarGroupLabel className="uppercase text-sidebar-foreground/50">
              Administração
            </SidebarGroupLabel>
            <SidebarGroupContent className="px-2">
              <SidebarMenu>
                <SidebarMenuItem>
                  <SidebarMenuButton
                    asChild
                    className="group/menu-button font-medium gap-3 h-9 rounded-md data-[active=true]:hover:bg-transparent data-[active=true]:bg-gradient-to-b data-[active=true]:from-sidebar-primary data-[active=true]:to-sidebar-primary/70 data-[active=true]:shadow-[0_1px_2px_0_rgb(0_0_0/.05),inset_0_1px_0_0_rgb(255_255_255/.12)] [&>svg]:size-auto"
                  >
                    <a href="/admin/users">
                      <RiUserSettingsLine
                        className="text-sidebar-foreground/50 group-data-[active=true]/menu-button:text-sidebar-foreground"
                        size={22}
                        aria-hidden="true"
                      />
                      <span>Gerenciar Usuários</span>
                    </a>
                  </SidebarMenuButton>
                </SidebarMenuItem>
                {isAdmin && (
                  <SidebarMenuItem>
                    <SidebarMenuButton
                      asChild
                      className="group/menu-button font-medium gap-3 h-9 rounded-md data-[active=true]:hover:bg-transparent data-[active=true]:bg-gradient-to-b data-[active=true]:from-sidebar-primary data-[active=true]:to-sidebar-primary/70 data-[active=true]:shadow-[0_1px_2px_0_rgb(0_0_0/.05),inset_0_1px_0_0_rgb(255_255_255/.12)] [&>svg]:size-auto"
                    >
                      <a href="/admin/auditoria">
                        <RiShieldCheckLine
                          className="text-sidebar-foreground/50 group-data-[active=true]/menu-button:text-sidebar-foreground"
                          size={22}
                          aria-hidden="true"
                        />
                        <span>Auditoria</span>
                      </a>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                )}
                {isAdmin && (
                  <SidebarMenuItem>
                    <SidebarMenuButton
                      asChild
                      className="group/menu-button font-medium gap-3 h-9 rounded-md data-[active=true]:hover:bg-transparent data-[active=true]:bg-gradient-to-b data-[active=true]:from-sidebar-primary data-[active=true]:to-sidebar-primary/70 data-[active=true]:shadow-[0_1px_2px_0_rgb(0_0_0/.05),inset_0_1px_0_0_rgb(255_255_255/.12)] [&>svg]:size-auto"
                    >
                      <a href="/admin/validacoes">
                        <RiFileSearchLine
                          className="text-sidebar-foreground/50 group-data-[active=true]/menu-button:text-sidebar-foreground"
                          size={22}
                          aria-hidden="true"
                        />
                        <span>Revisões</span>
                      </a>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                )}
                <SidebarMenuItem>
                  <SidebarMenuButton
                    asChild
                    className="group/menu-button font-medium gap-3 h-9 rounded-md data-[active=true]:hover:bg-transparent data-[active=true]:bg-gradient-to-b data-[active=true]:from-sidebar-primary data-[active=true]:to-sidebar-primary/70 data-[active=true]:shadow-[0_1px_2px_0_rgb(0_0_0/.05),inset_0_1px_0_0_rgb(255_255_255/.12)] [&>svg]:size-auto"
                  >
                    <a href="/admin/clinics">
                      <RiHospitalLine
                        className="text-sidebar-foreground/50 group-data-[active=true]/menu-button:text-sidebar-foreground"
                        size={22}
                        aria-hidden="true"
                      />
                      <span>Gerenciar Clínicas</span>
                    </a>
                  </SidebarMenuButton>
                </SidebarMenuItem>
                <SidebarMenuItem>
                  <SidebarMenuButton
                    asChild
                    className="group/menu-button font-medium gap-3 h-9 rounded-md data-[active=true]:hover:bg-transparent data-[active=true]:bg-gradient-to-b data-[active=true]:from-sidebar-primary data-[active=true]:to-sidebar-primary/70 data-[active=true]:shadow-[0_1px_2px_0_rgb(0_0_0/.05),inset_0_1px_0_0_rgb(255_255_255/.12)] [&>svg]:size-auto"
                  >
                    <a href="/admin/exames">
                      <RiTestTubeLine
                        className="text-sidebar-foreground/50 group-data-[active=true]/menu-button:text-sidebar-foreground"
                        size={22}
                        aria-hidden="true"
                      />
                      <span>Catálogo de Exames</span>
                    </a>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        )}
      </SidebarContent>
      <SidebarFooter className="p-4">
        <div className="space-y-2">
          <TourGuiado />
          <CentroAjudaDialog />
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}
