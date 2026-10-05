import { VerificationTimeline as Timeline } from '@/components/domain/VerificationTimeline'
import type { ClassRow } from '../types/om.types'

/** Professor -> CL/CH -> OM for one class row. Thin adapter over the shared timeline. */
export function VerificationTimeline({ row, compact }: { row: ClassRow; compact?: boolean }) {
  const v = row.verification
  return <Timeline submitted={!!v.submitted_at} submissionStatus={v.submission_status} steps={v.steps.map((s) => ({ ...s, round: v.round }))} round={v.round} compact={compact} />
}
