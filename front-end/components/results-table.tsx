"use client"

import { useState } from "react"
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { ProcessResult } from "@/types/process"
import { Download, Eye, MoreHorizontal, Search, FileDown } from "lucide-react"
import { cn } from "@/lib/utils"

interface ResultsTableProps {
  results: ProcessResult[]
  onViewDetails?: (result: ProcessResult) => void
  onDownloadPDF?: (result: ProcessResult) => void
  onDownloadJSON?: (result: ProcessResult) => void
  className?: string
}

// Helper to export CSV
const exportToCSV = (results: ProcessResult[]) => {
  const headers = ["CPF", "Paciente", "Data Upload", "Status", "Exames Faltantes", "Exames Extras", "Enviado Por"]
  const rows = results.map((r) => [
    r.cpf,
    r.patientName,
    format(r.uploadedAt, "dd/MM/yyyy HH:mm", { locale: ptBR }),
    r.status === "approved" ? "Aprovado" : r.status === "rejected" ? "Rejeitado" : "Pendente",
    r.examesFaltantes.toString(),
    r.examesExtras.toString(),
    r.submittedBy,
  ])

  const csvContent = [
    headers.join(","),
    ...rows.map((row) => row.map((cell) => `"${cell}"`).join(",")),
  ].join("\n")

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

type StatusFilter = "all" | "approved" | "rejected" | "pending_review"

export function ResultsTable({
  results,
  onViewDetails,
  onDownloadPDF,
  onDownloadJSON,
  className,
}: ResultsTableProps) {
  const [searchCPF, setSearchCPF] = useState("")
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all")
  const [currentPage, setCurrentPage] = useState(1)
  const resultsPerPage = 10

  // Filter results
  const filteredResults = results.filter((result) => {
    const matchesCPF = searchCPF
      ? result.cpf.replace(/\D/g, "").includes(searchCPF.replace(/\D/g, ""))
      : true
    const matchesStatus =
      statusFilter === "all" ? true : result.status === statusFilter
    return matchesCPF && matchesStatus
  })

  // Pagination
  const totalPages = Math.ceil(filteredResults.length / resultsPerPage)
  const startIndex = (currentPage - 1) * resultsPerPage
  const endIndex = startIndex + resultsPerPage
  const paginatedResults = filteredResults.slice(startIndex, endIndex)

  // Format CPF for display
  const formatCPF = (cpf: string) => {
    const cleaned = cpf.replace(/\D/g, "")
    if (cleaned.length === 11) {
      return cleaned.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4")
    }
    return cpf
  }

  // Status badge variants
  const getStatusBadge = (status: ProcessResult["status"]) => {
    switch (status) {
      case "approved":
        return (
          <Badge variant="default" className="bg-green-500 hover:bg-green-600">
            ✓ Aprovado
          </Badge>
        )
      case "rejected":
        return (
          <Badge variant="destructive">
            ✗ Rejeitado
          </Badge>
        )
      case "pending_review":
        return (
          <Badge variant="secondary" className="bg-amber-100 text-amber-700 hover:bg-amber-200">
            ⚠ Pendente
          </Badge>
        )
    }
  }

  // Empty state
  if (results.length === 0) {
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
    <div className={cn("space-y-4", className)}>
      {/* Filters and Actions */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
          <Input
            placeholder="Buscar por CPF..."
            value={searchCPF}
            onChange={(e) => {
              setSearchCPF(e.target.value)
              setCurrentPage(1) // Reset to first page on search
            }}
            className="pl-9"
          />
        </div>
        <Select
          value={statusFilter}
          onValueChange={(value: StatusFilter) => {
            setStatusFilter(value)
            setCurrentPage(1) // Reset to first page on filter change
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

      {/* Table */}
      <div className="border rounded-lg overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>CPF</TableHead>
              <TableHead>Paciente</TableHead>
              <TableHead>Data</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-center">Faltantes</TableHead>
              <TableHead className="text-center">Extras</TableHead>
              <TableHead>Enviado por</TableHead>
              <TableHead className="text-right">Ações</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {paginatedResults.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} className="text-center py-8 text-muted-foreground">
                  Nenhum resultado encontrado com os filtros selecionados.
                </TableCell>
              </TableRow>
            ) : (
              paginatedResults.map((result, index) => (
                <TableRow key={`${result.id}-${result.batchId}-${index}`}>
                  <TableCell className="font-mono text-sm">
                    {formatCPF(result.cpf)}
                  </TableCell>
                  <TableCell>{result.patientName}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {format(result.uploadedAt, "dd/MM/yyyy HH:mm", {
                      locale: ptBR,
                    })}
                  </TableCell>
                  <TableCell>{getStatusBadge(result.status)}</TableCell>
                  <TableCell className="text-center">
                    {result.examesFaltantes > 0 ? (
                      <Badge variant="outline" className="text-red-600 border-red-300">
                        {result.examesFaltantes}
                      </Badge>
                    ) : (
                      <span className="text-muted-foreground">-</span>
                    )}
                  </TableCell>
                  <TableCell className="text-center">
                    {result.examesExtras > 0 ? (
                      <Badge variant="outline" className="text-blue-600 border-blue-300">
                        {result.examesExtras}
                      </Badge>
                    ) : (
                      <span className="text-muted-foreground">-</span>
                    )}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground truncate max-w-[200px]">
                    {result.submittedBy}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onViewDetails?.(result)}
                        className="gap-2"
                      >
                        <Eye className="size-4" />
                        Ver
                      </Button>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="size-8">
                            <MoreHorizontal className="size-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => onDownloadPDF?.(result)}>
                            <Download className="size-4 mr-2" />
                            Download PDF
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => onDownloadJSON?.(result)}>
                            <Download className="size-4 mr-2" />
                            Download JSON
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Mostrando {startIndex + 1} a {Math.min(endIndex, filteredResults.length)} de{" "}
            {filteredResults.length} resultados
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage === 1}
            >
              Anterior
            </Button>
            <div className="flex items-center gap-1">
              {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                // Show pages around current page
                let pageNum: number
                if (totalPages <= 5) {
                  pageNum = i + 1
                } else if (currentPage <= 3) {
                  pageNum = i + 1
                } else if (currentPage >= totalPages - 2) {
                  pageNum = totalPages - 4 + i
                } else {
                  pageNum = currentPage - 2 + i
                }

                return (
                  <Button
                    key={pageNum}
                    variant={currentPage === pageNum ? "default" : "outline"}
                    size="sm"
                    className="w-8"
                    onClick={() => setCurrentPage(pageNum)}
                  >
                    {pageNum}
                  </Button>
                )
              })}
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage === totalPages}
            >
              Próxima
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
