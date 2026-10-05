import { classPhase, countdownLabel, type InstNow } from '@/lib/date-time/institution'
import type { Tone } from '@/lib/status'
import type { SprintRow } from '@/types/domain'

export type RowState = {
  key: 'COMPLETED' | 'PARTIAL' | 'NOT_CONDUCTED' | 'LIVE' | 'NEXT' | 'UPCOMING' | 'PENDING_UPDATE' | 'AWAITING_START'
  label: string
  tone: Tone
  /** "Starts in 18 min", shown beside the time for the next class. */
  countdown: string
  action: string
  primary: boolean
}

/**
 * What a class row should say and offer right now. Decided in one place so the dashboard,
 * Today's Classes and the Sprint Plan can never disagree. `isNext` = the first class today
 * that has not been delivered yet.
 */
export function rowState(row: SprintRow, now: InstNow, lead: number, isNext: boolean): RowState {
  const submitted = !!row.submission_status && row.submission_status !== 'DRAFT' && row.submission_status !== 'CORRECTION_REQUIRED'
  const base = { countdown: '', primary: false }
  if (row.execution_status === 'COMPLETED' || row.execution_status === 'PARTIALLY_COMPLETED') {
    const partial = row.execution_status === 'PARTIALLY_COMPLETED'
    return { ...base, key: partial ? 'PARTIAL' : 'COMPLETED', label: partial ? 'Partially completed' : 'Completed', tone: partial ? 'warning' : 'success',
      action: submitted ? 'View details' : row.submission_status === 'CORRECTION_REQUIRED' ? 'Fix record' : 'Submit record', primary: !submitted }
  }
  if (row.execution_status === 'NOT_CONDUCTED') return { ...base, key: 'NOT_CONDUCTED', label: 'Not conducted', tone: 'danger', action: 'View details' }
  if (row.started_at && !row.ended_at) return { ...base, key: 'LIVE', label: 'In progress', tone: 'success', action: 'Open class', primary: true }
  if (row.started_at && row.ended_at) return { ...base, key: 'PENDING_UPDATE', label: 'Record pending', tone: 'warning', action: 'Complete record', primary: true }
  const { phase, minutesToStart } = classPhase(row.date, row.start, row.end, now, lead)
  if (phase === 'OTHER_DAY_PAST' || phase === 'OVER') return { ...base, key: 'PENDING_UPDATE', label: 'Update pending', tone: 'warning', action: 'Update now', primary: true }
  if (phase === 'NOW') return { key: 'AWAITING_START', label: 'Start class', tone: 'success', countdown: 'Starting now', action: 'Start class', primary: true }
  if (isNext && (phase === 'SOON' || phase === 'UPCOMING')) return { key: 'NEXT', label: 'Next class', tone: 'info', countdown: countdownLabel(minutesToStart, phase), action: 'Open class', primary: true }
  return { ...base, key: 'UPCOMING', label: 'Upcoming', tone: 'neutral', action: phase === 'OTHER_DAY_FUTURE' ? 'View details' : 'Open class' }
}

/** Index of the first class of `today` that still has to happen (or is running). -1 if none. */
export function nextIndex(rows: SprintRow[], now: InstNow): number {
  return rows.findIndex((r) => {
    if (r.date !== now.date || r.execution_status === 'COMPLETED' || r.execution_status === 'PARTIALLY_COMPLETED' || r.execution_status === 'NOT_CONDUCTED') return false
    if (r.started_at) return !r.ended_at
    const p = classPhase(r.date, r.start, r.end, now).phase
    return p === 'UPCOMING' || p === 'SOON' || p === 'NOW'
  })
}
