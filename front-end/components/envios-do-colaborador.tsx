"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { AlertTriangleIcon, ExternalLinkIcon, HistoryIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { avisoDeReenvio, buscarEnvios, dataCurta, linkNoHistorico, orientacaoDoReenvio } from "@/lib/reenvio"
import type { EnvioDoColaborador, ReenvioLiberado } from "@/types/process"

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

/** Os envios ligados ao documento; null enquanto carrega. Sem `documentId`, não busca. */
export function useEnvios(documentId: string | null): EnvioDoColaborador[] | null {
  const [envios, setEnvios] = useState<EnvioDoColaborador[] | null>(null)
  useEffect(() => {
    let ativo = true
    setEnvios(null)
    if (!documentId) return
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
 * Aviso interno do revisor, na "Análise de Validação" da Checagem, quando o
 * documento é reenvio de um prontuário já liberado ou em revisão
 * (`result.reenvio`): quem revisou o original e quando, que correção ou
 * identificação errada segue o procedimento normal, e o link do original.
 * Discreto, no tom do texto da análise (pedido de 06/11/2026: o quadro em
 * destaque no topo chamava atenção demais). Só a Checagem o usa — a clínica vê
 * a tag, sem nome de revisor (a rota de envios nem o manda para ela).
 */
export function AvisoDeReenvio({ documentId, reenvio }: { documentId: string; reenvio?: ReenvioLiberado | null }) {
  const envios = useEnvios(reenvio ? documentId : null)
  if (!reenvio) return null
  // Enquanto a lista carrega, o aviso sai com o que a detecção gravou.
  const original = envios?.find((envio) => envio.documento_id === reenvio.documento_id) ?? null
  const { titulo, detalhe } = avisoDeReenvio(reenvio, original, "revisor")
  return (
    // Mesmo desenho da linha "N outros envios deste colaborador" logo abaixo:
    // ícone numa coluna própria, 6px até o texto, e a quebra alinhada pelo texto.
    // O destaque é só o triângulo âmbar — o mesmo alerta do "Dados de outra
    // pessoa" —, com o texto no tom da análise e sem caixa colorida.
    <div role="note" className="mt-2 flex items-start gap-1.5 text-sm text-muted-foreground leading-relaxed">
      <AlertTriangleIcon className="mt-[0.3rem] size-3.5 shrink-0 text-amber-600" />
      <p>
        {titulo}
        {detalhe ? ` ${detalhe}` : ""} {orientacaoDoReenvio("revisor")}{" "}
        <Link
          href={linkNoHistorico(reenvio.documento_id)}
          target="_blank"
          rel="noopener"
          className="inline-flex items-center gap-0.5 underline underline-offset-2 hover:text-foreground"
        >
          Ver o envio anterior
          <ExternalLinkIcon className="size-3" />
        </Link>
      </p>
    </div>
  )
}

/**
 * O texto do aviso de reenvio e o botão que abre o documento original no
 * Histórico. O mesmo para o revisor (aviso no detalhe da Checagem) e para a
 * clínica (ao clicar na tag), mudando o texto (`avisoDeReenvio`). O revisor abre
 * o original em outra aba, para não perder a revisão em andamento.
 */
export function ConteudoDoAvisoDeReenvio({
  reenvio,
  envios,
  para,
}: {
  reenvio: ReenvioLiberado
  envios: EnvioDoColaborador[] | null
  para: "revisor" | "clinica"
}) {
  // Enquanto a lista carrega, o aviso sai com o que a detecção gravou.
  const original = envios?.find((envio) => envio.documento_id === reenvio.documento_id) ?? null
  const { titulo, detalhe } = avisoDeReenvio(reenvio, original, para)
  return (
    <div className="space-y-2">
      <p>
        <span className="font-medium">{titulo}</span>
        {detalhe ? ` ${detalhe}` : ""}
      </p>
      <p className="opacity-90">{orientacaoDoReenvio(para)}</p>
      <Button asChild size="sm" variant="outline" className="h-7 gap-1.5 bg-white text-xs">
        <Link
          href={linkNoHistorico(reenvio.documento_id)}
          target={para === "revisor" ? "_blank" : undefined}
          rel={para === "revisor" ? "noopener" : undefined}
        >
          <ExternalLinkIcon className="size-3.5" />
          Ver o envio anterior no Histórico
        </Link>
      </Button>
    </div>
  )
}

/**
 * Os outros envios do mesmo colaborador — o original, os reenvios, os
 * complementos e os outros envios do mesmo pedido do BRNET ou do mesmo CPF —
 * para o revisor, na Checagem, e para a clínica, no detalhe do Histórico, de
 * Pendentes e do Anexar (a rota só devolve a ela os envios da própria clínica):
 * uma linha discreta que abre a lista só se quiser. Some quando o documento é o
 * único envio.
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
