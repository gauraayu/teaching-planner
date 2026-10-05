import { CheckSquare, ExternalLink, Lock, Square } from 'lucide-react'
import type { ReactNode } from 'react'
import { StatusBadge, Tag } from '@/components/ui/Badge'
import { DefinitionList } from '@/components/ui/Display'
import { BLOOM_LABEL, EXECUTION_STATUS, fmt, LECTURE_TYPE_LABEL, VERIFICATION_STATUS } from '@/lib/status'
import { fileSrc } from '@/lib/api/uploads'
import { levelName, type LectureDetail, type VerificationEntry } from '@/types/domain'
import { cn } from '@/utils/cn'

export function Section({ title, aside, children, label }: { title: string; aside?: ReactNode; children: ReactNode; label?: string }) {
  return (
    <section className="panel" aria-label={title}>
      <div className="panel-header">
        <div className="flex items-center gap-2">
          {label && <span className="flex h-5 w-5 items-center justify-center rounded-sm bg-primary text-[11px] font-semibold text-on-primary">{label}</span>}
          <h2 className="panel-title">{title}</h2>
        </div>
        {aside}
      </div>
      <div className="p-4">{children}</div>
    </section>
  )
}

/** Admin-owned master plan. Always read-only outside the admin correction flow. */
export function MasterPlanPanel({ d, label }: { d: LectureDetail; label?: string }) {
  const m = d.master
  return (
    <Section
      title="Planned lecture"
      label={label}
      aside={
        <span className="inline-flex items-center gap-1 text-[12px] text-fg-label">
          <Lock className="h-3.5 w-3.5" aria-hidden /> Set by Admin
        </span>
      }
    >
      <h3 className="text-[15px] font-semibold text-fg">{m.content_topic}</h3>
      <div className="mt-3">
        <DefinitionList
          columns={4}
          items={[
            { label: 'Professor', value: d.professor?.full_name ?? '—' },
            { label: 'Subject', value: m.subject },
            { label: 'Lecture', value: `Lecture ${m.lecture_no} · ${LECTURE_TYPE_LABEL[m.lecture_type] ?? m.lecture_type}` },
            { label: 'Unit', value: m.unit_no ? `Unit ${m.unit_no}` : '—' },
            { label: "Bloom's taxonomy", value: m.blooms_taxonomy ? `${m.blooms_taxonomy} · ${BLOOM_LABEL[m.blooms_taxonomy]}` : '—' },
            { label: 'Planned date', value: m.planned_date ? `${fmt.weekday(m.planned_date)}, ${fmt.date(m.planned_date)}` : 'Not scheduled' },
            { label: 'Planned time', value: fmt.timeRange(m.planned_start_time, m.planned_end_time) || '—' },
            { label: 'Section', value: `${d.plan.semester} · Section ${d.plan.section}` },
            { label: 'Room', value: d.room ?? '—' },
          ]}
        />
      </div>
      {d.sprint_change && d.sprint_change.change_type !== 'CANCEL' && (
        <p className="mt-3 rounded-md border border-info-border bg-info-soft px-3 py-2 text-[12.5px] text-fg-soft">
          <span className="font-semibold text-info">Sprint revision v{d.sprint_change.revision_number}</span>
          {d.sprint_change.change_type === 'ADD' ? ' · added in the weekly sprint meeting' : ` · ${d.sprint_change.changed_fields.join(', ').toLowerCase()} updated`} · {d.sprint_change.reason_label}
        </p>
      )}
      {m.subtopics.length > 0 && (
        <div className="mt-4">
          <div className="text-[12px] font-medium text-fg-label">Subtopics</div>
          <ol className="mt-1 list-decimal space-y-0.5 pl-5 text-[13px] text-fg">
            {m.subtopics.map((s) => (
              <li key={s.id}>{s.title}</li>
            ))}
          </ol>
        </div>
      )}
    </Section>
  )
}

