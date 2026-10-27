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
import type { CampoData, FiltroData, PeriodoDias } from "@/hooks/use-documents-paged"

type DateFilterProps = {
  value: FiltroData
  onChange: (value: FiltroData) => void
  className?: string
}

type Atalho = { label: string; periodo: () => PeriodoDias }

const pad = (n: number) => String(n).padStart(2, "0")

/** Dia do calendário LOCAL, não o de UTC: `toISOString` viraria o dia às 21h. */
function diaLocal(data: Date): string {
  return `${data.getFullYear()}-${pad(data.getMonth() + 1)}-${pad(data.getDate())}`
}

function paraData(dia: string): Date {
  const [y, m, d] = dia.split("-").map(Number)
  return new Date(y, m - 1, d)
}

/** O dia de hoje deslocado em `dias` (negativo é passado). */
function diaRelativo(dias: number): string {
  const hoje = new Date()
  return diaLocal(new Date(hoje.getFullYear(), hoje.getMonth(), hoje.getDate() + dias))
}

function rotuloPeriodo(periodo: PeriodoDias): string {
  const br = (dia: string) => dia.split("-").reverse().join("/")
  if (!periodo.from) return periodo.to ? `até ${br(periodo.to)}` : ""
  if (!periodo.to) return `a partir de ${br(periodo.from)}`
  const [ya, ma, da] = periodo.from.split("-")
  const [yb, mb, db] = periodo.to.split("-")
  if (periodo.from === periodo.to) return `${da}/${ma}/${ya}`
  // O ano só uma vez quando as duas pontas são do mesmo ano.
  return ya === yb ? `${da}/${ma} a ${db}/${mb}/${yb}` : `${da}/${ma}/${ya} a ${db}/${mb}/${yb}`
}

/**
 * As duas datas do documento que dão para recortar a lista. Um campo só, e não
 * dois lado a lado: são o mesmo gesto ("mostre os de tal período") sobre datas
 * diferentes, e dois calendários na barra pareciam filtros independentes.
 *
 * Os atalhos cobrem a pergunta de todo dia sem abrir o calendário, e são
 * calculados no clique, para "hoje" não ficar preso ao dia em que a tela foi
 * carregada.
 */
const CAMPOS: Record<CampoData, { nome: string; curto: string; atalhos: Atalho[]; ateHoje: boolean }> = {
  // "O que chegou ontem?" Não há envio no futuro: o calendário trava esses dias.
  envio: {
    nome: "Envio",
    curto: "Envio",
    ateHoje: true,
    atalhos: [
      { label: "Hoje", periodo: () => ({ from: diaRelativo(0), to: diaRelativo(0) }) },
      { label: "Ontem", periodo: () => ({ from: diaRelativo(-1), to: diaRelativo(-1) }) },
      { label: "Últimos 7 dias", periodo: () => ({ from: diaRelativo(-6), to: diaRelativo(0) }) },
      { label: "Últimos 30 dias", periodo: () => ({ from: diaRelativo(-29), to: diaRelativo(0) }) },
    ],
  },
  // "O que vence quando?" Os nomes repetem as marcas da coluna "Prev.
  // liberação" (Atrasado, Hoje, D-1...), para filtro e coluna falarem igual.
  previsao: {
    nome: "Previsão de liberação",
    curto: "Previsão",
    ateHoje: false,
    atalhos: [
      { label: "Atrasados", periodo: () => ({ to: diaRelativo(-1) }) },
      { label: "Hoje", periodo: () => ({ from: diaRelativo(0), to: diaRelativo(0) }) },
      { label: "Amanhã", periodo: () => ({ from: diaRelativo(1), to: diaRelativo(1) }) },
      { label: "Próximos 7 dias", periodo: () => ({ from: diaRelativo(0), to: diaRelativo(6) }) },
    ],
  },
}

const ORDEM_CAMPOS: CampoData[] = ["envio", "previsao"]

