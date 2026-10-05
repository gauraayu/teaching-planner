import { Badge, StatusBadge } from '@/components/ui/Badge'
import { Button, ButtonLink } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { DefinitionList } from '@/components/ui/Display'
import { useApi } from '@/hooks/useApi'
import { EXECUTION_STATUS, fmt } from '@/lib/status'
import type { ClassDetail, ClassRow } from '../types/om.types'
import { ClassStateBadge, TimingBadge } from './status'
import { VerificationTimeline } from './VerificationTimeline'

/** "View": everything known about one class - schedule, timing, the professor's update and the chain. */
export function ClassDetailDialog({ row, onClose }: { row: ClassRow | null; onClose: () => void }) {
  const detail = useApi<ClassDetail>(row ? `/om/classes/${row.lecture_id}` : null)
  if (!row) return null
  const d = detail.data ?? row
  const update = detail.data?.professor_update
  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={`${d.subject.short_name ?? d.subject.code} · Lecture ${d.lecture_no}`}
      description={d.topic}
      footer={
        <>
          {d.verification.om_verification_id && d.verification.levels.OM === 'PENDING' ? (
            <ButtonLink variant="primary" to={`/om/review/${d.verification.om_verification_id}`}>Final Verify</ButtonLink>
          ) : d.verification.submission_status !== 'FINAL_VERIFIED' && d.verification.waiting_for ? (
            // Final verification opens only after CL/CH has verified; say why it is not available yet.
            <>
              <span className="meta mr-auto">{d.verification.waiting_for}</span>
              <Button variant="primary" disabled>Final Verify</Button>
            </>
          ) : null}
          <Button onClick={onClose}>Close</Button>
        </>
      }
    >
      <div className="space-y-5">
        <div className="flex flex-wrap items-center gap-2">
          <ClassStateBadge state={d.state} />
          <TimingBadge row={d} />
          {d.is_rescheduled && <Badge tone="info">Rescheduled class</Badge>}
        </div>
        <DefinitionList
          columns={4}
          items={[
            { label: 'Professor', value: d.professor.full_name },
            { label: 'Section', value: `Sem ${d.semester.replace('Semester ', '')}-${d.section} · ${d.branch_code}` },
            { label: 'Date', value: fmt.date(d.date) },
            { label: 'Room', value: d.room ?? '—' },
            { label: 'Scheduled', value: <span className="tnum">{fmt.timeRange(d.scheduled_start, d.scheduled_end)}</span> },
            { label: 'Entry', value: <span className="tnum">{fmt.clock(d.entry_time) || '—'}</span> },
            { label: 'Exit', value: <span className="tnum">{fmt.clock(d.exit_time) || '—'}</span> },
            { label: 'Time in class', value: d.duration_minutes != null ? `${d.duration_minutes} min` : '—' },
            { label: 'Professor start', value: <span className="tnum">{fmt.clock(d.professor_started_at) || '—'}</span> },
            { label: 'Professor end', value: <span className="tnum">{fmt.clock(d.professor_ended_at) || '—'}</span> },
            { label: 'Teaching status', value: <StatusBadge value={d.execution_status} map={EXECUTION_STATUS} /> },
            { label: 'Final status', value: d.verification.submission_status === 'FINAL_VERIFIED' ? 'Final verified' : d.verification.waiting_for ?? (d.verification.levels.OM === 'PENDING' ? 'Ready for final verification' : '—') },
          ]}
        />
        {d.timing_status === 'DELAYED' && (
          <div className="rounded-md border border-warning-border bg-warning-soft px-3.5 py-2.5 text-[13px]">
            <span className="font-semibold text-warning">Delay {d.delay_minutes} min · {d.delay_reason_label}</span>
            {d.delay_remarks && <p className="mt-0.5 text-fg-soft">{d.delay_remarks}</p>}
          </div>
        )}
        {d.early_exit_reason && (
          <div className="rounded-md border border-warning-border bg-warning-soft px-3.5 py-2.5 text-[13px]">
            <span className="font-semibold text-warning">Early exit {d.early_exit_minutes} min</span>
            <p className="mt-0.5 text-fg-soft">{d.early_exit_reason}</p>
          </div>
        )}
        <div>
          <div className="th mb-3">Verification</div>
          <VerificationTimeline row={d} />
        </div>
        <div>
          <div className="th mb-2">Professor's update</div>
          {update ? (
            <div className="space-y-1.5 text-[13px]">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge value={update.execution_status} map={EXECUTION_STATUS} />
                <span className="meta">Completed {fmt.date(update.actual_completion_date)} · {update.notes_count} notes link{update.notes_count === 1 ? '' : 's'}{update.has_assignment ? ' · assignment attached' : ''}</span>
              </div>
              {update.remarks && <p className="text-fg-soft">{update.remarks}</p>}
            </div>
          ) : (
            <p className="meta">{detail.loading ? 'Loading…' : 'The professor has not updated this lecture yet.'}</p>
          )}
        </div>
      </div>
    </Dialog>
  )
}
