'use client'

import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'
import { useSession } from 'next-auth/react'
import {
  Notification,
  CreateNotificationInput,
  NotificationPreferences
} from '@/types/notification'
import {
  ProcessNotification,
  ProcessResult,
  ProgressBarState,
  CreateProcessInput,
  ProcessStep
} from '@/types/process'
import {
  DocumentProcessingResult,
  ProcessingDocumentState,
  ProcessingStage
} from '@/types/document-processing'
import { API_ENDPOINTS } from '@/lib/config'
import { authFetch } from '@/lib/auth-fetch'
import { useAsyncJob } from '@/hooks/use-async-job'
import { Job } from '@/types/job'

type StartBackgroundProcessingOptions = {
  submittedBy?: string
  originPath?: string
}

// Interface do contexto
interface NotificationContextType {
  // Notificações
  notifications: Notification[]
  unreadCount: number
  addNotification: (notification: CreateNotificationInput) => string
  markAsRead: (id: string) => void
  markAllAsRead: () => void
  clearHistory: () => void
  getNotificationById: (id: string) => Notification | undefined

  // Processos ativos
  activeProcess: ProcessNotification | null
  startProcess: (input: CreateProcessInput) => string
  updateProcess: (processId: string, update: Partial<ProcessNotification>) => void
  completeProcess: (processId: string, results: ProcessResult[]) => void
  failProcess: (processId: string, error: string) => void

  // Processamento em background
  processingDocuments: ProcessingDocumentState[]
  startBackgroundProcessing: (files: File[], options?: StartBackgroundProcessingOptions) => string | null
  clearProcessingState: () => void

  // Resultados de processos
  processResults: ProcessResult[]
  addProcessResult: (result: ProcessResult) => void
  getResultsByBatchId: (batchId: string) => ProcessResult[]
  updateProcessResultStatus: (id: string, status: 'approved' | 'rejected' | 'pending_review', reviewerEmail: string, rejectionReason?: string, approvalReason?: string) => void

  // Estado da UI
  notificationCenterOpen: boolean
  setNotificationCenterOpen: (open: boolean) => void
  progressBarMinimized: boolean
  minimizeProgressBar: () => void
  showProgressBar: () => void

  // Preferências
  preferences: NotificationPreferences
  updatePreferences: (prefs: Partial<NotificationPreferences>) => void
}

const NotificationContext = createContext<NotificationContextType | undefined>(undefined)

// Chaves do LocalStorage
const STORAGE_KEYS = {
  NOTIFICATIONS: 'notifications',
  ACTIVE_PROCESS: 'active_process',
  PROCESSING_DOCUMENTS: 'processing_documents',
  PROCESS_RESULTS: 'process_results',
  PROGRESS_BAR_STATE: 'progress_bar_state',
  PREFERENCES: 'notification_center_preferences',
}

// Constantes
const MAX_NOTIFICATIONS = 100
const MAX_NOTIFICATION_AGE_DAYS = 30

// Funções auxiliares para localStorage
function loadFromStorage<T>(key: string, defaultValue: T): T {
  if (typeof window === 'undefined') return defaultValue
  try {
    const item = localStorage.getItem(key)
    if (!item) return defaultValue
    const parsed = JSON.parse(item)
    // Converte strings de data de volta para objetos Date
    return convertDatesToObjects(parsed)
  } catch (error) {
    console.error(`Error loading ${key} from localStorage:`, error)
    return defaultValue
  }
}

function saveToStorage<T>(key: string, value: T): void {
  if (typeof window === 'undefined') return
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch (error) {
    console.error(`Error saving ${key} to localStorage:`, error)
  }
}

function convertDatesToObjects(obj: any): any {
  if (obj === null || obj === undefined) return obj
  if (typeof obj === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(obj)) {
    return new Date(obj)
  }
  if (Array.isArray(obj)) {
    return obj.map(convertDatesToObjects)
  }
  if (typeof obj === 'object') {
    const result: any = {}
    for (const key in obj) {
      result[key] = convertDatesToObjects(obj[key])
    }
    return result
  }
  return obj
}

function parseApiTimestamp(value: any): Date {
  if (!value) return new Date()
  if (value instanceof Date) return value
  if (typeof value === 'number') return new Date(value)
  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (!trimmed) return new Date()
    const hasTimezone = /[zZ]|[+-]\d{2}:?\d{2}$/.test(trimmed)
    const normalized = trimmed.replace(' ', 'T')
    return new Date(hasTimezone ? normalized : `${normalized}Z`)
  }
  return new Date(value)
}

