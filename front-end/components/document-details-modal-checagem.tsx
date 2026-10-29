"use client"

import { ReactNode, useEffect, useRef, useState } from "react"
import { format } from "date-fns"
import { ptBR } from "date-fns/locale"
import { AlertTriangleIcon, CheckIcon, XIcon, Download, Loader2, MessageSquareIcon } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { ScrollArea } from "@/components/ui/scroll-area"
import { FieldCheck, OutraPessoa, ProcessResult, TabelaComparacaoItem } from "@/types/process"
import ExamesComparativoTable, { ExamesComparativoTableProps, ordenarComparativo } from "@/components/exames-comparativo-table"
import { ControleNavegacao, Destaque, VisualizadorPdf } from "@/components/visualizador-pdf"
import { TagNovo } from "@/components/tag-novo"
import { carregarTextoDocumento, useLocalizacoes } from "@/hooks/use-localizacoes"
import { cn } from "@/lib/utils"

// O que o destaque no PDF aponta: um exame (previsto no BRNET ou além do
// previsto) ou um campo da Checklist de Campos.
type Alvo = { tipo: "exame" | "campo"; nome: string }

/**
 * Item da Checklist de Campos. Com ocorrência no PDF, o item inteiro é o atalho
 * até ela — como a linha do exame na lista de exames; clicar de novo passa
 * para a próxima. Sem ocorrência (documento antigo, campo não encontrado), fica
 * como era.
 */
function ItemChecklist({
  children,
  localizavel,
  selecionado,
  onLocalizar,
}: {
  children: ReactNode
  localizavel: boolean
  selecionado: boolean
  onLocalizar: () => void
}) {
  // Como a lista de exames: ao passar de campo em campo pelo botão do PDF, a
  // checklist rola até o campo em foco.
  const botao = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (selecionado) botao.current?.scrollIntoView({ block: "nearest", behavior: "smooth" })
  }, [selecionado])
  if (!localizavel) {
    return <div className="flex items-center justify-between gap-2 rounded border px-3 py-2">{children}</div>
  }
  return (
    <button
      ref={botao}
      type="button"
      onClick={onLocalizar}
      aria-pressed={selecionado}
      title="Ver no documento"
      className={cn(
        "flex items-center justify-between gap-2 rounded border px-3 py-2 text-left transition-colors hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
        selecionado && "bg-cyan-50/70 text-primary shadow-[inset_2px_0_0_0_var(--primary)] hover:bg-cyan-50/70",
      )}
    >
      {children}
    </button>
  )
}

