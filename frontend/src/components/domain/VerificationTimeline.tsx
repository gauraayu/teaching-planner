import { Check, Clock, DoorOpen, TriangleAlert } from 'lucide-react'
import { Section } from '@/components/domain/LectureRecord'
import { Badge } from '@/components/ui/Badge'
import { DefinitionList } from '@/components/ui/Display'
import { fmt } from '@/lib/status'
import { levelName, VERIFICATION_CHAIN, type ClassSessionBrief, type SubmissionStatus, type VerificationLevel, type VerificationStatus } from '@/types/domain'
import { cn } from '@/utils/cn'

type Step = { verification_level?: VerificationLevel; level?: VerificationLevel; status: VerificationStatus; round?: number; verified_at?: string | null }
type NodeState = 'done' | 'current' | 'correction' | 'future'

const NODE: Record<NodeState, { dot: string; text: string }> = {
  done: { dot: 'border-primary bg-primary text-on-primary', text: 'text-primary' },
  current: { dot: 'border-warning bg-warning-soft text-warning', text: 'text-warning' },
  correction: { dot: 'border-danger bg-danger-soft text-danger', text: 'text-danger' },
  future: { dot: 'border-line-strong bg-surface text-fg-faint', text: 'text-fg-muted' },
}

/**
 * Professor -> CL/CH -> OM on one line. Green = done, amber = waiting here,
 * red = sent back for correction, grey = not reached yet. Each node also has a text
 * label, so the state never depends on colour alone.
 */
export function VerificationTimeline({
  submitted,
  submissionStatus,
  steps,
  chain = VERIFICATION_CHAIN,
  round,
  compact,
}: {
  submitted: boolean
  submissionStatus: SubmissionStatus | null | undefined
  steps: Step[]
  chain?: VerificationLevel[]
  round?: number
  compact?: boolean
}) {
  const latestRound = round ?? Math.max(0, ...steps.map((s) => s.round ?? 1))
  const current = steps.filter((s) => (s.round ?? latestRound) === latestRound && s.status !== 'SUPERSEDED')
  const byLevel = Object.fromEntries(current.map((s) => [s.verification_level ?? s.level, s])) as Partial<Record<VerificationLevel, Step>>
  const reopened = submissionStatus === 'CORRECTION_REQUIRED'

  const nodes: { key: string; label: string; state: NodeState; caption: string }[] = [
    {
      key: 'P',
      label: 'Professor',
      state: reopened ? 'current' : submitted ? 'done' : 'current',
      caption: reopened ? 'Correcting' : submitted ? 'Submitted' : 'Not submitted',
    },
    ...chain.map((lvl) => {
      const s = byLevel[lvl]
      const state: NodeState = !s ? 'future' : s.status === 'VERIFIED' ? 'done' : s.status === 'CORRECTION_REQUIRED' ? 'correction' : 'current'
      const last = lvl === chain[chain.length - 1]
      const caption = !s ? 'Waiting' : s.status === 'VERIFIED' ? (last ? 'Final verified' : 'Verified') : s.status === 'CORRECTION_REQUIRED' ? 'Correction' : last ? 'Final verification pending' : 'Pending'
      return { key: lvl, label: levelName(lvl), state, caption }
    }),
  ]

  return (
    <ol className="flex w-full items-start" aria-label="Verification progress">
      {nodes.map((n, i) => {
        const style = NODE[n.state]
        const prevDone = i > 0 && nodes[i - 1].state === 'done'
        return (
          <li key={n.key} className="relative flex min-w-0 flex-1 flex-col items-center text-center">
            {i > 0 && <span className={cn('absolute top-[9px] right-1/2 left-[-50%] h-px', prevDone ? 'bg-primary-muted' : 'bg-line-strong')} aria-hidden />}
            <span className={cn('relative z-[1] flex h-[19px] w-[19px] items-center justify-center rounded-full border', style.dot)}>
              {n.state === 'done' ? <Check className="h-3 w-3" strokeWidth={3} aria-hidden /> : n.state === 'correction' ? <TriangleAlert className="h-2.5 w-2.5" aria-hidden /> : n.state === 'current' ? <Clock className="h-2.5 w-2.5" aria-hidden /> : null}
            </span>
            <span className={cn('mt-1.5 text-[12px] font-semibold', n.state === 'future' ? 'text-fg-muted' : 'text-fg')}>{n.label}</span>
            {!compact && <span className={cn('text-[11.5px]', style.text)}>{n.caption}</span>}
          </li>
        )
      })}
    </ol>
  )
}

/** The OM's entry / exit record for a class, read-only. Shown to the professor and every verifier. */
export function ClassTimingPanel({ session, label, emphasise }: { session: ClassSessionBrief | null; label?: string; emphasise?: boolean }) {
  return (
    <Section
      title="Class timing (recorded by OM)"
      label={label}
      aside={session ? <Badge tone={session.timing_status === 'DELAYED' ? 'warning' : 'success'}>{session.timing_status === 'DELAYED' ? `Delayed ${session.delay_minutes} min` : 'On time'}</Badge> : undefined}
    >
      {!session ? (
        <div className={cn('flex items-start gap-2.5 text-[13px]', emphasise ? 'text-warning' : 'text-fg-label')}>
          <DoorOpen className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <span>Entry and exit were not recorded for this class.{emphasise && ' Record them from Class Schedule before giving the final verification, or note the reason in your remarks.'}</span>
        </div>
      ) : (
        <DefinitionList
          columns={4}
          items={[
            { label: 'Held on', value: fmt.date(session.date) },
            { label: 'Scheduled', value: <span className="tnum">{fmt.timeRange(session.scheduled_start, session.scheduled_end)}</span> },
            { label: 'Entry', value: <span className="tnum">{fmt.clock(session.entry_time)}</span> },
            { label: 'Exit', value: session.exit_time ? <span className="tnum">{fmt.clock(session.exit_time)}</span> : <span className="text-warning">Not recorded</span> },
            { label: 'Room', value: session.room ?? '—' },
            { label: 'Time in class', value: session.duration_minutes != null ? `${session.duration_minutes} min` : '—' },
            ...(session.early_exit_reason ? [{ label: 'Early exit', value: `${session.early_exit_minutes} min – ${session.early_exit_reason}` }] : []),
            ...(session.timing_status === 'DELAYED'
              ? [{ label: 'Delay reason', value: `${session.delay_reason_label ?? '—'}${session.delay_remarks ? ` – ${session.delay_remarks}` : ''}` }]
              : []),
          ]}
        />
      )}
    </Section>
  )
}
