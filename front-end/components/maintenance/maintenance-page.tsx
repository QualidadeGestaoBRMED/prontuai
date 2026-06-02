"use client"

import { RefreshCw, Wrench } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import type { MaintenanceStatusResponse } from "@/types/maintenance"

type MaintenancePageProps = {
  maintenance: MaintenanceStatusResponse
}

export function MaintenancePage({ maintenance }: MaintenancePageProps) {
  return (
    <main className="min-h-screen flex items-center justify-center bg-slate-50 px-4 py-10 text-slate-950 dark:bg-slate-950 dark:text-slate-50">
      <Card className="w-full max-w-xl border-slate-200 bg-white/95 shadow-2xl shadow-slate-950/10 dark:border-slate-800 dark:bg-slate-900/95">
        <CardHeader className="text-center">
          <div className="mx-auto mb-4 flex size-14 items-center justify-center rounded-full bg-amber-100 text-amber-700 dark:bg-amber-400/10 dark:text-amber-300">
            <Wrench className="size-7" aria-hidden="true" />
          </div>
          <CardTitle className="text-3xl font-bold tracking-tight">Voltamos logo!</CardTitle>
          <CardDescription className="text-base">
            {maintenance.message || "Estamos realizando uma manutenção para melhorar sua experiência."}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm text-muted-foreground">
              <span>Manutenção em andamento</span>
              <span>Em progresso</span>
            </div>
            <Progress value={72} className="h-2 bg-slate-200 dark:bg-slate-800" indicatorClassName="bg-amber-500" />
          </div>

          {maintenance.eta && (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-center text-amber-950 dark:border-amber-400/20 dark:bg-amber-400/10 dark:text-amber-100">
              <p className="text-xs uppercase tracking-[0.2em] text-amber-700 dark:text-amber-300">
                Previsão
              </p>
              <p className="mt-1 text-lg font-semibold">{maintenance.eta}</p>
            </div>
          )}
        </CardContent>
        <CardFooter className="justify-center">
          <Button type="button" onClick={() => window.location.reload()} className="rounded-full">
            <RefreshCw className="size-4" aria-hidden="true" />
            Verificar novamente
          </Button>
        </CardFooter>
      </Card>
    </main>
  )
}
