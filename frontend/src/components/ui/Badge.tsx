import { AlertTriangle, CheckCircle2, Circle, CircleDot, Info, XCircle } from 'lucide-react'
import type { ReactNode } from 'react'
import type { Tone } from '@/lib/status'
import { cn } from '@/utils/cn'

// Tinted text on a 10% wash of the same hue: readable on black without being loud.
const TONES: Record<Tone, string> = {
  neutral: 'bg-surface-3 text-fg-secondary ring-line',
  brand: 'bg-primary-soft text-primary ring-primary-border',
  success: 'bg-primary-soft text-primary ring-primary-border',
  warning: 'bg-warning-soft text-warning ring-warning-border',
  danger: 'bg-danger-soft text-danger ring-danger-border',
  info: 'bg-info-soft text-info ring-info-border',
}

// Each tone also carries a distinct icon so status never depends on colour alone.
const ICONS: Record<Tone, typeof Circle> = {
  neutral: Circle,
  brand: CircleDot,
  success: CheckCircle2,
  warning: AlertTriangle,
  danger: XCircle,
  info: Info,
}

export function Badge({ tone = 'neutral', children, icon = true, className }: { tone?: Tone; children: ReactNode; icon?: boolean; className?: string }) {
  const Icon = ICONS[tone]
  return (
    <span
      className={cn(
        'inline-flex h-[22px] items-center gap-1 rounded-sm px-1.5 text-[12px] font-medium whitespace-nowrap ring-1 ring-inset',
        TONES[tone],
        className,
      )}
    >
      {icon && <Icon className="h-3 w-3 shrink-0" aria-hidden strokeWidth={2.25} />}
      {children}
    </span>
  )
}

export function StatusBadge<K extends string>({ value, map, className }: { value: K | null | undefined; map: Record<K, { label: string; tone: Tone }>; className?: string }) {
  if (!value) return <span className="meta">—</span>
  const meta = map[value] ?? { label: value, tone: 'neutral' as Tone }
  return (
    <Badge tone={meta.tone} className={className}>
      {meta.label}
    </Badge>
  )
}

/** Neutral pill for metadata like K2 or Unit 3 (no status meaning). */
export function Tag({ children, className, title }: { children: ReactNode; className?: string; title?: string }) {
  return (
    <span title={title} className={cn('inline-flex h-5 items-center rounded-sm bg-surface-3 px-1.5 text-[11.5px] font-medium text-fg-secondary ring-1 ring-line ring-inset', className)}>
      {children}
    </span>
  )
}
