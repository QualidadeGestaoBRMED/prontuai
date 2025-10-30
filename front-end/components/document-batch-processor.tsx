"use client"

import { useState, useEffect, useCallback } from "react"
import { FileWithPreview } from "@/hooks/use-file-upload"
import { ProcessingStepper, ProcessingStage } from "./processing-stepper"
import { Card } from "./ui/card"
import { Badge } from "./ui/badge"
import { FileIcon, AlertCircleIcon, CheckCircle2Icon } from "lucide-react"
import { formatBytes } from "@/hooks/use-file-upload"
import { useNotifications } from "@/hooks/use-notifications"
import { ProcessStep } from "@/types/process"

export interface DocumentProcessingResult {
  cpf_processado: string
  exames_ocr: string[]
  exames_brnet: string[]
  tabela_comparacao: TabelaComparacaoItem[]
  analise_comparacao: string
  decisao_final: string
  erro?: string
}

export interface TabelaComparacaoItem {
  exame: string
  status: "encontrado" | "faltante" | "parcialmente_encontrado" | "extra_no_ocr"
  justificativa: string
}

interface DocumentProcessingState {
  id: string
  file: File
  stage: ProcessingStage
  progress: number
  statusMessage: string
  result?: DocumentProcessingResult
  error?: string
}

interface DocumentBatchProcessorProps {
  files: FileWithPreview[]
  onComplete?: (results: DocumentProcessingResult[]) => void
  onError?: (error: string) => void
}

