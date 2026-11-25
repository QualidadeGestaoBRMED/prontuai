"use client"

import { useMemo, useState } from "react"
import { AppSidebar } from "@/components/app-sidebar"
import { NotificationBell } from "@/components/notification-bell"
import { NotificationCenter } from "@/components/notification-center"
import { RequireRole } from "@/components/require-role"
import { paraDocumentoAprovado } from "@/components/tela-medico/documento-medico"
import { ListaAnalises } from "@/components/tela-medico/lista-analises"
import { ModalRevisaoAso } from "@/components/tela-medico/modal-revisao-aso"
import type { DocumentoAprovado, SituacaoAso } from "@/components/tela-medico/tipos"
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar"
import UserDropdown from "@/components/user-dropdown"
import { useClinicOptions } from "@/hooks/use-clinic-options"
import { useDocumentsPaged } from "@/hooks/use-documents-paged"
import { useNotifications } from "@/hooks/use-notifications"

/**
 * Tela do médico: a lista dos documentos que um revisor aprovou na Checagem
 * (fila `medico`) e, ao clicar, a Revisão do ASO em modal, como na Checagem. O
 * fluxo é clínica envia → revisor aprova → médico decide; rejeitado e o
 * aprovado só pela IA não chegam aqui. A normalidade é a leitura que já existe;
 * a sugestão de conduta ainda não (a API não existe), e a decisão fica só na
 * memória da página. Só ADMIN e MANAGER, até haver um cargo de médico.
 */
export default function Page() {
  const { unreadCount, activeProcess, setNotificationCenterOpen } = useNotifications()
  const [selecionada, setSelecionada] = useState<DocumentoAprovado | null>(null)
  const [decisoes, setDecisoes] = useState<Record<string, SituacaoAso>>({})
  const fila = useDocumentsPaged({ queue: "medico", pageSize: 10 })
  const clinicas = useClinicOptions()
  const documentos = useMemo(() => fila.documents.map(paraDocumentoAprovado), [fila.documents])

  return (
    <RequireRole allowedRoles={["ADMIN", "MANAGER"]}>
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset className="bg-sidebar group/sidebar-inset min-w-0">
          <header className="flex h-16 shrink-0 items-center gap-2 px-4 md:px-6 lg:px-8 bg-sidebar text-sidebar-foreground relative before:absolute before:inset-y-3 before:-left-px before:w-px before:bg-gradient-to-b before:from-white/5 before:via-white/15 before:to-white/5 before:z-50">
            <SidebarTrigger className="-ms-2 text-sidebar-foreground hover:text-sidebar-foreground/70" />
            <h1 className="text-lg font-semibold">Conduta Médica</h1>
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
              <ListaAnalises
                documentos={documentos}
                carregando={fila.loading}
                erro={fila.error}
                decisoes={decisoes}
                onAbrir={setSelecionada}
                onBuscar={fila.setSearch}
                data={{ value: fila.dataFilter, onChange: fila.setDataFilter }}
                clinica={{
                  value: fila.clinicFilter,
                  onChange: fila.setClinicFilter,
                  options: clinicas.options,
                  loading: clinicas.loading,
                  enabled: clinicas.enabled,
                }}
                paginacao={{ page: fila.page, totalPages: fila.totalPages, onPageChange: fila.setPage }}
              />
            </div>
          </div>
        </SidebarInset>
        <NotificationCenter />
      </SidebarProvider>

      <ModalRevisaoAso
        documento={selecionada}
        onOpenChange={(open) => {
          if (!open) setSelecionada(null)
        }}
        decisaoRegistrada={selecionada ? decisoes[selecionada.documento_id] : null}
        onRegistrar={(decisao) => {
          const id = selecionada?.documento_id
          const conduta = decisao.conduta_final.situacao_aso
          if (id && conduta) setDecisoes((d) => ({ ...d, [id]: conduta }))
        }}
      />
    </RequireRole>
  )
}
