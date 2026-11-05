"use client"

import { useEffect, useState } from "react"
import { HistoryIcon } from "lucide-react"

import { cn } from "@/lib/utils"
import { buscarEnvios, dataCurta } from "@/lib/reenvio"
import type { EnvioDoColaborador } from "@/types/process"

const PAPEL: Record<EnvioDoColaborador["papel"], string> = {
  este: "Este envio",
  original: "Original",
  reenvio: "Reenvio",
  complemento: "Complemento",
  outro_envio: "Outro envio",
}

function situacao(envio: EnvioDoColaborador): string {
  if (envio.validation_status === "reenvio") return "não foi para a revisão"
  if (!envio.revisado) return "aguardando revisão"
  return envio.validation_status === "rejected" ? "rejeitado" : "aprovado"
}

function ListaDeEnvios({ envios }: { envios: EnvioDoColaborador[] }) {
  return (
    <ul className="mt-2 space-y-1">
      {envios.map((envio) => (
        <li
          key={envio.documento_id}
          className={cn("flex flex-wrap items-baseline gap-x-2 text-xs", envio.papel === "este" && "font-medium")}
        >
          <span className="w-[4.5rem] shrink-0 tabular-nums">{dataCurta(envio.enviado_em)}</span>
          <span className="shrink-0">{PAPEL[envio.papel] ?? PAPEL.outro_envio}</span>
          <span className="shrink-0 opacity-80">· {situacao(envio)}</span>
          <span className="min-w-0 flex-1 truncate opacity-70" title={envio.filename}>
            {envio.filename}
          </span>
        </li>
      ))}
    </ul>
  )
}

function useEnvios(documentId: string): EnvioDoColaborador[] | null {
  const [envios, setEnvios] = useState<EnvioDoColaborador[] | null>(null)
  useEffect(() => {
    let ativo = true
    setEnvios(null)
    buscarEnvios(documentId)
      .then((lista) => ativo && setEnvios(lista))
      // Histórico é apoio: sem ele o detalhe segue igual.
      .catch(() => ativo && setEnvios([]))
    return () => {
      ativo = false
    }
  }, [documentId])
  return envios
}

/**
 * Os outros envios do mesmo colaborador — o original, os reenvios, os
 * complementos e os outros envios do mesmo pedido do BRNET ou do mesmo CPF —
 * para o revisor, na Checagem: uma linha discreta que abre a lista só se ele
 * quiser. Some quando o documento é o único envio.
 */
export function EnviosDoColaborador({ documentId }: { documentId: string }) {
  const envios = useEnvios(documentId)
  const outros = (envios ?? []).filter((envio) => envio.papel !== "este").length
  if (!envios || outros === 0) return null
  return (
    <details className="text-xs text-muted-foreground">
      <summary className="inline-flex cursor-pointer items-center gap-1.5 hover:text-foreground">
        <HistoryIcon className="size-3.5" />
        {outros === 1 ? "1 outro envio deste colaborador" : `${outros} outros envios deste colaborador`}
      </summary>
      <ListaDeEnvios envios={envios} />
    </details>
  )
}
