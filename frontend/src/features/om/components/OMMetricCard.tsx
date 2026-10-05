import type { ReactNode } from 'react'
import { cn } from '@/utils/cn'

type Tone = 'primary' | 'neutral' | 'warning' | 'danger'
const VALUE: Record<Tone, string> = { primary: 'text-primary', neutral: 'text-fg', warning: 'text-warning', danger: 'text-danger' }

/** Dark metric card: muted label, one large figure, one line of context. No glow. */
export function OMMetricCard({ label, value, sub, tone = 'primary', live }: { label: string; value: ReactNode; sub?: ReactNode; tone?: Tone; live?: boolean }) {
  return (
    <div className="panel min-w-0 px-4 py-3.5">
      <div className="flex items-center gap-1.5 text-[11px] font-semibold tracking-[0.06em] text-fg-label uppercase">
        {live && <span className="live-dot" aria-hidden />}
        <span className="truncate">{label}</span>
      </div>
      <div className={cn('tnum mt-2 text-[28px] leading-8 font-semibold tracking-tight', VALUE[tone])}>{value}</div>
      {sub && <div className="meta mt-1 truncate">{sub}</div>}
    </div>
  )
}

export function OMMetricGrid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">{children}</div>
}
