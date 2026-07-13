"use client"

import { useMemo, useState } from "react"
import { Check, ChevronsUpDown, Search, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { cn } from "@/lib/utils"
import type { ClinicOption } from "@/hooks/use-clinic-options"

type ClinicFilterProps = {
  value: string
  onChange: (value: string) => void
  options: ClinicOption[]
  loading?: boolean
  label?: string
  className?: string
  showActiveChip?: boolean
}

const ALL_CLINICS = "all"

function normalize(value: string) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
}

export function ClinicFilter({
  value,
  onChange,
  options,
  loading = false,
  label = "Clínica",
  className,
  showActiveChip = false,
}: ClinicFilterProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const selected = options.find((option) => option.id === value)
  const selectedLabel = selected?.name || "Todas as clínicas"
  const filteredOptions = useMemo(() => {
    const term = normalize(query.trim())
    if (!term) return options
    return options.filter((option) => normalize(option.name).includes(term))
  }, [options, query])

  const selectClinic = (nextValue: string) => {
    onChange(nextValue)
    setOpen(false)
    setQuery("")
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
              role="combobox"
              aria-expanded={open}
              disabled={loading}
              className="w-full justify-between gap-2 px-3 font-normal"
            >
              <span className="truncate">{loading ? "Carregando..." : selectedLabel}</span>
              <ChevronsUpDown className="size-4 shrink-0 opacity-50" />
            </Button>
          </PopoverTrigger>
          <PopoverContent align="start" className="w-72 p-0">
            <div className="border-b p-2">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Buscar clínica"
                  className="h-9 pl-9"
                />
              </div>
            </div>
            <div className="max-h-64 overflow-auto p-1">
              <button
                type="button"
                className={cn(
                  "flex w-full items-center gap-2 rounded-sm px-2 py-2 text-left text-sm hover:bg-accent hover:text-accent-foreground",
                  value === ALL_CLINICS && "bg-accent/10 text-accent-foreground",
                )}
                onClick={() => selectClinic(ALL_CLINICS)}
              >
                <Check className={cn("size-4", value === ALL_CLINICS ? "opacity-100" : "opacity-0")} />
                <span>Todas as clínicas</span>
              </button>
              {filteredOptions.length === 0 ? (
                <div className="px-3 py-6 text-center text-sm text-muted-foreground">Nenhuma clínica encontrada.</div>
              ) : (
                filteredOptions.map((option) => (
                  <button
                    key={option.id}
                    type="button"
                    className={cn(
                      "flex w-full items-center gap-2 rounded-sm px-2 py-2 text-left text-sm hover:bg-accent hover:text-accent-foreground",
                      value === option.id && "bg-accent/10 text-accent-foreground",
                    )}
                    onClick={() => selectClinic(option.id)}
                  >
                    <Check className={cn("size-4", value === option.id ? "opacity-100" : "opacity-0")} />
                    <span className="truncate">{option.name}</span>
                  </button>
                ))
              )}
            </div>
          </PopoverContent>
        </Popover>
      </div>
      {showActiveChip && selected ? (
        <Button
          type="button"
          variant="secondary"
          size="sm"
          className="mb-0.5 gap-1 rounded-full"
          onClick={() => onChange(ALL_CLINICS)}
        >
          <span className="max-w-48 truncate">{selected.name}</span>
          <X className="size-3.5" />
        </Button>
      ) : null}
    </div>
  )
}
