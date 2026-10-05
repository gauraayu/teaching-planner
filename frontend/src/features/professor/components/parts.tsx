import { Check, Clock, MapPin, TriangleAlert } from 'lucide-react'
import type { ReactNode } from 'react'
import { Badge, Tag } from '@/components/ui/Badge'
import { fmt } from '@/lib/status'
import { levelName, VERIFICATION_CHAIN, type SprintRow, type VerificationLevel, type VerificationStatus } from '@/types/domain'
import { cn } from '@/utils/cn'
import type { RowState } from '../rowState'

type Accent = 'primary' | 'info' | 'warning' | 'danger' | 'accent' | 'neutral'
const TOP: Record<Accent, string> = { primary: 'border-t-primary', info: 'border-t-info', warning: 'border-t-warning', danger: 'border-t-danger', accent: 'border-t-accent', neutral: 'border-t-line-strong' }
const VALUE: Record<Accent, string> = { primary: 'text-primary', info: 'text-info', warning: 'text-warning', danger: 'text-danger', accent: 'text-accent', neutral: 'text-fg' }

/** Professor metric card: coloured top rule, label, one large figure, one line of context. */
export function ProfStat({ label, value, unit, sub, accent = 'neutral', icon, children }: { label: string; value: ReactNode; unit?: string; sub?: ReactNode; accent?: Accent; icon?: ReactNode; children?: ReactNode }) {
  return (
    <div className={cn('min-w-0 rounded-md border border-t-2 border-line bg-surface px-4 py-3.5', TOP[accent])}>
      <div className="flex items-center justify-between gap-2 text-[11px] font-semibold tracking-[0.08em] text-fg-label uppercase">
        <span className="truncate">{label}</span>
        <span className="text-fg-muted">{icon}</span>
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className={cn('tnum text-[28px] leading-8 font-semibold tracking-tight', VALUE[accent])}>{value}</span>
        {unit && <span className={cn('truncate text-[12.5px] font-medium', accent === 'neutral' ? 'text-fg-label' : VALUE[accent])}>{unit}</span>}
      </div>
      {sub && <div className="mt-1 truncate text-[12.5px] text-fg-secondary">{sub}</div>}
      {children}
    </div>
  )
}

export function StateBadge({ state }: { state: RowState }) {
  if (state.key === 'LIVE') {
    return <span className="inline-flex items-center gap-1.5 text-[11.5px] font-semibold tracking-wide whitespace-nowrap text-primary uppercase"><span className="live-dot" aria-hidden />In progress</span>
  }
  return <Badge tone={state.tone}>{state.label}</Badge>
}

/** Prof / CL/CH / OM in one line: tick = done, clock = waiting there, dash = not reached. */
export function AuditSequence({ row }: { row: SprintRow }) {
  const submitted = !!row.submission_status && row.submission_status !== 'DRAFT'
  const mark = (s: VerificationStatus | null | 'DONE') =>
    s === 'DONE' || s === 'VERIFIED' ? <Check className="h-3 w-3 text-primary" strokeWidth={3} aria-label="done" />
      : s === 'PENDING' ? <Clock className="h-3 w-3 text-warning" aria-label="pending" />
        : s === 'CORRECTION_REQUIRED' ? <TriangleAlert className="h-3 w-3 text-danger" aria-label="correction required" />
          : <span className="text-fg-faint" aria-label="not reached">–</span>
  const levels: VerificationLevel[] = VERIFICATION_CHAIN
  return (
    <div className="text-[12px] whitespace-nowrap">
      <div className="th text-[10px]">Verification</div>
      <div className="mt-0.5 flex items-center gap-2 text-fg-secondary">
        <span className="inline-flex items-center gap-1">Prof {mark(submitted ? 'DONE' : null)}</span>
        {levels.map((l) => <span key={l} className="inline-flex items-center gap-1">{levelName(l)} {mark(row.verification[l])}</span>)}
      </div>
    </div>
  )
}

export function CohortVenue({ row, className }: { row: SprintRow; className?: string }) {
  return (
    <div className={cn('text-[13px]', className)}>
      <div className="font-medium text-fg-soft">Sem {row.semester.replace('Semester ', '')} · Section {row.section}</div>
      <div className="mt-0.5 inline-flex items-center gap-1 text-fg-secondary"><MapPin className="h-3.5 w-3.5 text-fg-muted" aria-hidden />{row.room ? `Room ${row.room}` : 'Room not set'}</div>
    </div>
  )
}

export function SubjectTopic({ row }: { row: SprintRow }) {
  return (
    <div className="min-w-0">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="text-[14.5px] leading-snug font-semibold text-fg">{row.subject.name}</span>
        <Tag>{row.subject.code}</Tag>
        {row.origin === 'CARRY_FORWARD' && <Tag className="text-info">Carry-forward</Tag>}
        {row.lecture_type !== 'THEORY' && <Tag>{row.lecture_type.charAt(0) + row.lecture_type.slice(1).toLowerCase()}</Tag>}
      </div>
      <div className="mt-0.5 text-[13px] text-fg-secondary">
        <span className="tnum text-fg-label">Lecture {row.lecture_no}:</span> {row.topic}
      </div>
    </div>
  )
}

export function slotLabel(row: SprintRow) {
  return fmt.timeRange(row.start, row.end) || 'Time not set'
}
