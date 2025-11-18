/**
 * Hook para gerenciar jobs assíncronos com polling
 */

import { useState, useCallback, useRef, useEffect } from "react"
import { Job, CreateJobResponse, PollingOptions } from "@/types/job"
import { API_ENDPOINTS } from "@/lib/config"
import { DocumentProcessingResult } from "@/components/document-batch-processor"

interface UseAsyncJobReturn {
  /**
   * Inicia o processamento de um documento
   */
  startJob: (file: File, examesObrigatorios: string[]) => Promise<string>

  /**
   * Consulta o status de um job
   */
  getJobStatus: (jobId: string) => Promise<Job>

  /**
   * Inicia polling de um job
   */
  pollJob: (jobId: string, options?: PollingOptions) => Promise<DocumentProcessingResult>

  /**
   * Cancela o polling atual
   */
  cancelPolling: () => void

  /**
   * Job atual sendo monitorado
   */
  currentJob: Job | null

  /**
   * Indica se está fazendo polling
   */
  isPolling: boolean

  /**
   * Erro, se houver
   */
  error: string | null
}

export function useAsyncJob(): UseAsyncJobReturn {
  const [currentJob, setCurrentJob] = useState<Job | null>(null)
  const [isPolling, setIsPolling] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null)
  const pollingTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  /**
   * Limpa timers de polling
   */
  const clearPolling = useCallback(() => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current)
      pollingIntervalRef.current = null
    }
    if (pollingTimeoutRef.current) {
      clearTimeout(pollingTimeoutRef.current)
      pollingTimeoutRef.current = null
    }
    setIsPolling(false)
  }, [])

  /**
   * Cleanup ao desmontar
   */
  useEffect(() => {
    return () => {
      clearPolling()
    }
  }, [clearPolling])

  /**
   * Inicia o processamento de um documento
   */
  const startJob = useCallback(async (file: File, examesObrigatorios: string[]): Promise<string> => {
    try {
      setError(null)

      const formData = new FormData()
      formData.append("arquivo", file)
      formData.append("exames_obrigatorios", JSON.stringify(examesObrigatorios))

      const response = await fetch(API_ENDPOINTS.PROCESS_DOCUMENT_ASYNC, {
        method: "POST",
        body: formData,
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: "Erro desconhecido" }))
        throw new Error(errorData.detail || `HTTP error! status: ${response.status}`)
      }

      const data: CreateJobResponse = await response.json()
      console.log(`[useAsyncJob] Job criado: ${data.job_id}`)

      return data.job_id
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Erro ao iniciar processamento"
      setError(errorMessage)
      throw err
    }
  }, [])

  /**
   * Consulta o status de um job
   */
  const getJobStatus = useCallback(async (jobId: string): Promise<Job> => {
    try {
      const response = await fetch(API_ENDPOINTS.JOB_STATUS(jobId))

      if (!response.ok) {
        if (response.status === 404) {
          throw new Error("Job não encontrado ou expirado")
        }
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const job: Job = await response.json()
      return job
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Erro ao consultar status"
      setError(errorMessage)
      throw err
    }
  }, [])

  /**
   * Inicia polling de um job até completar ou falhar
   */
  const pollJob = useCallback(
    async (jobId: string, options: PollingOptions = {}): Promise<DocumentProcessingResult> => {
      const {
        interval = 2000, // 2 segundos
        timeout = 300000, // 5 minutos
        onProgress,
        onComplete,
        onError,
      } = options

      return new Promise((resolve, reject) => {
        setIsPolling(true)
        setError(null)

        console.log(`[useAsyncJob] Iniciando polling para job: ${jobId}`)

        // Timeout global
        pollingTimeoutRef.current = setTimeout(() => {
          clearPolling()
          const timeoutError = "Timeout: Processamento demorou muito tempo"
          setError(timeoutError)
          onError?.(timeoutError)
          reject(new Error(timeoutError))
        }, timeout)

        // Função de polling
        const poll = async () => {
          try {
            const job = await getJobStatus(jobId)
            setCurrentJob(job)

            console.log(`[useAsyncJob] Status: ${job.status} (${job.progress}%)`)

            // Callback de progresso
            onProgress?.(job)

            // Verifica se completou
            if (job.status === "completed") {
              clearPolling()
              console.log(`[useAsyncJob] Job completo!`)

              if (!job.result) {
                const error = "Job completo mas sem resultado"
                setError(error)
                onError?.(error)
                reject(new Error(error))
                return
              }

              onComplete?.(job.result)
              resolve(job.result)
              return
            }

            // Verifica se falhou
            if (job.status === "failed") {
              clearPolling()
              const errorMsg = job.error || "Erro desconhecido no processamento"
              console.error(`[useAsyncJob] Job falhou: ${errorMsg}`)
              setError(errorMsg)
              onError?.(errorMsg)
              reject(new Error(errorMsg))
              return
            }

            // Verifica se foi cancelado
            if (job.status === "cancelled") {
              clearPolling()
              const cancelMsg = "Processamento cancelado"
              setError(cancelMsg)
              onError?.(cancelMsg)
              reject(new Error(cancelMsg))
              return
            }

            // Continua polling se ainda estiver em progresso ou pendente
          } catch (err) {
            clearPolling()
            const errorMsg = err instanceof Error ? err.message : "Erro durante polling"
            setError(errorMsg)
            onError?.(errorMsg)
            reject(err)
          }
        }

        // Primeira poll imediata
        poll()

        // Continua polling em intervalo
        pollingIntervalRef.current = setInterval(poll, interval)
      })
    },
    [getJobStatus, clearPolling]
  )

  /**
   * Cancela o polling atual
   */
  const cancelPolling = useCallback(() => {
    console.log(`[useAsyncJob] Polling cancelado`)
    clearPolling()
  }, [clearPolling])

  return {
    startJob,
    getJobStatus,
    pollJob,
    cancelPolling,
    currentJob,
    isPolling,
    error,
  }
}
