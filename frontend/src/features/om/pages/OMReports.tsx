import { useState } from 'react'
import { ErrorState, LoadingRows } from '@/components/feedback/States'
import { PageHeader, useBreadcrumbs } from '@/components/layout/PageHeader'
import { FilterBar, FilterDate } from '@/components/tables/FilterBar'
import { useApi } from '@/hooks/useApi'
import { fmt, todayISO } from '@/lib/status'
import { OMMetricCard, OMMetricGrid } from '../components/OMMetricCard'
import type { OMReport } from '../types/om.types'
import { daysAgo } from './OperationsRecords'

/** Stacked daily bars: on time (emerald) + delayed (amber). Two series, each with a legend entry and a tooltip. */
function DailyChart({ daily }: { daily: OMReport['daily'] }) {
  const max = Math.max(1, ...daily.map((d) => d.recorded))
  const ticks = [max, Math.round(max / 2), 0]
  if (!daily.length) return <p className="meta px-4 py-8 text-center">No recorded classes in this range.</p>
  return (
    <div className="px-4 pt-4 pb-3">
      <div className="mb-3 flex items-center gap-4 text-[12px] text-fg-secondary">
        <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-[2px] bg-primary" aria-hidden />On time</span>
        <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-[2px] bg-warning" aria-hidden />Delayed</span>
      </div>
      <div className="flex gap-2">
        <div className="tnum flex h-40 flex-col justify-between text-right text-[11px] text-fg-muted" aria-hidden>
          {ticks.map((t, i) => <span key={i}>{t}</span>)}
        </div>
        <div className="min-w-0 flex-1 overflow-x-auto scroll-thin">
          <div className="relative flex h-40 items-end gap-[3px] border-b border-line" style={{ minWidth: daily.length * 14 }}>
            <span className="pointer-events-none absolute inset-x-0 top-0 border-t border-line-subtle" aria-hidden />
            <span className="pointer-events-none absolute inset-x-0 top-1/2 border-t border-line-subtle" aria-hidden />
            {daily.map((d) => (
              <div
                key={d.date}
                className="group relative flex h-full max-w-9 flex-1 flex-col justify-end gap-[2px]"
                title={`${fmt.weekday(d.date)} ${fmt.dateShort(d.date)}: ${d.on_time} on time, ${d.delayed} delayed`}
              >
                {d.delayed > 0 && <div className="rounded-t-[3px] bg-warning group-hover:opacity-80" style={{ height: `${(d.delayed / max) * 100}%` }} />}
                {d.on_time > 0 && <div className={`bg-primary group-hover:opacity-80 ${d.delayed ? '' : 'rounded-t-[3px]'}`} style={{ height: `${(d.on_time / max) * 100}%` }} />}
              </div>
            ))}
          </div>
          <div className="mt-1.5 flex justify-between text-[11px] text-fg-muted" style={{ minWidth: daily.length * 14 }}>
            <span>{fmt.dateShort(daily[0].date)}</span>
            {daily.length > 1 && <span>{fmt.dateShort(daily[daily.length - 1].date)}</span>}
          </div>
        </div>
      </div>
      <table className="sr-only">
        <caption>Recorded classes per day</caption>
        <thead><tr><th>Date</th><th>On time</th><th>Delayed</th></tr></thead>
        <tbody>{daily.map((d) => <tr key={d.date}><td>{d.date}</td><td>{d.on_time}</td><td>{d.delayed}</td></tr>)}</tbody>
      </table>
    </div>
  )
}

function ReasonBars({ reasons, total }: { reasons: OMReport['reasons']; total: number }) {
  if (!reasons.length) return <p className="meta px-4 py-8 text-center">No delayed entries in this range.</p>
  const max = Math.max(...reasons.map((r) => r.count))
  return (
    <ul className="space-y-3 p-4">
      {reasons.map((r) => (
        <li key={r.reason} title={`${r.label}: ${r.count} of ${total} delayed entries`}>
          <div className="mb-1 flex items-baseline justify-between gap-3 text-[13px]">
            <span className="text-fg-soft">{r.label}</span>
            <span className="tnum text-fg">{r.count} <span className="text-fg-muted">· {Math.round((r.count * 100) / total)}%</span></span>
          </div>
          <div className="h-2 rounded-full bg-track">
            <div className="h-full rounded-full bg-warning" style={{ width: `${(r.count / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  )
}

export function OMReports() {
  useBreadcrumbs([{ label: 'Reports' }, { label: 'Operational Reports' }])
  const initial = { date_from: daysAgo(30), date_to: todayISO() }
  const [f, setF] = useState(initial)
  const rep = useApi<OMReport>('/om/reports/summary', f)
  const r = rep.data
  const s = r?.summary
  return (
    <div>
      <PageHeader title="Operational Reports" description="Punctuality and coverage from recorded class timings." />
      <div className="mb-4">
        <FilterBar onReset={() => setF(initial)} active={JSON.stringify(f) !== JSON.stringify(initial)}>
          <FilterDate label="From" value={f.date_from} onChange={(v) => setF((x) => ({ ...x, date_from: v }))} />
          <FilterDate label="To" value={f.date_to} onChange={(v) => setF((x) => ({ ...x, date_to: v }))} />
        </FilterBar>
      </div>
      {rep.error ? (
        <div className="panel"><ErrorState message={rep.error.message} onRetry={rep.reload} /></div>
      ) : !r || !s ? (
        <div className="panel"><LoadingRows /></div>
      ) : (
        <>
          <OMMetricGrid>
            <OMMetricCard label="Classes recorded" value={s.recorded} sub={`of ${s.scheduled} scheduled`} tone="neutral" />
            <OMMetricCard label="Coverage" value={`${s.coverage_pct}%`} sub="Scheduled with entry" />
            <OMMetricCard label="On-time entry" value={`${s.on_time_pct}%`} sub={`${s.on_time} classes`} />
            <OMMetricCard label="Delayed entry" value={s.delayed} sub={`Beyond ${r.tolerance_minutes} min`} tone={s.delayed ? 'warning' : 'neutral'} />
            <OMMetricCard label="Average delay" value={s.delayed ? `${s.average_delay_minutes} min` : '—'} sub={`${s.total_delay_minutes} min lost in total`} tone="neutral" />
            <OMMetricCard label="Exit missing" value={s.exit_missing} sub="Entry without exit" tone={s.exit_missing ? 'warning' : 'neutral'} />
          </OMMetricGrid>
          <div className="mt-5 grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
            <section className="panel">
              <div className="panel-header"><h2 className="panel-title">Recorded classes per day</h2><span className="meta">{fmt.dateShort(r.date_from)} – {fmt.dateShort(r.date_to)}</span></div>
              <DailyChart daily={r.daily} />
            </section>
            <section className="panel">
              <div className="panel-header"><h2 className="panel-title">Delay reasons</h2><span className="meta">{s.delayed} delayed</span></div>
              <ReasonBars reasons={r.reasons} total={s.delayed} />
            </section>
          </div>
          <section className="panel mt-5">
            <div className="panel-header"><h2 className="panel-title">Definitions</h2></div>
            <dl className="grid grid-cols-1 gap-x-8 gap-y-2 p-4 text-[13px] sm:grid-cols-3">
              {Object.entries(r.definitions).map(([k, v]) => (
                <div key={k}><dt className="font-medium text-fg capitalize">{k.replace('_', ' ')}</dt><dd className="meta mt-0.5">{v}</dd></div>
              ))}
            </dl>
          </section>
        </>
      )}
    </div>
  )
}
