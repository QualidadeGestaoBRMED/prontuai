"use client"

import { useState } from "react"
import { CheckIcon, LinkIcon } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { linkDoDocumento } from "@/hooks/use-documento-do-link"
import { cn } from "@/lib/utils"

/**
 * Copia o link que abre este documento na tela atual (`?viewId=`). Quem abre o
 * link cai no mesmo modal, na mesma tela: Pendentes, Checagem, Histórico ou
 * Conduta Médica (ver `useDocumentoDoLink`).
 */
export function BotaoCopiarLink({ documentoId, className }: { documentoId: string; className?: string }) {
  const { copiado, copiar } = useCopiarLink(documentoId)
  return (
    <Button
      type="button"
      variant="outline"
      size="icon"
      onClick={copiar}
      className={cn("size-8", className)}
      aria-label="Copiar link do documento"
      title={copiado ? "Link copiado" : "Copiar link do documento"}
    >
      {copiado ? <CheckIcon className="size-4" /> : <LinkIcon className="size-4" />}
    </Button>
  )
}

/** A ação do botão, para telas com botão de outro visual (a Revisão do ASO). */
export function useCopiarLink(documentoId: string) {
  const [copiado, setCopiado] = useState(false)

  const copiar = async () => {
    const link = linkDoDocumento(documentoId)
    try {
      await navigator.clipboard.writeText(link)
      setCopiado(true)
      window.setTimeout(() => setCopiado(false), 2000)
      toast.success("Link do documento copiado.")
    } catch {
      // Sem permissão de área de transferência (HTTP sem TLS, navegador antigo):
      // o link aparece para copiar à mão.
      toast.info(link, { duration: 15000, description: "Copie o link acima." })
    }
  }

  return { copiado, copiar }
}