export function DocumentBatchProcessor({
  files,
  onComplete,
  onError,
}: DocumentBatchProcessorProps) {
  const [documents, setDocuments] = useState<DocumentProcessingState[]>([])
  const [isProcessing, setIsProcessing] = useState(false)
  const [processId, setProcessId] = useState<string | null>(null)
  const { startProcess, updateProcess, completeProcess, failProcess } = useNotifications()

  useEffect(() => {
    // Initialize document states only once
    if (documents.length > 0) return

    const initialDocs: DocumentProcessingState[] = files
      .filter((f) => f.file instanceof File)
      .map((f) => ({
        id: f.id,
        file: f.file as File,
        stage: "upload" as ProcessingStage,
        progress: 0,
        statusMessage: "Preparando envio...",
      }))

    if (initialDocs.length === 0) return

    setDocuments(initialDocs)
    setIsProcessing(true)

    // Start notification process - only if not already started
    if (!processId) {
      const batchId = `batch-${Date.now()}`
      const filename = initialDocs.length === 1
        ? initialDocs[0].file.name
        : `${initialDocs.length} documentos`

      const newProcessId = startProcess({
        batchId,
        filename,
        documentCount: initialDocs.length,
      })
      setProcessId(newProcessId)

      // Start processing all documents in parallel
      initialDocs.forEach((doc) => {
        processDocument(doc.id, doc.file)
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const processDocument = useCallback(
    async (docId: string, file: File) => {
      try {
        const formData = new FormData()
        formData.append("arquivo", file)
        formData.append("exames_obrigatorios", JSON.stringify([]))

        const response = await fetch(
          "http://localhost:8000/v1/processar-documento-stream",
          {
            method: "POST",
            body: formData,
          }
        )

        if (!response.ok || !response.body) {
          throw new Error(`HTTP error! status: ${response.status}`)
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ""

        console.log(`[FRONTEND] Starting SSE stream for: ${file.name}`)

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          console.log(`[FRONTEND] Received chunk, buffer length: ${buffer.length}`)

          // Split by multiple possible line endings
          const lines = buffer.split(/\n\n|\r\n\r\n|\r\r/)
          buffer = lines.pop() || ""

          console.log(`[FRONTEND] Parsed ${lines.length} lines from buffer`)

          for (const line of lines) {
            // Skip empty lines
            if (!line.trim()) {
              console.log('[FRONTEND] Skipping empty line')
              continue
            }

            if (line.startsWith("data: ")) {
              try {
                const jsonStr = line.slice(6).trim()
                if (!jsonStr) {
                  console.log('[FRONTEND] Skipping empty JSON string')
                  continue
                }

                const event = JSON.parse(jsonStr)

                // Log ALL SSE events for debugging
                console.log('[FRONTEND] SSE Event received:', event)

                // Log progress updates for debugging
                if (event.progress !== undefined) {
                  console.log(`[FRONTEND] Progress update: ${event.progress}% - ${event.message || ''}`)
                }

                setDocuments((prev) =>
                  prev.map((doc) => {
                    if (doc.id !== docId) return doc

                    const updatedDoc = { ...doc }

                    if (event.progress !== undefined) {
                      updatedDoc.progress = event.progress

                      // Map progress to stages
                      if (event.progress === 0) {
                        updatedDoc.stage = "upload"
                      } else if (event.progress > 0 && event.progress < 30) {
                        updatedDoc.stage = "ocr"
                      } else if (event.progress >= 30 && event.progress < 60) {
                        updatedDoc.stage = "brnet"
                      } else if (event.progress >= 60 && event.progress < 100) {
                        updatedDoc.stage = "validation"
                      } else if (event.progress === 100) {
                        updatedDoc.stage = "completed"
                      }

                      // Handle error
                      if (event.progress === -1) {
                        const errorMessage = event.message || "Erro no processamento"
                        updatedDoc.error = errorMessage
                      }
                    }

                    if (event.message) {
                      updatedDoc.statusMessage = event.message
                    }

                    if (event.resultado) {
                      updatedDoc.result = event.resultado
                    }

                    return updatedDoc
                  })
                )
              } catch (e) {
                console.error("Error parsing SSE event:", e)
              }
            }
          }
        }
      } catch (error) {
        console.error("Error processing document:", error)
        setDocuments((prev) =>
          prev.map((doc) =>
            doc.id === docId
              ? {
                  ...doc,
                  error: `Erro: ${error instanceof Error ? error.message : "Erro desconhecido"}`,
                }
              : doc
          )
        )
        onError?.(
          `Erro ao processar ${file.name}: ${error instanceof Error ? error.message : "Erro desconhecido"}`
        )
      }
    },
    [onError]
  )

  // Update notification process when documents change
  useEffect(() => {
    if (!processId || documents.length === 0) return

    // Calculate average progress
    const avgProgress = Math.round(
      documents.reduce((sum, d) => sum + d.progress, 0) / documents.length
    )

    // Determine current step based on average progress
    let currentStep: ProcessStep = "upload"
    if (avgProgress === 0) {
      currentStep = "upload"
    } else if (avgProgress > 0 && avgProgress < 30) {
      currentStep = "ocr"
    } else if (avgProgress >= 30 && avgProgress < 60) {
      currentStep = "brmed"
    } else if (avgProgress >= 60 && avgProgress < 100) {
      currentStep = "validation"
    } else if (avgProgress === 100) {
      currentStep = "completed"
    }

    // Get status message from most recent document being processed
    const processingDoc = documents.find(d => d.progress > 0 && d.progress < 100)
    const statusMessage = processingDoc?.statusMessage || "Processando..."

    // Update process
    updateProcess(processId, {
      progress: avgProgress,
      currentStep,
      stepMessage: statusMessage,
      documents: documents.map(d => ({
        filename: d.file.name,
        status: d.error ? 'error' as const :
                d.stage === 'completed' ? 'completed' as const :
                d.progress > 0 ? 'processing' as const : 'pending' as const,
        progress: d.progress,
        error: d.error,
      })),
    })

    // Handle errors
    const errorDoc = documents.find(d => d.error)
    if (errorDoc && errorDoc.error) {
      failProcess(processId, errorDoc.error)
    }
  }, [documents, processId, updateProcess, failProcess])

  useEffect(() => {
    // Check if all documents are processed
    const allCompleted = documents.every(
      (doc) => doc.stage === "completed" || doc.error
    )
    if (allCompleted && documents.length > 0 && isProcessing && processId) {
      setIsProcessing(false)
      const results = documents
        .filter((doc) => doc.result)
        .map((doc) => doc.result!)

      // Complete notification process
      const processResults = documents.map((doc) => ({
        id: doc.id,
        batchId: processId,
        filename: doc.file.name,
        cpf: doc.result?.cpf_processado || 'N/A',
        patientName: 'Paciente',
        uploadedAt: new Date(),
        processedAt: new Date(),
        status: doc.error ? 'rejected' as const : (
          doc.result?.decisao_final.toLowerCase().includes('aprovado') ? 'approved' as const : 'pending_review' as const
        ),
        rejectionReason: doc.error,
        examesFaltantes: doc.result?.tabela_comparacao.filter(e => e.status === 'faltante').length || 0,
        examesExtras: doc.result?.tabela_comparacao.filter(e => e.status === 'extra_no_ocr').length || 0,
        result: {
          cpf: doc.result?.cpf_processado || '',
          status: doc.error ? 'error' as const : 'success' as const,
          ocr_result: {
            text: '',
            exames_extraidos: doc.result?.exames_ocr || [],
          },
          brmed_result: {
            exames_obrigatorios: doc.result?.exames_brnet || [],
          },
          validation_result: {
            exames_faltantes: doc.result?.tabela_comparacao.filter(e => e.status === 'faltante').map(e => e.exame) || [],
            exames_extras: doc.result?.tabela_comparacao.filter(e => e.status === 'extra_no_ocr').map(e => e.exame) || [],
            analysis: doc.result?.analise_comparacao,
          },
          error: doc.error,
        },
        submittedBy: 'usuario@grupobrmed.com.br',
      }))

      completeProcess(processId, processResults)
      onComplete?.(results)
    }
  }, [documents, isProcessing, onComplete, processId, completeProcess])

  if (documents.length === 0) {
    return null
  }

  return (
    <div className="space-y-4 max-w-4xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">Processando Documentos</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Progresso médio:{" "}
            <span className="font-medium">
              {Math.round(
                documents.reduce((sum, d) => sum + d.progress, 0) / documents.length
              )}%
            </span>
          </p>
        </div>
        <Badge variant="secondary">
          {documents.filter((d) => d.stage === "completed").length} / {documents.length}{" "}
          concluídos
        </Badge>
      </div>

      <div className="grid gap-4">
        {documents.map((doc) => (
          <Card key={doc.id} className="p-6">
            <div className="flex items-start gap-4 mb-6">
              <div className="flex size-12 shrink-0 items-center justify-center rounded-lg border-2 bg-background">
                {doc.error ? (
                  <AlertCircleIcon className="size-6 text-destructive" />
                ) : doc.stage === "completed" ? (
                  <CheckCircle2Icon className="size-6 text-green-500" />
                ) : (
                  <FileIcon className="size-6 text-muted-foreground" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="font-medium truncate">{doc.file.name}</h3>
                <p className="text-sm text-muted-foreground">
                  {formatBytes(doc.file.size)}
                </p>
                {doc.error && (
                  <p className="text-sm text-destructive mt-1">{doc.error}</p>
                )}
                {!doc.error && doc.progress > 0 && doc.progress < 100 && (
                  <p className="text-sm text-primary mt-1">
                    {doc.statusMessage || "Processando..."}
                  </p>
                )}
              </div>
              <div className="text-right">
                <p className="text-2xl font-bold tabular-nums">{doc.progress}%</p>
                {doc.stage !== "completed" && !doc.error && (
                  <p className="text-xs text-muted-foreground mt-1">
                    {doc.stage === "upload" && "Upload"}
                    {doc.stage === "ocr" && "OCR"}
                    {doc.stage === "brnet" && "BRMED"}
                    {doc.stage === "validation" && "Validação"}
                  </p>
                )}
              </div>
            </div>

            <ProcessingStepper
              currentStage={doc.stage}
              statusMessage={doc.statusMessage}
            />

            {doc.result && (
              <div className="mt-6 pt-6 border-t">
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">CPF:</span>
                    <span className="font-medium">{doc.result.cpf_processado}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Exames OCR:</span>
                    <span className="font-medium">{doc.result.exames_ocr.length}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Exames BRNET:</span>
                    <span className="font-medium">{doc.result.exames_brnet.length}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Decisão:</span>
                    <Badge
                      variant={
                        doc.result.decisao_final.toLowerCase().includes("aprovado")
                          ? "default"
                          : "destructive"
                      }
                    >
                      {doc.result.decisao_final}
                    </Badge>
                  </div>
                </div>
              </div>
            )}
          </Card>
        ))}
      </div>
    </div>
  )
}
