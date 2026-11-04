"use client"

import { useCallback, useRef, useState } from "react"
import { useSession } from "next-auth/react"
import { toast } from "sonner"
import { AppSidebar } from "@/components/app-sidebar"
import { DocumentBatchProcessor } from "@/components/document-batch-processor"
import { DocumentUploadZone } from "@/components/document-upload-zone"
import { NotificationBell } from "@/components/notification-bell"
import { NotificationCenter } from "@/components/notification-center"
import { PainelChecagem } from "@/components/painel-checagem"
import { RequireRole } from "@/components/require-role"
import { Button } from "@/components/ui/button"
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar"
import UserDropdown from "@/components/user-dropdown"
import type { FileWithPreview } from "@/hooks/use-file-upload"
import { useNotifications } from "@/hooks/use-notifications"

// Enquanto há envio em andamento a lista se atualiza sozinha, para o documento
// aparecer sem recarregar. Fora disso não há o que buscar: é o mesmo custo de
// polling que a Checagem evita (ver `hooks/use-visible-interval.ts`).
const ATUALIZACAO_DURANTE_ENVIO_MS = 7000

/**
 * Fluxo da filial: a mesma pessoa envia o documento e decide o resultado, sem
 * trocar de tela. Reaproveita o envio do Anexar Prontuário e o painel da
 * Checagem. Quais documentos aparecem e quais podem ser decididos é o back-end
 * que recorta, pelo cargo FILIAL (`garantir_decisao_no_documento`).
 */
export default function Page() {
  const { data: session } = useSession()
  const { unreadCount, activeProcess, processingDocuments, setNotificationCenterOpen, clearProcessingState } =
    useNotifications()
  const [arquivos, setArquivos] = useState<FileWithPreview[]>([])
  const travaEnvioRef = useRef(false)

  const emAndamento = processingDocuments.some((doc) => !doc.error && doc.stage !== "completed")
  const comErro = processingDocuments.some((doc) => doc.error)
  const processando = arquivos.length > 0 || emAndamento

  const enviar = (files: FileWithPreview[]) => {
    const devAuthBypass =
      process.env.NODE_ENV !== "production" && process.env.NEXT_PUBLIC_DEV_AUTH_BYPASS === "true"
    if (!session?.user?.email && !devAuthBypass) {
      toast.error("Sessão inválida. Faça login novamente para enviar documentos.")
      return
    }
    if (travaEnvioRef.current || processando) return
    travaEnvioRef.current = true
    // Sem limpar, o processador veria o envio anterior já concluído e daria este
    // por terminado antes de começar.
    clearProcessingState()
    setArquivos(files)
  }

  const aoConcluir = useCallback(() => {
    setArquivos([])
    travaEnvioRef.current = false
    window.dispatchEvent(new CustomEvent("documents:refresh"))
  }, [])

  const encerrar = () => {
    clearProcessingState()
    setArquivos([])
    travaEnvioRef.current = false
  }

  return (
    <RequireRole allowedRoles={["FILIAL", "ADMIN", "MANAGER"]}>
      <SidebarProvider>
        <AppSidebar />
        {/* `min-w-0`: sem ele, a tabela larga estica a página toda, e o botão da
            faixa de envio sai da tela no celular. Quem rola é a área de conteúdo. */}
        <SidebarInset className="bg-sidebar group/sidebar-inset min-w-0">
          <header className="flex h-16 shrink-0 items-center gap-2 px-4 md:px-6 lg:px-8 bg-sidebar text-sidebar-foreground relative before:absolute before:inset-y-3 before:-left-px before:w-px before:bg-gradient-to-b before:from-white/5 before:via-white/15 before:to-white/5 before:z-50">
            <SidebarTrigger className="-ms-2 text-sidebar-foreground hover:text-sidebar-foreground/70" />
            <h1 className="text-lg font-semibold">Envio e Checagem</h1>
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
            <div className="flex-1 min-h-0 flex flex-col gap-4 p-4 md:p-6 lg:p-8 overflow-auto">
              <section aria-label="Enviar documento" className="shrink-0 bg-white rounded-lg p-4 shadow-sm">
                {processando || comErro ? (
                  <div className="flex flex-wrap items-start gap-x-6 gap-y-3">
                    <div className="min-w-64 flex-1">
                      <DocumentBatchProcessor
                        files={arquivos}
                        onComplete={aoConcluir}
                        submittedBy={session?.user?.email || undefined}
                        compacto
                      />
                    </div>
                    <Button variant="outline" size="sm" onClick={encerrar} className="shrink-0">
                      {processando ? "Encerrar processo" : "Fechar e enviar outro"}
                    </Button>
                  </div>
                ) : (
                  <DocumentUploadZone onProcessFiles={enviar} compacta />
                )}
              </section>

              {/* A altura mínima mantém a lista usável com a área de envio aberta:
                  sem ela, a tabela é espremida e quem rola é a página. */}
              <section aria-label="Documentos enviados" className="flex-1 min-h-[640px] flex flex-col">
                <PainelChecagem atualizarACadaMs={processando ? ATUALIZACAO_DURANTE_ENVIO_MS : 0} />
              </section>
            </div>
          </div>
        </SidebarInset>
        <NotificationCenter />
      </SidebarProvider>
    </RequireRole>
  )
}
