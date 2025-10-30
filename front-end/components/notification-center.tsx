'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { formatDistanceToNow } from 'date-fns'
import { ptBR } from 'date-fns/locale'
import {
  CheckCircle2,
  XCircle,
  AlertCircle,
  Info,
  Loader2,
  ChevronRight,
  CheckCheck,
  Trash2,
  Eye,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import { useNotifications } from '@/hooks/use-notifications'
import { Notification } from '@/types/notification'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { Progress } from '@/components/ui/progress'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

// Get icon for notification type
function getNotificationIcon(notification: Notification) {
  switch (notification.type) {
    case 'process_completed':
      return notification.variant === 'success' ? (
        <CheckCircle2 className="h-5 w-5 text-green-500" />
      ) : (
        <AlertCircle className="h-5 w-5 text-yellow-500" />
      )
    case 'process_error':
      return <XCircle className="h-5 w-5 text-red-500" />
    case 'process_started':
      return <Loader2 className="h-5 w-5 text-blue-500 animate-spin" />
    case 'review_approved':
      return <CheckCircle2 className="h-5 w-5 text-green-500" />
    case 'review_rejected':
      return <XCircle className="h-5 w-5 text-red-500" />
    case 'system_message':
      return <Info className="h-5 w-5 text-blue-500" />
    default:
      return <Info className="h-5 w-5 text-gray-500" />
  }
}

// Individual notification item
function NotificationItem({
  notification,
  onMarkAsRead,
  onNavigate,
}: {
  notification: Notification
  onMarkAsRead: (id: string) => void
  onNavigate: (url: string) => void
}) {
  return (
    <div
      className={cn(
        'group flex gap-3 p-4 rounded-lg transition-colors cursor-pointer border',
        notification.read
          ? 'bg-transparent border-transparent hover:bg-muted/50'
          : 'bg-muted/30 border-muted-foreground/10 hover:bg-muted/50'
      )}
      onClick={() => {
        if (!notification.read) {
          onMarkAsRead(notification.id)
        }
        if (notification.actionUrl) {
          onNavigate(notification.actionUrl)
        }
      }}
    >
      {/* Icon */}
      <div className="flex-shrink-0 mt-0.5">
        {getNotificationIcon(notification)}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0 space-y-1">
        <div className="flex items-start justify-between gap-2">
          <p className="text-sm font-medium leading-none">
            {notification.title}
          </p>
          {!notification.read && (
            <div className="h-2 w-2 rounded-full bg-blue-500 flex-shrink-0 mt-1" />
          )}
        </div>

        <p className="text-sm text-muted-foreground line-clamp-2">
          {notification.message}
        </p>

        <div className="flex items-center justify-between gap-2 pt-1">
          <p className="text-xs text-muted-foreground">
            {formatDistanceToNow(new Date(notification.timestamp), {
              addSuffix: true,
              locale: ptBR,
            })}
          </p>

          {notification.actionLabel && (
            <Button
              variant="ghost"
              size="sm"
              className="h-auto py-1 px-2 text-xs opacity-0 group-hover:opacity-100 transition-opacity"
            >
              {notification.actionLabel}
              <ChevronRight className="h-3 w-3 ml-1" />
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

// Active process display
function ActiveProcessDisplay() {
  const { activeProcess, showProgressBar } = useNotifications()

  if (!activeProcess) return null

  const completedDocs = activeProcess.documents.filter(
    d => d.status === 'completed'
  ).length

  return (
    <div className="p-4 rounded-lg border bg-card space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
            <p className="text-sm font-medium">
              {activeProcess.stepMessage}
            </p>
          </div>
          <p className="text-xs text-muted-foreground">
            {activeProcess.filename} ({completedDocs}/{activeProcess.documentCount} documentos)
          </p>
        </div>
        <Badge variant="secondary" className="text-xs">
          {activeProcess.progress}%
        </Badge>
      </div>

      <Progress value={activeProcess.progress} className="h-2" />

      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          className="flex-1 h-8 text-xs"
          onClick={showProgressBar}
        >
          <Eye className="h-3 w-3 mr-1" />
          Ver Detalhes
        </Button>
      </div>
    </div>
  )
}

// Notification section (collapsible)
function NotificationSection({
  title,
  count,
  notifications,
  emptyMessage,
  defaultOpen = true,
  onMarkAsRead,
  onNavigate,
}: {
  title: string
  count: number
  notifications: Notification[]
  emptyMessage: string
  defaultOpen?: boolean
  onMarkAsRead: (id: string) => void
  onNavigate: (url: string) => void
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen)

  return (
    <div className="space-y-2">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center justify-between w-full p-2 rounded-md hover:bg-muted/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold">
            {title}
          </h3>
          {count > 0 && (
            <Badge variant="secondary" className="h-5 px-1.5 text-xs">
              {count}
            </Badge>
          )}
        </div>
        {isOpen ? (
          <ChevronUp className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        )}
      </button>

      {isOpen && (
        <div className="space-y-2">
          {notifications.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">
              {emptyMessage}
            </p>
          ) : (
            notifications.map(notification => (
              <NotificationItem
                key={notification.id}
                notification={notification}
                onMarkAsRead={onMarkAsRead}
                onNavigate={onNavigate}
              />
            ))
          )}
        </div>
      )}
    </div>
  )
}

// Main notification center component
export function NotificationCenter() {
  const router = useRouter()
  const {
    notifications,
    unreadCount,
    notificationCenterOpen,
    setNotificationCenterOpen,
    markAsRead,
    markAllAsRead,
    clearHistory,
    activeProcess,
  } = useNotifications()

  // Auto-refresh when open (every 5 seconds)
  useEffect(() => {
    if (!notificationCenterOpen) return

    const interval = setInterval(() => {
      // Force re-render to update relative timestamps
      // In a real app, this might also fetch new notifications from server
    }, 5000)

    return () => clearInterval(interval)
  }, [notificationCenterOpen])

  // Group notifications
  const now = new Date()
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate())

  const completedToday = notifications.filter(n => {
    if (n.type !== 'process_completed' && n.type !== 'process_error') return false
    return new Date(n.timestamp) >= todayStart
  })

  const otherNotifications = notifications.filter(n => {
    if (n.type === 'process_completed' || n.type === 'process_error') {
      return new Date(n.timestamp) < todayStart
    }
    return true
  })

  const handleNavigate = (url: string) => {
    setNotificationCenterOpen(false)
    router.push(url)
  }

  return (
    <Sheet open={notificationCenterOpen} onOpenChange={setNotificationCenterOpen}>
      <SheetContent side="right" className="w-full sm:max-w-md">
        <SheetHeader>
          <SheetTitle>Notificações</SheetTitle>
          <SheetDescription>
            Acompanhe seus processos e atualizações
          </SheetDescription>
        </SheetHeader>

        {/* Actions */}
        <div className="flex gap-2 mt-4 mb-2">
          {unreadCount > 0 && (
            <Button
              variant="outline"
              size="sm"
              onClick={markAllAsRead}
              className="flex-1"
            >
              <CheckCheck className="h-4 w-4 mr-2" />
              Marcar todas como lidas
            </Button>
          )}
          {notifications.length > 0 && (
            <Button
              variant="outline"
              size="sm"
              onClick={clearHistory}
              className="flex-1"
            >
              <Trash2 className="h-4 w-4 mr-2" />
              Limpar histórico
            </Button>
          )}
        </div>

        <Separator className="my-4" />

        <ScrollArea className="h-[calc(100vh-180px)] pr-1">
          <div className="space-y-4 pr-3">
            {/* Active Process */}
            {activeProcess && (
              <>
                <div className="space-y-2">
                  <h3 className="text-sm font-semibold flex items-center gap-2">
                    PROCESSOS ATIVOS
                    <Badge variant="secondary" className="h-5 px-1.5 text-xs">
                      1
                    </Badge>
                  </h3>
                  <ActiveProcessDisplay />
                </div>
                <Separator />
              </>
            )}

            {/* Completed Today */}
            <NotificationSection
              title="CONCLUÍDOS HOJE"
              count={completedToday.length}
              notifications={completedToday}
              emptyMessage="Nenhum processamento concluído hoje"
              defaultOpen={true}
              onMarkAsRead={markAsRead}
              onNavigate={handleNavigate}
            />

            <Separator />

            {/* History */}
            <NotificationSection
              title="HISTÓRICO"
              count={otherNotifications.length}
              notifications={otherNotifications}
              emptyMessage="Nenhuma notificação no histórico"
              defaultOpen={false}
              onMarkAsRead={markAsRead}
              onNavigate={handleNavigate}
            />

            {/* Empty state */}
            {notifications.length === 0 && !activeProcess && (
              <div className="text-center py-12 space-y-2">
                <Info className="h-12 w-12 text-muted-foreground mx-auto" />
                <p className="text-sm text-muted-foreground">
                  Você não tem notificações
                </p>
              </div>
            )}
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  )
}