function ConteudoCampo({ item }: { item: FieldCheck }) {
  return (
    <>
      <span className="text-sm">{item.label}</span>
      <Badge
        variant="secondary"
        className={item.found ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-600"}
      >
        {item.found ? "Encontrado" : "Não encontrado"}
      </Badge>
    </>
  )
}

/**
 * Pessoa que não é o paciente, identificada no documento fora do laudo de
 * qualquer exame da tabela (STC-947) — título que o catálogo não conhece, ou
 * documento sem tabela. Quem está no laudo de um exame aparece na própria linha
 * do exame, como "Laudo de outra pessoa".
 */
function ConteudoOutraPessoa({ pessoa }: { pessoa: OutraPessoa }) {
  return (
    <>
      <span className="flex min-w-0 flex-col">
        <span className="text-sm">Dados de outra pessoa</span>
        <span className="text-xs text-yellow-600">
          {pessoa.nome} · CPF {pessoa.cpf}
          {pessoa.pagina ? ` · página ${pessoa.pagina}` : ""}
        </span>
      </span>
      <Badge variant="secondary" className="shrink-0 gap-1 bg-yellow-100 text-yellow-700">
        <AlertTriangleIcon className="size-3" />
        Conferir
      </Badge>
    </>
  )
}

/**
 * Os exames da comparação em duas partes, na linguagem de quem confere a grade
 * do BRNET: os **previstos no BRNET** (o que está na timeline do atendimento) e,
 * numa seção à parte e fechada, os que vieram no prontuário **além do previsto**.
 * Antes ficava tudo numa tabela só ("Comparação Detalhada"), e o "Extra no OCR"
 * no meio dos previstos confundia a conferência.
 *
 * A seção dos além do previsto abre sozinha quando o destaque no PDF chega num
 * deles (pelo botão que passa de exame em exame), para a linha selecionada não
 * ficar escondida. Abre já no render em que o destaque chega, e não num efeito
 * depois: a tabela rola até a linha em seguida, e a linha precisa estar à vista.
 */
function ExamesDaComparacao({
  tabela,
  localizar,
}: {
  tabela: TabelaComparacaoItem[]
  localizar?: ExamesComparativoTableProps["localizar"]
}) {
  const previstos = tabela.filter((item) => item.status !== "extra_no_ocr")
  const alem = tabela.filter((item) => item.status === "extra_no_ocr")
  const [alemAberto, setAlemAberto] = useState(false)
  const ativo = localizar?.ativo?.exame
  const [ativoAnterior, setAtivoAnterior] = useState(ativo)
  if (ativo !== ativoAnterior) {
    setAtivoAnterior(ativo)
    if (ativo && alem.some((item) => item.exame === ativo)) setAlemAberto(true)
  }

  return (
    <div>
      <h4 className={cn("font-semibold", localizar ? "mb-1" : "mb-3")}>Exames previstos no BR NET</h4>
      {localizar && (
        <p className="mb-3 flex items-center gap-2 text-xs text-muted-foreground">
          Clique no exame para vê-lo no documento.
          <TagNovo />
        </p>
      )}
      {previstos.length > 0 && (
        <div className="mb-4">
          <ExamesComparativoTable tabela={previstos} mostrarEvidencia localizar={localizar} />
        </div>
      )}
      {alem.length > 0 && (
        <details
          className="mb-6 rounded-lg border"
          open={alemAberto}
          onToggle={(e) => setAlemAberto(e.currentTarget.open)}
        >
          <summary className="cursor-pointer px-3 py-2 text-sm font-medium">
            Exames além do previsto no BR NET ({alem.length})
            <span className="block text-xs font-normal text-muted-foreground">
              Vieram no prontuário, mas não estão previstos no BR NET para este atendimento.
            </span>
          </summary>
          <div className="border-t px-1 pb-1">
            <ExamesComparativoTable
              tabela={alem}
              mostrarEvidencia
              localizar={localizar}
              rotuloColunaExame="Exame no prontuário"
              rotuloExtra="Além do previsto"
            />
          </div>
        </details>
      )}
    </div>
  )
}

interface DocumentDetailsModalChecagemProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  result: ProcessResult | null
  /**
   * Pede à página que abra o diálogo de decisão. A confirmação (e o parecer
   * sobre a IA) mora lá: o parecer precisa aparecer ANTES da aprovação, e
   * empilhar mais um diálogo em cima deste daria três telas em sequência.
   */
  onSolicitarDecisao?: (decisao: "aprovado" | "rejeitado") => void
  onViewDocument?: () => void
  documentUrl?: string | null
  /**
   * O PDF já baixado. O visualizador lê os bytes daqui; a URL fica para o
   * "Abrir em nova aba". Ver `VisualizadorPdf`.
   */
  documentBlob?: Blob | null
  /** Avisa o cronômetro de revisão que o PDF foi aberto fora da aba. */
  onAbrirPdfExterno?: () => void
  documentLoading?: boolean
  /**
   * Abre o parecer sobre o acerto da IA de um documento JÁ decidido. Documento
   * pendente não recebe o botão: ali o parecer entra sozinho, logo depois da
   * decisão. Aqui é a segunda chance — para quem pulou na hora, ou mudou de
   * ideia depois de ver o documento de novo.
   */
  onAvaliarIA?: () => void
  /**
   * Papéis que acompanham a checagem sem decidir (hoje o CURATOR). Só esconde
   * os botões; o PATCH da decisão é barrado no back-end por `require_checker`.
   */
  somenteLeitura?: boolean
}

