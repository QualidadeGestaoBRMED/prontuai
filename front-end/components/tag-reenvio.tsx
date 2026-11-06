import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { CLASSE_TAG_REENVIO, explicacaoReenvioParaRevisor, rotuloReenvio } from "@/lib/reenvio"
import type { ReenvioLiberado } from "@/types/process"

/**
 * Tag "Já liberado" / "Já em revisão" do revisor, na lista e no modal da
 * Checagem. O reenvio entra na fila como qualquer envio (nov/2026); a tag é o
 * que avisa que o mesmo prontuário já passou por ali.
 */
export function TagReenvio({ reenvio, className }: { reenvio?: ReenvioLiberado | null; className?: string }) {
  if (!reenvio) return null
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
