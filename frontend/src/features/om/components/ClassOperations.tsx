import { CalendarX2 } from 'lucide-react'
import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { EmptyState, ErrorState, LoadingRows } from '@/components/feedback/States'
import { todayISO } from '@/lib/status'
import type { ClassRow } from '../types/om.types'
import { ClassDetailDialog } from './ClassDetailDialog'
import { LiveClassCard, nextAction, type ClassAction } from './LiveClassCard'
import { OperationsTable } from './OperationsTable'
import { RecordEntryDialog } from './RecordEntryDialog'
import { RecordExitDialog } from './RecordExitDialog'

/**
 * One list of classes, two presentations: a TanStack table from the `lg` breakpoint up,
 * operational cards below it. Owns the entry / exit / view dialogs so every OM screen
 * records timings the same way.
 */
export function ClassOperations({
  rows,
  loading,
  error,
  onRetry,
  onChanged,
  showDate,
  toolbar,
  cardsOnly,
  emptyTitle = 'No classes scheduled',
  emptyDescription = 'There are no published classes for this day.',
  pageSize,
  searchable,
  openId,
  onOpened,
}: {
  rows: ClassRow[] | undefined
  loading?: boolean
  error?: string | null
  onRetry?: () => void
  onChanged: (row: ClassRow) => void
  showDate?: boolean
  toolbar?: ReactNode
  cardsOnly?: boolean
  emptyTitle?: string
  emptyDescription?: string
  pageSize?: number
  searchable?: boolean
  /** Lecture to open straight away (e.g. from the "class starts in 5 minutes" alert). */
  openId?: string | null
  onOpened?: () => void
}) {
  const today = todayISO()
  const [dialog, setDialog] = useState<{ kind: ClassAction; row: ClassRow } | null>(null)
  const onAction = useCallback((kind: ClassAction, row: ClassRow) => setDialog({ kind, row }), [])
  const close = () => setDialog(null)
  useEffect(() => {
    if (!openId || !rows) return
    const row = rows.find((r) => r.lecture_id === openId)
    if (row) setDialog({ kind: nextAction(row, today).action, row })
    onOpened?.()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openId, rows])
  const empty = <EmptyState icon={<CalendarX2 className="h-5 w-5" />} title={emptyTitle} description={emptyDescription} />

  return (
    <>
      {!cardsOnly && (
        <div className="panel max-lg:hidden lg:block">
          <OperationsTable rows={rows} today={today} loading={loading} error={error} onRetry={onRetry} onAction={onAction} showDate={showDate} toolbar={toolbar} empty={empty} pageSize={pageSize} searchable={searchable} />
        </div>
      )}
      <div className={cardsOnly ? '' : 'lg:hidden'}>
        {toolbar && !cardsOnly && <div className="mb-3">{toolbar}</div>}
        {error ? (
          <div className="panel"><ErrorState message={error} onRetry={onRetry} /></div>
        ) : loading && !rows ? (
          <div className="panel"><LoadingRows rows={4} /></div>
        ) : !rows?.length ? (
          <div className="panel">{empty}</div>
        ) : (
          <div className={cardsOnly ? 'grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3' : 'grid grid-cols-1 gap-3 sm:grid-cols-2'}>
            {rows.map((r) => <LiveClassCard key={r.lecture_id} row={r} today={today} onAction={onAction} showDate={showDate} />)}
          </div>
        )}
      </div>
      <RecordEntryDialog row={dialog?.kind === 'entry' ? dialog.row : null} onClose={close} onSaved={onChanged} />
      <RecordExitDialog row={dialog?.kind === 'exit' ? dialog.row : null} onClose={close} onSaved={onChanged} />
      <ClassDetailDialog row={dialog?.kind === 'view' ? dialog.row : null} onClose={close} />
    </>
  )
}
