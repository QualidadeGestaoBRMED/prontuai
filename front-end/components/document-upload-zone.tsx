"use client"

import {
  AlertCircleIcon,
  FileArchiveIcon,
  FileIcon,
  FileSpreadsheetIcon,
  FileTextIcon,
  FileUpIcon,
  HeadphonesIcon,
  ImageIcon,
  VideoIcon,
  XIcon,
} from "lucide-react"

import {
  formatBytes,
  useFileUpload,
  type FileWithPreview,
} from "@/hooks/use-file-upload"
import { Button } from "@/components/ui/button"

const getFileIcon = (file: FileWithPreview) => {
  const fileType = file.file instanceof File ? file.file.type : file.file.type
  const fileName = file.file instanceof File ? file.file.name : file.file.name

  if (
    fileType.includes("pdf") ||
    fileName.endsWith(".pdf") ||
    fileType.includes("word") ||
    fileName.endsWith(".doc") ||
    fileName.endsWith(".docx")
  ) {
    return <FileTextIcon className="size-4 opacity-60" />
  } else if (
    fileType.includes("zip") ||
    fileType.includes("archive") ||
    fileName.endsWith(".zip") ||
    fileName.endsWith(".rar")
  ) {
    return <FileArchiveIcon className="size-4 opacity-60" />
  } else if (
    fileType.includes("excel") ||
    fileName.endsWith(".xls") ||
    fileName.endsWith(".xlsx")
  ) {
    return <FileSpreadsheetIcon className="size-4 opacity-60" />
  } else if (fileType.includes("video/")) {
    return <VideoIcon className="size-4 opacity-60" />
  } else if (fileType.includes("audio/")) {
    return <HeadphonesIcon className="size-4 opacity-60" />
  } else if (fileType.startsWith("image/")) {
    return <ImageIcon className="size-4 opacity-60" />
  }
  return <FileIcon className="size-4 opacity-60" />
}

interface DocumentUploadZoneProps {
  onProcessFiles?: (files: FileWithPreview[]) => void
  maxSize?: number
  maxFiles?: number
}

export function DocumentUploadZone({
  onProcessFiles,
  maxSize = 100 * 1024 * 1024, // 100MB default
  maxFiles = 10,
}: DocumentUploadZoneProps) {
  const [
    { files, isDragging, errors },
    {
      handleDragEnter,
      handleDragLeave,
      handleDragOver,
      handleDrop,
      openFileDialog,
      removeFile,
      clearFiles,
      getInputProps,
    },
  ] = useFileUpload({
    multiple: true,
    maxFiles,
    maxSize,
  })

  const handleProcessFiles = () => {
    if (onProcessFiles && files.length > 0) {
      onProcessFiles(files)
    }
  }

  return (
    <div className="flex flex-col gap-4 max-w-4xl mx-auto">
      {/* Drop area */}
      <div
        role="button"
        onClick={openFileDialog}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        data-dragging={isDragging || undefined}
        className="flex min-h-64 flex-col items-center justify-center rounded-xl border-2 border-dashed border-input p-8 transition-colors hover:bg-accent/50
has-disabled:pointer-events-none has-disabled:opacity-50 has-[input:focus]:border-ring has-[input:focus]:ring-[3px] has-[input:focus]:ring-ring/50
data-[dragging=true]:bg-accent/50 data-[dragging=true]:border-primary cursor-pointer"
      >
        <input
          {...getInputProps()}
          className="sr-only"
          aria-label="Upload files"
        />

        <div className="flex flex-col items-center justify-center text-center">
          <div
            className="mb-4 flex size-16 shrink-0 items-center justify-center rounded-full border-2 bg-background shadow-sm"
            aria-hidden="true"
          >
            <FileUpIcon className="size-8 opacity-60" />
          </div>
          <p className="mb-2 text-lg font-semibold">Enviar Documentos</p>
          <p className="mb-3 text-sm text-muted-foreground">
            Arraste e solte ou clique para selecionar
          </p>
          <div className="flex flex-wrap justify-center gap-2 text-xs text-muted-foreground/70">
            <span>PDF, DOC, DOCX, XLS, XLSX e mais</span>
            <span>•</span>
            <span>Máximo {maxFiles} arquivos</span>
            <span>•</span>
            <span>Até {formatBytes(maxSize)} por arquivo</span>
          </div>
        </div>
      </div>

      {errors.length > 0 && (
        <div
          className="flex items-center gap-2 rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive"
          role="alert"
        >
          <AlertCircleIcon className="size-4 shrink-0" />
          <span>{errors[0]}</span>
        </div>
      )}

      {/* File list */}
      {files.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-muted-foreground">
              {files.length} {files.length === 1 ? "arquivo" : "arquivos"} selecionado
              {files.length === 1 ? "" : "s"}
            </p>
            {files.length > 1 && (
              <Button
                size="sm"
                variant="ghost"
                onClick={clearFiles}
                className="text-muted-foreground"
              >
                Remover todos
              </Button>
            )}
          </div>

          <div className="space-y-2">
            {files.map((file) => (
              <div
                key={file.id}
                className="flex items-center justify-between gap-3 rounded-lg border bg-card p-3 transition-colors hover:bg-accent/50"
              >
                <div className="flex items-center gap-3 overflow-hidden flex-1">
                  <div className="flex aspect-square size-10 shrink-0 items-center justify-center rounded border bg-background">
                    {getFileIcon(file)}
                  </div>
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <p className="truncate text-sm font-medium">
                      {file.file instanceof File
                        ? file.file.name
                        : file.file.name}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {formatBytes(
                        file.file instanceof File
                          ? file.file.size
                          : file.file.size
                      )}
                    </p>
                  </div>
                </div>

                <Button
                  size="icon"
                  variant="ghost"
                  className="size-8 shrink-0 text-muted-foreground hover:text-foreground"
                  onClick={() => removeFile(file.id)}
                  aria-label="Remover arquivo"
                >
                  <XIcon className="size-4" aria-hidden="true" />
                </Button>
              </div>
            ))}
          </div>

          <Button
            size="lg"
            onClick={handleProcessFiles}
            className="w-full"
            disabled={files.length === 0}
          >
            Processar {files.length} {files.length === 1 ? "Documento" : "Documentos"}
          </Button>
        </div>
      )}
    </div>
  )
}
