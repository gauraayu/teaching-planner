import type { ReactNode } from 'react'
import { cn } from '@/utils/cn'

export function ProgressBar({ value, tone = 'brand', className, label }: { value: number; tone?: 'brand' | 'success' | 'warning'; className?: string; label?: string }) {
  const v = Math.max(0, Math.min(100, value))
  const color = { brand: 'bg-primary', success: 'bg-primary', warning: 'bg-warning' }[tone]
  return (
    <div
      role="progressbar"
      aria-valuenow={v}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
      className={cn('h-1.5 w-full overflow-hidden rounded-full bg-track', className)}
    >
      <div className={cn('h-full rounded-full transition-[width]', color)} style={{ width: `${v}%` }} />
    </div>
  )
}

/** Stacked bar for completed / partial / delayed / pending - every segment also has a text legend. */
export function SegmentBar({ segments, className }: { segments: { value: number; className: string; label: string }[]; className?: string }) {
  const total = segments.reduce((a, s) => a + s.value, 0) || 1
  return (
    <div className={cn('flex h-2 w-full overflow-hidden rounded-full bg-track', className)} role="img" aria-label={segments.map((s) => `${s.label} ${s.value}`).join(', ')}>
      {segments.map((s) => (s.value ? <div key={s.label} className={s.className} style={{ width: `${(s.value / total) * 100}%` }} title={`${s.label}: ${s.value}`} /> : null))}
    </div>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded bg-track', className)} aria-hidden />
}

/** Compact summary panel, not a giant card. */
export function Metric({ label, value, sub, tone, icon }: { label: string; value: ReactNode; sub?: ReactNode; tone?: 'danger' | 'warning' | 'success' | 'neutral'; icon?: ReactNode }) {
  const toneText = tone === 'danger' ? 'text-danger' : tone === 'warning' ? 'text-warning' : tone === 'neutral' ? 'text-fg' : 'text-primary'
  return (
    <div className="min-w-0 px-4 py-3">
      <div className="flex items-center gap-1.5 text-[11.5px] font-semibold tracking-wide text-fg-label uppercase">
        {icon}
        <span className="truncate">{label}</span>
      </div>
      <div className={cn('tnum mt-1 text-[22px] leading-7 font-semibold tracking-tight', toneText)}>{value}</div>
      {sub && <div className="meta mt-0.5 truncate">{sub}</div>}
    </div>
  )
}

export function MetricStrip({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn('panel grid grid-cols-2 divide-line sm:grid-cols-3 lg:flex lg:divide-x [&>*]:flex-1', className)}>{children}</div>
  )
}

export function DefinitionList({ items, columns = 2 }: { items: { label: string; value: ReactNode }[]; columns?: 1 | 2 | 3 | 4 }) {
  const cols = { 1: '', 2: 'sm:grid-cols-2', 3: 'sm:grid-cols-3', 4: 'sm:grid-cols-2 lg:grid-cols-4' }[columns]
  return (
    <dl className={cn('grid grid-cols-1 gap-x-6 gap-y-3', cols)}>
      {items.map((it) => (
        <div key={it.label} className="min-w-0">
          <dt className="text-[12px] font-medium text-fg-label">{it.label}</dt>
          <dd className="mt-0.5 text-sm text-fg">{it.value ?? '—'}</dd>
        </div>
      ))}
    </dl>
  )
}
