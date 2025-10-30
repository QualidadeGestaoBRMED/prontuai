'use client'

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'
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

// Context interface
interface NotificationContextType {
  // Notifications
  notifications: Notification[]
  unreadCount: number
  addNotification: (notification: CreateNotificationInput) => string
  markAsRead: (id: string) => void
  markAllAsRead: () => void
  clearHistory: () => void
  getNotificationById: (id: string) => Notification | undefined

  // Active processes
  activeProcess: ProcessNotification | null
  startProcess: (input: CreateProcessInput) => string
  updateProcess: (processId: string, update: Partial<ProcessNotification>) => void
  completeProcess: (processId: string, results: ProcessResult[]) => void
  failProcess: (processId: string, error: string) => void

  // Process results
  processResults: ProcessResult[]
  addProcessResult: (result: ProcessResult) => void
  getResultsByBatchId: (batchId: string) => ProcessResult[]

  // UI State
  notificationCenterOpen: boolean
  setNotificationCenterOpen: (open: boolean) => void
  progressBarMinimized: boolean
  minimizeProgressBar: () => void
  showProgressBar: () => void

  // Preferences
  preferences: NotificationPreferences
  updatePreferences: (prefs: Partial<NotificationPreferences>) => void
}

const NotificationContext = createContext<NotificationContextType | undefined>(undefined)

// LocalStorage keys
const STORAGE_KEYS = {
  NOTIFICATIONS: 'notifications',
  ACTIVE_PROCESS: 'active_process',
  PROCESS_RESULTS: 'process_results',
  PROGRESS_BAR_STATE: 'progress_bar_state',
  PREFERENCES: 'notification_center_preferences',
}

// Constants
const MAX_NOTIFICATIONS = 100
const MAX_NOTIFICATION_AGE_DAYS = 30

// Helper functions for localStorage
function loadFromStorage<T>(key: string, defaultValue: T): T {
  if (typeof window === 'undefined') return defaultValue
  try {
    const item = localStorage.getItem(key)
    if (!item) return defaultValue
    const parsed = JSON.parse(item)
    // Convert date strings back to Date objects
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

// Cleanup old notifications
function cleanupOldNotifications(notifications: Notification[]): Notification[] {
  const cutoffDate = new Date()
  cutoffDate.setDate(cutoffDate.getDate() - MAX_NOTIFICATION_AGE_DAYS)

  return notifications
    .filter(n => new Date(n.timestamp) > cutoffDate)
    .slice(-MAX_NOTIFICATIONS)
}

// Provider component
export function NotificationProvider({ children }: { children: React.ReactNode }) {
  // State
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

  // Load from localStorage on mount
  useEffect(() => {
    const loadedNotifications = loadFromStorage<Notification[]>(STORAGE_KEYS.NOTIFICATIONS, [])
    const cleanedNotifications = cleanupOldNotifications(loadedNotifications)
    setNotifications(cleanedNotifications)

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
  }, [])

  // Save to localStorage when state changes
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

  // Notification functions
  const addNotification = useCallback((input: CreateNotificationInput): string => {
    const notification: Notification = {
      ...input,
      id: `notif-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      timestamp: new Date(),
    }
    setNotifications(prev => cleanupOldNotifications([...prev, notification]))
    return notification.id
  }, [])

  const markAsRead = useCallback((id: string) => {
    setNotifications(prev =>
      prev.map(n => n.id === id ? { ...n, read: true } : n)
    )
  }, [])

  const markAllAsRead = useCallback(() => {
    setNotifications(prev => prev.map(n => ({ ...n, read: true })))
  }, [])

  const clearHistory = useCallback(() => {
    setNotifications([])
  }, [])

  const getNotificationById = useCallback((id: string) => {
    return notifications.find(n => n.id === id)
  }, [notifications])

  const unreadCount = notifications.filter(n => !n.read).length

  // Process functions
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

    // Add notification
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

      // Add results to process results
      setProcessResults(prevResults => [...prevResults, ...results])

      // Add completion notification
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

      // Auto-hide progress bar after 5 seconds
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

      // Add error notification
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

      // Clear active process
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

  // Progress bar functions
  const minimizeProgressBar = useCallback(() => {
    setProgressBarState(prev => ({ ...prev, minimized: true }))
  }, [])

  const showProgressBar = useCallback(() => {
    setProgressBarState(prev => ({ ...prev, minimized: false }))
  }, [])

  const progressBarMinimized = progressBarState.minimized

  // Preferences functions
  const updatePreferences = useCallback((prefs: Partial<NotificationPreferences>) => {
    setPreferences(prev => ({ ...prev, ...prefs }))
  }, [])

  // Update last opened when notification center opens
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

// Hook to use the context
export function useNotifications() {
  const context = useContext(NotificationContext)
  if (context === undefined) {
    throw new Error('useNotifications must be used within a NotificationProvider')
  }
  return context
}
