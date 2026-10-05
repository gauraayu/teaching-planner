import { AlertTriangle, CheckCircle2, Info, Loader2, RefreshCw, XCircle } from 'lucide-react'
import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { Button } from '@/components/ui/Button'
import { Skeleton } from '@/components/ui/Display'
import { cn } from '@/utils/cn'

export function EmptyState({ icon, title, description, action, className }: { icon?: ReactNode; title: string; description?: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={cn('flex flex-col items-center justify-center px-6 py-12 text-center', className)}>
      {icon && <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-md bg-surface-3 text-fg-label">{icon}</div>}
      <p className="text-sm font-semibold text-fg">{title}</p>
      {description && <p className="meta mt-1 max-w-md">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function ErrorState({ message, onRetry, className }: { message: string; onRetry?: () => void; className?: string }) {
  return (
    <div className={cn('flex flex-col items-center justify-center px-6 py-10 text-center', className)} role="alert">
      <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-md bg-danger-soft text-danger">
        <XCircle className="h-5 w-5" />
      </div>
      <p className="text-sm font-semibold text-fg">Unable to load this information</p>
      <p className="meta mt-1 max-w-md">{message}</p>
      {onRetry && (
        <Button className="mt-4" size="sm" icon={<RefreshCw className="h-3.5 w-3.5" />} onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  )
}

export function LoadingRows({ rows = 6 }: { rows?: number }) {
  return (
    <div className="space-y-3 p-4" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className={cn('h-4', i % 3 === 0 ? 'w-2/3' : i % 3 === 1 ? 'w-full' : 'w-5/6')} />
      ))}
    </div>
  )
}

export function PageLoading() {
  return (
    <div className="flex h-64 items-center justify-center text-fg-label" aria-busy="true">
      <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading…
    </div>
  )
}

const ALERT = {
  info: { cls: 'border-info-border bg-info-soft text-info', icon: Info },
  success: { cls: 'border-primary-border bg-primary-soft text-primary', icon: CheckCircle2 },
  warning: { cls: 'border-warning-border bg-warning-soft text-warning', icon: AlertTriangle },
  danger: { cls: 'border-danger-border bg-danger-soft text-danger', icon: XCircle },
}

/** Inline status - preferred over toasts for long-running workflows. */
export function InlineAlert({ tone = 'info', title, children, action, className }: { tone?: keyof typeof ALERT; title?: ReactNode; children?: ReactNode; action?: ReactNode; className?: string }) {
  const { cls, icon: Icon } = ALERT[tone]
  return (
    <div className={cn('flex gap-3 rounded-md border px-3.5 py-3 text-[13px]', cls, className)} role={tone === 'danger' ? 'alert' : 'status'}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className={cn('leading-relaxed', !!title && 'mt-0.5')}>{children}</div>}
      </div>
      {action && <div className="shrink-0 self-center">{action}</div>}
    </div>
  )
}

// ------------------------------------------------------------- toasts (used sparingly)

const TOAST_TONE = { success: 'border-primary-border text-primary', danger: 'border-danger-border text-danger', info: 'border-info-border text-info' } as const

type Toast = { id: number; tone: 'success' | 'danger' | 'info'; message: string }
const ToastContext = createContext<(tone: Toast['tone'], message: string) => void>(() => {})

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const push = useCallback((tone: Toast['tone'], message: string) => {
    const id = Date.now() + Math.random()
    setToasts((t) => [...t.slice(-2), { id, tone, message }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500)
  }, [])
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed right-4 bottom-4 z-[60] flex w-[min(92vw,380px)] flex-col gap-2" aria-live="polite">
        {toasts.map((t) => {
          const { icon: Icon } = ALERT[t.tone]
          // Opaque surface: a toast sits on top of tables and must stay readable over them.
          return (
            <div key={t.id} className={cn('pointer-events-auto flex items-start gap-2.5 rounded-md border bg-surface-3 px-3.5 py-3 text-[13px] shadow-pop', TOAST_TONE[t.tone])}>
              <Icon className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{t.message}</span>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}

export const useToast = () => useContext(ToastContext)
