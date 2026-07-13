"use client"

import { useEffect, useState } from "react"
import { format } from "date-fns"
import { ptBR } from "date-fns/locale"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { ProcessResult } from "@/types/process"
import { Download, Eye, Search, FileDown } from "lucide-react"
import { cn } from "@/lib/utils"
import { ClinicFilter } from "@/components/clinic-filter"
import type { ClinicOption } from "@/hooks/use-clinic-options"

type StatusFilter = "all" | "approved" | "rejected" | "pending_review"

interface ResultsTableProps {
  results: ProcessResult[]
  onViewDetails?: (result: ProcessResult) => void
  onDownloadPDF?: (result: ProcessResult) => void
  initialSearch?: string
  serverMode?: boolean
  searchQuery?: string
  onSearchQueryChange?: (value: string) => void
  statusFilter?: StatusFilter
  onStatusFilterChange?: (value: StatusFilter) => void
  clinicFilter?: string
  onClinicFilterChange?: (value: string) => void
  clinicOptions?: ClinicOption[]
  clinicOptionsLoading?: boolean
  showClinicFilter?: boolean
  currentPage?: number
  totalPages?: number
  totalItems?: number
  pageSize?: number
  onPageChange?: (page: number) => void
  className?: string
}

const exportToCSV = (results: ProcessResult[]) => {
  const headers = ["CPF", "Paciente", "Clínica", "Data Upload", "Status", "Exames Faltantes", "Enviado Por"]
  const rows = results.map((r) => [
    r.cpf,
    r.patientName,
    r.clinicName || "",
    format(r.uploadedAt, "dd/MM/yyyy HH:mm", { locale: ptBR }),
    r.status === "approved" ? "Aprovado" : r.status === "rejected" ? "Rejeitado" : "Pendente",
    r.examesFaltantes.toString(),
    r.submittedBy,
  ])
  const csvContent = [headers.join(","), ...rows.map((row) => row.map((cell) => `"${cell}"`).join(","))].join("\n")
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" })
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = `resultados-${format(new Date(), "yyyy-MM-dd-HHmm")}.csv`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

export function ResultsTable({
  results,
  onViewDetails,
  onDownloadPDF,
  initialSearch,
  serverMode = false,
  searchQuery: controlledSearchQuery,
  onSearchQueryChange,
  statusFilter: controlledStatusFilter,
  onStatusFilterChange,
  clinicFilter: controlledClinicFilter,
  onClinicFilterChange,
  clinicOptions = [],
  clinicOptionsLoading = false,
  showClinicFilter = false,
  currentPage: controlledCurrentPage,
  totalPages: controlledTotalPages,
  totalItems: controlledTotalItems,
  pageSize: controlledPageSize,
  onPageChange,
  className,
}: ResultsTableProps) {
  const [searchQuery, setSearchQuery] = useState(initialSearch ?? "")
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all")
  const [clinicFilter, setClinicFilter] = useState("all")
  const [currentPage, setCurrentPage] = useState(1)
  const defaultPageSize = 10

  useEffect(() => {
    if (initialSearch === undefined || serverMode) return
    setSearchQuery(initialSearch)
    setCurrentPage(1)
  }, [initialSearch, serverMode])

  const effectiveSearch = serverMode ? (controlledSearchQuery ?? "") : searchQuery
  const effectiveStatusFilter = serverMode ? (controlledStatusFilter ?? "all") : statusFilter
  const effectiveClinicFilter = serverMode ? (controlledClinicFilter ?? "all") : clinicFilter
  const effectiveCurrentPage = serverMode ? (controlledCurrentPage ?? 1) : currentPage
  const effectivePageSize = serverMode ? (controlledPageSize ?? defaultPageSize) : defaultPageSize
  const selectedClinicName = clinicOptions.find((option) => option.id === effectiveClinicFilter)?.name

  const filteredResults = serverMode
    ? results
    : results.filter((result) => {
        const rawQuery = searchQuery.trim().toLowerCase()
        const queryDigits = rawQuery.replace(/\D/g, "")
        const matchesCPF = queryDigits ? result.cpf.replace(/\D/g, "").includes(queryDigits) : false
        const matchesText = rawQuery
          ? [result.patientName, result.filename, result.submittedBy]
              .filter(Boolean)
              .some((value) => value.toLowerCase().includes(rawQuery))
          : false
        const matchesSearch = rawQuery ? matchesCPF || matchesText : true
        const matchesStatus = statusFilter === "all" ? true : result.status === statusFilter
        const matchesClinic = clinicFilter === "all" ? true : result.clinicId === clinicFilter
        return matchesSearch && matchesStatus && matchesClinic
      })

  const totalPages = serverMode
    ? Math.max(1, controlledTotalPages ?? 1)
    : Math.max(1, Math.ceil(filteredResults.length / effectivePageSize))
  const startIndex = (effectiveCurrentPage - 1) * effectivePageSize
  const endIndex = startIndex + effectivePageSize
  const paginatedResults = serverMode ? filteredResults : filteredResults.slice(startIndex, endIndex)

  const formatCPF = (cpf: string) => {
    const cleaned = cpf.replace(/\D/g, "")
    if (cleaned.length === 11) return cleaned.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4")
    return cpf
  }

  const getStatusBadge = (result: ProcessResult) => {
    const { status, reviewedBy } = result
    if (status === "approved" && reviewedBy) {
      return <Badge variant="default" className="bg-green-500 hover:bg-green-600">Aprovado</Badge>
    }
    if (status === "approved" && !reviewedBy) {
      return <Badge variant="secondary" className="bg-amber-100 text-amber-700 hover:bg-amber-200">Aguardando Revisão</Badge>
    }
    if (status === "pending_review") {
      return <Badge variant="secondary" className="bg-orange-100 text-orange-700 hover:bg-orange-200">Aguardando Revisão</Badge>
    }
    if (status === "rejected" && reviewedBy) {
      return <Badge variant="destructive">Documentos Incompletos</Badge>
    }
    return <Badge variant="secondary">{status}</Badge>
  }

  if (results.length === 0 && !serverMode) {
    return (
      <div className={cn("text-center py-12 border rounded-lg", className)}>
        <p className="text-muted-foreground">
          Nenhum resultado disponível ainda.
          <br />
          Envie documentos para ver os resultados aqui.
        </p>
      </div>
    )
  }

  return (
    <div className={cn("flex h-full min-h-0 flex-col gap-4", className)}>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
          <Input
            placeholder="Buscar por CPF ou nome do documento..."
            value={effectiveSearch}
            onChange={(e) => {
              if (serverMode) {
                onSearchQueryChange?.(e.target.value)
                onPageChange?.(1)
              } else {
                setSearchQuery(e.target.value)
                setCurrentPage(1)
              }
            }}
            className="pl-9"
          />
        </div>
        <Select
          value={effectiveStatusFilter}
          onValueChange={(value: StatusFilter) => {
            if (serverMode) {
              onStatusFilterChange?.(value)
              onPageChange?.(1)
            } else {
              setStatusFilter(value)
              setCurrentPage(1)
            }
          }}
        >
          <SelectTrigger className="w-full sm:w-[200px]">
            <SelectValue placeholder="Filtrar por status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos os Status</SelectItem>
            <SelectItem value="approved">Aprovados</SelectItem>
            <SelectItem value="rejected">Rejeitados</SelectItem>
            <SelectItem value="pending_review">Pendentes</SelectItem>
          </SelectContent>
        </Select>
        {showClinicFilter ? (
          <ClinicFilter
            value={effectiveClinicFilter}
            onChange={(value) => {
              if (serverMode) {
                onClinicFilterChange?.(value)
                onPageChange?.(1)
              } else {
                setClinicFilter(value)
                setCurrentPage(1)
              }
            }}
            options={clinicOptions}
            loading={clinicOptionsLoading}
            showActiveChip
            className="lg:w-auto"
          />
        ) : null}
        <Button
          variant="outline"
          size="default"
          onClick={() => exportToCSV(filteredResults)}
          className="gap-2"
          disabled={filteredResults.length === 0}
        >
          <FileDown className="size-4" />
          Exportar CSV
        </Button>
      </div>

      <div className="flex-1 min-h-0 overflow-auto border rounded-lg">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>CPF</TableHead>
              <TableHead>Paciente</TableHead>
              <TableHead>Clínica</TableHead>
              <TableHead>Data</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-center">Faltantes</TableHead>
              <TableHead>Enviado por</TableHead>
              <TableHead className="text-right">Ações</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {paginatedResults.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} className="text-center py-8 text-muted-foreground">
                  {effectiveClinicFilter !== "all"
                    ? `Nenhum atendimento da ${selectedClinicName || "clínica selecionada"} com os filtros atuais.`
                    : "Nenhum resultado encontrado com os filtros selecionados."}
                </TableCell>
              </TableRow>
            ) : (
              paginatedResults.map((result) => (
                <TableRow
                  key={result.id}
                  className="cursor-pointer hover:bg-muted/50 transition-colors"
                  onClick={() => onViewDetails?.(result)}
                >
                  <TableCell className="font-mono text-sm">{formatCPF(result.cpf)}</TableCell>
                  <TableCell>{result.patientName}</TableCell>
                  <TableCell className="max-w-[180px] truncate text-sm text-muted-foreground">
                    {result.clinicName || "-"}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {format(result.uploadedAt, "dd/MM/yyyy HH:mm", { locale: ptBR })}
                  </TableCell>
                  <TableCell>{getStatusBadge(result)}</TableCell>
                  <TableCell className="text-center">
                    {result.examesFaltantes > 0 ? (
                      <Badge variant="outline" className="text-red-600 border-red-300">
                        {result.examesFaltantes}
                      </Badge>
                    ) : (
                      <span className="text-muted-foreground">-</span>
                    )}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground truncate max-w-[200px]">{result.submittedBy}</TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        type="button"
                        onPointerDown={(e) => {
                          e.preventDefault()
                          e.stopPropagation()
                          onViewDetails?.(result)
                        }}
                        onClick={(e) => {
                          e.preventDefault()
                          e.stopPropagation()
                        }}
                        className="inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium text-foreground cursor-pointer hover:bg-accent hover:text-accent-foreground focus-visible:bg-accent focus-visible:text-accent-foreground"
                      >
                        <Eye className="size-4" />
                        Ver
                      </button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation()
                          onDownloadPDF?.(result)
                        }}
                        className="gap-2"
                      >
                        <Download className="size-4" />
                        PDF
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Mostrando {Math.min(startIndex + 1, serverMode ? (controlledTotalItems ?? 0) : filteredResults.length)} a{" "}
            {Math.min(endIndex, serverMode ? (controlledTotalItems ?? 0) : filteredResults.length)} de{" "}
            {serverMode ? (controlledTotalItems ?? filteredResults.length) : filteredResults.length} resultados
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                if (serverMode) onPageChange?.(Math.max(1, effectiveCurrentPage - 1))
                else setCurrentPage((p) => Math.max(1, p - 1))
              }}
              disabled={effectiveCurrentPage === 1}
            >
              Anterior
            </Button>
            <span className="text-sm text-muted-foreground">Página {effectiveCurrentPage} de {totalPages}</span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                if (serverMode) onPageChange?.(Math.min(totalPages, effectiveCurrentPage + 1))
                else setCurrentPage((p) => Math.min(totalPages, p + 1))
              }}
              disabled={effectiveCurrentPage === totalPages}
            >
              Próxima
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