export function DocumentDetailsModalChecagem({
  open,
  onOpenChange,
  result,
  onSolicitarDecisao,
  onViewDocument,
  documentUrl,
  documentBlob,
  onAbrirPdfExterno,
  documentLoading,
  onAvaliarIA,
  somenteLeitura = false,
}: DocumentDetailsModalChecagemProps) {
  // Atalho "clicar no exame e ir até ele no PDF". Os hooks vêm antes do
  // `return null` abaixo: a ordem deles não pode depender de haver documento.
  const localizacoes = useLocalizacoes(open ? result?.id : null)
  const [destaque, setDestaque] = useState<(Destaque & { alvo: Alvo; indice: number }) | null>(null)
  useEffect(() => setDestaque(null), [result?.id])

  if (!result) return null
  const showPreview = Boolean(documentUrl || documentLoading)

  const ocorrenciasDe = (alvo: Alvo) =>
    (alvo.tipo === "exame" ? localizacoes.porExame : localizacoes.porCampo)[alvo.nome]
  const ehOAlvo = (alvo: Alvo) => destaque?.alvo.tipo === alvo.tipo && destaque.alvo.nome === alvo.nome
  // Vai à ocorrência `indice` do exame ou campo (dá a volta nas pontas). Sem o PDF
  // na tela, abre: o visualizador aplica o destaque quando o documento carregar.
  const mostrarOcorrencia = (alvo: Alvo, indice: number) => {
    const ocorrencias = ocorrenciasDe(alvo)
    if (!ocorrencias?.length) return
    const i = (indice + ocorrencias.length) % ocorrencias.length
    setDestaque({ ...ocorrencias[i], alvo, indice: i, chave: Date.now() })
    if (!documentUrl && !documentLoading) onViewDocument?.()
  }
  // Clicar de novo no mesmo exame (ou campo) passa para a próxima ocorrência.
  const irPara = (alvo: Alvo) => mostrarOcorrencia(alvo, destaque && ehOAlvo(alvo) ? destaque.indice + 1 : 0)
  // O botão flutuante do visualizador: à esquerda, o exame (ou campo) entre os
  // que têm ocorrência no PDF, na mesma sequência da tela — exames na ordem da
  // lista (previstos no BRNET, depois os além do previsto), campos na da
  // Checklist; à direita, as ocorrências do
  // trecho, quando há mais de uma.
  const fieldChecks = result.result.analysis_details?.field_checks ?? []
  // A pessoa achada no laudo de um exame aparece na linha do exame; as demais,
  // como item da Checklist de Campos.
  const pessoasSemExame = (result.result.analysis_details?.outra_pessoa ?? []).filter((p) => !p.exames?.length)
  const sequencia = (tipo: Alvo["tipo"]) =>
    tipo === "exame"
      ? [...new Set(ordenarComparativo(Array.isArray(result.result.tabela_comparacao) ? result.result.tabela_comparacao : [], true).map((i) => i.exame))]
          .filter((exame) => localizacoes.porExame[exame]?.length)
      : [...fieldChecks.map((c) => c.field), ...pessoasSemExame.map((p) => p.chave)].filter(
          (campo) => localizacoes.porCampo[campo]?.length,
        )
  const navegacao: ControleNavegacao[] = []
  if (destaque) {
    const { tipo, nome } = destaque.alvo
    const itens = sequencia(tipo)
    const posicao = itens.indexOf(nome)
    if (posicao >= 0 && itens.length > 1) {
      const vizinho = (passo: number) => ({ tipo, nome: itens[(posicao + passo + itens.length) % itens.length] })
      navegacao.push({
        rotulo: `${tipo} ${posicao + 1} de ${itens.length}`,
        // O nome fica no tooltip: o rótulo mostra só a posição, como a ocorrência.
        dica:
          tipo === "exame"
            ? nome
            : fieldChecks.find((c) => c.field === nome)?.label ??
              pessoasSemExame.find((p) => p.chave === nome)?.nome ??
              nome,
        rotuloAnterior: tipo === "exame" ? "Exame anterior" : "Campo anterior",
        rotuloProximo: tipo === "exame" ? "Próximo exame" : "Próximo campo",
        onAnterior: () => mostrarOcorrencia(vizinho(-1), 0),
        onProximo: () => mostrarOcorrencia(vizinho(1), 0),
      })
    }
    const total = ocorrenciasDe(destaque.alvo)?.length ?? 0
    if (total > 1) {
      navegacao.push({
        rotulo: `ocorrência ${destaque.indice + 1} de ${total}`,
        rotuloAnterior: "Ocorrência anterior",
        rotuloProximo: "Próxima ocorrência",
        onAnterior: () => mostrarOcorrencia(destaque.alvo, destaque.indice - 1),
        onProximo: () => mostrarOcorrencia(destaque.alvo, destaque.indice + 1),
      })
    }
  }
  const localizar = Object.keys(localizacoes.porExame).length
    ? {
        porExame: Object.fromEntries(Object.entries(localizacoes.porExame).map(([exame, o]) => [exame, o.length])),
        ativo: destaque?.alvo.tipo === "exame" ? { exame: destaque.alvo.nome, indice: destaque.indice } : null,
        onLocalizar: (exame: string) => irPara({ tipo: "exame", nome: exame }),
      }
    : undefined
  const camposLocalizaveis = Object.keys(localizacoes.porCampo).length > 0
  const highlightLiberacao = (text?: string | null) => {
    if (!text) return null
    const phrase = "Liberação concedida"
    const lower = text.toLowerCase()
    const idx = lower.indexOf(phrase.toLowerCase())
    if (idx === -1) return text
    const before = text.slice(0, idx)
    const match = text.slice(idx, idx + phrase.length)
    const after = text.slice(idx + phrase.length)
    return (
      <>
        {before}
        <span className="font-semibold text-emerald-700">{match}</span>
        {after}
      </>
    )
  }

  const getStatusBadge = (result: ProcessResult) => {
    const { status, reviewedBy } = result

    // Approved by human (final approval)
    if (status === "approved" && reviewedBy) {
      return (
        <Badge variant="default" className="bg-green-500 hover:bg-green-600">
          Aprovado por Revisor
        </Badge>
      )
    }

    // Approved by AI, awaiting human validation
    if (status === "approved" && !reviewedBy) {
      return (
        <Badge variant="secondary" className="bg-amber-100 text-amber-700 hover:bg-amber-200">
          Aprovado pela IA - Aguardando Validação Humana
        </Badge>
      )
    }

    // Rejected by AI, awaiting human review
    if (status === "pending_review") {
      return (
        <Badge variant="secondary" className="bg-orange-100 text-orange-700 hover:bg-orange-200">
          Rejeitado pela IA - Aguardando Revisão Humana
        </Badge>
      )
    }

    // Rejected by human (final rejection)
    if (status === "rejected" && reviewedBy) {
      return (
        <Badge variant="destructive">
          Rejeitado pelo Revisor
        </Badge>
      )
    }

    // Fallback
    return <Badge variant="secondary">{status}</Badge>
  }

  const isPending = !result.reviewedBy

  // Este modal FICA ABERTO atrás do diálogo de decisão. Empilhar é o que já
  // acontecia com os AlertDialogs que o diálogo substituiu, então o Radix dá
  // conta; e fechar aqui tirava da vista a comparação de exames justamente
  // quando o parecer pergunta "em quais exames?".
  //
  // Quem fecha os dois é a página, e só depois da decisão gravada.
  const pedirDecisao = (decisao: "aprovado" | "rejeitado") => {
    onSolicitarDecisao?.(decisao)
  }
  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent
          className={cn(
            "p-4",
            showPreview
              ? "!w-[96vw] !h-[94svh] !max-w-[96vw] !max-h-[94svh] rounded-2xl"
              : "max-h-[90vh] max-w-4xl"
          )}
        >
          <DialogHeader className="pr-8">
            <div className="space-y-1">
              <DialogTitle className="text-2xl">
                Detalhes do Documento
              </DialogTitle>
              <DialogDescription>{result.filename}</DialogDescription>
            </div>
            <div className="absolute top-4 right-12">
              {getStatusBadge(result)}
            </div>
          </DialogHeader>

          {showPreview ? (
            <div className="flex flex-col gap-4 lg:grid lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
              <ScrollArea className="h-[70vh] pr-2">
                <div className="space-y-6">
              {/* Basic Information */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">CPF</p>
                  <p className="font-medium font-mono">{result.cpf}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Paciente</p>
                  <p className="font-medium">{result.patientName}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Data de Upload</p>
                  <p className="text-sm">
                    {format(result.uploadedAt, "dd/MM/yyyy 'às' HH:mm", {
                      locale: ptBR,
                    })}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">
                    Data de Processamento
                  </p>
                  <p className="text-sm">
                    {format(result.processedAt, "dd/MM/yyyy 'às' HH:mm", {
                      locale: ptBR,
                    })}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Enviado por</p>
                  <p className="text-sm">{result.submittedBy}</p>
                </div>
                {result.reviewedBy && (
                  <div>
                    <p className="text-sm text-muted-foreground">Revisado por</p>
                    <p className="text-sm">{result.reviewedBy}</p>
                    {result.reviewedAt && (
                      <p className="text-xs text-muted-foreground">
                        {format(result.reviewedAt, "dd/MM/yyyy 'às' HH:mm", {
                          locale: ptBR,
                        })}
                      </p>
                    )}
                  </div>
                )}
              </div>

              <Separator />

              {/* Summary Counters */}
              <div className="grid grid-cols-3 gap-4">
                <div className="text-center p-4 border rounded-lg bg-muted/30">
                  <p className="text-2xl font-bold">
                    {Array.isArray(result.result.ocr_result?.exames_extraidos) ? result.result.ocr_result.exames_extraidos.length : 0}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    Exames no Documento
                  </p>
                </div>
                <div className="text-center p-4 border rounded-lg bg-muted/30">
                  <p className="text-2xl font-bold">
                    {Array.isArray(result.result.brmed_result?.exames_obrigatorios) ? result.result.brmed_result.exames_obrigatorios.length : 0}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    Exames Obrigatórios
                  </p>
                </div>
                <div className="text-center p-4 border rounded-lg bg-muted/30">
                  <p className="text-2xl font-bold text-red-600">
                    {result.examesFaltantes}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    Exames Faltantes
                  </p>
                </div>
              </div>

              {/* Rejection Reason (if rejected) */}
              {result.status === "rejected" && result.rejectionReason && (
                <div className="p-4 border border-red-200 rounded-lg bg-red-50">
                  <h4 className="font-semibold text-red-900 mb-2">
                    Motivo da Rejeição
                  </h4>
                  <p className="text-sm text-red-700">{result.rejectionReason}</p>
                </div>
              )}

              {/* Analysis */}
              {result.result.validation_result?.analysis && (
                <>
                  <Separator />
                  <div>
                    <h4 className="font-semibold mb-3">Análise de Validação</h4>
                    <p className="text-sm text-muted-foreground leading-relaxed">
                      {highlightLiberacao(result.result.validation_result?.analysis)}
                    </p>
                  </div>
                </>
              )}


              {/* Checklist de Campos */}
              {result.result.analysis_details?.field_checks?.length ? (
                <>
                  <Separator />
                  <div>
                    <h4 className={cn("font-semibold", camposLocalizaveis ? "mb-1" : "mb-3")}>Checklist de Campos</h4>
                    {camposLocalizaveis && (
                      <p className="mb-3 flex items-center gap-2 text-xs text-muted-foreground">
                        Clique no campo para vê-lo no documento.
                        <TagNovo />
                      </p>
                    )}
                    <div className="grid grid-cols-2 gap-2">
                      {result.result.analysis_details.field_checks.map((item) => (
                        <ItemChecklist
                          key={item.field}
                          localizavel={Boolean(localizacoes.porCampo[item.field]?.length)}
                          selecionado={ehOAlvo({ tipo: "campo", nome: item.field })}
                          onLocalizar={() => irPara({ tipo: "campo", nome: item.field })}
                        >
                          <ConteudoCampo item={item} />
                        </ItemChecklist>
                      ))}
                      {pessoasSemExame.map((pessoa) => (
                        <ItemChecklist
                          key={pessoa.chave}
                          localizavel={Boolean(localizacoes.porCampo[pessoa.chave]?.length)}
                          selecionado={ehOAlvo({ tipo: "campo", nome: pessoa.chave })}
                          onLocalizar={() => irPara({ tipo: "campo", nome: pessoa.chave })}
                        >
                          <ConteudoOutraPessoa pessoa={pessoa} />
                        </ItemChecklist>
                      ))}
                    </div>

                    <details className="mt-3">
                      <summary className="text-sm text-muted-foreground cursor-pointer">
                        Evidências (trechos do OCR onde o campo aparece)
                      </summary>
                      <div className="mt-2 space-y-2">
                        {result.result.analysis_details.field_checks.map((item) => (
                          item.evidence?.length ? (
                            <div key={`${item.field}-evidence`} className="text-sm">
                              <p className="font-medium">{item.label}</p>
                              <ul className="text-muted-foreground list-disc ml-5">
                                {item.evidence.map((line, idx) => (
                                  <li key={`${item.field}-${idx}`}>{line}</li>
                                ))}
                              </ul>
                            </div>
                          ) : null
                        ))}
                        <EvidenciasExames tabela={result.result.tabela_comparacao} />
                      </div>
                    </details>
                  </div>
                </>
              ) : null}

              <Separator />

              {/* Exames previstos no BR NET e, à parte, os além do previsto */}
              <ExamesDaComparacao
                tabela={Array.isArray(result.result.tabela_comparacao) ? result.result.tabela_comparacao : []}
                localizar={localizar}
              />
                </div>
              </ScrollArea>

              <div className="flex flex-col gap-3">
                <div className="flex items-center justify-between">
                  <h4 className="font-semibold">Documento</h4>
                  {documentUrl && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        onAbrirPdfExterno?.()
                        window.open(documentUrl, "_blank", "noopener,noreferrer")
                      }}
                    >
                      Abrir em nova aba
                    </Button>
                  )}
                </div>
                <div className="h-[70vh] rounded-lg border bg-muted/20 overflow-hidden">
                  {documentUrl ? (
                    <VisualizadorPdf
                      arquivo={documentBlob ?? null}
                      url={documentUrl}
                      titulo={`Documento ${result.filename}`}
                      destaque={destaque}
                      navegacao={navegacao}
                      carregarTexto={() => carregarTextoDocumento(result.id)}
                    />
                  ) : (
                    <div className="h-full flex items-center justify-center text-sm text-muted-foreground px-6 text-center">
                      <div className="flex items-center gap-2">
                        <Loader2 className="size-4 animate-spin" />
                        Carregando documento...
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <ScrollArea className="max-h-[calc(90vh-12rem)] pr-2">
              <div className="space-y-6">
                {/* Basic Information */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-sm text-muted-foreground">CPF</p>
                    <p className="font-medium font-mono">{result.cpf}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Paciente</p>
                    <p className="font-medium">{result.patientName}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Data de Upload</p>
                    <p className="text-sm">
                      {format(result.uploadedAt, "dd/MM/yyyy 'às' HH:mm", {
                        locale: ptBR,
                      })}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">
                      Data de Processamento
                    </p>
                    <p className="text-sm">
                      {format(result.processedAt, "dd/MM/yyyy 'às' HH:mm", {
                        locale: ptBR,
                      })}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Enviado por</p>
                    <p className="text-sm">{result.submittedBy}</p>
                  </div>
                  {result.reviewedBy && (
                    <div>
                      <p className="text-sm text-muted-foreground">Revisado por</p>
                      <p className="text-sm">{result.reviewedBy}</p>
                      {result.reviewedAt && (
                        <p className="text-xs text-muted-foreground">
                          {format(result.reviewedAt, "dd/MM/yyyy 'às' HH:mm", {
                            locale: ptBR,
                          })}
                        </p>
                      )}
                    </div>
                  )}
                </div>

                <Separator />

                {/* Summary Counters */}
                <div className="grid grid-cols-3 gap-4">
                  <div className="text-center p-4 border rounded-lg bg-muted/30">
                    <p className="text-2xl font-bold">
                      {Array.isArray(result.result.ocr_result?.exames_extraidos) ? result.result.ocr_result.exames_extraidos.length : 0}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      Exames no Documento
                    </p>
                  </div>
                  <div className="text-center p-4 border rounded-lg bg-muted/30">
                    <p className="text-2xl font-bold">
                      {Array.isArray(result.result.brmed_result?.exames_obrigatorios) ? result.result.brmed_result.exames_obrigatorios.length : 0}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      Exames Obrigatórios
                    </p>
                  </div>
                  <div className="text-center p-4 border rounded-lg bg-muted/30">
                    <p className="text-2xl font-bold text-red-600">
                      {result.examesFaltantes}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      Exames Faltantes
                    </p>
                  </div>
                </div>

                {/* Rejection Reason (if rejected) */}
                {result.status === "rejected" && result.rejectionReason && (
                  <div className="p-4 border border-red-200 rounded-lg bg-red-50">
                    <h4 className="font-semibold text-red-900 mb-2">
                      Motivo da Rejeição
                    </h4>
                    <p className="text-sm text-red-700">{result.rejectionReason}</p>
                  </div>
                )}

                {/* Analysis */}
                {result.result.validation_result?.analysis && (
                  <>
                    <Separator />
                      <div>
                        <h4 className="font-semibold mb-3">Análise de Validação</h4>
                        <p className="text-sm text-muted-foreground leading-relaxed">
                          {highlightLiberacao(result.result.validation_result?.analysis)}
                        </p>
                      </div>
                    </>
                  )}


                {/* Checklist de Campos */}
                {result.result.analysis_details?.field_checks?.length ? (
                  <>
                    <Separator />
                    <div>
                      <h4 className={cn("font-semibold", camposLocalizaveis ? "mb-1" : "mb-3")}>Checklist de Campos</h4>
                      {camposLocalizaveis && (
                        <p className="mb-3 flex items-center gap-2 text-xs text-muted-foreground">
                          Clique no campo para vê-lo no documento.
                          <TagNovo />
                        </p>
                      )}
                      <div className="grid grid-cols-2 gap-2">
                        {result.result.analysis_details.field_checks.map((item) => (
                          <ItemChecklist
                            key={item.field}
                            localizavel={Boolean(localizacoes.porCampo[item.field]?.length)}
                            selecionado={ehOAlvo({ tipo: "campo", nome: item.field })}
                            onLocalizar={() => irPara({ tipo: "campo", nome: item.field })}
                          >
                            <ConteudoCampo item={item} />
                          </ItemChecklist>
                        ))}
                        {pessoasSemExame.map((pessoa) => (
                          <ItemChecklist
                            key={pessoa.chave}
                            localizavel={Boolean(localizacoes.porCampo[pessoa.chave]?.length)}
                            selecionado={ehOAlvo({ tipo: "campo", nome: pessoa.chave })}
                            onLocalizar={() => irPara({ tipo: "campo", nome: pessoa.chave })}
                          >
                            <ConteudoOutraPessoa pessoa={pessoa} />
                          </ItemChecklist>
                        ))}
                      </div>

                      <details className="mt-3">
                        <summary className="text-sm text-muted-foreground cursor-pointer">
                          Evidências (trechos do OCR onde o campo aparece)
                        </summary>
                        <div className="mt-2 space-y-2">
                          {result.result.analysis_details.field_checks.map((item) => (
                            item.evidence?.length ? (
                              <div key={`${item.field}-evidence`} className="text-sm">
                                <p className="font-medium">{item.label}</p>
                                <ul className="text-muted-foreground list-disc ml-5">
                                  {item.evidence.map((line, idx) => (
                                    <li key={`${item.field}-${idx}`}>{line}</li>
                                  ))}
                                </ul>
                              </div>
                            ) : null
                          ))}
                          <EvidenciasExames tabela={result.result.tabela_comparacao} />
                        </div>
                      </details>
                    </div>
                  </>
                ) : null}

                <Separator />

                {/* Exames previstos no BR NET e, à parte, os além do previsto */}
                <ExamesDaComparacao
                  tabela={Array.isArray(result.result.tabela_comparacao) ? result.result.tabela_comparacao : []}
                  localizar={localizar}
                />
              </div>
            </ScrollArea>
          )}

          {/* Footer Actions */}
          <div className="flex items-center justify-between pt-4 border-t">
            {onViewDocument && (
              <div className="flex gap-2">
                {onViewDocument && (
                  <Button variant="outline" size="sm" onClick={onViewDocument} disabled={documentLoading}>
                    {documentLoading ? (
                      <Loader2 className="size-4 mr-2 animate-spin" />
                    ) : (
                      <Download className="size-4 mr-2" />
                    )}
                    {documentUrl ? "Recarregar documento" : "Visualizar documento"}
                  </Button>
                )}
              </div>
            )}
            <div className="flex gap-2 ml-auto">
              {isPending && somenteLeitura && (
                <span className="self-center text-sm text-muted-foreground">
                  Somente leitura
                </span>
              )}
              {!isPending && !somenteLeitura && onAvaliarIA && (
                <Button
                  variant="outline"
                  onClick={() => {
                    // Fecha este modal antes de abrir o de parecer: dois Dialogs
                    // empilhados brigam pelo foco.
                    onOpenChange(false)
                    onAvaliarIA()
                  }}
                  className="text-blue-600 hover:text-blue-700 hover:bg-blue-50"
                >
                  <MessageSquareIcon className="size-4 mr-2" />
                  Avaliar IA
                </Button>
              )}
              {isPending && !somenteLeitura && (
                <>
                  <Button
                    variant="outline"
                    onClick={() => pedirDecisao("rejeitado")}
                    className="text-red-600 hover:text-red-700 hover:bg-red-50"
                  >
                    <XIcon className="size-4 mr-2" />
                    Rejeitar
                  </Button>
                  <Button
                    onClick={() => pedirDecisao("aprovado")}
                    className="bg-green-600 hover:bg-green-700"
                  >
                    <CheckIcon className="size-4 mr-2" />
                    Aprovar
                  </Button>
                </>
              )}
              <Button variant="ghost" onClick={() => onOpenChange(false)}>
                Fechar
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

    </>
  )
}

