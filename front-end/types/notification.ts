// Tipos para o sistema de notificações

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
    approvalReason?: string
  }
  variant?: NotificationVariant
}

// Tipo auxiliar para criar novas notificações (sem campos auto-gerados)
export type CreateNotificationInput = Omit<Notification, 'id' | 'timestamp'>

// Preferências para UI do centro de notificações
export interface NotificationPreferences {
  lastOpenedAt: Date | null
  autoMarkAsReadOnClick: boolean
}
