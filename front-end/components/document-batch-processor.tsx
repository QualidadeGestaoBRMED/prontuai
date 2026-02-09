"use client"

import { useEffect, useRef } from "react"
import { FileWithPreview } from "@/hooks/use-file-upload"
import { ProcessingStepper } from "./processing-stepper"
import { Card } from "./ui/card"
import { Badge } from "./ui/badge"
import { FileIcon, AlertCircleIcon, CheckCircle2Icon } from "lucide-react"
import { formatBytes } from "@/hooks/use-file-upload"
import { useNotifications } from "@/hooks/use-notifications"
import {
  DocumentProcessingResult,
  ProcessingDocumentState,
} from "@/types/document-processing"

interface DocumentBatchProcessorProps {
  files: FileWithPreview[]
  onComplete?: (results: DocumentProcessingResult[]) => void
  onError?: (error: string) => void
  submittedBy?: string
  /**
   * Usa API assíncrona com polling (recomendado para evitar timeouts)
   * @default true
   */
  useAsync?: boolean
}

export function DocumentBatchProcessor({
  files,
  onComplete,
  onError,
  submittedBy,
  useAsync = true,
}: DocumentBatchProcessorProps) {
  const { startBackgroundProcessing, processingDocuments } = useNotifications()
  const hasInitializedRef = useRef(false)
  const hasCompletedRef = useRef(false)

  useEffect(() => {
    if (!useAsync) return
    if (hasInitializedRef.current || files.length === 0) return

    const validFiles = files.filter((f) => f.file instanceof File)
    if (validFiles.length === 0) return

    hasInitializedRef.current = true
    hasCompletedRef.current = false

    startBackgroundProcessing(validFiles.map((f) => f.file as File), {
      submittedBy,
      originPath: typeof window !== "undefined" ? window.location.pathname : undefined,
    })
  }, [files, startBackgroundProcessing, submittedBy, useAsync])

  useEffect(() => {
    if (processingDocuments.length === 0) return

    const allCompleted = processingDocuments.every(
      (doc) => doc.stage === "completed" || doc.error
    )

    if (allCompleted && !hasCompletedRef.current) {
      hasCompletedRef.current = true
      const results = processingDocuments
        .filter((doc) => doc.result)
        .map((doc) => doc.result as DocumentProcessingResult)
      onComplete?.(results)
    }

    const errorDoc = processingDocuments.find((doc) => doc.error)
    if (errorDoc?.error) {
      onError?.(errorDoc.error)
    }
  }, [processingDocuments, onComplete, onError])

  const documents: ProcessingDocumentState[] = processingDocuments

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
                documents.reduce((sum, d) => sum + d.displayProgress, 0) / documents.length
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
                <h3 className="font-medium truncate">
                  {doc.file?.name ?? doc.fileName ?? "Documento"}
                </h3>
                <p className="text-sm text-muted-foreground">
                  {formatBytes(doc.file?.size ?? doc.fileSize ?? 0)}
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
                <p className="text-2xl font-bold tabular-nums">{doc.displayProgress}%</p>
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

            <ProcessingStepper currentStage={doc.stage} statusMessage={doc.statusMessage} />

            {doc.result && (
              <div className="mt-6 pt-6 border-t">
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">CPF:</span>
                    <span className="font-medium">{doc.result.cpf_processado}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Exames OCR:</span>
                    <span className="font-medium">{doc.result.exames_ocr?.length ?? 0}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Exames BRNET:</span>
                    <span className="font-medium">{doc.result.exames_brnet?.length ?? 0}</span>
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
