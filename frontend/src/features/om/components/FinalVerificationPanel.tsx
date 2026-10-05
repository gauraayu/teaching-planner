import type { ColumnDef } from '@tanstack/react-table'
import { ShieldCheck } from 'lucide-react'
import { useMemo, type ReactNode } from 'react'
import { EmptyState, ErrorState, LoadingRows } from '@/components/feedback/States'
import { DataTable } from '@/components/tables/DataTable'
import { Badge, StatusBadge } from '@/components/ui/Badge'
import { Button, ButtonLink } from '@/components/ui/Button'
import { fmt, VERIFICATION_STATUS } from '@/lib/status'
import { useNavigate } from '@/lib/router'
import { levelName, type QueueRow } from '@/types/domain'

/** Why a pending record deserves a closer look before the OM signs it off. */
export function reviewFlag(r: QueueRow): { label: string; tone: 'warning' | 'danger' } | null {
  if (!r.class_session) return { label: 'Timing not recorded', tone: 'danger' }
  if (!r.class_session.exit_time) return { label: 'Exit not recorded', tone: 'warning' }
  if (r.class_session.timing_status === 'DELAYED') return { label: `Entry delayed ${r.class_session.delay_minutes} min`, tone: 'warning' }
  if (r.actual_date && r.class_session.date !== r.actual_date) return { label: 'Date differs from professor update', tone: 'warning' }
  return null
}

function Timing({ r }: { r: QueueRow }) {
  const s = r.class_session
  if (!s) return <Badge tone="danger">Not recorded</Badge>
  return (
    <div className="whitespace-nowrap">
      <div className="tnum text-fg">{fmt.clock(s.entry_time)} – {fmt.clock(s.exit_time) || '…'}</div>
      <div className={s.timing_status === 'DELAYED' ? 'text-[12px] font-medium text-warning' : 'meta'}>
        {s.timing_status === 'DELAYED' ? `Delayed ${s.delay_minutes} min` : 'On time'}{s.room ? ` · ${s.room}` : ''}
      </div>
    </div>
  )
}

/**
 * The OM's verification queue: CL/CH-verified records with the class timing beside
 * them. Table on desktop, cards on phones. Used by Final Verification and Review Required.
 */
export function FinalVerificationPanel({
  rows,
  loading,
  error,
  onRetry,
  mode = 'pending',
  emptyTitle = 'Nothing waiting for final verification',
  emptyDescription = 'Records appear here once CL/CH has verified them. Until then: waiting for CL/CH academic verification.',
  toolbar,
}: {
  rows: QueueRow[] | undefined
  loading?: boolean
  error?: string | null
  onRetry?: () => void
  mode?: 'pending' | 'closed'
  emptyTitle?: string
  emptyDescription?: string
  toolbar?: ReactNode
}) {
  const navigate = useNavigate()
  const columns = useMemo<ColumnDef<QueueRow>[]>(
    () => [
      { id: 'professor', header: 'Professor', accessorFn: (r) => r.professor.full_name, cell: ({ getValue }) => <span className="font-medium whitespace-nowrap text-fg">{getValue<string>()}</span> },
      {
        id: 'class',
        header: 'Class',
        accessorFn: (r) => `${r.subject.name} ${r.subject.code} ${r.topic}`,
        cell: ({ row: { original: r } }) => (
          <div className="max-w-[300px] min-w-[180px]">
            <div className="truncate text-fg">{r.subject.short_name ?? r.subject.code} <span className="text-fg-label">· {r.section} · L{r.lecture_no}</span></div>
            <div className="meta truncate">{r.topic}</div>
          </div>
        ),
      },
      { id: 'held', header: 'Held on', accessorFn: (r) => r.class_session?.date ?? r.actual_date ?? '', cell: ({ getValue }) => <span className="whitespace-nowrap">{fmt.dateShort(getValue<string>() || null)}</span> },
      { id: 'timing', header: 'Entry – exit', accessorFn: (r) => r.class_session?.delay_minutes ?? -1, cell: ({ row: { original: r } }) => <Timing r={r} /> },
      {
        id: 'chain',
        header: 'CL/CH',
        enableSorting: false,
        cell: ({ row: { original: r } }) => (
          <div className="text-[12.5px] whitespace-nowrap">
            {r.prior_verifications.map((p) => (
              <div key={p.id} className="text-primary">{levelName(p.verification_level)} ✓ <span className="text-fg-label">{p.verifier?.full_name}</span></div>
            ))}
          </div>
        ),
      },
      {
        id: 'flag',
        header: mode === 'pending' ? 'Check' : 'Status',
        accessorFn: (r) => (mode === 'pending' ? reviewFlag(r)?.label ?? '' : r.status),
        cell: ({ row: { original: r } }) => {
          if (mode !== 'pending') return <div><StatusBadge value={r.status} map={VERIFICATION_STATUS} />{r.remarks && <div className="meta mt-0.5 max-w-[220px] truncate">“{r.remarks}”</div>}</div>
          const f = reviewFlag(r)
          return f ? <Badge tone={f.tone}>{f.label}</Badge> : <Badge tone="success">Ready</Badge>
        },
      },
      { id: 'action', header: '', enableSorting: false, meta: { align: 'right' }, cell: () => <Button size="sm" variant={mode === 'pending' ? 'primary' : 'secondary'}>{mode === 'pending' ? 'Review' : 'Open'}</Button> },
    ],
    [mode],
  )
  const empty = <EmptyState icon={<ShieldCheck className="h-5 w-5" />} title={emptyTitle} description={emptyDescription} />
  return (
    <>
      <div className="panel max-lg:hidden lg:block">
        <DataTable columns={columns} data={rows} loading={loading} error={error} onRetry={onRetry} toolbar={toolbar} searchPlaceholder="Search professor, subject, topic…" onRowClick={(r) => navigate(`/om/review/${r.id}`)} empty={empty} />
      </div>
      <div className="lg:hidden">
        {toolbar && <div className="mb-3">{toolbar}</div>}
        {error ? (
          <div className="panel"><ErrorState message={error} onRetry={onRetry} /></div>
        ) : loading && !rows ? (
          <div className="panel"><LoadingRows rows={4} /></div>
        ) : !rows?.length ? (
          <div className="panel">{empty}</div>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {rows.map((r) => {
              const f = reviewFlag(r)
              return (
                <article key={r.id} className="panel flex flex-col">
                  <div className="flex-1 px-4 pt-3.5 pb-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="text-[12px] font-semibold tracking-wide text-primary uppercase">{r.subject.short_name ?? r.subject.code} <span className="font-normal text-fg-muted normal-case">· {r.section} · L{r.lecture_no}</span></div>
                      {mode === 'pending' ? (f ? <Badge tone={f.tone}>{f.label}</Badge> : <Badge tone="success">Ready</Badge>) : <StatusBadge value={r.status} map={VERIFICATION_STATUS} />}
                    </div>
                    <h3 className="mt-1.5 text-[14.5px] leading-snug font-semibold text-fg">{r.topic}</h3>
                    <p className="meta mt-0.5">{r.professor.full_name} · {fmt.dateShort(r.class_session?.date ?? r.actual_date)}</p>
                    <div className="mt-2.5"><Timing r={r} /></div>
                  </div>
                  <div className="border-t border-line-subtle p-2">
                    <ButtonLink to={`/om/review/${r.id}`} variant={mode === 'pending' ? 'primary' : 'secondary'} className="h-10 w-full justify-center">{mode === 'pending' ? 'Review' : 'Open'}</ButtonLink>
                  </div>
                </article>
              )
            })}
          </div>
        )}
      </div>
    </>
  )
}
