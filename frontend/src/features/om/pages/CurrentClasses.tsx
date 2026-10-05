import { PageHeader, useBreadcrumbs } from '@/components/layout/PageHeader'
import { fmt } from '@/lib/status'
import { ClassOperations } from '../components/ClassOperations'
import { LiveTag } from '../components/status'
import { useOmDay } from '../hooks/useOmDay'

/** The walk-around board: classes in session right now, as cards on every screen size. */
export function CurrentClasses() {
  useBreadcrumbs([{ label: 'Live Operations' }, { label: 'Currently Running' }])
  const day = useOmDay()
  const all = day.data?.classes
  const running = all?.filter((c) => c.state === 'IN_CLASS')
  const due = all?.filter((c) => c.state === 'ENTRY_DUE') ?? []
  return (
    <div>
      <PageHeader
        title="Currently Running"
        description="Classes in session now. Record the exit as each professor leaves."
        meta={day.data ? <><LiveTag label={`${running?.length ?? 0} in class`} /><span className="meta">as of {fmt.clock(day.data.now)}</span></> : undefined}
      />
      <ClassOperations
        cardsOnly
        rows={running}
        loading={day.loading}
        error={day.error?.message}
        onRetry={day.reload}
        onChanged={day.applyRow}
        emptyTitle="No class is in session"
        emptyDescription="A class appears here as soon as its entry time is recorded."
      />
      {due.length > 0 && (
        <section className="mt-7">
          <h2 className="th mb-1 text-[12px]">Slot started, entry not recorded</h2>
          <p className="meta mb-3">These classes should be running by the schedule. Record the entry when the professor is in the room.</p>
          <ClassOperations cardsOnly rows={due} onChanged={day.applyRow} />
        </section>
      )}
    </div>
  )
}