function mapApiNotification(n: any): Notification {
  return {
    id: n.id,
    type: n.type,
    title: n.title,
    message: n.message,
    timestamp: parseApiTimestamp(n.created_at || n.timestamp || Date.now()),
    read: Boolean(n.read),
    actionUrl: n.action_url || n.actionUrl,
    actionLabel: n.action_label || n.actionLabel,
    metadata: n.metadata || undefined,
    variant: n.variant,
  }
}

function applyClearFilter(notifications: Notification[], lastClearedAt: Date | null): Notification[] {
  if (!lastClearedAt) return notifications
  const cutoff = lastClearedAt.getTime()
  return notifications.filter(n => {
    const ts = n.timestamp instanceof Date ? n.timestamp.getTime() : new Date(n.timestamp).getTime()
    return Number.isNaN(ts) ? true : ts > cutoff
  })
}

// Limpa notificações antigas e remove duplicadas
function filterResolvedProcessStarts(notifications: Notification[]): Notification[] {
  const resolvedIds = new Set<string>()

  for (const notif of notifications) {
    if (notif.type !== 'process_completed' && notif.type !== 'process_error') continue
    if (notif.metadata?.processId) resolvedIds.add(notif.metadata.processId)
    if (notif.metadata?.batchId) resolvedIds.add(notif.metadata.batchId)
  }

  if (resolvedIds.size === 0) return notifications

  return notifications.filter(notif => {
    if (notif.type !== 'process_started') return true
    const processId = notif.metadata?.processId
    const batchId = notif.metadata?.batchId
    if (processId && resolvedIds.has(processId)) return false
    if (batchId && resolvedIds.has(batchId)) return false
    return true
  })
}

function keepLatestProcessStarted(notifications: Notification[]): Notification[] {
  const processStarted = notifications.filter(n => n.type === 'process_started')
  if (processStarted.length <= 1) return notifications

  const latest = processStarted.reduce((acc, current) =>
    new Date(current.timestamp).getTime() > new Date(acc.timestamp).getTime()
      ? current
      : acc
  )

  return notifications.filter(n => n.type !== 'process_started' || n.id === latest.id)
}

function cleanupOldNotifications(notifications: Notification[]): Notification[] {
  const cutoffDate = new Date()
  cutoffDate.setDate(cutoffDate.getDate() - MAX_NOTIFICATION_AGE_DAYS)

  // Filtra notificações antigas
  const filtered = notifications.filter(n => new Date(n.timestamp) > cutoffDate)

  // Remove duplicadas (mesmo tipo, mensagem e metadata dentro de 1 minuto)
  const deduped: Notification[] = []
  for (const notif of filtered) {
    const isDuplicate = deduped.some(existing => {
      const timeDiff = Math.abs(new Date(notif.timestamp).getTime() - new Date(existing.timestamp).getTime())
      const withinOneMinute = timeDiff < 60000 // 1 minuto

      const sameTypeAndMessage = existing.type === notif.type && existing.message === notif.message

      const sameMetadata =
        (existing.metadata?.processId && existing.metadata?.processId === notif.metadata?.processId) ||
        (existing.metadata?.batchId && existing.metadata?.batchId === notif.metadata?.batchId) ||
        (existing.metadata?.documentId && existing.metadata?.documentId === notif.metadata?.documentId)

      return sameTypeAndMessage && withinOneMinute && sameMetadata
    })

    if (!isDuplicate) {
      deduped.push(notif)
    }
  }

  const normalized = keepLatestProcessStarted(filterResolvedProcessStarts(deduped))

  // Mantém apenas as MAX_NOTIFICATIONS mais recentes
  return normalized.slice(-MAX_NOTIFICATIONS)
}

