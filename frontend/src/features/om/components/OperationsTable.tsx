import type { ColumnDef } from '@tanstack/react-table'
import { CalendarX2 } from 'lucide-react'
import { useMemo, type ReactNode } from 'react'
import { EmptyState } from '@/components/feedback/States'
import { DataTable } from '@/components/tables/DataTable'
import { Button } from '@/components/ui/Button'
import { fmt } from '@/lib/status'
import type { ClassRow } from '../types/om.types'
import { nextAction, type ClassAction } from './LiveClassCard'
import { ClassStateBadge, LevelStatus, TimingBadge } from './status'

/** Desktop table for class operations: schedule, timing and the CL/CH → OM chain on one row. */
export function OperationsTable({
  rows,
  today,
  loading,
  error,
  onRetry,
  onAction,
  showDate,
  toolbar,
  empty,
  pageSize = 25,
  searchable = true,
}: {
  rows: ClassRow[] | undefined
  today: string
  loading?: boolean
  error?: string | null
  onRetry?: () => void
  onAction: (a: ClassAction, row: ClassRow) => void
  showDate?: boolean
  toolbar?: ReactNode
  empty?: ReactNode
  pageSize?: number
  searchable?: boolean
}) {
  const columns = useMemo<ColumnDef<ClassRow>[]>(
    () => [
      {
        id: 'time',
        header: showDate ? 'Date · time' : 'Scheduled time',
        accessorFn: (r) => `${r.date} ${r.scheduled_start ?? ''}`,
        cell: ({ row: { original: r } }) => (
          <div className="whitespace-nowrap">
            {showDate && <div className="font-medium text-fg">{fmt.weekday(r.date)} {fmt.dateShort(r.date)}</div>}
            <div className={showDate ? 'tnum meta' : 'tnum font-medium text-fg'}>{fmt.timeRange(r.scheduled_start, r.scheduled_end) || '—'}</div>
            {!showDate && <div className="mt-1"><ClassStateBadge state={r.state} /></div>}
          </div>
        ),
      },
      { id: 'professor', header: 'Professor', accessorFn: (r) => r.professor.full_name, cell: ({ getValue }) => <span className="font-medium whitespace-nowrap text-fg">{getValue<string>()}</span> },
      {
        id: 'subject',
        header: 'Subject',
        accessorFn: (r) => `${r.subject.name} ${r.subject.code} ${r.topic}`,
        cell: ({ row: { original: r } }) => (
          <div className="max-w-[220px] min-w-[140px]">
            <div className="truncate text-fg">{r.subject.name}</div>
            <div className="meta truncate">L{r.lecture_no} · {r.topic}</div>
          </div>
        ),
      },
      { id: 'section', header: 'Section', accessorFn: (r) => `Sem ${r.semester.replace('Semester ', '')}-${r.section}`, cell: ({ getValue }) => <span className="whitespace-nowrap">{getValue<string>()}</span> },
      { id: 'room', header: 'Room', accessorFn: (r) => r.room ?? '', cell: ({ getValue }) => <span className="tnum whitespace-nowrap">{getValue<string>() || '—'}</span> },
      { id: 'entry', header: 'Entry', accessorFn: (r) => r.entry_time ?? '', cell: ({ row: { original: r } }) => <span className="tnum whitespace-nowrap text-fg">{fmt.clock(r.entry_time) || <span className="text-fg-faint">—</span>}</span> },
      { id: 'exit', header: 'Exit', accessorFn: (r) => r.exit_time ?? '', cell: ({ row: { original: r } }) => <span className="tnum whitespace-nowrap text-fg">{fmt.clock(r.exit_time) || <span className="text-fg-faint">—</span>}</span> },
      { id: 'timing', header: 'Timing status', accessorFn: (r) => r.delay_minutes ?? -1, cell: ({ row: { original: r } }) => <TimingBadge row={r} /> },
      { id: 'clch', header: 'CL/CH', enableSorting: false, cell: ({ row: { original: r } }) => <LevelStatus status={r.verification.levels.CL_CH} compact={showDate} /> },
      { id: 'om', header: 'OM', enableSorting: false, cell: ({ row: { original: r } }) => <LevelStatus status={r.verification.levels.OM} compact={showDate} /> },
      {
        id: 'action',
        header: 'Action',
        enableSorting: false,
        meta: { align: 'right' },
        cell: ({ row: { original: r } }) => {
          const next = nextAction(r, today)
          return (
            <Button size="sm" variant={next.primary ? 'primary' : 'secondary'} onClick={(e) => { e.stopPropagation(); onAction(next.action, r) }}>
              {next.label}
            </Button>
          )
        },
      },
    ],
    [onAction, showDate, today],
  )
  return (
    <DataTable
      columns={columns}
      data={rows}
      loading={loading}
      error={error}
      onRetry={onRetry}
      toolbar={toolbar}
      searchable={searchable}
      pageSize={pageSize}
      searchPlaceholder="Search professor, subject, room…"
      onRowClick={(r) => onAction('view', r)}
      rowClassName={(row) => (row.original.state === 'IN_CLASS' ? 'bg-primary/[0.04]' : undefined)}
      caption="Class operations"
      empty={empty ?? <EmptyState icon={<CalendarX2 className="h-5 w-5" />} title="No classes scheduled" description="There are no published classes for this day." />}
    />
  )
}
