import { RefreshCw } from 'lucide-react'
import { InlineAlert } from '@/components/feedback/States'
import { PageHeader, useBreadcrumbs } from '@/components/layout/PageHeader'
import { Button, ButtonLink } from '@/components/ui/Button'
import { fmt } from '@/lib/status'
import { Link } from '@/lib/router'
import { ClassOperations } from '../components/ClassOperations'
import { OMMetricCard, OMMetricGrid } from '../components/OMMetricCard'
import { useOmDay } from '../hooks/useOmDay'

export function OMDashboard() {
  useBreadcrumbs([{ label: 'Dashboard' }])
  const day = useOmDay()
  const d = day.data
  const m = d?.metrics
  const v = (n: number | undefined) => n ?? '–'
  return (
    <div>
      <PageHeader
        title="Operations Dashboard"
        description="Monitor scheduled classes, faculty timings and final verification."
        actions={
          <>
            <Button icon={<RefreshCw className="h-4 w-4" />} onClick={() => day.reload()} loading={day.loading && !!d}>Refresh</Button>
            <ButtonLink to="/om/final-verification" variant="primary">Final verification{m?.awaiting_final_verification ? ` (${m.awaiting_final_verification})` : ''}</ButtonLink>
          </>
        }
      />
      <OMMetricGrid>
        <OMMetricCard label="Today's classes" value={v(m?.total)} sub={d ? `${fmt.weekday(d.date)}, ${fmt.dateShort(d.date)}` : undefined} tone="neutral" />
        <OMMetricCard label="Currently running" value={v(m?.running)} sub={m?.entry_due ? `${m.entry_due} waiting for entry` : 'Entry recorded'} live={!!m?.running} />
        <OMMetricCard label="Yet to start" value={v(m?.yet_to_start)} sub="Later today" tone="neutral" />
        <OMMetricCard label="Completed" value={v(m?.completed)} sub={m?.not_recorded ? `${m.not_recorded} not recorded` : 'Entry and exit recorded'} />
        <OMMetricCard label="Delayed entry" value={v(m?.delayed_entry)} sub={d ? `Beyond ${d.tolerance_minutes} min tolerance` : undefined} tone={m?.delayed_entry ? 'warning' : 'neutral'} />
        <OMMetricCard label="Awaiting final verification" value={v(m?.awaiting_final_verification)} sub="CL/CH verified" tone={m?.awaiting_final_verification ? 'warning' : 'neutral'} />
      </OMMetricGrid>

      {m && m.not_recorded > 0 && (
        <InlineAlert tone="warning" className="mt-4" title={`${m.not_recorded} class${m.not_recorded === 1 ? '' : 'es'} finished without an entry record`}>
          Record the entry and exit below while the details are fresh.
        </InlineAlert>
      )}

      <div className="mt-6 mb-3 flex items-end justify-between gap-3">
        <div>
          <h2 className="th text-[12px]">Today's class operations</h2>
          {d && <p className="meta mt-0.5">Updated {fmt.clock(d.now)} · refreshes every minute</p>}
        </div>
        <Link to="/om/schedule" className="link text-[12.5px]">Other dates</Link>
      </div>
      <ClassOperations
        rows={d?.classes}
        loading={day.loading}
        error={day.error?.message}
        onRetry={day.reload}
        onChanged={day.applyRow}
        emptyTitle="No classes scheduled today"
        emptyDescription="Open Class Schedule to see or record timings for another day."
        pageSize={30}
      />
    </div>
  )
}
