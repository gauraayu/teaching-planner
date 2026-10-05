import type { ColumnDef } from '@tanstack/react-table'
import { Users } from 'lucide-react'
import { useMemo, useState } from 'react'
import { EmptyState } from '@/components/feedback/States'
import { PageHeader, useBreadcrumbs } from '@/components/layout/PageHeader'
import { DataTable } from '@/components/tables/DataTable'
import { FilterBar, FilterDate } from '@/components/tables/FilterBar'
import { ProgressBar } from '@/components/ui/Display'
import { useApi } from '@/hooks/useApi'
import { fmt, todayISO } from '@/lib/status'
import type { Paged } from '@/services/api'
import type { FacultyRecord } from '../types/om.types'
import { daysAgo } from './OperationsRecords'

export function FacultyRecords() {
  useBreadcrumbs([{ label: 'Records' }, { label: 'Faculty Records' }])
  const initial = { date_from: daysAgo(30), date_to: todayISO() }
  const [f, setF] = useState(initial)
  const data = useApi<Paged<FacultyRecord>>('/om/faculty', f)
  const columns = useMemo<ColumnDef<FacultyRecord>[]>(
    () => [
      {
        id: 'professor',
        header: 'Professor',
        accessorFn: (r) => r.professor.full_name,
        cell: ({ row: { original: r } }) => (
          <div className="min-w-[170px]">
            <div className="font-medium text-fg">{r.professor.full_name}</div>
            <div className="meta truncate">{r.subjects.join(', ')}</div>
          </div>
        ),
      },
      { id: 'recorded', header: 'Classes recorded', accessorFn: (r) => r.recorded, meta: { align: 'right', className: 'tnum' } },
      { id: 'on_time', header: 'On time', accessorFn: (r) => r.on_time, meta: { align: 'right', className: 'tnum' } },
      { id: 'delayed', header: 'Delayed', accessorFn: (r) => r.delayed, meta: { align: 'right' }, cell: ({ getValue }) => <span className={`tnum ${getValue<number>() ? 'font-semibold text-warning' : 'text-fg-muted'}`}>{getValue<number>()}</span> },
      {
        id: 'pct',
        header: 'On-time entry',
        accessorFn: (r) => r.on_time_pct,
        cell: ({ row: { original: r } }) => (
          <div className="flex min-w-[140px] items-center gap-2.5">
            <ProgressBar value={r.on_time_pct} label={`${r.professor.full_name} on-time entry`} tone={r.on_time_pct < 70 ? 'warning' : 'brand'} />
            <span className="tnum w-9 text-right font-medium text-fg">{r.on_time_pct}%</span>
          </div>
        ),
      },
      { id: 'avg', header: 'Avg delay', accessorFn: (r) => r.average_delay_minutes, meta: { align: 'right' }, cell: ({ getValue }) => <span className="tnum whitespace-nowrap">{getValue<number>() ? `${getValue<number>()} min` : '—'}</span> },
      { id: 'reason', header: 'Most common reason', accessorFn: (r) => r.top_delay_reason ?? '', cell: ({ getValue }) => <span className="whitespace-nowrap">{getValue<string>() || <span className="text-fg-faint">—</span>}</span> },
      { id: 'last', header: 'Last recorded', accessorFn: (r) => r.last_recorded, cell: ({ getValue }) => <span className="meta whitespace-nowrap">{fmt.dateShort(getValue<string>())}</span> },
    ],
    [],
  )
  return (
    <div>
      <PageHeader title="Faculty Records" description="Entry punctuality per professor, from recorded class timings. Delayed = entry beyond the configured tolerance." />
      <div className="mb-4">
        <FilterBar onReset={() => setF(initial)} active={JSON.stringify(f) !== JSON.stringify(initial)}>
          <FilterDate label="From" value={f.date_from} onChange={(v) => setF((x) => ({ ...x, date_from: v }))} />
          <FilterDate label="To" value={f.date_to} onChange={(v) => setF((x) => ({ ...x, date_to: v }))} />
        </FilterBar>
      </div>
      <div className="panel">
        <DataTable
          columns={columns}
          data={data.data?.items}
          loading={data.loading}
          error={data.error?.message}
          onRetry={data.reload}
          searchPlaceholder="Search professor…"
          initialSorting={[{ id: 'delayed', desc: true }]}
          empty={<EmptyState icon={<Users className="h-5 w-5" />} title="No recorded classes in this range" />}
        />
      </div>
    </div>
  )
}