/**
 * Linha do documento de onde o nome de cada exame foi lido. O exame que só
 * aparece na lista de procedimentos do ASO vem primeiro, em âmbar, com o aviso
 * de que não há resultado no PDF. Documento antigo, sem `linha_origem`, não
 * mostra nada.
 */
function EvidenciasExames({ tabela }: { tabela?: TabelaComparacaoItem[] }) {
  const itens = (Array.isArray(tabela) ? tabela : [])
    .filter((item) => item.linha_origem?.trim())
    .sort((a, b) => Number(b.evidencia === "so_lista") - Number(a.evidencia === "so_lista"))
  if (!itens.length) return null
  return (
    <div className="text-sm">
      <p className="font-medium">Exames</p>
      <ul className="list-disc ml-5">
        {itens.map((item, idx) =>
          item.evidencia === "so_lista" ? (
            <li key={`exame-${idx}`} className="text-yellow-500">
              {item.exame} · Linha de origem:{" "}
              <span className="font-mono break-words">{item.linha_origem?.trim()}</span>. Nenhum resultado
              encontrado no PDF.
            </li>
          ) : (
            <li key={`exame-${idx}`} className="text-muted-foreground">
              {item.exame} · Linha de origem:{" "}
              <span className="font-mono break-words">{item.linha_origem?.trim()}</span>
            </li>
          ),
        )}
      </ul>
    </div>
  )
}
