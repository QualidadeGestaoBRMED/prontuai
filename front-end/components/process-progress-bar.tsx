"use client"

import { Progress } from "@/components/ui/progress"
import { Button } from "@/components/ui/button"
import { ChevronDown, ChevronUp, Clock } from "lucide-react"
import { cn } from "@/lib/utils"
import { ProcessNotification } from "@/types/process"
import { useNotifications } from "@/hooks/use-notifications"
import { useEffect, useState } from "react"
import { formatDistanceToNow } from "date-fns"
import { ptBR } from "date-fns/locale"

interface ProcessProgressBarProps {
  process: ProcessNotification
  className?: string
}

const STEP_LABELS = {
  upload: "Enviando documento",
  ocr: "Extraindo texto (OCR)",
  brmed: "Consultando BRMED",
  validation: "Validando exames",
  completed: "Concluído",
}

const STEP_COLORS = {
  upload: "bg-blue-500",
  ocr: "bg-purple-500",
  brmed: "bg-indigo-500",
  validation: "bg-amber-500",
  completed: "bg-green-500",
}

export function ProcessProgressBar({
  process,
  className,
}: ProcessProgressBarProps) {
  const { progressBarMinimized, minimizeProgressBar, showProgressBar } = useNotifications()
  const [elapsed, setElapsed] = useState<string>("")

  const isCompleted = process.status === "completed"
  const hasError = process.status === "error"

  // Update elapsed time every second
  useEffect(() => {
    const updateElapsed = () => {
      setElapsed(formatDistanceToNow(new Date(process.startedAt), {
        addSuffix: false,
        locale: ptBR
      }))
    }

    updateElapsed()
    const interval = setInterval(updateElapsed, 1000)
    return () => clearInterval(interval)
  }, [process.startedAt])

  // Auto-hide after 5s when completed
  useEffect(() => {
    if (isCompleted && !progressBarMinimized) {
      const timeout = setTimeout(() => {
        minimizeProgressBar()
      }, 5000)
      return () => clearTimeout(timeout)
    }
  }, [isCompleted, progressBarMinimized, minimizeProgressBar])

  return (
    <div
      className={cn(
        "fixed top-16 right-4 z-50 bg-background border rounded-lg shadow-lg transition-all duration-300",
        progressBarMinimized ? "w-64" : "w-96",
        className
      )}
    >
      {!progressBarMinimized ? (
        // Expanded state - simple view
        <div className="p-4 space-y-3">
          {/* Header */}
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <div
                  className={cn(
                    "size-2 rounded-full",
                    !hasError && !isCompleted && "animate-pulse",
                    hasError && "bg-red-500",
                    isCompleted && "bg-green-500",
                    !hasError && !isCompleted && STEP_COLORS[process.currentStep]
                  )}
                />
                <h3 className="font-semibold text-sm">
                  {hasError
                    ? "Erro no processamento"
                    : isCompleted
                    ? "Processamento concluído"
                    : `Processando ${process.documentCount > 1 ? `${process.documentCount} documentos` : "documento"}`}
                </h3>
              </div>
              <div className="flex items-center gap-1 mt-1 text-xs text-muted-foreground">
                <Clock className="size-3" />
                <span>{elapsed}</span>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                className="size-6"
                onClick={minimizeProgressBar}
                title="Minimizar"
              >
                <ChevronUp className="size-3 rotate-90" />
              </Button>
            </div>
          </div>

          {/* Progress bar */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">
                {STEP_LABELS[process.currentStep]}
              </span>
              <span className="font-bold tabular-nums">{process.progress}%</span>
            </div>
            <Progress
              value={process.progress}
              className="h-2"
              indicatorClassName={cn(
                "transition-all duration-500",
                hasError && "bg-red-500",
                isCompleted && "bg-green-500",
                !hasError && !isCompleted && STEP_COLORS[process.currentStep]
              )}
            />
          </div>

          {/* Status message */}
          {process.stepMessage && !hasError && (
            <p className="text-xs text-muted-foreground">
              {process.stepMessage}
            </p>
          )}

          {/* Error message */}
          {hasError && process.stepMessage && (
            <p className="text-xs text-destructive">
              {process.stepMessage}
            </p>
          )}
        </div>
      ) : (
        // Minimized state - compact
        <button
          onClick={showProgressBar}
          className="w-full p-3 flex items-center gap-3 hover:bg-muted/50 transition-colors"
        >
          <div
            className={cn(
              "size-2 rounded-full shrink-0",
              !hasError && !isCompleted && "animate-pulse",
              hasError && "bg-red-500",
              isCompleted && "bg-green-500",
              !hasError && !isCompleted && STEP_COLORS[process.currentStep]
            )}
          />
          <div className="flex-1 min-w-0 text-left">
            <p className="text-xs font-medium truncate">
              {hasError ? "Erro" : isCompleted ? "Concluído" : "Processando"}
            </p>
          </div>
          <span className="text-xs font-bold tabular-nums">{process.progress}%</span>
          <ChevronDown className="size-3 shrink-0 -rotate-90" />
        </button>
      )}
    </div>
  )
}
