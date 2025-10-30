// Types for the notification system

export type NotificationType =
  | 'process_started'
  | 'process_completed'
  | 'process_error'
  | 'review_approved'
  | 'review_rejected'
  | 'system_message'

export type NotificationVariant = 'default' | 'success' | 'error' | 'warning'

export interface Notification {
  id: string
  type: NotificationType
  title: string
  message: string
  timestamp: Date
  read: boolean
  actionUrl?: string  // Para navegação direta
  actionLabel?: string  // Ex: "Ver Resultados", "Baixar PDF"
  metadata?: {
    processId?: string
    batchId?: string
    documentId?: string
    cpf?: string
    reviewerEmail?: string
    documentCount?: number
    status?: string
  }
  variant?: NotificationVariant
}

// Helper type for creating new notifications (without auto-generated fields)
export type CreateNotificationInput = Omit<Notification, 'id' | 'timestamp'>

// Preferences for notification center UI
export interface NotificationPreferences {
  lastOpenedAt: Date | null
  autoMarkAsReadOnClick: boolean
}
