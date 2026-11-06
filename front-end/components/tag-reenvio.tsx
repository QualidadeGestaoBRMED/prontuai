import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { CLASSE_TAG_REENVIO, explicacaoReenvioParaRevisor, mensagemReenvio, rotuloReenvio } from "@/lib/reenvio"
import type { ReenvioLiberado } from "@/types/process"

/**
 * Tag "Já liberado" / "Já em revisão" ao lado do status. O reenvio entra na
 * Checagem como qualquer envio (nov/2026); a tag é o que avisa que o mesmo
 * prontuário já passou por ali — ao revisor, na Checagem, e à clínica, no
 * Histórico, em Pendentes e no Anexar. Muda só a explicação ao passar o mouse:
 * o revisor é orientado a comparar com o envio anterior; a clínica, a não
 * reenviar.
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
  return (
    <Badge
      variant="outline"
      className={cn("shrink-0", CLASSE_TAG_REENVIO, className)}
      title={para === "clinica" ? mensagemReenvio(reenvio) : explicacaoReenvioParaRevisor(reenvio)}
    >
      {rotuloReenvio(reenvio)}
    </Badge>
  )
}
