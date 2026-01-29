'use client'

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'
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
  CreateProcessInput
} from '@/types/process'
import { API_ENDPOINTS } from '@/lib/config'

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

// Limpa notificações antigas e remove duplicadas
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

  // Mantém apenas as MAX_NOTIFICATIONS mais recentes
  return deduped.slice(-MAX_NOTIFICATIONS)
}

// Componente Provider
export function NotificationProvider({ children }: { children: React.ReactNode }) {
  const { data: session } = useSession()
  // Estado
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [activeProcess, setActiveProcess] = useState<ProcessNotification | null>(null)
  const [processResults, setProcessResults] = useState<ProcessResult[]>([])
  const [notificationCenterOpen, setNotificationCenterOpen] = useState(false)
  const [progressBarState, setProgressBarState] = useState<ProgressBarState>({
    minimized: false,
    processId: null,
  })
  const [preferences, setPreferences] = useState<NotificationPreferences>({
    lastOpenedAt: null,
    autoMarkAsReadOnClick: true,
  })

  // Carrega do backend na montagem (fallback localStorage)
  useEffect(() => {
    const load = async () => {
      try {
        const headers: Record<string, string> = {}
        if (session?.accessToken) {
          headers.Authorization = `Bearer ${session.accessToken}`
        }
        const response = await fetch(API_ENDPOINTS.NOTIFICATIONS, { headers })
        if (!response.ok) throw new Error('Erro ao carregar notificações')
        const data = await response.json()
        setNotifications(cleanupOldNotifications((data || []).map(mapApiNotification)))
      } catch {
        const loadedNotifications = loadFromStorage<Notification[]>(STORAGE_KEYS.NOTIFICATIONS, [])
        setNotifications(cleanupOldNotifications(loadedNotifications))
      }
    }
    load()

    const loadedProcess = loadFromStorage<ProcessNotification | null>(STORAGE_KEYS.ACTIVE_PROCESS, null)
    setActiveProcess(loadedProcess)

    const loadedResults = loadFromStorage<ProcessResult[]>(STORAGE_KEYS.PROCESS_RESULTS, [])
    setProcessResults(loadedResults)

    const loadedBarState = loadFromStorage<ProgressBarState>(STORAGE_KEYS.PROGRESS_BAR_STATE, {
      minimized: false,
      processId: null,
    })
    setProgressBarState(loadedBarState)

    const loadedPrefs = loadFromStorage<NotificationPreferences>(STORAGE_KEYS.PREFERENCES, {
      lastOpenedAt: null,
      autoMarkAsReadOnClick: true,
    })
    setPreferences(loadedPrefs)
  }, [session?.accessToken])

  // Salva no localStorage quando o estado muda
  useEffect(() => {
    saveToStorage(STORAGE_KEYS.NOTIFICATIONS, notifications)
  }, [notifications])

  useEffect(() => {
    saveToStorage(STORAGE_KEYS.ACTIVE_PROCESS, activeProcess)
  }, [activeProcess])

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
      fetch(API_ENDPOINTS.NOTIFICATIONS, {
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
      fetch(API_ENDPOINTS.NOTIFICATION_READ(id), { method: 'POST', headers }).catch(() => {})
    }
  }, [session?.accessToken])

  const markAllAsRead = useCallback(() => {
    setNotifications(prev => prev.map(n => ({ ...n, read: true })))
    const headers: Record<string, string> = {}
    if (session?.accessToken) {
      headers.Authorization = `Bearer ${session.accessToken}`
    }
    if (session?.accessToken) {
      fetch(API_ENDPOINTS.NOTIFICATIONS_READ_ALL, { method: 'POST', headers }).catch(() => {})
    }
  }, [session?.accessToken])

  const clearHistory = useCallback(() => {
    setNotifications([])
    const headers: Record<string, string> = {}
    if (session?.accessToken) {
      headers.Authorization = `Bearer ${session.accessToken}`
    }
    if (session?.accessToken) {
      fetch(API_ENDPOINTS.NOTIFICATIONS_READ_ALL, { method: 'POST', headers }).catch(() => {})
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

  const addProcessResult = useCallback((result: ProcessResult) => {
    setProcessResults(prev => [...prev, result])
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
    setPreferences(prev => ({ ...prev, ...prefs }))
  }, [])

  // Atualiza última abertura quando o centro de notificações abre
  useEffect(() => {
    if (notificationCenterOpen) {
      updatePreferences({ lastOpenedAt: new Date() })
    }
  }, [notificationCenterOpen, updatePreferences])

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