// Componente Provider
export function NotificationProvider({ children }: { children: React.ReactNode }) {
  const { data: session } = useSession()
  // Estado
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [activeProcess, setActiveProcess] = useState<ProcessNotification | null>(null)
  const [processResults, setProcessResults] = useState<ProcessResult[]>([])
  const [processingDocuments, setProcessingDocuments] = useState<ProcessingDocumentState[]>([])
  const [processingProcessId, setProcessingProcessId] = useState<string | null>(null)
  const [notificationCenterOpen, setNotificationCenterOpen] = useState(false)
  const [progressBarState, setProgressBarState] = useState<ProgressBarState>({
    minimized: false,
    processId: null,
  })
  const [preferences, setPreferences] = useState<NotificationPreferences>({
    lastOpenedAt: null,
    autoMarkAsReadOnClick: true,
    lastClearedAt: null,
  })
  const lastClearedAtRef = useRef<Date | null>(null)
  const completionNotifiedRef = useRef(false)
  const errorNotifiedRef = useRef(false)
  const submittedByRef = useRef<string | undefined>(undefined)
  const pollingJobsRef = useRef<Set<string>>(new Set())
  const { startJob, pollJob } = useAsyncJob()

  // Carrega do backend na montagem (fallback localStorage)
  useEffect(() => {
    const loadedPrefs = loadFromStorage<NotificationPreferences>(STORAGE_KEYS.PREFERENCES, {
      lastOpenedAt: null,
      autoMarkAsReadOnClick: true,
      lastClearedAt: null,
    })
    lastClearedAtRef.current = loadedPrefs.lastClearedAt ?? null
    setPreferences(loadedPrefs)

    const load = async () => {
      const isLoginPage = typeof window !== 'undefined' && window.location.pathname === '/login'
      const shouldSkipRemote = !session?.accessToken || isLoginPage

      if (shouldSkipRemote) {
        const loadedNotifications = loadFromStorage<Notification[]>(STORAGE_KEYS.NOTIFICATIONS, [])
        const filtered = applyClearFilter(loadedNotifications, lastClearedAtRef.current)
        setNotifications(cleanupOldNotifications(filtered))
        return
      }
      try {
        const headers: Record<string, string> = {}
        if (session?.accessToken) {
          headers.Authorization = `Bearer ${session.accessToken}`
        }
        const response = await authFetch(API_ENDPOINTS.NOTIFICATIONS, { headers })
        if (!response.ok) throw new Error('Erro ao carregar notificações')
        const data = await response.json()
        const mapped = (data || []).map(mapApiNotification)
        const filtered = applyClearFilter(mapped, lastClearedAtRef.current)
        setNotifications(cleanupOldNotifications(filtered))
      } catch {
        const loadedNotifications = loadFromStorage<Notification[]>(STORAGE_KEYS.NOTIFICATIONS, [])
        const filtered = applyClearFilter(loadedNotifications, lastClearedAtRef.current)
        setNotifications(cleanupOldNotifications(filtered))
      }
    }
    load()

    const loadedProcess = loadFromStorage<ProcessNotification | null>(STORAGE_KEYS.ACTIVE_PROCESS, null)
    setActiveProcess(loadedProcess)
    setProcessingProcessId(loadedProcess?.id ?? null)

    const loadedProcessingDocs = loadFromStorage<ProcessingDocumentState[]>(
      STORAGE_KEYS.PROCESSING_DOCUMENTS,
      []
    )
    setProcessingDocuments(loadedProcessingDocs)

    const loadedResults = loadFromStorage<ProcessResult[]>(STORAGE_KEYS.PROCESS_RESULTS, [])
    setProcessResults(loadedResults)

    const loadedBarState = loadFromStorage<ProgressBarState>(STORAGE_KEYS.PROGRESS_BAR_STATE, {
      minimized: false,
      processId: null,
    })
    setProgressBarState(loadedBarState)

    // preferences already loaded above
  }, [session?.accessToken])

  // Salva no localStorage quando o estado muda
  useEffect(() => {
    saveToStorage(STORAGE_KEYS.NOTIFICATIONS, notifications)
  }, [notifications])

  useEffect(() => {
    saveToStorage(STORAGE_KEYS.ACTIVE_PROCESS, activeProcess)
  }, [activeProcess])

  useEffect(() => {
    saveToStorage(STORAGE_KEYS.PROCESSING_DOCUMENTS, processingDocuments)
  }, [processingDocuments])

  useEffect(() => {
    saveToStorage(STORAGE_KEYS.PROCESS_RESULTS, processResults)
  }, [processResults])

  useEffect(() => {
    saveToStorage(STORAGE_KEYS.PROGRESS_BAR_STATE, progressBarState)
  }, [progressBarState])

  useEffect(() => {
    saveToStorage(STORAGE_KEYS.PREFERENCES, preferences)
  }, [preferences])

  // Funções de notificação
  const addNotification = useCallback((input: CreateNotificationInput): string => {
    const notification: Notification = {
      ...input,
      id: `notif-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      timestamp: new Date(),
    }

    setNotifications(prev => {
      // Verifica notificações duplicadas com múltiplos critérios
      const fiveSecondsAgo = new Date(Date.now() - 5000)
      const isDuplicate = prev.some(existing => {
        // Mesmo tipo e mensagem
        const sameTypeAndMessage = existing.type === notification.type && existing.message === notification.message

        // Timestamp recente (dentro de 5 segundos)
        const isRecent = existing.timestamp > fiveSecondsAgo

        // Mesmos metadados (processId, batchId, ou documentId)
        const sameMetadata =
          (existing.metadata?.processId && existing.metadata?.processId === notification.metadata?.processId) ||
          (existing.metadata?.batchId && existing.metadata?.batchId === notification.metadata?.batchId) ||
          (existing.metadata?.documentId && existing.metadata?.documentId === notification.metadata?.documentId)

        return sameTypeAndMessage && (isRecent || sameMetadata)
      })

      if (isDuplicate) {
        console.log('Duplicate notification prevented:', notification.type, notification.message)
        return prev
      }

      return cleanupOldNotifications([...prev, notification])
    })

    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (session?.accessToken) {
      headers.Authorization = `Bearer ${session.accessToken}`
    }
    if (session?.accessToken) {
      authFetch(API_ENDPOINTS.NOTIFICATIONS, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          type: input.type,
          title: input.title,
          message: input.message,
          variant: input.variant,
          action_url: input.actionUrl,
          action_label: input.actionLabel,
          metadata: input.metadata,
          document_id: input.metadata?.documentId,
        }),
      })
        .then(async (res) => {
          if (!res.ok) return
          const created = mapApiNotification(await res.json())
          setNotifications(prev => cleanupOldNotifications([
            ...prev.filter(n => n.id !== notification.id),
            created,
          ]))
        })
        .catch(() => {})
    }

    return notification.id
  }, [session?.accessToken])

  const markAsRead = useCallback((id: string) => {
    setNotifications(prev =>
      prev.map(n => n.id === id ? { ...n, read: true } : n)
    )
    const headers: Record<string, string> = {}
    if (session?.accessToken) {
      headers.Authorization = `Bearer ${session.accessToken}`
    }
    if (session?.accessToken) {
      authFetch(API_ENDPOINTS.NOTIFICATION_READ(id), { method: 'POST', headers }).catch(() => {})
    }
  }, [session?.accessToken])

  const markAllAsRead = useCallback(() => {
    setNotifications(prev => prev.map(n => ({ ...n, read: true })))
    const headers: Record<string, string> = {}
    if (session?.accessToken) {
      headers.Authorization = `Bearer ${session.accessToken}`
    }
    if (session?.accessToken) {
      authFetch(API_ENDPOINTS.NOTIFICATIONS_READ_ALL, { method: 'POST', headers }).catch(() => {})
    }
  }, [session?.accessToken])

  const clearHistory = useCallback(() => {
    const clearedAt = new Date()
    lastClearedAtRef.current = clearedAt
    setNotifications([])
    setPreferences(prev => ({ ...prev, lastClearedAt: clearedAt }))
    const headers: Record<string, string> = {}
    if (session?.accessToken) {
      headers.Authorization = `Bearer ${session.accessToken}`
    }
    if (session?.accessToken) {
      authFetch(API_ENDPOINTS.NOTIFICATIONS_CLEAR, { method: 'DELETE', headers }).catch(() => {})
    }
  }, [session?.accessToken])

  const getNotificationById = useCallback((id: string) => {
    return notifications.find(n => n.id === id)
  }, [notifications])

  const unreadCount = notifications.filter(n => !n.read).length

  // Funções de processo
  const startProcess = useCallback((input: CreateProcessInput): string => {
    const processId = `process-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
    const process: ProcessNotification = {
      id: processId,
      ...input,
      status: 'processing',
      progress: 0,
      currentStep: 'upload',
      stepMessage: 'Iniciando upload...',
      startedAt: new Date(),
      documents: Array.from({ length: input.documentCount }, (_, i) => ({
        filename: `doc-${i + 1}`,
        status: 'pending',
        progress: 0,
      })),
    }

    setActiveProcess(process)
    setProgressBarState({
      minimized: false,
      processId,
    })

    setNotifications(prev => prev.filter(n => n.type !== 'process_started'))

    // Adiciona notificação
    addNotification({
      type: 'process_started',
      title: 'Processamento Iniciado',
      message: `Iniciando processamento de ${input.documentCount} documento(s)`,
      read: false,
      variant: 'default',
      metadata: {
        processId,
        batchId: input.batchId,
        documentCount: input.documentCount,
      },
    })

    return processId
  }, [addNotification])

  const updateProcess = useCallback((processId: string, update: Partial<ProcessNotification>) => {
    setActiveProcess(prev => {
      if (!prev || prev.id !== processId) return prev
      return { ...prev, ...update }
    })
  }, [])

  const completeProcess = useCallback((processId: string, results: ProcessResult[]) => {
    setActiveProcess(prev => {
      if (!prev || prev.id !== processId) return prev

      const completed: ProcessNotification = {
        ...prev,
        status: 'completed',
        progress: 100,
        currentStep: 'completed',
        stepMessage: 'Processamento concluído',
        completedAt: new Date(),
      }

      setNotifications(prevNotifications =>
        prevNotifications.filter(
          notif => !(notif.type === 'process_started' && notif.metadata?.processId === processId)
        )
      )

      // Adiciona resultados aos resultados de processo (sem duplicar por id)
      setProcessResults(prevResults => {
        const merged = [...prevResults]
        for (const result of results) {
          const index = merged.findIndex(r => r.id === result.id)
          if (index >= 0) {
            merged[index] = result
          } else {
            merged.push(result)
          }
        }
        return merged
      })

      // Adiciona notificação de conclusão
      const approved = results.filter(r => r.status === 'approved').length
      const rejected = results.filter(r => r.status === 'rejected').length
      const pending = results.filter(r => r.status === 'pending_review').length

      let message = ''
      let variant: 'success' | 'warning' | 'error' = 'success'

      if (rejected === 0 && pending === 0) {
        message = `Todos os ${approved} documentos foram aprovados!`
        variant = 'success'
      } else if (rejected > 0) {
        message = `${approved} aprovados, ${rejected} rejeitados, ${pending} pendentes`
        variant = 'warning'
      } else {
        message = `${approved} aprovados, ${pending} pendentes de revisão`
        variant = 'warning'
      }

      addNotification({
        type: 'process_completed',
        title: 'Processamento Concluído',
        message,
        read: false,
        variant,
        actionUrl: results.length > 0 ? `/historico?viewId=${results[0].id}` : '/historico',
        actionLabel: 'Ver Resultados',
        metadata: {
          processId,
          batchId: prev.batchId,
          documentCount: results.length,
        },
      })

      // Auto-oculta a barra de progresso após 5 segundos
      setTimeout(() => {
        setActiveProcess(null)
        setProgressBarState({ minimized: false, processId: null })
      }, 5000)

      return completed
    })
  }, [addNotification])

  const failProcess = useCallback((processId: string, error: string) => {
    setActiveProcess(prev => {
      if (!prev || prev.id !== processId) return prev

      setNotifications(prevNotifications =>
        prevNotifications.filter(
          notif => !(notif.type === 'process_started' && notif.metadata?.processId === processId)
        )
      )

      // Adiciona notificação de erro
      addNotification({
        type: 'process_error',
        title: 'Erro no Processamento',
        message: error,
        read: false,
        variant: 'error',
        metadata: {
          processId,
          batchId: prev.batchId,
        },
      })

      // Limpa o processo ativo
      setTimeout(() => {
        setActiveProcess(null)
        setProgressBarState({ minimized: false, processId: null })
      }, 5000)

      return {
        ...prev,
        status: 'error',
        error,
        stepMessage: 'Erro no processamento',
      }
    })
  }, [addNotification])

  const updateProcessingDocument = useCallback(
    (docId: string, updater: (doc: ProcessingDocumentState) => ProcessingDocumentState) => {
      setProcessingDocuments(prev =>
        prev.map(doc => {
          if (doc.id !== docId) return doc
          const updated = updater(doc)
          return {
            ...updated,
            lastUpdatedAt: new Date(),
          }
        })
      )
    },
    []
  )

  const startPollingForDocument = useCallback(
    (docId: string, jobId: string) => {
      if (pollingJobsRef.current.has(jobId)) return
      pollingJobsRef.current.add(jobId)

      pollJob(jobId, {
        interval: 2000,
        timeout: 0,
        onProgress: (job: Job) => {
          const stepToStage: Record<string, ProcessingStage> = {
            pending: 'upload',
            upload: 'upload',
            ocr: 'ocr',
            brmed: 'brnet',
            validacao: 'validation',
            concluido: 'completed',
            erro: 'upload',
          }

          updateProcessingDocument(docId, (current) => ({
            ...current,
            progress: job.progress,
            stage: stepToStage[job.current_step] || current.stage,
            statusMessage: job.message || current.statusMessage,
          }))
        },
        onComplete: (result: DocumentProcessingResult) => {
          updateProcessingDocument(docId, (current) => ({
            ...current,
            stage: 'completed',
            progress: 100,
            displayProgress: 100,
            statusMessage: 'Processamento concluído!',
            result,
          }))
          pollingJobsRef.current.delete(jobId)
        },
        onError: (error: string) => {
          updateProcessingDocument(docId, (current) => ({
            ...current,
            error: `Erro: ${error}`,
            statusMessage: 'Erro no processamento',
          }))
          pollingJobsRef.current.delete(jobId)
        },
      }).catch(() => {
        pollingJobsRef.current.delete(jobId)
      })
    },
    [pollJob, updateProcessingDocument]
  )

  const startBackgroundProcessing = useCallback(
    (files: File[], options: StartBackgroundProcessingOptions = {}) => {
      if (!files || files.length === 0) return null

      const initialDocs: ProcessingDocumentState[] = files.map((file, index) => ({
        id: `doc-${Date.now()}-${index}`,
        file,
        fileName: file.name,
        fileSize: file.size,
        stage: 'upload' as ProcessingStage,
        progress: 0,
        displayProgress: 0,
        statusMessage: 'Preparando envio...',
        lastUpdatedAt: new Date(),
      }))

      setProcessingDocuments(initialDocs)
      completionNotifiedRef.current = false
      errorNotifiedRef.current = false
      submittedByRef.current = options.submittedBy

      const batchId = `batch-${Date.now()}`
      const filename =
        files.length === 1 ? files[0].name : `${files.length} documentos`

      const processId = startProcess({
        batchId,
        filename,
        documentCount: files.length,
        originPath: options.originPath,
      })

      setProcessingProcessId(processId)

      initialDocs.forEach((doc) => {
        if (!doc.file) {
          updateProcessingDocument(doc.id, (current) => ({
            ...current,
            error: 'Arquivo indisponível para processamento.',
            statusMessage: 'Arquivo indisponível',
          }))
          return
        }

        startJob(doc.file, [])
          .then((jobId) => {
            updateProcessingDocument(doc.id, (current) => ({
              ...current,
              jobId,
              statusMessage: current.statusMessage || 'Upload enviado...',
            }))

            startPollingForDocument(doc.id, jobId)
          })
          .catch((error) => {
            const message =
              error instanceof Error ? error.message : 'Erro ao iniciar processamento'
            updateProcessingDocument(doc.id, (current) => ({
              ...current,
              error: `Erro: ${message}`,
              statusMessage: 'Erro ao iniciar processamento',
            }))
            failProcess(processId, message)
          })
      })

      return processId
    },
    [failProcess, startJob, startProcess, startPollingForDocument, updateProcessingDocument]
  )

  useEffect(() => {
    if (processingDocuments.length === 0) return
    const interval = setInterval(() => {
      setProcessingDocuments((prev) =>
        prev.map((doc) => {
          if (doc.displayProgress === doc.progress) return doc
          const delta = doc.progress - doc.displayProgress
          if (delta <= 0) return doc
          const step = Math.max(1, Math.ceil(delta / 12))
          return {
            ...doc,
            displayProgress: Math.min(doc.progress, doc.displayProgress + step),
          }
        })
      )
    }, 200)

    return () => clearInterval(interval)
  }, [processingDocuments.length])

  useEffect(() => {
    if (!processingProcessId || processingDocuments.length === 0) return

    const avgProgress = Math.round(
      processingDocuments.reduce((sum, d) => sum + d.displayProgress, 0) /
        processingDocuments.length
    )

    let currentStep: ProcessStep = 'upload'
    if (avgProgress === 0) {
      currentStep = 'upload'
    } else if (avgProgress > 0 && avgProgress < 30) {
      currentStep = 'ocr'
    } else if (avgProgress >= 30 && avgProgress < 60) {
      currentStep = 'brmed'
    } else if (avgProgress >= 60 && avgProgress < 100) {
      currentStep = 'validation'
    } else if (avgProgress === 100) {
      currentStep = 'completed'
    }

    const processingDoc = processingDocuments.find(
      d => d.progress > 0 && d.progress < 100
    )
    const statusMessage = processingDoc?.statusMessage || 'Processando...'

    updateProcess(processingProcessId, {
      progress: avgProgress,
      currentStep,
      stepMessage: statusMessage,
      documents: processingDocuments.map((doc) => ({
        filename: doc.file?.name ?? doc.fileName ?? 'Documento',
        status: doc.error
          ? ('error' as const)
          : doc.stage === 'completed'
          ? ('completed' as const)
          : doc.progress > 0
          ? ('processing' as const)
          : ('pending' as const),
        progress: doc.displayProgress,
        error: doc.error,
      })),
    })

    const errorDoc = processingDocuments.find((doc) => doc.error)
    if (errorDoc?.error && !errorNotifiedRef.current) {
      errorNotifiedRef.current = true
      failProcess(processingProcessId, errorDoc.error)
    }
  }, [processingDocuments, processingProcessId, updateProcess, failProcess])

  useEffect(() => {
    if (!processingProcessId || processingDocuments.length === 0) return
    if (completionNotifiedRef.current) return

    const allCompleted = processingDocuments.every(
      (doc) => doc.stage === 'completed' || doc.error
    )
    if (!allCompleted) return

    completionNotifiedRef.current = true

    const processResults = processingDocuments.map((doc) => {
      const tabelaComparacao = doc.result?.tabela_comparacao || []
      const examesFaltantes = tabelaComparacao.filter(
        (e) => e.status === 'faltante'
      ).length
      const examesExtras = tabelaComparacao.filter(
        (e) => e.status === 'extra_no_ocr'
      ).length
      const analysisDetails = doc.result?.analysis_details
      const normalizedAnalysisDetails =
        analysisDetails?.quality &&
        analysisDetails?.field_checks &&
        analysisDetails?.match_confidence
          ? {
              quality: analysisDetails.quality,
              field_checks: analysisDetails.field_checks,
              match_confidence: analysisDetails.match_confidence,
            }
          : undefined

      return {
        id: doc.result?.document_id || doc.id,
        batchId: processingProcessId,
        filename: doc.file?.name ?? doc.fileName ?? 'Documento',
        cpf: doc.result?.cpf_processado || 'N/A',
        patientName: doc.result?.patient_name || 'Paciente',
        uploadedAt: new Date(),
        processedAt: new Date(),
        status: doc.error
          ? ('rejected' as const)
          : examesFaltantes === 0
          ? ('approved' as const)
          : ('pending_review' as const),
        rejectionReason: doc.error,
        examesFaltantes,
        examesExtras,
        result: {
          cpf: doc.result?.cpf_processado || '',
          patient_name: doc.result?.patient_name,
          status: doc.error ? ('error' as const) : ('success' as const),
          ocr_result: {
            text: '',
            exames_extraidos: doc.result?.exames_ocr || [],
          },
          brmed_result: {
            exames_obrigatorios: doc.result?.exames_brnet || [],
          },
          tabela_comparacao: doc.result?.tabela_comparacao || [],
          analysis_details: normalizedAnalysisDetails,
          validation_result: {
            exames_faltantes: tabelaComparacao
              .filter((e) => e.status === 'faltante')
              .map((e) => e.exame),
            exames_extras: tabelaComparacao
              .filter((e) => e.status === 'extra_no_ocr')
              .map((e) => e.exame),
            analysis: doc.result?.analise_comparacao,
          },
          error: doc.error,
        },
        submittedBy: submittedByRef.current || 'usuario@grupobrmed.com.br',
      }
    })

    completeProcess(processingProcessId, processResults)
  }, [processingDocuments, processingProcessId, completeProcess])

  useEffect(() => {
    const hasInFlight = processingDocuments.some(
      (doc) => !doc.error && doc.stage !== 'completed'
    )
    if (hasInFlight) return

    setNotifications((prev) => prev.filter((n) => n.type !== 'process_started'))
  }, [processingDocuments])

  const addProcessResult = useCallback((result: ProcessResult) => {
    setProcessResults(prev => [...prev, result])
  }, [])

  const clearProcessingState = useCallback(() => {
    setProcessingDocuments([])
    setProcessingProcessId(null)
    setActiveProcess(null)
    setProgressBarState({ minimized: false, processId: null })
    completionNotifiedRef.current = false
    errorNotifiedRef.current = false
    pollingJobsRef.current.clear()
  }, [])

  const getResultsByBatchId = useCallback((batchId: string) => {
    return processResults.filter(r => r.batchId === batchId)
  }, [processResults])

  const updateProcessResultStatus = useCallback((
    id: string,
    status: 'approved' | 'rejected' | 'pending_review',
    reviewerEmail: string,
    rejectionReason?: string,
    approvalReason?: string
  ) => {
    setProcessResults(prev =>
      prev.map(result =>
        result.id === id
          ? {
              ...result,
              status,
              reviewedBy: reviewerEmail,
              reviewedAt: new Date(),
              rejectionReason: rejectionReason || result.rejectionReason,
              approvalReason: approvalReason || result.approvalReason,
            }
          : result
      )
    )
  }, [])

  // Funções da barra de progresso
  const minimizeProgressBar = useCallback(() => {
    setProgressBarState(prev => ({ ...prev, minimized: true }))
  }, [])

  const showProgressBar = useCallback(() => {
    setProgressBarState(prev => ({ ...prev, minimized: false }))
  }, [])

  const progressBarMinimized = progressBarState.minimized

  // Funções de preferências
  const updatePreferences = useCallback((prefs: Partial<NotificationPreferences>) => {
    setPreferences(prev => {
      const next = { ...prev, ...prefs }
      if (prefs.lastClearedAt) {
        lastClearedAtRef.current = prefs.lastClearedAt
      }
      return next
    })
  }, [])

  // Atualiza última abertura quando o centro de notificações abre
  useEffect(() => {
    if (notificationCenterOpen) {
      updatePreferences({ lastOpenedAt: new Date() })
    }
  }, [notificationCenterOpen, updatePreferences])

  useEffect(() => {
    if (!session?.accessToken) return
    let cancelled = false

    const fetchNotifications = async () => {
      const headers: Record<string, string> = { Authorization: `Bearer ${session.accessToken}` }
      try {
        const response = await authFetch(API_ENDPOINTS.NOTIFICATIONS, { headers })
        if (!response.ok) return
        const data = await response.json()
        const incoming = (data || []).map(mapApiNotification)
        const filteredIncoming = applyClearFilter(incoming, lastClearedAtRef.current)
        setNotifications(prev => {
          const byId = new Map<string, Notification>()
          prev.forEach(n => byId.set(n.id, n))
          filteredIncoming.forEach(n => {
            const existing = byId.get(n.id)
            byId.set(n.id, {
              ...existing,
              ...n,
              read: existing?.read || n.read,
            })
          })
          const merged = Array.from(byId.values())
          return cleanupOldNotifications(merged)
        })
      } catch {
        if (cancelled) return
      }
    }

    fetchNotifications()
    const interval = setInterval(fetchNotifications, 10000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [session?.accessToken])

  useEffect(() => {
    if (processingDocuments.length === 0) return

    processingDocuments.forEach((doc) => {
      if (!doc.jobId) return
      if (doc.stage === 'completed' || doc.error) return
      startPollingForDocument(doc.id, doc.jobId)
    })
  }, [processingDocuments, startPollingForDocument])

  const value: NotificationContextType = {
    notifications,
    unreadCount,
    addNotification,
    markAsRead,
    markAllAsRead,
    clearHistory,
    getNotificationById,
    activeProcess,
    startProcess,
    updateProcess,
    completeProcess,
    failProcess,
    processingDocuments,
    startBackgroundProcessing,
    clearProcessingState,
    processResults,
    addProcessResult,
    getResultsByBatchId,
    updateProcessResultStatus,
    notificationCenterOpen,
    setNotificationCenterOpen,
    progressBarMinimized,
    minimizeProgressBar,
    showProgressBar,
    preferences,
    updatePreferences,
  }

  return (
    <NotificationContext.Provider value={value}>
      {children}
    </NotificationContext.Provider>
  )
}

// Hook para usar o contexto
export function useNotifications() {
  const context = useContext(NotificationContext)
  if (context === undefined) {
    throw new Error('useNotifications must be used within a NotificationProvider')
  }
  return context
}
