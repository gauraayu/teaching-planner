import { ArrowRight } from 'lucide-react'
import { Badge } from '@/components/ui/Badge'
import { fmt, LECTURE_TYPE_LABEL } from '@/lib/status'
import type { SprintChange, SprintValues } from '@/types/domain'

const ORDER: { key: keyof SprintValues; label: string; show: (v: SprintValues) => string }[] = [
  { key: 'planned_date', label: 'Date', show: (v) => (v.planned_date ? `${fmt.weekday(v.planned_date)}, ${fmt.date(v.planned_date)}` : '—') },
  { key: 'planned_start_time', label: 'Start', show: (v) => fmt.clock(v.planned_start_time) || '—' },
  { key: 'planned_end_time', label: 'End', show: (v) => fmt.clock(v.planned_end_time) || '—' },
  { key: 'room', label: 'Room', show: (v) => v.room || '—' },
  { key: 'professor_id', label: 'Professor', show: (v) => v.professor_name || '—' },
  { key: 'content_topic', label: 'Topic', show: (v) => v.content_topic || '—' },
  { key: 'subtopics', label: 'Subtopics', show: (v) => (v.subtopics?.length ? v.subtopics.join(' · ') : '—') },
  { key: 'lecture_type', label: 'Type', show: (v) => LECTURE_TYPE_LABEL[v.lecture_type ?? ''] ?? v.lecture_type ?? '—' },
]

export function describeSlot(v: SprintValues | null | undefined): string {
  if (!v) return '—'
  const bits = [
    v.planned_date ? `${fmt.weekday(v.planned_date)} ${fmt.dateShort(v.planned_date)}` : null,
    v.planned_start_time ? fmt.timeRange(v.planned_start_time, v.planned_end_time) : null,
    v.room ? `Room ${v.room}` : null,
  ].filter(Boolean)
  return bits.join(' · ') || '—'
}

export function changeTitle(c: SprintChange): string {
  if (c.change_type === 'CANCEL') return 'Lecture cancelled'
  if (c.change_type === 'ADD') return c.is_carry_forward ? 'Carry-forward added' : 'Lecture added'
  return `${c.changed_fields.join(', ')} changed`
}

/** Before / after for one changed lecture. Informational: used in the admin review and the professor's "View changes". */
export function ChangeDiff({ c, index }: { c: SprintChange; index?: number }) {
  const tone = c.change_type === 'CANCEL' ? 'danger' : c.change_type === 'ADD' ? 'success' : 'warning'
  return (
    <div className="rounded-md border border-line bg-surface-2 p-3.5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          {index != null && <div className="th mb-0.5 text-[10.5px]">Change {String(index + 1).padStart(2, '0')}</div>}
          <div className="text-[13.5px] font-semibold text-fg">
            {c.subject.short_name ?? c.subject.code} <span className="font-normal text-fg-label">· Sem {c.semester.replace('Semester ', '')}-{c.section}{c.lecture_no ? ` · Lecture ${c.lecture_no}` : ''}</span>
          </div>
          <div className="mt-0.5 truncate text-[13px] text-fg-secondary">{c.topic}</div>
        </div>
        <Badge tone={tone}>{changeTitle(c)}</Badge>
      </div>

      {c.change_type === 'UPDATE' && (
        <dl className="mt-3 space-y-1.5 text-[13px]">
          {ORDER.filter((f) => c.new && f.key in c.new).map((f) => (
            <div key={f.key} className="grid grid-cols-[84px_minmax(0,1fr)] gap-x-3 sm:grid-cols-[84px_minmax(0,1fr)_16px_minmax(0,1fr)] sm:items-baseline">
              <dt className="text-fg-label">{f.label}</dt>
              <dd className="text-fg-secondary line-through decoration-line-hover">{f.show(c.old ?? {})}</dd>
              <ArrowRight className="max-sm:hidden h-3.5 w-3.5 self-center text-fg-muted sm:block" aria-hidden />
              <dd className="col-start-2 font-medium text-fg sm:col-start-4"><span className="sr-only">changed to </span>{f.show(c.new ?? {})}</dd>
            </div>
          ))}
        </dl>
      )}
      {c.change_type === 'CANCEL' && <p className="mt-3 text-[13px] text-fg-secondary">Was scheduled: <span className="text-fg">{describeSlot(c.old)}</span></p>}
      {c.change_type === 'ADD' && (
        <div className="mt-3 text-[13px] text-fg-secondary">
          Scheduled: <span className="text-fg">{describeSlot(c.new)}</span>{c.new?.professor_name ? ` · ${c.new.professor_name}` : ''}
          {c.new?.subtopics?.length ? <div className="mt-1">Subtopics: <span className="text-fg-soft">{c.new.subtopics.join(' · ')}</span></div> : null}
        </div>
      )}
      <p className="mt-3 border-t border-line-subtle pt-2.5 text-[12.5px] text-fg-label">
        Reason: <span className="text-fg-soft">{c.reason_label}</span>{c.remarks ? ` – ${c.remarks}` : ''}
      </p>
    </div>
  )
}
