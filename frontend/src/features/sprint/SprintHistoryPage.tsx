import type { ColumnDef } from '@tanstack/react-table'
import { History } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { EmptyState, ErrorState, LoadingRows } from '@/components/feedback/States'
import { PageHeader, useBreadcrumbs } from '@/components/layout/PageHeader'
import { DataTable } from '@/components/tables/DataTable'
import { Badge } from '@/components/ui/Badge'
import { Button, ButtonLink } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { useApi } from '@/hooks/useApi'
import { adminSprintApi, type RevisionChanges } from '@/lib/api/sprint'
import { fmt } from '@/lib/status'
import { errorMessage, type Paged } from '@/services/api'
import type { SprintRevisionBrief, SprintWeekInfo } from '@/types/domain'
import { ChangeDiff } from './components/ChangeDiff'
import { weekLabel } from './components/WeekNav'

type Row = SprintRevisionBrief & { week: SprintWeekInfo }

export function RevisionDialog({ revisionId, onClose, load }: { revisionId: string | null; onClose: () => void; load: (id: string) => Promise<RevisionChanges> }) {
  const [data, setData] = useState<RevisionChanges | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (!revisionId) return
    setData(null)
    setError(null)
    load(revisionId).then(setData).catch((e) => setError(errorMessage(e)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [revisionId])
  if (!revisionId) return null
  const r = data?.revision
  return (
    <Dialog open onClose={onClose} size="lg" title={r ? `Sprint revision v${r.revision_number ?? '–'}` : 'Sprint revision'} description={data ? `${data.week.number ? `Week ${data.week.number} · ` : ''}${weekLabel(data.week)}` : undefined} footer={<Button onClick={onClose}>Close</Button>}>
      {error ? <ErrorState message={error} /> : !data ? <LoadingRows rows={3} /> : (
        <div className="space-y-3">
          <p className="meta">
            {r!.status === 'PUBLISHED' ? `Published by ${r!.published_by?.full_name ?? '—'} on ${fmt.dateTime(r!.published_at)}` : 'Draft – not published'}
            {r!.meeting_date ? ` · meeting ${fmt.date(r!.meeting_date)}` : ''}
          </p>
          {r!.meeting_notes && <p className="rounded-md bg-surface-2 px-3 py-2 text-[13px] text-fg-soft">{r!.meeting_notes}</p>}
          {data.changes.length === 0 ? <p className="meta">The week was reviewed; no schedule changes were made.</p> : data.changes.map((c, i) => <ChangeDiff key={c.id} c={c} index={i} />)}
        </div>
      )}
    </Dialog>
  )
}

/** Every published weekly revision (and any meeting still in draft), newest week first. */
export function SprintHistoryPage() {
  useBreadcrumbs([{ label: 'Teaching Management' }, { label: 'Sprint Meeting History' }])
  const history = useApi<Paged<Row>>('/admin/sprint-plan/history')
  const [open, setOpen] = useState<string | null>(null)
  const columns = useMemo<ColumnDef<Row>[]>(
    () => [
      { id: 'week', header: 'Week', accessorFn: (r) => r.week_start, cell: ({ row: { original: r } }) => <div className="whitespace-nowrap"><div className="font-medium text-fg">{weekLabel(r.week)}</div>{r.week.number && <div className="meta">Week {r.week.number}</div>}</div> },
      { id: 'meeting', header: 'Meeting date', accessorFn: (r) => r.meeting_date ?? '', cell: ({ getValue }) => <span className="whitespace-nowrap">{fmt.dateShort(getValue<string>() || null)}</span> },
      { id: 'rev', header: 'Revision', accessorFn: (r) => r.revision_number ?? 0, cell: ({ row: { original: r } }) => <span className="tnum font-semibold text-fg">{r.revision_number ? `v${r.revision_number}` : '—'}</span> },
      { id: 'changes', header: 'Changes', accessorFn: (r) => r.change_count, cell: ({ getValue }) => <span className="tnum whitespace-nowrap">{getValue<number>()} change{getValue<number>() === 1 ? '' : 's'}</span> },
      { id: 'by', header: 'Published by', accessorFn: (r) => r.published_by?.full_name ?? r.created_by?.full_name ?? '', cell: ({ getValue }) => <span className="whitespace-nowrap">{getValue<string>() || '—'}</span> },
      { id: 'at', header: 'Published at', accessorFn: (r) => r.published_at ?? '', cell: ({ getValue }) => <span className="meta whitespace-nowrap">{fmt.dateTime(getValue<string>() || null)}</span> },
      { id: 'status', header: 'Status', accessorFn: (r) => r.status, cell: ({ row: { original: r } }) => <Badge tone={r.status === 'PUBLISHED' ? 'success' : 'warning'}>{r.status === 'PUBLISHED' ? 'Published' : 'Draft'}</Badge> },
      { id: 'action', header: '', enableSorting: false, meta: { align: 'right' }, cell: ({ row: { original: r } }) => r.status === 'DRAFT' ? <ButtonLink size="sm" to={`/admin/sprint-plan?week=${r.week_start}`}>Continue</ButtonLink> : <Button size="sm">View</Button> },
    ],
    [],
  )
  return (
    <div>
      <PageHeader title="Sprint Meeting History" description="Every weekly revision of the semester plan. v1 is always the master plan itself; published revisions are never edited or deleted." actions={<ButtonLink to="/admin/sprint-plan" variant="primary">Open weekly sprint plan</ButtonLink>} />
      <div className="panel">
        <DataTable
          columns={columns}
          data={history.data?.items}
          loading={history.loading}
          error={history.error?.message}
          onRetry={history.reload}
          searchable={false}
          onRowClick={(r) => r.status === 'PUBLISHED' && setOpen(r.id)}
          empty={<EmptyState icon={<History className="h-5 w-5" />} title="No sprint revisions yet" description="Every week follows the semester master plan until a sprint meeting update is published." />}
        />
      </div>
      <RevisionDialog revisionId={open} onClose={() => setOpen(null)} load={adminSprintApi.changes} />
    </div>
  )
}
