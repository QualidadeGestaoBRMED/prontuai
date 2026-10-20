"use client"

import { useState } from "react"
import { ptBR } from "date-fns/locale"
import { CalendarDays, X } from "lucide-react"
import type { DateRange } from "react-day-picker"
import { Button } from "@/components/ui/button"
import { Calendar } from "@/components/ui/calendar"
import { Label } from "@/components/ui/label"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { cn } from "@/lib/utils"
import type { UploadDateFilter as Periodo } from "@/hooks/use-documents-paged"

type UploadDateFilterProps = {
  value: Periodo
  onChange: (value: Periodo) => void
  label?: string
  className?: string
}

const pad = (n: number) => String(n).padStart(2, "0")

/** Dia do calendário LOCAL, não o de UTC: `toISOString` viraria o dia às 21h. */
function diaLocal(data: Date): string {
  return `${data.getFullYear()}-${pad(data.getMonth() + 1)}-${pad(data.getDate())}`
}

function paraData(dia: string): Date {
  const [y, m, d] = dia.split("-").map(Number)
  return new Date(y, m - 1, d)
}

function diasAtras(dias: number): string {
  const hoje = new Date()
  return diaLocal(new Date(hoje.getFullYear(), hoje.getMonth(), hoje.getDate() - dias))
}

function rotulo(periodo: NonNullable<Periodo>): string {
  const [ya, ma, da] = periodo.from.split("-")
  const [yb, mb, db] = periodo.to.split("-")
  if (periodo.from === periodo.to) return `${da}/${ma}/${ya}`
  // O ano só uma vez quando as duas pontas são do mesmo ano.
  return ya === yb ? `${da}/${ma} a ${db}/${mb}/${yb}` : `${da}/${ma}/${ya} a ${db}/${mb}/${yb}`
}

// Os atalhos cobrem a pergunta de todo dia — "o que chegou ontem?" — sem abrir
// o calendário. Calculados no clique, para "hoje" não ficar preso ao dia em que
// a tela foi carregada.
const ATALHOS: { label: string; periodo: () => NonNullable<Periodo> }[] = [
  { label: "Hoje", periodo: () => ({ from: diasAtras(0), to: diasAtras(0) }) },
  { label: "Ontem", periodo: () => ({ from: diasAtras(1), to: diasAtras(1) }) },
  { label: "Últimos 7 dias", periodo: () => ({ from: diasAtras(6), to: diasAtras(0) }) },
  { label: "Últimos 30 dias", periodo: () => ({ from: diasAtras(29), to: diasAtras(0) }) },
]

export function UploadDateFilter({
  value,
  onChange,
  label = "Data de envio",
  className,
}: UploadDateFilterProps) {
  const [open, setOpen] = useState(false)
  const selecionado: DateRange | undefined = value
    ? { from: paraData(value.from), to: paraData(value.to) }
    : undefined

  /**
   * O calendário aplica a cada clique, sem botão de confirmar: o primeiro clique
   * já filtra aquele dia, o segundo estende até o outro. Com um intervalo de
   * vários dias já marcado, o clique seguinte recomeça do dia clicado — o
   * padrão do `react-day-picker` seria esticar o intervalo existente, e quem
   * clica num dia novo quer outro período, não um maior.
   */
  const selecionar = (range: DateRange | undefined, clicado: Date) => {
    if (value && value.from !== value.to) {
      const dia = diaLocal(clicado)
      onChange({ from: dia, to: dia })
      return
    }
    if (!range?.from) {
      onChange(null)
      return
    }
    onChange({ from: diaLocal(range.from), to: diaLocal(range.to ?? range.from) })
  }

  return (
    <div className={cn("flex flex-wrap items-end gap-2", className)}>
      <div className="w-full space-y-2 sm:w-56">
        <Label>{label}</Label>
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button
              type="button"
              variant="outline"
              aria-expanded={open}
              className="w-full justify-between gap-2 px-3 font-normal"
            >
              <span className="truncate">{value ? rotulo(value) : "Todas as datas"}</span>
              <CalendarDays className="size-4 shrink-0 opacity-50" />
            </Button>
          </PopoverTrigger>
          <PopoverContent align="start" className="flex w-auto p-0">
            <div className="flex w-36 flex-col gap-0.5 border-r p-2">
              {ATALHOS.map((atalho) => (
                <button
                  key={atalho.label}
                  type="button"
                  className="rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
                  onClick={() => {
                    onChange(atalho.periodo())
                    setOpen(false)
                  }}
                >
                  {atalho.label}
                </button>
              ))}
              {value ? (
                <button
                  type="button"
                  className="mt-auto rounded-sm px-2 py-1.5 text-left text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                  onClick={() => {
                    onChange(null)
                    setOpen(false)
                  }}
                >
                  Todas as datas
                </button>
              ) : null}
            </div>
            <Calendar
              mode="range"
              locale={ptBR}
              selected={selecionado}
              onSelect={selecionar}
              defaultMonth={selecionado?.to ?? new Date()}
              // Não há envio no futuro; deixar clicar só produziria lista vazia.
              disabled={{ after: new Date() }}
            />
          </PopoverContent>
        </Popover>
      </div>
      {value ? (
        <Button
          type="button"
          variant="secondary"
          size="sm"
          className="mb-0.5 gap-1 rounded-full"
          onClick={() => onChange(null)}
          aria-label="Limpar filtro de data de envio"
        >
          <span className="max-w-48 truncate">{rotulo(value)}</span>
          <X className="size-3.5" />
        </Button>
      ) : null}
    </div>
  )
}
