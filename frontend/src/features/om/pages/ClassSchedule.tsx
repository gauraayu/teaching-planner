import { ChevronLeft, ChevronRight } from 'lucide-react'
import { PageHeader, useBreadcrumbs } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { fmt, isoLocal, parseDate, todayISO } from '@/lib/status'
import { useSearchParams } from '@/lib/router'
import { ClassOperations } from '../components/ClassOperations'
import { useOmDay } from '../hooks/useOmDay'

function shift(iso: string, days: number) {
  const d = parseDate(iso)
  d.setDate(d.getDate() + days)
  return isoLocal(d)
}

/** Any day's classes. Past days can still be recorded (back-fill); future days are read-only. */
export function ClassSchedule() {
  useBreadcrumbs([{ label: 'Live Operations' }, { label: 'Class Schedule' }])
  const [params, setParams] = useSearchParams()
  const today = todayISO()
  const on = params.get('date') || today
  const go = (d: string) => setParams(d === today ? {} : { date: d }, { replace: true })
  const day = useOmDay(on)
  const m = day.data?.metrics
  return (
    <div>
      <PageHeader title="Class Schedule" description="Browse classes by day. Timings for an earlier day can be recorded here if they were missed." />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Button size="icon" aria-label="Previous day" onClick={() => go(shift(on, -1))}><ChevronLeft className="h-4 w-4" /></Button>
        <input type="date" aria-label="Date" value={on} onChange={(e) => e.target.value && go(e.target.value)} className="field h-8 w-40 text-[13px]" />
        <Button size="icon" aria-label="Next day" onClick={() => go(shift(on, 1))}><ChevronRight className="h-4 w-4" /></Button>
        {on !== today && <Button size="sm" variant="ghost" onClick={() => go(today)}>Today</Button>}
        <span className="ml-1 text-[13px] text-fg-secondary">
          <span className="font-medium text-fg">{fmt.weekday(on)}, {fmt.date(on)}</span>
          {m && ` · ${m.total} class${m.total === 1 ? '' : 'es'}${m.total ? ` · ${m.completed} completed${m.not_recorded ? ` · ${m.not_recorded} not recorded` : ''}` : ''}`}
        </span>
      </div>
      <ClassOperations
        rows={day.data?.classes}
        loading={day.loading}
        error={day.error?.message}
        onRetry={day.reload}
        onChanged={day.applyRow}
        emptyDescription="No published class falls on this date. Try the next teaching day."
        pageSize={50}
      />
    </div>
  )
}
