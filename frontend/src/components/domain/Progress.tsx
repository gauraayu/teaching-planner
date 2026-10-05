import { CheckCircle2, FilePlus2, FileWarning, Pencil, Send, ShieldCheck, Upload } from 'lucide-react'
import { fmt } from '@/lib/status'
import type { AuditEntry, Metrics, UnitRow } from '@/types/domain'
import { cn } from '@/utils/cn'
import { SegmentBar } from '@/components/ui/Display'

const ICON: Record<string, typeof Pencil> = {
  'plan.created': FilePlus2,
  'plan.imported': Upload,
  'plan.published': Send,
  'progress.saved': Pencil,
  'progress.submitted': Send,
  'progress.resubmitted': Send,
  'verification.verified': ShieldCheck,
  'verification.final_verified': CheckCircle2,
  'verification.correction_requested': FileWarning,
  'lecture.corrected': Pencil,
}

/** Activity timeline, sourced from the append-only audit log. */
export function ActivityTimeline({ items, empty = 'No activity recorded yet.' }: { items: AuditEntry[]; empty?: string }) {
  if (!items.length) return <p className="meta px-4 py-6">{empty}</p>
  const dayOf = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
  return (
    <ol className="px-4 py-3">
      {items.map((a, i) => {
        const day = dayOf(a.created_at)
        const header = i === 0 || day !== dayOf(items[i - 1].created_at)
        const Icon = ICON[a.action] ?? Pencil
        const tone = a.action.includes('correction') ? 'text-danger bg-danger-soft' : a.action.includes('final') ? 'text-primary bg-primary-soft' : 'text-fg-secondary bg-surface-3'
        return (
          <li key={a.id}>
            {header && <div className="mt-2 mb-1.5 text-[11.5px] font-semibold tracking-wide text-fg-muted uppercase first:mt-0">{day}</div>}
            <div className="flex gap-3 py-1.5">
              <span className="tnum w-16 shrink-0 pt-0.5 text-[12px] text-fg-muted">{fmt.time(a.created_at)}</span>
              <span className={cn('flex h-6 w-6 shrink-0 items-center justify-center rounded-full', tone)}>
                <Icon className="h-3.5 w-3.5" aria-hidden />
              </span>
              <div className="min-w-0 text-[13px]">
                <p className="text-fg">{a.summary}</p>
                <p className="meta">
                  {a.actor?.full_name ?? 'System'}
                  {a.actor_role && ` · ${a.actor_role}`}
                </p>
              </div>
            </div>
          </li>
        )
      })}
    </ol>
  )
}

export const BUCKET_SEGMENTS = (m: Metrics) => [
  { value: m.completed, className: 'bg-primary', label: 'Completed' },
  { value: m.partial, className: 'bg-warning', label: 'Partial' },
  { value: m.delayed, className: 'bg-danger', label: 'Delayed' },
  { value: m.pending, className: 'bg-line-strong', label: 'Pending' },
]

export function BucketLegend({ m }: { m: Metrics }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-fg-secondary">
      {BUCKET_SEGMENTS(m).map((s) => (
        <span key={s.label} className="inline-flex items-center gap-1.5">
          <span className={cn('h-2 w-2 rounded-sm', s.className)} aria-hidden />
          {s.label} <b className="tnum text-fg">{s.value}</b>
        </span>
      ))}
    </div>
  )
}

export function UnitProgressTable({ units }: { units: UnitRow[] }) {
  if (!units.length) return <p className="meta px-4 py-6">No lectures yet.</p>
  return (
    <table className="w-full text-[13px]">
      <thead>
        <tr className="border-b border-line bg-surface-2 text-left text-[11.5px] font-semibold tracking-wide text-fg-label uppercase">
          <th className="px-4 py-2">Unit</th>
          <th className="px-3 py-2">Lectures</th>
          <th className="w-[45%] px-3 py-2">Progress</th>
          <th className="px-3 py-2 text-right">Done</th>
        </tr>
      </thead>
      <tbody>
        {units.map((u) => (
          <tr key={u.unit_no ?? 'none'} className="border-b border-line-subtle last:border-0">
            <td className="px-4 py-2.5">
              <div className="font-medium text-fg">{u.unit_no ? `Unit ${u.unit_no}` : 'No unit'}</div>
              <div className="meta max-w-xs truncate">Starts with {u.first_topic}</div>
            </td>
            <td className="tnum px-3 py-2.5">{u.total}</td>
            <td className="px-3 py-2.5">
              <SegmentBar segments={BUCKET_SEGMENTS(u)} />
            </td>
            <td className="tnum px-3 py-2.5 text-right font-medium">{u.execution_pct}%</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function MetricDefinitions({ definitions }: { definitions: Record<string, string> }) {
  const labels: Record<string, string> = {
    completed: 'Completed', partial: 'Partial', delayed: 'Delayed', pending: 'Pending',
    execution_pct: 'Execution completion', verified_pct: 'Verified completion', on_time_pct: 'On-time completion',
  }
  return (
    <details className="group">
      <summary className="cursor-pointer text-[12.5px] font-medium text-fg-label hover:text-fg">How these numbers are calculated</summary>
      <dl className="mt-2 grid gap-x-6 gap-y-1.5 text-[12.5px] sm:grid-cols-2">
        {Object.entries(definitions).map(([k, v]) => (
          <div key={k}>
            <dt className="inline font-medium text-fg-soft">{labels[k] ?? k}: </dt>
            <dd className="inline text-fg-label">{v}</dd>
          </div>
        ))}
      </dl>
    </details>
  )
}