export function ExecutionSummary({ d, label }: { d: LectureDetail; label?: string }) {
  const e = d.execution
  if (!e) {
    return (
      <Section title="Professor execution" label={label}>
        <p className="meta">The professor has not recorded this lecture yet.</p>
      </Section>
    )
  }
  const covered = new Set(e.covered_subtopic_ids)
  return (
    <Section title="Professor execution" label={label} aside={<StatusBadge value={e.execution_status} map={EXECUTION_STATUS} />}>
      <DefinitionList
        columns={4}
        items={[
          { label: 'Actual date', value: e.actual_completion_date ? fmt.date(e.actual_completion_date) : '—' },
          {
            label: 'Against plan',
            value:
              e.actual_completion_date && d.master.planned_date
                ? e.actual_completion_date === d.master.planned_date
                  ? 'On the planned day'
                  : e.actual_completion_date < d.master.planned_date
                    ? 'Ahead of plan'
                    : `${Math.round((Date.parse(e.actual_completion_date) - Date.parse(d.master.planned_date)) / 86400000)} day(s) late`
                : '—',
          },
          { label: 'Shared with students', value: e.shared_with_students === null ? 'Not answered' : e.shared_with_students ? `Yes${e.shared_at ? ` · ${fmt.dateTime(e.shared_at)}` : ''}` : 'No' },
          { label: 'Submitted', value: e.submitted_at ? fmt.dateTime(e.submitted_at) : 'Not submitted' },
        ]}
      />
      {(e.professor_started_at || e.evidence?.length > 0) && (
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <div>
            <div className="text-[12px] font-medium text-fg-label">Professor start / end class</div>
            <div className="tnum mt-1 text-[13px] text-fg">
              {e.professor_started_at ? fmt.time(e.professor_started_at) : '—'} – {e.professor_ended_at ? fmt.time(e.professor_ended_at) : 'not ended'}
            </div>
            <div className="meta">Self-recorded. The OM&apos;s entry and exit are the official times.</div>
          </div>
          {e.evidence?.length > 0 && (
            <div>
              <div className="text-[12px] font-medium text-fg-label">Class photos · {e.evidence.length}</div>
              <div className="mt-1 flex flex-wrap gap-2">
                {e.evidence.map((m) => (
                  <a key={m.id} href={fileSrc(m.file_url)} target="_blank" rel="noreferrer" title={m.caption ?? m.file_name ?? 'Class photo'}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={fileSrc(m.file_url)} alt={m.caption ?? 'Class photo'} className="h-14 w-14 rounded border border-line object-cover" />
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
      {e.shared_with_students === false && e.not_shared_reason && (
        <p className="mt-3 rounded-md bg-warning-soft px-3 py-2 text-[13px] text-warning">
          <b>Reason not shared:</b> {e.not_shared_reason}
        </p>
      )}
      {d.master.subtopics.length > 0 && (
        <div className="mt-4">
          <div className="text-[12px] font-medium text-fg-label">
            Covered subtopics · {covered.size} of {d.master.subtopics.length}
          </div>
          <ul className="mt-1 space-y-1 text-[13px]">
            {d.master.subtopics.map((s) => (
              <li key={s.id} className={cn('flex items-center gap-2', covered.has(s.id) ? 'text-fg' : 'text-fg-muted')}>
                {covered.has(s.id) ? <CheckSquare className="h-4 w-4 text-primary" aria-label="Covered" /> : <Square className="h-4 w-4" aria-label="Not covered" />}
                {s.title}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <div className="text-[12px] font-medium text-fg-label">Daily lecture notes</div>
          {e.notes.length === 0 ? (
            <p className="meta mt-1">None attached</p>
          ) : (
            <ul className="mt-1 space-y-1">
              {e.notes.map((n) => (
                <li key={n.id}>
                  <a href={n.file_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-[13px] text-primary hover:underline">
                    <ExternalLink className="h-3.5 w-3.5" /> {n.title || 'Lecture notes'}
                  </a>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <div className="text-[12px] font-medium text-fg-label">Weekly assignment</div>
          {!e.assignment ? (
            <p className="meta mt-1">No assignment</p>
          ) : (
            <div className="mt-1 text-[13px]">
              <div className="font-medium text-fg">{e.assignment.title}</div>
              <div className="meta">
                Due {fmt.date(e.assignment.due_date)} · {e.assignment.shared_with_students ? 'Shared with students' : e.assignment.shared_with_students === false ? `Not shared: ${e.assignment.not_shared_reason}` : 'Sharing not recorded'}
              </div>
              {e.assignment.link_url && (
                <a href={e.assignment.link_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">
                  <ExternalLink className="h-3.5 w-3.5" /> Open assignment
                </a>
              )}
            </div>
          )}
        </div>
      </div>
      {e.remarks && (
        <div className="mt-4">
          <div className="text-[12px] font-medium text-fg-label">Professor remarks</div>
          <p className="mt-1 text-[13px] whitespace-pre-line text-fg">{e.remarks}</p>
        </div>
      )}
    </Section>
  )
}

export function VerificationHistory({ items }: { items: VerificationEntry[] }) {
  if (!items.length) return <p className="meta">No verification activity yet.</p>
  return (
    <ol className="space-y-3">
      {items.map((v) => (
        <li key={v.id} className="flex gap-3 text-[13px]">
          <Tag className="mt-0.5 shrink-0">{levelName(v.verification_level)}</Tag>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge value={v.status} map={VERIFICATION_STATUS} />
              <span className="meta">Round {v.round}</span>
            </div>
            <div className="meta mt-0.5">
              {v.verifier ? `${v.verifier.full_name} · ${fmt.dateTime(v.verified_at)}` : `Waiting since ${fmt.dateTime(v.created_at)}`}
            </div>
            {v.remarks && <p className="mt-1 rounded bg-surface-2 px-2.5 py-1.5 text-fg-soft">“{v.remarks}”</p>}
          </div>
        </li>
      ))}
    </ol>
  )
}
