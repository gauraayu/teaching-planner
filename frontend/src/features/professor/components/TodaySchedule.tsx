import { ArrowRight, CalendarCheck2 } from 'lucide-react'
import { EmptyState } from '@/components/feedback/States'
import { buttonClass } from '@/components/ui/Button'
import { useInstNow } from '@/lib/date-time/institution'
import { Link } from '@/lib/router'
import { useTodayFeed } from '@/providers/ScheduleNotificationProvider'
import type { SprintRow } from '@/types/domain'
import { cn } from '@/utils/cn'
import { nextIndex, rowState } from '../rowState'
import { CohortVenue, slotLabel, StateBadge, SubjectTopic } from './parts'

/** Today's teaching schedule: a five-column table from `md` up, stacked cards on a phone. */
export function TodaySchedule({ rows }: { rows: SprintRow[] }) {
  const now = useInstNow(15_000)
  const { leadMinutes } = useTodayFeed()
  const next = nextIndex(rows, now)
  if (!rows.length) {
    return <EmptyState icon={<CalendarCheck2 className="h-5 w-5" />} title="No classes scheduled today" description="Your week is on the Sprint Plan page." />
  }
  return (
    <div>
      <div className="max-md:hidden grid-cols-[130px_minmax(0,1.5fr)_minmax(0,0.9fr)_140px_130px] gap-4 border-b border-line bg-surface-2 px-4 py-2 md:grid">
        {['Time window', 'Subject & topic', 'Cohort & venue', 'Status', ''].map((h) => <div key={h} className="th">{h}</div>)}
      </div>
      <ul>
        {rows.map((row, i) => {
          const s = rowState(row, now, leadMinutes, i === next)
          const highlight = s.key === 'NEXT' || s.key === 'LIVE' || s.key === 'AWAITING_START'
          return (
            <li key={row.lecture_id} className={cn('grid grid-cols-1 gap-x-4 gap-y-2.5 border-b border-line-subtle px-4 py-3.5 last:border-0 md:grid-cols-[130px_minmax(0,1.5fr)_minmax(0,0.9fr)_140px_130px] md:items-center', highlight && 'bg-primary/[0.04]')}>
              <div>
                <div className={cn('tnum text-[13.5px] font-semibold whitespace-nowrap', highlight ? 'text-primary' : 'text-fg')}>{slotLabel(row)}</div>
                {s.countdown && <div className="text-[12px] font-medium text-info">{s.countdown}</div>}
              </div>
              <SubjectTopic row={row} />
              <CohortVenue row={row} />
              <div><StateBadge state={s} /></div>
              <Link to={`/professor/lectures/${row.lecture_id}`} className={cn(buttonClass(s.primary ? 'primary' : 'secondary', 'sm'), 'justify-center max-md:h-10')}>
                {s.action} {s.primary && <ArrowRight className="h-3.5 w-3.5" />}
              </Link>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
