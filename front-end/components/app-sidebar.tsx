'use client'

import * as React from "react";
import Image from "next/image";
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
        },
        {
          title: "Pendentes",
          url: "/pendentes",
          icon: RiHistoryLine,
        },
        {
          title: "Checagem",
          url: "/checagem",
          icon: RiCheckDoubleLine,
        },
      ],
    },
  ],
};

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const { isAdmin } = usePermissions();

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
        <SidebarGroup>
          <SidebarGroupLabel className="uppercase text-sidebar-foreground/50">
            {data.navMain[0]?.title}
          </SidebarGroupLabel>
          <SidebarGroupContent className="px-2">
            <SidebarMenu>
              {data.navMain[0]?.items.map((item) => (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton
                    asChild
                    className="group/menu-button font-medium gap-3 h-9 rounded-md data-[active=true]:hover:bg-transparent data-[active=true]:bg-gradient-to-b data-[active=true]:from-sidebar-primary data-[active=true]:to-sidebar-primary/70 data-[active=true]:shadow-[0_1px_2px_0_rgb(0_0_0/.05),inset_0_1px_0_0_rgb(255_255_255/.12)] [&>svg]:size-auto"
                    isActive={item.isActive}
                  >
                    <a
                      href={item.url}
                      data-tour={item.title.toLowerCase()}
                    >
                      {item.icon && (
                        <item.icon
                          className="text-sidebar-foreground/50 group-data-[active=true]/menu-button:text-sidebar-foreground"
                          size={22}
                          aria-hidden="true"
                        />
                      )}
                      <span>{item.title}</span>
                    </a>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {/* Admin Section - Apenas para administradores */}
        {isAdmin && (
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
