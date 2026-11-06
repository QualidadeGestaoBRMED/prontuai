"use client"

import { useState } from "react"
import { InfoIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { ConteudoDoAvisoDeReenvio, useEnvios } from "@/components/envios-do-colaborador"
import { cn } from "@/lib/utils"
import { CLASSE_TAG_REENVIO, explicacaoReenvioParaRevisor, rotuloReenvio } from "@/lib/reenvio"
import type { ReenvioLiberado } from "@/types/process"

/**
 * Tag do reenvio de prontuário já liberado ou em revisão.
 *
 * - Revisor (Checagem): "Já liberado"/"Já em revisão" ao lado do status; o
 *   aviso completo, com quem revisou, fica no topo do detalhe (`AvisoDeReenvio`).
 * - Clínica (Anexar, Pendentes, Histórico): "Já revisado"/"Já em revisão" NO
 *   LUGAR do status (pedido de 06/11/2026: status e tag juntos confundiam). A
 *   tag é um botão: abre o aviso, sem identificar o revisor, com o link do envio
 *   anterior no Histórico. A lista de envios só é buscada ao abrir.
 */
export function TagReenvio({
  reenvio,
  para = "revisor",
  className,
}: {
  reenvio?: ReenvioLiberado | null
  para?: "revisor" | "clinica"
  className?: string
}) {
  if (!reenvio) return null
  if (para === "clinica") return <TagReenvioDaClinica reenvio={reenvio} className={className} />
  return (
    <Badge
      variant="outline"
      className={cn("shrink-0", CLASSE_TAG_REENVIO, className)}
      title={explicacaoReenvioParaRevisor(reenvio)}
    >
      {rotuloReenvio(reenvio)}
    </Badge>
  )
}

function TagReenvioDaClinica({ reenvio, className }: { reenvio: ReenvioLiberado; className?: string }) {
  const [aberto, setAberto] = useState(false)
  // O documento original lista os envios ligados a ele, inclusive ele mesmo.
  const envios = useEnvios(aberto ? reenvio.documento_id : null)
  return (
    <Popover open={aberto} onOpenChange={setAberto}>
      <PopoverTrigger asChild>
        <button
          type="button"
          // A linha da tabela abre o detalhe ao clicar; a tag só abre o aviso.
          onClick={(evento) => evento.stopPropagation()}
          className="rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400"
        >
          <Badge variant="outline" className={cn("shrink-0 cursor-pointer gap-1", CLASSE_TAG_REENVIO, className)}>
            {rotuloReenvio(reenvio, "clinica")}
            <InfoIcon className="size-3" />
          </Badge>
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="w-80 text-sm"
        // O conteúdo sai num portal, mas o clique ainda sobe pela árvore do React até a linha.
        onClick={(evento) => evento.stopPropagation()}
      >
        <ConteudoDoAvisoDeReenvio reenvio={reenvio} envios={envios} para="clinica" />
      </PopoverContent>
    </Popover>
  )
}