function rotulo(filtro: NonNullable<FiltroData>): string {
  return `${CAMPOS[filtro.campo].curto}: ${rotuloPeriodo(filtro.periodo)}`
}

export function DateFilter({ value, onChange, className }: DateFilterProps) {
  const [open, setOpen] = useState(false)
  // Qual data o calendário está escolhendo. Trocar não filtra nada: só muda os
  // atalhos e o calendário, e o filtro vale no próximo clique — senão a lista
  // mudaria duas vezes até o revisor chegar ao período que queria.
  const [campo, setCampo] = useState<CampoData>(value?.campo ?? "envio")
  const config = CAMPOS[campo]
  const periodo = value?.campo === campo ? value.periodo : null

  // Período aberto ("atrasados" = só o fim) não tem como ser pintado num
  // calendário de intervalo: ele fica sem marcação e o rótulo diz o recorte.
  const selecionado: DateRange | undefined = periodo?.from
    ? { from: paraData(periodo.from), to: periodo.to ? paraData(periodo.to) : undefined }
    : undefined

  const aplicar = (novo: PeriodoDias | null) => onChange(novo ? { campo, periodo: novo } : null)

  /**
   * O calendário aplica a cada clique, sem botão de confirmar: o primeiro clique
   * já filtra aquele dia, o segundo estende até o outro. Com um intervalo de
   * vários dias já marcado (ou aberto, como "atrasados"), o clique seguinte
   * recomeça do dia clicado — o padrão do `react-day-picker` seria esticar o
   * intervalo existente, e quem clica num dia novo quer outro período, não um
   * maior.
   */
  const selecionar = (range: DateRange | undefined, clicado: Date) => {
    if (periodo && periodo.from !== periodo.to) {
      const dia = diaLocal(clicado)
      aplicar({ from: dia, to: dia })
      return
    }
    if (!range?.from) {
      aplicar(null)
      return
    }
    aplicar({ from: diaLocal(range.from), to: diaLocal(range.to ?? range.from) })
  }

  return (
    <div className={cn("flex flex-wrap items-end gap-2", className)}>
      <div className="w-full space-y-2 sm:w-64">
        <Label>Data</Label>
        <Popover
          open={open}
          onOpenChange={(aberto) => {
            // Abre na data que está filtrando, não na última que foi espiada.
            if (aberto && value) setCampo(value.campo)
            setOpen(aberto)
          }}
        >
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
          <PopoverContent align="start" className="w-auto p-0">
            <div className="flex gap-1 border-b p-2" role="group" aria-label="Filtrar pela data de">
              {ORDEM_CAMPOS.map((c) => (
                <button
                  key={c}
                  type="button"
                  aria-pressed={campo === c}
                  onClick={() => setCampo(c)}
                  className={cn(
                    "rounded-md px-3 py-1.5 text-sm transition-colors",
                    campo === c
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                  )}
                >
                  {CAMPOS[c].nome}
                </button>
              ))}
            </div>
            <div className="flex">
              <div className="flex w-36 flex-col gap-0.5 border-r p-2">
                {config.atalhos.map((atalho) => (
                  <button
                    key={atalho.label}
                    type="button"
                    className="rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
                    onClick={() => {
                      aplicar(atalho.periodo())
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
                // Remonta ao trocar de data: o mês exibido volta para o do
                // período daquela data, ou o atual.
                key={campo}
                mode="range"
                locale={ptBR}
                selected={selecionado}
                onSelect={selecionar}
                defaultMonth={selecionado?.to ?? (periodo?.to ? paraData(periodo.to) : new Date())}
                disabled={config.ateHoje ? { after: new Date() } : undefined}
              />
            </div>
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
          aria-label="Limpar filtro de data"
        >
          <span className="max-w-56 truncate">{rotulo(value)}</span>
          <X className="size-3.5" />
        </Button>
      ) : null}
    </div>
  )
}
