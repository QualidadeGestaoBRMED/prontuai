"use client"

import { useEffect, useId, useRef, useState } from "react"
import { Loader2, SearchIcon } from "lucide-react"
import { ClinicFilter } from "@/components/clinic-filter"
import { DateFilter } from "@/components/date-filter"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { ClinicOption } from "@/hooks/use-clinic-options"
import type { CampoData, FiltroData } from "@/hooks/use-documents-paged"
import { contarPontos, rotuloTipoExame } from "./documento-medico"
import { CONDUTA } from "./tela-medico"
import type { DocumentoAprovado, SituacaoAso } from "./tipos"
import { useNormalidadesDaPagina } from "./use-normalidades-da-pagina"

function formatarCpf(cpf: string | null): string {
  const digitos = (cpf || "").replace(/\D/g, "")
  if (digitos.length === 11) return digitos.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4")
  return cpf || "—"
}

function formatarDataHora(iso: string | null): string {
  if (!iso) return "—"
  return new Date(iso).toLocaleDateString("pt-BR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

type FiltroSituacao = "all" | "aguardando" | "registrado"
const OPCOES_SITUACAO: { value: FiltroSituacao; label: string }[] = [
  { value: "all", label: "Todos" },
  { value: "aguardando", label: "Aguardando" },
  { value: "registrado", label: "Registrado" },
]
/** Aprovação primeiro: é quando o documento chega ao médico. */
const CAMPOS_DATA: CampoData[] = ["aprovacao", "envio"]

/** Campo de texto com lupa, igual ao `Filter` de texto da Checagem. */
function FiltroTexto({ rotulo, valor, onChange }: { rotulo: string; valor: string; onChange: (v: string) => void }) {
  const id = useId()
  return (
    <div className="space-y-2">
      <Label htmlFor={`${id}-input`}>{rotulo}</Label>
      <div className="relative">
        <Input
          id={`${id}-input`}
          className="peer ps-9"
          value={valor}
          onChange={(e) => onChange(e.target.value)}
          placeholder={`Buscar ${rotulo.toLowerCase()}`}
          type="text"
        />
        <div className="pointer-events-none absolute inset-y-0 start-0 flex items-center justify-center ps-3 text-muted-foreground/80 peer-disabled:opacity-50">
          <SearchIcon size={16} />
        </div>
      </div>
    </div>
  )
}

interface ListaAnalisesProps {
  /** A página atual da fila `medico` (aprovados pelo revisor). */
  documentos: DocumentoAprovado[]
  carregando: boolean
  erro: string | null
  /** Decisão registrada, por `documento_id`. */
  decisoes: Record<string, SituacaoAso>
  onAbrir: (documento: DocumentoAprovado) => void
  /** Busca no servidor: nome do paciente ou CPF, como na Checagem. */
  onBuscar: (termo: string) => void
  data: { value: FiltroData; onChange: (value: FiltroData) => void }
  clinica: {
    value: string
    onChange: (value: string) => void
    options: ClinicOption[]
    loading: boolean
    /** false para quem não enxerga todas as clínicas: o filtro some, como na Checagem. */
    enabled: boolean
  }
  paginacao: { page: number; totalPages: number; onPageChange: (page: number) => void }
}

/**
 * Lista dos documentos que um revisor aprovou na Checagem, no visual da tabela
 * da Checagem; clicar na linha abre a Revisão do ASO. Paciente, CPF, Data e
 * Clínica filtram no servidor; Situação filtra a página, porque a decisão do
 * médico ainda só existe nesta tela (não há API para gravá-la).
 */
export function ListaAnalises({
  documentos,
  carregando,
  erro,
  decisoes,
  onAbrir,
  onBuscar,
  data,
  clinica,
  paginacao,
}: ListaAnalisesProps) {
  const [paciente, setPaciente] = useState("")
  const [cpf, setCpf] = useState("")
  const [situacao, setSituacao] = useState<FiltroSituacao>("all")

  // Mesma regra da Checagem: um termo só (o nome vence), com espera de 400 ms
  // para não buscar a cada tecla. O CPF vai só com os dígitos.
  const onBuscarRef = useRef(onBuscar)
  onBuscarRef.current = onBuscar
  const primeiraVez = useRef(true)
  useEffect(() => {
    if (primeiraVez.current) {
      primeiraVez.current = false
      return
    }
    const termo = paciente.trim() || cpf.replace(/\D/g, "") || cpf.trim()
    const espera = window.setTimeout(() => onBuscarRef.current(termo), 400)
    return () => window.clearTimeout(espera)
  }, [paciente, cpf])

  const normalidades = useNormalidadesDaPagina(documentos.map((d) => d.documento_id))
  const visiveis = documentos.filter((d) => {
    const registrada = !!decisoes[d.documento_id]
    if (situacao === "aguardando") return !registrada
    if (situacao === "registrado") return registrada
    return true
  })
  const filtrando = !!(paciente.trim() || cpf.trim() || situacao !== "all" || data.value || clinica.value !== "all")

  return (
    <div className="flex-1 min-h-0 bg-white rounded-lg p-6 shadow-sm overflow-hidden flex flex-col gap-6">
      {/* Filtros: mesmos campos, larguras e ordem da Checagem. */}
      <div className="flex flex-wrap gap-3">
        <div className="w-52">
          <FiltroTexto rotulo="Paciente" valor={paciente} onChange={setPaciente} />
        </div>
        <div className="w-40">
          <FiltroTexto rotulo="CPF" valor={cpf} onChange={setCpf} />
        </div>
        <div className="w-36">
          <div className="space-y-2">
            <Label htmlFor="medico-situacao-select">Situação</Label>
            <Select value={situacao} onValueChange={(v) => setSituacao(v as FiltroSituacao)}>
              <SelectTrigger id="medico-situacao-select" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {OPCOES_SITUACAO.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DateFilter value={data.value} onChange={data.onChange} campos={CAMPOS_DATA} />
        {clinica.enabled && (
          <ClinicFilter
            value={clinica.value}
            onChange={clinica.onChange}
            options={clinica.options}
            loading={clinica.loading}
            showActiveChip
          />
        )}
      </div>
      <div className="flex-1 min-h-0 overflow-auto rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/50">
              {/* Mesma ordem da Checagem: CPF, Paciente, Clínica, Data, situação e o que falta. */}
              <TableHead className="h-10 border-t">CPF</TableHead>
              <TableHead className="h-10 border-t">Paciente</TableHead>
              <TableHead className="h-10 border-t">Clínica</TableHead>
              <TableHead className="h-10 border-t">Aprovado em</TableHead>
              <TableHead className="h-10 border-t">Tipo de exame</TableHead>
              <TableHead className="h-10 border-t">Situação</TableHead>
              <TableHead className="h-10 border-t">Pontos de atenção</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {visiveis.length ? (
              visiveis.map((d) => {
                const leitura = normalidades[d.documento_id]
                const pontos = contarPontos(d, leitura ?? null)
                const decisao = decisoes[d.documento_id]
                return (
                  <TableRow key={d.documento_id} className="cursor-pointer hover:bg-muted/50" onClick={() => onAbrir(d)}>
                    <TableCell>
                      <div className="font-mono text-sm">{formatarCpf(d.paciente_cpf)}</div>
                    </TableCell>
                    <TableCell>
                      <div className="font-medium">{d.paciente_nome ?? "—"}</div>
                    </TableCell>
                    <TableCell>
                      <div className="max-w-[180px] truncate text-sm text-muted-foreground" title={d.clinica ?? undefined}>
                        {d.clinica || "-"}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="text-sm">{formatarDataHora(d.aprovado_em)}</div>
                    </TableCell>
                    <TableCell>{rotuloTipoExame(d.tipo_exame)}</TableCell>
                    <TableCell>
                      {decisao ? (
                        <Badge variant="outline" className="bg-green-100 text-green-700 border-green-300">
                          Registrado: {CONDUTA[decisao]}
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="bg-orange-100 text-orange-700 border-orange-300">
                          Aguardando decisão
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      {leitura === undefined ? (
                        <Loader2 className="size-4 animate-spin text-muted-foreground" aria-label="Lendo os exames" />
                      ) : pontos > 0 ? (
                        <Badge variant="outline" className="bg-red-100 text-red-700 border-red-300">
                          {pontos}
                        </Badge>
                      ) : (
                        <span className="text-muted-foreground">Nenhum</span>
                      )}
                    </TableCell>
                  </TableRow>
                )
              })
            ) : (
              <TableRow>
                <TableCell colSpan={7} className="h-24 text-center">
                  {carregando ? (
                    <span className="inline-flex items-center gap-2 text-muted-foreground">
                      <Loader2 className="size-4 animate-spin" />
                      Carregando documentos aprovados...
                    </span>
                  ) : erro ? (
                    "Não foi possível carregar os documentos aprovados."
                  ) : filtrando ? (
                    "Nenhum documento aprovado com esses filtros."
                  ) : (
                    "Nenhum documento aprovado aguardando o médico."
                  )}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {/* Paginação, como na Checagem. */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm text-muted-foreground">
          Página {paginacao.page} de {paginacao.totalPages}
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => paginacao.onPageChange(Math.max(1, paginacao.page - 1))}
            disabled={paginacao.page <= 1}
          >
            Anterior
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => paginacao.onPageChange(Math.min(paginacao.totalPages, paginacao.page + 1))}
            disabled={paginacao.page >= paginacao.totalPages}
          >
            Próxima
          </Button>
        </div>
      </div>
    </div>
  )
}
