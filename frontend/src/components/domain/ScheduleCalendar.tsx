import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useMemo } from 'react'
import { Link } from '@/lib/router'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { fmt, isoLocal, parseDate, todayISO, type Tone } from '@/lib/status'
import { cn } from '@/utils/cn'

export type CalendarItem = { id: string; date: string; title: string; subtitle?: string; time?: string; status: string; tone: Tone; href?: string }

const TONE_DOT: Record<Tone, string> = {
  neutral: 'border-line-strong bg-surface', brand: 'border-primary bg-primary', success: 'border-primary bg-primary',
  warning: 'border-warning bg-warning', danger: 'border-danger bg-danger', info: 'border-info bg-info',
}

export function monthRange(month: Date) {
  const first = new Date(month.getFullYear(), month.getMonth(), 1)
  const start = new Date(first)
  start.setDate(first.getDate() - ((first.getDay() + 6) % 7))
  const end = new Date(start)
  end.setDate(start.getDate() + 41)
  return { first, start, end }
}

/** Month calendar on desktop, agenda list on mobile. Status is shown as text + marker, never colour alone. */
export function ScheduleCalendar({ month, onMonth, items, legend }: { month: Date; onMonth: (d: Date) => void; items: CalendarItem[]; legend: { label: string; tone: Tone }[] }) {
  const { first, start } = monthRange(month)
  const today = todayISO()
  const byDay = useMemo(() => {
    const m = new Map<string, CalendarItem[]>()
    for (const it of items) m.set(it.date, [...(m.get(it.date) ?? []), it])
    return m
  }, [items])
  const days = Array.from({ length: 42 }, (_, i) => {
    const d = new Date(start)
    d.setDate(start.getDate() + i)
    return d
  })
  const monthItems = items.filter((i) => parseDate(i.date).getMonth() === first.getMonth()).sort((a, b) => (a.date + (a.time ?? '')).localeCompare(b.date + (b.time ?? '')))
  const shift = (n: number) => onMonth(new Date(month.getFullYear(), month.getMonth() + n, 1))

  return (
    <div className="panel">
      <div className="panel-header">
        <div className="flex items-center gap-1">
          <Button size="icon" variant="ghost" aria-label="Previous month" onClick={() => shift(-1)}><ChevronLeft className="h-4 w-4" /></Button>
          <h2 className="w-36 text-center text-[14px] font-semibold text-fg">{first.toLocaleDateString('en-IN', { month: 'long', year: 'numeric' })}</h2>
          <Button size="icon" variant="ghost" aria-label="Next month" onClick={() => shift(1)}><ChevronRight className="h-4 w-4" /></Button>
          <Button size="sm" variant="ghost" onClick={() => onMonth(new Date())}>Today</Button>
        </div>
        <div className="max-sm:hidden flex-wrap gap-3 text-[12px] text-fg-secondary sm:flex">
          {legend.map((l) => (
            <span key={l.label} className="inline-flex items-center gap-1.5">
              <span className={cn('h-2.5 w-2.5 rounded-full border', TONE_DOT[l.tone])} aria-hidden /> {l.label}
            </span>
          ))}
        </div>
      </div>

      {/* Desktop month grid */}
      <div className="max-md:hidden md:block">
        <div className="grid grid-cols-7 border-b border-line bg-surface-2 text-[11.5px] font-semibold tracking-wide text-fg-label uppercase">
          {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d) => <div key={d} className="px-2 py-1.5">{d}</div>)}
        </div>
        <div className="grid grid-cols-7">
          {days.map((d) => {
            const key = isoLocal(d)
            const list = byDay.get(key) ?? []
            const inMonth = d.getMonth() === first.getMonth()
            return (
              <div key={key} className={cn('min-h-[104px] border-r border-b border-line-subtle p-1.5 [&:nth-child(7n)]:border-r-0', !inMonth && 'bg-surface-2/60')}>
                <div className={cn('tnum mb-1 flex h-5 w-5 items-center justify-center rounded-full text-[12px]', key === today ? 'bg-primary font-semibold text-on-primary' : inMonth ? 'text-fg-soft' : 'text-fg-faint')}>{d.getDate()}</div>
                <ul className="space-y-0.5">
                  {list.slice(0, 3).map((it) => {
                    const inner = (
                      <>
                        <span className={cn('mt-1 h-2 w-2 shrink-0 rounded-full border', TONE_DOT[it.tone])} aria-hidden />
                        <span className="min-w-0 truncate">{it.title}</span>
                        <span className="sr-only">({it.status})</span>
                      </>
                    )
                    return (
                      <li key={it.id} title={`${it.title}${it.subtitle ? ` · ${it.subtitle}` : ''} · ${it.status}`}>
                        {it.href ? <Link to={it.href} className="flex gap-1 rounded px-1 py-0.5 text-[11.5px] text-fg-soft hover:bg-surface-3">{inner}</Link> : <div className="flex gap-1 px-1 py-0.5 text-[11.5px] text-fg-soft">{inner}</div>}
                      </li>
                    )
                  })}
                  {list.length > 3 && <li className="px-1 text-[11px] text-fg-label">+{list.length - 3} more</li>}
                </ul>
              </div>
            )
          })}
        </div>
      </div>

      {/* Mobile agenda */}
      <ul className="divide-y divide-line-subtle md:hidden">
        {monthItems.length === 0 && <li className="meta px-4 py-6 text-center">No lectures this month.</li>}
        {monthItems.map((it) => {
          const body = (
            <div className={cn('flex gap-3 px-4 py-3', it.date === today && 'bg-primary/5')}>
              <div className="w-12 shrink-0 text-center">
                <div className="text-[11px] text-fg-label uppercase">{fmt.weekday(it.date)}</div>
                <div className="tnum text-[17px] font-semibold text-fg">{parseDate(it.date).getDate()}</div>
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-[13.5px] font-medium text-fg">{it.title}</div>
                <div className="meta truncate">{[it.time, it.subtitle].filter(Boolean).join(' · ')}</div>
                <Badge tone={it.tone} className="mt-1">{it.status}</Badge>
              </div>
            </div>
          )
          return <li key={it.id}>{it.href ? <Link to={it.href}>{body}</Link> : body}</li>
        })}
      </ul>
    </div>
  )
}
