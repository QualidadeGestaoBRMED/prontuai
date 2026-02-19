/**
 * Hook para gerenciar jobs assíncronos com polling
 */

import { useState, useCallback, useRef, useEffect } from "react"
import { getSession, useSession } from "next-auth/react"
import { Job, CreateJobResponse, PollingOptions } from "@/types/job"
import { API_ENDPOINTS } from "@/lib/config"
import { DocumentProcessingResult } from "@/types/document-processing"
import { authFetch } from "@/lib/auth-fetch"

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
  const { data: session } = useSession()
  const [currentJob, setCurrentJob] = useState<Job | null>(null)
  const [isPolling, setIsPolling] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const pollingIntervalsRef = useRef<Map<string, NodeJS.Timeout>>(new Map())
  const pollingTimeoutsRef = useRef<Map<string, NodeJS.Timeout>>(new Map())
  const inFlightJobsRef = useRef<Map<string, Promise<string>>>(new Map())

  /**
   * Limpa timers de polling
   */
  const clearPolling = useCallback((jobId?: string) => {
    if (jobId) {
      const interval = pollingIntervalsRef.current.get(jobId)
      if (interval) {
        clearInterval(interval)
        pollingIntervalsRef.current.delete(jobId)
      }
      const timeout = pollingTimeoutsRef.current.get(jobId)
      if (timeout) {
        clearTimeout(timeout)
        pollingTimeoutsRef.current.delete(jobId)
      }
    } else {
      pollingIntervalsRef.current.forEach((interval) => clearInterval(interval))
      pollingIntervalsRef.current.clear()
      pollingTimeoutsRef.current.forEach((timeout) => clearTimeout(timeout))
      pollingTimeoutsRef.current.clear()
    }
    setIsPolling(pollingIntervalsRef.current.size > 0)
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
    const fileKey = `${file.name}:${file.size}:${file.lastModified}`
    const existingPromise = inFlightJobsRef.current.get(fileKey)
    if (existingPromise) {
      console.warn(`[useAsyncJob] Upload duplicado ignorado (fileKey=${fileKey})`)
      return existingPromise
    }

    const jobPromise = (async () => {
      try {
        setError(null)

        const formData = new FormData()
        formData.append("arquivo", file)
        formData.append("exames_obrigatorios", JSON.stringify(examesObrigatorios))

        let token = session?.accessToken as string | undefined
        if (!token) {
          const freshSession = await getSession()
          token = (freshSession?.accessToken as string | undefined) ?? undefined
        }
        if (!token) {
          throw new Error("Sessão inválida. Faça login novamente.")
        }

        const headers: Record<string, string> = {
          Authorization: `Bearer ${token}`,
        }

        const response = await authFetch(API_ENDPOINTS.PROCESS_DOCUMENT_ASYNC, {
          method: "POST",
          body: formData,
          headers,
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
    })()

    inFlightJobsRef.current.set(fileKey, jobPromise)
    try {
      const jobId = await jobPromise
      return jobId
    } finally {
      window.setTimeout(() => {
        inFlightJobsRef.current.delete(fileKey)
      }, 15000)
    }
  }, [session?.accessToken])

  /**
   * Consulta o status de um job
   */
  const getJobStatus = useCallback(async (jobId: string): Promise<Job> => {
    try {
      const response = await authFetch(API_ENDPOINTS.JOB_STATUS(jobId))

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
        let finished = false

        const finish = (
          result: { type: "resolve"; value: DocumentProcessingResult } | { type: "reject"; error: Error }
        ) => {
          if (finished) return
          finished = true
          clearPolling(jobId)
          if (result.type === "resolve") {
            resolve(result.value)
          } else {
            reject(result.error)
          }
        }

        // Timeout global (se <= 0, desabilita)
        if (timeout && timeout > 0) {
          const timeoutHandle = setTimeout(() => {
            const timeoutError = "Timeout: Processamento demorou muito tempo"
            setError(timeoutError)
            onError?.(timeoutError)
            finish({ type: "reject", error: new Error(timeoutError) })
          }, timeout)
          pollingTimeoutsRef.current.set(jobId, timeoutHandle)
        }

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
              console.log(`[useAsyncJob] Job completo!`)

              if (!job.result) {
                const error = "Job completo mas sem resultado"
                setError(error)
                onError?.(error)
                finish({ type: "reject", error: new Error(error) })
                return
              }

              onComplete?.(job.result)
              finish({ type: "resolve", value: job.result })
              return
            }

            // Verifica se falhou
            if (job.status === "failed") {
              const errorMsg = job.error || "Erro desconhecido no processamento"
              console.error(`[useAsyncJob] Job falhou: ${errorMsg}`)
              setError(errorMsg)
              onError?.(errorMsg)
              finish({ type: "reject", error: new Error(errorMsg) })
              return
            }

            // Verifica se foi cancelado
            if (job.status === "cancelled") {
              const cancelMsg = "Processamento cancelado"
              setError(cancelMsg)
              onError?.(cancelMsg)
              finish({ type: "reject", error: new Error(cancelMsg) })
              return
            }

            // Continua polling se ainda estiver em progresso ou pendente
          } catch (err) {
            const errorMsg = err instanceof Error ? err.message : "Erro durante polling"
            setError(errorMsg)
            onError?.(errorMsg)
            finish({ type: "reject", error: err instanceof Error ? err : new Error(errorMsg) })
          }
        }

        // Primeira poll imediata
        poll()

        // Continua polling em intervalo
        const intervalHandle = setInterval(poll, interval)
        pollingIntervalsRef.current.set(jobId, intervalHandle)
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
