import { AlertTriangle, ChevronRight, Clock } from 'lucide-react'
import { Link } from '@/lib/router'
import { StatusBadge, Tag } from '@/components/ui/Badge'
import { buttonClass } from '@/components/ui/Button'
import { EXECUTION_STATUS, fmt, SUBMISSION_STATUS } from '@/lib/status'
import type { TaskCard as Task } from '@/types/domain'
import { cn } from '@/utils/cn'

/** Compact task card - the primary unit of the professor's mobile experience. */
export function TaskCard({ t, showDate, compact }: { t: Task; showDate?: boolean; compact?: boolean }) {
  const needsAction = !t.submission_status || t.submission_status === 'DRAFT' || t.submission_status === 'CORRECTION_REQUIRED'
  return (
    <article className={cn('panel flex flex-col', t.submission_status === 'CORRECTION_REQUIRED' && 'border-danger-border')}>
      <div className="flex-1 px-4 pt-3.5 pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-[12px] font-semibold tracking-wide text-primary uppercase">
              {t.subject.short_name ?? t.subject.code} <span className="font-normal text-fg-muted normal-case">· Section {t.plan.section}</span>
            </div>
            <div className="meta mt-0.5 tnum">Lecture {t.lecture_no}{t.unit_no ? ` · Unit ${t.unit_no}` : ''}</div>
          </div>
          <StatusBadge value={t.execution_status} map={EXECUTION_STATUS} />
        </div>
        <h3 className="mt-2 text-[14.5px] leading-snug font-semibold text-fg">{t.content_topic}</h3>
        {!compact && t.subtopics.length > 0 && (
          <p className="meta mt-1 line-clamp-2">{t.subtopics.map((s) => s.title).join(' · ')}</p>
        )}
        <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[12.5px] text-fg-secondary">
          <span className="inline-flex items-center gap-1">
            <Clock className="h-3.5 w-3.5 text-fg-muted" aria-hidden />
            {showDate && `${fmt.weekday(t.planned_date)} ${fmt.dateShort(t.planned_date)} · `}
            {fmt.timeRange(t.planned_start_time, t.planned_end_time) || 'Time not set'}
          </span>
          {t.blooms_taxonomy && <Tag>{t.blooms_taxonomy}</Tag>}
          {t.is_overdue && (
            <span className="inline-flex items-center gap-1 font-medium text-danger">
              <AlertTriangle className="h-3.5 w-3.5" aria-hidden /> Overdue
            </span>
          )}
          {t.execution_status === 'RESCHEDULED' && t.effective_date && <span className="text-info">Moved to {fmt.dateShort(t.effective_date)}</span>}
          {t.submission_status && t.submission_status !== 'DRAFT' && <StatusBadge value={t.submission_status} map={SUBMISSION_STATUS} />}
        </div>
      </div>
      <div className="flex border-t border-line-subtle">
        <Link to={`/professor/lectures/${t.id}`} className={cn(buttonClass(needsAction ? 'primary' : 'ghost', 'md'), 'm-2 flex-1 justify-center')}>
          {t.submission_status === 'CORRECTION_REQUIRED' ? 'Fix and resubmit' : needsAction ? 'Update lecture' : 'View record'}
          <ChevronRight className="h-4 w-4" />
        </Link>
      </div>
    </article>
  )
}

/** Dense row variant for desktop lists. */
export function TaskRow({ t }: { t: Task }) {
  return (
    <Link to={`/professor/lectures/${t.id}`} className="flex items-center gap-3 border-b border-line-subtle px-4 py-2.5 text-[13px] last:border-0 hover:bg-surface-2">
      <span className="w-24 shrink-0 whitespace-nowrap text-fg-secondary">
        {fmt.weekday(t.planned_date)} {fmt.dateShort(t.planned_date)}
      </span>
      <span className="w-16 shrink-0 whitespace-nowrap font-semibold text-primary" title={`Section ${t.plan.section}`}>
        {t.subject.short_name ?? t.subject.code}
        <span className="font-normal text-fg-muted"> · {t.plan.section}</span>
      </span>
      <span className="tnum w-10 shrink-0 text-fg-muted">L{t.lecture_no}</span>
      <span className="min-w-0 flex-1 truncate text-fg">{t.content_topic}</span>
      <span className="max-sm:hidden sm:block">
        {t.submission_status && t.submission_status !== 'DRAFT' ? <StatusBadge value={t.submission_status} map={SUBMISSION_STATUS} /> : <StatusBadge value={t.execution_status} map={EXECUTION_STATUS} />}
      </span>
      <ChevronRight className="h-4 w-4 shrink-0 text-fg-faint" />
    </Link>
  )
}
