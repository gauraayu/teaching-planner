import { Check, Clock, Minus, TriangleAlert } from 'lucide-react'
import { Badge } from '@/components/ui/Badge'
import type { Tone } from '@/lib/status'
import type { VerificationStatus } from '@/types/domain'
import { cn } from '@/utils/cn'
import type { ClassRow, ClassState } from '../types/om.types'

export const CLASS_STATE: Record<ClassState, { label: string; tone: Tone }> = {
  YET_TO_START: { label: 'Yet to start', tone: 'neutral' },
  ENTRY_DUE: { label: 'Entry due', tone: 'warning' },
  IN_CLASS: { label: 'In class', tone: 'success' },
  EXIT_MISSING: { label: 'Exit not recorded', tone: 'warning' },
  COMPLETED: { label: 'Completed', tone: 'neutral' },
  NOT_RECORDED: { label: 'Not recorded', tone: 'danger' },
}

/** Small green dot + LIVE for a class that is running. The only animated element on these screens. */
export function LiveTag({ label = 'Live' }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[11.5px] font-semibold tracking-wide text-primary uppercase">
      <span className="live-dot" aria-hidden />
      {label}
    </span>
  )
}

export function ClassStateBadge({ state }: { state: ClassState }) {
  if (state === 'IN_CLASS') return <LiveTag label="In class" />
  const s = CLASS_STATE[state]
  return <Badge tone={s.tone}>{s.label}</Badge>
}

/** On time / Delayed, as judged by the backend's tolerance. */
export function TimingBadge({ row }: { row: Pick<ClassRow, 'timing_status' | 'delay_minutes'> }) {
  if (!row.timing_status) return <span className="text-fg-faint">—</span>
  return row.timing_status === 'DELAYED' ? <Badge tone="warning">Delayed {row.delay_minutes} min</Badge> : <Badge tone="success">On time</Badge>
}

/** One verification level in a table cell: icon + word, coloured by state. */
export function LevelStatus({ status, compact }: { status: VerificationStatus | null; compact?: boolean }) {
  const map = {
    VERIFIED: { icon: Check, cls: 'text-primary', label: 'Verified' },
    PENDING: { icon: Clock, cls: 'text-warning', label: 'Pending' },
    CORRECTION_REQUIRED: { icon: TriangleAlert, cls: 'text-danger', label: 'Correction' },
    SUPERSEDED: { icon: Minus, cls: 'text-fg-faint', label: '—' },
  } as const
  if (!status) return <span className="text-fg-faint" aria-label="Not reached">—</span>
  const m = map[status]
  return (
    <span title={compact ? m.label : undefined} className={cn('inline-flex items-center gap-1 text-[12.5px] font-medium whitespace-nowrap', m.cls)}>
      <m.icon className="h-3.5 w-3.5" strokeWidth={2.5} aria-hidden />
      {compact ? <span className="sr-only">{m.label}</span> : m.label}
    </span>
  )
}
