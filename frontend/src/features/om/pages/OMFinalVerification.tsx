import { useState } from 'react'
import { Segmented } from '@/components/forms/Fields'
import { PageHeader, useBreadcrumbs } from '@/components/layout/PageHeader'
import { useApi } from '@/hooks/useApi'
import type { Paged } from '@/services/api'
import type { QueueRow } from '@/types/domain'
import { FinalVerificationPanel, reviewFlag } from '../components/FinalVerificationPanel'

type View = 'pending' | 'verified'

/** Last step of the chain: records already verified by CL/CH, waiting for the OM. */
export function OMFinalVerification() {
  useBreadcrumbs([{ label: 'Verification' }, { label: 'Final Verification' }])
  const [view, setView] = useState<View>('pending')
  const pending = useApi<Paged<QueueRow>>('/verifications/queue/pending')
  const verified = useApi<Paged<QueueRow>>(view === 'verified' ? '/verifications/queue/verified' : null)
  const q = view === 'pending' ? pending : verified
  const flagged = pending.data?.items.filter((r) => reviewFlag(r)).length ?? 0
  return (
    <div>
      <PageHeader
        title="Final Verification"
        description={`CL/CH has verified these records. Check them against the class timing and give the final verification.${flagged ? ` ${flagged} need a closer look.` : ''}`}
      />
      <FinalVerificationPanel
        rows={q.data?.items}
        loading={q.loading}
        error={q.error?.message}
        onRetry={q.reload}
        mode={view === 'pending' ? 'pending' : 'closed'}
        emptyTitle={view === 'pending' ? 'Nothing waiting for final verification' : 'No final-verified records yet'}
        emptyDescription={view === 'pending' ? 'Waiting for CL/CH academic verification. Records appear here once CL/CH has verified them.' : 'Records you final verify are listed here.'}
        toolbar={
          <Segmented
            ariaLabel="Queue"
            size="sm"
            value={view}
            onChange={setView}
            options={[{ value: 'pending', label: 'Awaiting final verification', count: pending.data?.total }, { value: 'verified', label: 'Final verified' }]}
          />
        }
      />
    </div>
  )
}

/** Pending records with a timing problem, and corrections the OM has sent back. */
export function OMReviewRequired() {
  useBreadcrumbs([{ label: 'Verification' }, { label: 'Review Required' }])
  const pending = useApi<Paged<QueueRow>>('/verifications/queue/pending')
  const corrections = useApi<Paged<QueueRow>>('/verifications/queue/corrections')
  const flagged = pending.data?.items.filter((r) => reviewFlag(r))
  const open = corrections.data?.items.filter((r) => r.submission_status === 'CORRECTION_REQUIRED')
  return (
    <div>
      <PageHeader title="Review Required" description="Records that should not be signed off without a second look: missing or delayed timings, and corrections you are waiting on." />
      <h2 className="th mb-2 text-[12px]">Timing needs attention{flagged ? ` · ${flagged.length}` : ''}</h2>
      <FinalVerificationPanel
        rows={flagged}
        loading={pending.loading}
        error={pending.error?.message}
        onRetry={pending.reload}
        emptyTitle="No timing issues"
        emptyDescription="Every record awaiting final verification has an on-time, complete timing record."
      />
      <h2 className="th mt-7 mb-2 text-[12px]">Returned to professor by OM{open ? ` · ${open.length}` : ''}</h2>
      <FinalVerificationPanel
        rows={open}
        loading={corrections.loading}
        error={corrections.error?.message}
        onRetry={corrections.reload}
        mode="closed"
        emptyTitle="No open corrections"
        emptyDescription="Corrections you request stay here until the professor resubmits."
      />
    </div>
  )
}
