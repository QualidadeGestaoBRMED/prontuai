import { notFound } from "next/navigation"

import { PainelFerramentasDeStaging } from "@/components/staging/painel-ferramentas-de-staging"
import { ferramentasDeStagingAtivas } from "@/lib/staging"

// A variável é lida a cada acesso, e não congelada no build.
export const dynamic = "force-dynamic"

/**
 * Ferramentas só de staging. Fora de staging não existe: 404, igual a uma rota
 * que nunca foi criada. O middleware já barra antes; isto é a segunda barreira.
 */
export default function FerramentasDeStagingPage() {
  if (!ferramentasDeStagingAtivas()) notFound()
  return <PainelFerramentasDeStaging />
}
