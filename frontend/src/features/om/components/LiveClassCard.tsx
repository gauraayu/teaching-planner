import { DoorOpen, Eye, LogOut } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { fmt } from '@/lib/status'
import { cn } from '@/utils/cn'
import type { ClassRow } from '../types/om.types'
import { ClassStateBadge, LevelStatus } from './status'

export type ClassAction = 'entry' | 'exit' | 'view'

/** What the OM should do next for this class, decided in one place for both the table and the cards. */
export function nextAction(row: ClassRow, today: string): { action: ClassAction; label: string; primary: boolean } {
  const locked = row.verification.submission_status === 'FINAL_VERIFIED'
  if (locked || row.date > today || !row.scheduled_start) return { action: 'view', label: 'View', primary: false }
  if (!row.entry_time) return { action: 'entry', label: 'Record Entry', primary: row.state === 'ENTRY_DUE' || row.state === 'NOT_RECORDED' }
  if (!row.exit_time) return { action: 'exit', label: 'Record Exit', primary: true }
  return { action: 'view', label: 'View', primary: false }
}

/** Operational card for phones and the "Currently Running" board: one class, one obvious next step. */
export function LiveClassCard({ row, today, onAction, showDate }: { row: ClassRow; today: string; onAction: (a: ClassAction, row: ClassRow) => void; showDate?: boolean }) {
  const next = nextAction(row, today)
  const Icon = next.action === 'entry' ? DoorOpen : next.action === 'exit' ? LogOut : Eye
  return (
    <article className={cn('panel flex flex-col', row.state === 'IN_CLASS' && 'border-primary-border')}>
      <div className="flex-1 px-4 pt-3.5 pb-3">
        <div className="flex items-center justify-between gap-3">
          <ClassStateBadge state={row.state} />
          <span className="text-[12.5px] font-medium text-fg-secondary">{row.room ? `Room ${row.room}` : 'Room not set'}</span>
        </div>
        <h3 className="mt-3 text-[15px] leading-snug font-semibold text-fg">{row.professor.full_name}</h3>
        <p className="mt-0.5 text-[13px] text-fg-secondary">
          {row.subject.name} <span className="text-fg-muted">· Sem {row.semester.replace('Semester ', '')}-{row.section}</span>
        </p>
        <p className="tnum mt-2 text-[13px] text-fg-soft">
          {showDate && <span className="text-fg-label">{fmt.weekday(row.date)} {fmt.dateShort(row.date)} · </span>}
          {fmt.timeRange(row.scheduled_start, row.scheduled_end) || 'Time not set'}
        </p>
        <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 border-t border-line-subtle pt-3 text-[13px]">
          <dt className="text-fg-label">Entry</dt>
          <dd className="tnum text-fg">{fmt.clock(row.entry_time) || '—'}</dd>
          {row.entry_time && (
            <>
              <dt className="text-fg-label">Delay</dt>
              <dd className={cn('tnum', row.timing_status === 'DELAYED' ? 'font-medium text-warning' : 'text-fg')}>
                {row.timing_status === 'DELAYED' ? `${row.delay_minutes} min${row.delay_reason_label ? ` · ${row.delay_reason_label}` : ''}` : 'On time'}
              </dd>
            </>
          )}
          {row.exit_time && (
            <>
              <dt className="text-fg-label">Exit</dt>
              <dd className="tnum text-fg">{fmt.clock(row.exit_time)} <span className="text-fg-muted">· {row.duration_minutes} min</span></dd>
            </>
          )}
        </dl>
        <div className="mt-3 flex items-center gap-4 text-[12px] text-fg-label">
          {(['CL_CH', 'OM'] as const).map((lvl) => (
            <span key={lvl} className="inline-flex items-center gap-1.5">
              {lvl === 'CL_CH' ? 'CL/CH' : lvl} <LevelStatus status={row.verification.levels[lvl]} compact />
            </span>
          ))}
        </div>
      </div>
      <div className="flex gap-2 border-t border-line-subtle p-2">
        <Button variant={next.primary ? 'primary' : 'secondary'} className="h-10 flex-1 justify-center" icon={<Icon className="h-4 w-4" />} onClick={() => onAction(next.action, row)}>
          {next.label}
        </Button>
        {next.action !== 'view' && (
          <Button variant="ghost" className="h-10" aria-label={`View ${row.subject.name} class`} onClick={() => onAction('view', row)}>
            View
          </Button>
        )}
      </div>
    </article>
  )
}
