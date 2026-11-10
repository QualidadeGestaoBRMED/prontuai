"use client"

import { FlaskConical } from "lucide-react"

import { RequireRole } from "@/components/require-role"
import { CardPedidosGuardados } from "@/components/staging/card-pedidos-guardados"

/**
 * Tela das ferramentas só de staging (`/admin/staging`). Ferramenta nova entra
 * aqui como mais um card, com o código em `components/staging/` e, no back-end,
 * em `app/staging/`.
 */
export function PainelFerramentasDeStaging() {
  return (
    <RequireRole allowedRoles={["ADMIN"]}>
      <main className="min-h-screen bg-slate-950 px-4 py-10 text-slate-50">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
          <div>
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-sky-400/30 bg-sky-400/10 px-3 py-1 text-sm text-sky-200">
              <FlaskConical className="size-4" aria-hidden="true" />
              Só em staging
            </div>
            <h1 className="text-3xl font-bold tracking-tight">Ferramentas de staging</h1>
            <p className="mt-2 max-w-2xl text-slate-400">
              Apoio a testes. Nada daqui existe em produção: lá esta página e as rotas dela respondem 404.
            </p>
          </div>

          <CardPedidosGuardados />
        </div>
      </main>
    </RequireRole>
  )
}
