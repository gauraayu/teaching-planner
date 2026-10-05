import { ChevronLeft, ChevronRight } from 'lucide-react'
import type { ReactNode } from 'react'
import { Button } from '@/components/ui/Button'
import { addDays, mondayOf } from '@/lib/api/sprint'
import { fmt, todayISO } from '@/lib/status'
import type { SprintWeekInfo } from '@/types/domain'

export function weekLabel(w: { start: string; end: string }) {
  return `${fmt.dateShort(w.start)} – ${fmt.date(w.end)}`
}

/** Previous / current / next week. One week (Monday-Saturday) is always shown as a whole. */
export function WeekNav({ week, weekStart, onChange, children }: { week?: SprintWeekInfo; weekStart: string; onChange: (monday: string) => void; children?: ReactNode }) {
  const current = mondayOf(todayISO())
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex items-stretch overflow-hidden rounded-md border border-line-strong">
        <button type="button" onClick={() => onChange(addDays(weekStart, -7))} className="flex items-center gap-1 px-2.5 text-[12.5px] font-medium text-fg-secondary hover:bg-surface-3 hover:text-fg" aria-label="Previous week">
          <ChevronLeft className="h-4 w-4" /> <span className="max-sm:hidden sm:inline">Prev</span>
        </button>
        <div className="tnum border-x border-line-strong px-3 py-1.5 text-center text-[12.5px] font-semibold tracking-wide text-fg uppercase">
          {week?.number ? <span className="text-primary">Week {week.number} · </span> : null}
          {weekLabel({ start: weekStart, end: addDays(weekStart, 5) })}
        </div>
        <button type="button" onClick={() => onChange(addDays(weekStart, 7))} className="flex items-center gap-1 px-2.5 text-[12.5px] font-medium text-fg-secondary hover:bg-surface-3 hover:text-fg" aria-label="Next week">
          <span className="max-sm:hidden sm:inline">Next</span> <ChevronRight className="h-4 w-4" />
        </button>
      </div>
      <Button size="sm" disabled={weekStart === current} onClick={() => onChange(current)}>Current week</Button>
      {children}
    </div>
  )
}
