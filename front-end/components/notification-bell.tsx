'use client'

import { Bell } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface NotificationBellProps {
  unreadCount: number
  hasActiveProcess?: boolean
  onClick: () => void
  className?: string
}

export function NotificationBell({
  unreadCount,
  hasActiveProcess = false,
  onClick,
  className,
}: NotificationBellProps) {
  return (
    <div className="relative">
      <Button
        variant="ghost"
        size="icon"
        onClick={onClick}
        className={cn(
          'relative',
          hasActiveProcess && 'animate-pulse',
          className
        )}
        aria-label={`Notificações${unreadCount > 0 ? ` (${unreadCount} não lidas)` : ''}`}
      >
        <Bell className="h-5 w-5" />

        {/* Badge for unread notifications */}
        {unreadCount > 0 && (
          <span className={cn(
            'absolute -top-1 -right-1 flex h-5 min-w-[20px] items-center justify-center rounded-full px-1 text-[10px] font-bold text-white',
            'bg-red-500 animate-in fade-in zoom-in duration-200'
          )}>
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}

        {/* Pulse indicator for active process */}
        {hasActiveProcess && unreadCount === 0 && (
          <span className="absolute -top-1 -right-1 flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3 w-3 bg-blue-500"></span>
          </span>
        )}
      </Button>
    </div>
  )
}
