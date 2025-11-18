/**
 * Componente para exibir progresso de um job assíncrono
 */

"use client"

import { Job } from "@/types/job"
import { Card } from "./ui/card"
import { Progress } from "./ui/progress"
import { Badge } from "./ui/badge"
import { Loader2, CheckCircle2, XCircle, Clock } from "lucide-react"

interface JobProgressIndicatorProps {
  job: Job | null
  showDetails?: boolean
}

export function JobProgressIndicator({ job, showDetails = true }: JobProgressIndicatorProps) {
  if (!job) return null

  const getStatusIcon = () => {
    switch (job.status) {
      case "pending":
        return <Clock className="h-4 w-4 text-yellow-500" />
      case "in_progress":
        return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />
      case "completed":
        return <CheckCircle2 className="h-4 w-4 text-green-500" />
      case "failed":
        return <XCircle className="h-4 w-4 text-red-500" />
      case "cancelled":
        return <XCircle className="h-4 w-4 text-gray-500" />
    }
  }

  const getStatusColor = () => {
    switch (job.status) {
      case "pending":
        return "bg-yellow-100 text-yellow-800 border-yellow-300"
      case "in_progress":
        return "bg-blue-100 text-blue-800 border-blue-300"
      case "completed":
        return "bg-green-100 text-green-800 border-green-300"
      case "failed":
        return "bg-red-100 text-red-800 border-red-300"
      case "cancelled":
        return "bg-gray-100 text-gray-800 border-gray-300"
    }
  }

  const getStepLabel = () => {
    switch (job.current_step) {
      case "pending":
        return "Aguardando"
      case "upload":
        return "Upload"
      case "ocr":
        return "Processando OCR"
      case "brmed":
        return "Consultando BRMED"
      case "validacao":
        return "Validando"
      case "concluido":
        return "Concluído"
      case "erro":
        return "Erro"
      default:
        return job.current_step
    }
  }

  return (
    <Card className="p-4">
      <div className="space-y-3">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {getStatusIcon()}
            <span className="font-medium">{job.metadata.filename}</span>
          </div>
          <Badge variant="outline" className={getStatusColor()}>
            {job.status}
          </Badge>
        </div>

        {/* Progress Bar */}
        <div className="space-y-1">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">{getStepLabel()}</span>
            <span className="font-medium">{job.progress}%</span>
          </div>
          <Progress value={job.progress} className="h-2" />
        </div>

        {/* Message */}
        <p className="text-sm text-muted-foreground">{job.message}</p>

        {/* Error */}
        {job.error && (
          <div className="rounded-md bg-red-50 p-3 text-sm text-red-800 border border-red-200">
            <p className="font-medium">Erro:</p>
            <p>{job.error}</p>
          </div>
        )}

        {/* Details */}
        {showDetails && (
          <div className="grid grid-cols-2 gap-2 pt-2 border-t text-xs text-muted-foreground">
            <div>
              <span className="font-medium">Tamanho:</span> {job.metadata.file_size}
            </div>
            <div>
              <span className="font-medium">Exames:</span> {job.metadata.num_exames_obrigatorios}
            </div>
            <div className="col-span-2">
              <span className="font-medium">Job ID:</span>{" "}
              <code className="text-xs">{job.job_id.slice(0, 8)}...</code>
            </div>
          </div>
        )}
      </div>
    </Card>
  )
}
