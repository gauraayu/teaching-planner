import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { hm, type TimingTemplate } from '@/lib/api/timetable'
import { fmt } from '@/lib/status'
import { cn } from '@/utils/cn'

export type GridTone = 'first' | 'senior' | 'other' | 'lab' | 'carry' | 'conflict' | 'neutral'

/** One class on the grid. Positioned by its real start and end time, never by a lecture number. */
export type GridItem = {
  key: string
  day: number // index into `days`
  start: string
  end: string
  template: string | null // timing template code of the class's year group
  title: string
  subtitle?: string
  meta?: string
  tone: GridTone
  accent?: string // subject colour (CSS colour) for the left edge and the dot
  corner?: ReactNode // small status mark, top right
  hint?: string
  dim?: boolean
  onClick?: () => void
}
export type GridDay = { label: string; sub?: string; today?: boolean }

// Small, controlled accents on the dark theme: a coloured edge and a dot, never a filled cell.
const EDGE: Record<GridTone, string> = {
  first: 'var(--color-info)', senior: 'var(--color-primary-muted)', other: 'var(--color-primary-muted)', lab: 'var(--color-accent)',
  carry: 'var(--color-warning)', conflict: 'var(--color-danger)', neutral: 'var(--color-line-strong)',
}
const SUBJECT_COLORS = 8

/** A stable accent per subject: the same subject has the same colour on every screen. */
export function subjectColor(code: string): string {
  let h = 0
  for (const ch of code) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return `var(--color-sub-${(h % SUBJECT_COLORS) + 1})`
}

/** Year group of a template: the first template is First Year, the others the senior years. */
export function groupTone(templates: TimingTemplate[], code: string | null): GridTone {
  if (!code) return 'neutral'
  return templates.findIndex((t) => t.code === code) === 0 ? 'first' : 'senior'
}

export function TimetableLegend({ extra = [] }: { templates?: TimingTemplate[]; all?: TimingTemplate[]; extra?: { label: string; tone: GridTone }[] }) {
  const items: { label: string; tone: GridTone }[] = [{ label: 'Lab / Practical', tone: 'lab' }, ...extra]
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-fg-label">
      <span className="inline-flex items-center gap-1.5">{[1, 3, 4].map((n) => <span key={n} className="h-3 w-[3px] rounded-full" style={{ background: `var(--color-sub-${n})` }} aria-hidden />)}Edge colour = subject</span>
      {items.map((i) => (
        <span key={i.label} className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ background: EDGE[i.tone] }} aria-hidden />{i.label}</span>
      ))}
      <span className="inline-flex items-center gap-1.5"><span className="h-2 w-3 rounded-[2px] bg-track ring-1 ring-line" aria-hidden />Lunch (that year group only)</span>
    </div>
  )
}

function Cell({ item }: { item: GridItem }) {
  const edge = item.tone === 'conflict' ? EDGE.conflict : item.accent ?? EDGE[item.tone]
  const body = (
    <>
      <div className="flex items-start justify-between gap-1">
        <span className="flex min-w-0 items-start gap-1.5 text-[12.5px] leading-tight font-semibold text-fg">
          <span className="mt-[5px] h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: edge }} aria-hidden />
          <span className="line-clamp-2 break-words">{item.title}</span>
        </span>
        {item.corner}
      </div>
      {item.subtitle && <div className="mt-0.5 line-clamp-2 text-[11.5px] leading-snug break-words text-fg-soft">{item.subtitle}</div>}
      {item.meta && <div className="mt-0.5 text-[11px] leading-snug break-words whitespace-pre-line text-fg-label">{item.meta}</div>}
    </>
  )
  const cls = cn(
    'block h-full w-full min-w-0 rounded-[5px] border border-l-[3px] border-line bg-surface-2 px-1.5 py-1 text-left',
    item.tone === 'conflict' && 'border-danger-border bg-danger-soft',
    item.tone === 'carry' && 'border-warning-border bg-warning/[0.06]',
    item.dim && 'opacity-50',
    item.onClick && 'cursor-pointer hover:border-line-hover hover:bg-surface-3',
  )
  const style = { borderLeftColor: edge }
  const title = item.hint ?? `${item.title} · ${fmt.timeRange(item.start, item.end)}${item.subtitle ? ` · ${item.subtitle}` : ''}${item.meta ? ` · ${item.meta.replace(/\n/g, ' · ')}` : ''}`
  return item.onClick ? <button type="button" className={cls} style={style} title={title} onClick={item.onClick}>{body}</button> : <div className={cls} style={style} title={title}>{body}</div>
}

/** Greedy lanes: classes that overlap in time are stacked, everything else shares a line. */
function lanes(items: GridItem[]): { item: GridItem; lane: number }[] {
  const ends: number[] = []
  return [...items].sort((a, b) => hm(a.start) - hm(b.start) || hm(a.end) - hm(b.end)).map((item) => {
    let lane = ends.findIndex((e) => e <= hm(item.start))
    if (lane < 0) lane = ends.length
    ends[lane] = hm(item.end)
    return { item, lane }
  })
}

/**
 * Days down, clock time across. `view` is one timing template's code, or "combined" for the whole institution.
 * In the combined view each year group has its own band per day, so the First Year lunch (12:40-13:20) and the
 * 2nd-4th Year lunch (11:50-12:30) are two different blocks and neither blocks the other group's classes.
 */
export function TimetableGrid({ templates, all, view, days, items, empty }: { templates: TimingTemplate[]; all?: TimingTemplate[]; view: string; days: GridDay[]; items: GridItem[]; empty?: ReactNode }) {
  const bands = useMemo(() => (view === 'combined' ? templates : templates.filter((t) => t.code === view)), [templates, view])
  const known = new Set(bands.map((b) => b.code))
  const shown = items.filter((i) => view === 'combined' || i.template === view)
  const edges = useMemo(() => [...new Set(bands.flatMap((b) => b.slots.flatMap((s) => [hm(s.start), hm(s.end)])))].sort((a, b) => a - b), [bands])
  const firstToday = Math.max(0, days.findIndex((d) => d.today))
  const [day, setDay] = useState(firstToday)
  useEffect(() => setDay(firstToday), [firstToday, days.length])

  if (!bands.length || edges.length < 2) return <p className="meta px-4 py-6">No timing template is configured for this view. Add one under Academic Setup → Timing Templates.</p>

  const dayStart = edges[0], dayEnd = edges[edges.length - 1]
  const inside = (i: GridItem) => hm(i.end) > dayStart && hm(i.start) < dayEnd
  const col = (t: number, side: 'start' | 'end') => {
    if (side === 'start') { let k = 0; edges.forEach((e, n) => { if (e <= t) k = n }); return Math.min(k, edges.length - 2) + 1 }
    const k = edges.findIndex((e) => e >= t)
    return (k <= 0 ? edges.length - 1 : k) + 1
  }
  const columns = edges.slice(1).map((e, n) => { const d = e - edges[n]; return `minmax(${Math.max(26, Math.round(d * 2))}px, ${d}fr)` }).join(' ')
  const bandOf = (i: GridItem) => (i.template && known.has(i.template) ? i.template : bands[0].code)
  const outside = shown.filter((i) => !inside(i))
  const combined = bands.length > 1
  const side = combined ? 'grid-cols-[96px_58px_minmax(0,1fr)]' : 'grid-cols-[96px_minmax(0,1fr)]'

  return (
    <div>
      {/* ---------- desktop: full grid ---------- */}
      <div className="overflow-x-auto scroll-thin max-lg:hidden">
        <div style={{ minWidth: combined ? 1120 : 960 }}>
          {bands.map((b, bi) => (
            <div key={b.code} className={cn('grid border-b border-line bg-surface-2', side, bi === 0 && 'rounded-t-md')}>
              <div className="th flex items-center px-3 text-[10.5px]">{bi === 0 ? 'Day' : ''}</div>
              {combined && <div className="flex items-center gap-1.5 px-1 text-[10.5px] font-semibold tracking-wide text-fg-label uppercase"><span className={cn('h-2 w-2 rounded-[2px]', groupTone(all ?? templates, b.code) === 'first' ? 'bg-info' : 'bg-primary-muted')} aria-hidden />{b.short_name.replace(' Year', '')}</div>}
              <div className="grid gap-x-[3px] px-[3px]" style={{ gridTemplateColumns: columns }}>
                {b.slots.map((s) => (
                  <div key={s.id} style={{ gridColumn: `${col(hm(s.start), 'start')} / ${col(hm(s.end), 'end')}` }} className={cn('min-w-0 border-l border-line-subtle px-1 py-1.5 text-center', !s.is_teaching_slot && 'bg-track/70')}>
                    <div className={cn('truncate text-[11px] font-semibold tracking-wide uppercase', s.is_teaching_slot ? 'text-fg-soft' : 'text-fg-muted')}>{s.is_teaching_slot ? `L${s.lecture_number}` : s.slot_type === 'LUNCH' ? 'Lunch' : 'Break'}</div>
                    <div className="tnum truncate text-[10.5px] text-fg-label">{s.start}–{s.end}</div>
                  </div>
                ))}
              </div>
            </div>
          ))}
          {days.map((d, di) => (
            <div key={di} className={cn('grid border-b border-line last:border-0', side, d.today && 'bg-primary/[0.03]')}>
              <div className={cn('flex flex-col justify-center border-r border-line-subtle px-3 py-2', d.today && 'border-l-2 border-l-primary')}>
                <span className={cn('text-[12.5px] font-semibold', d.today ? 'text-primary' : 'text-fg')}>{d.label}</span>
                {d.sub && <span className="tnum text-[11px] text-fg-label">{d.sub}</span>}
              </div>
              <div className={cn(combined && 'col-span-2')}>
                {bands.map((b, bi) => {
                  const mine = lanes(shown.filter((i) => i.day === di && inside(i) && bandOf(i) === b.code))
                  const rows = Math.max(1, ...mine.map((m) => m.lane + 1))
                  return (
                    <div key={b.code} className={cn('grid', combined && 'grid-cols-[58px_minmax(0,1fr)]', bi > 0 && 'border-t border-dashed border-line-subtle')}>
                      {combined && <div className="flex items-center px-1 text-[10.5px] text-fg-muted">{b.short_name.replace(' Year', '')}</div>}
                      <div className="grid gap-[3px] p-[3px]" style={{ gridTemplateColumns: columns, gridTemplateRows: `repeat(${rows}, minmax(${combined ? 56 : 60}px, auto))` }}>
                        {b.slots.filter((s) => !s.is_teaching_slot).map((s) => (
                          <div key={s.id} style={{ gridColumn: `${col(hm(s.start), 'start')} / ${col(hm(s.end), 'end')}`, gridRow: '1 / -1' }} className="flex flex-col items-center justify-center rounded-[5px] bg-track/70 text-[10px] leading-tight font-semibold tracking-[0.12em] text-fg-muted uppercase" title={`${b.name} ${s.slot_type.toLowerCase()} ${s.start}–${s.end}. Only ${b.short_name} classes pause here.`}>
                            {s.slot_type === 'LUNCH' ? 'Lunch' : 'Break'}
                            <span className="text-[9.5px] font-medium tracking-normal text-fg-faint normal-case">{b.short_name}</span>
                          </div>
                        ))}
                        {mine.map(({ item, lane }) => (
                          <div key={item.key} className="min-w-0" style={{ gridColumn: `${col(hm(item.start), 'start')} / ${col(hm(item.end), 'end')}`, gridRow: lane + 1 }}>
                            <Cell item={item} />
                          </div>
                        ))}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ---------- phone / tablet: one day at a time ---------- */}
      <div className="lg:hidden">
        <div className="flex gap-1 overflow-x-auto border-b border-line px-3 py-2 scroll-thin" role="tablist" aria-label="Day">
          {days.map((d, di) => (
            <button key={di} type="button" role="tab" aria-selected={di === day} onClick={() => setDay(di)}
              className={cn('flex h-10 min-w-[52px] shrink-0 flex-col items-center justify-center rounded-md px-2 text-[12px] font-semibold', di === day ? 'bg-primary-soft text-primary ring-1 ring-primary-border ring-inset' : 'text-fg-secondary hover:bg-surface-3')}>
              {d.label.slice(0, 3)}
              {d.sub && <span className="tnum text-[10px] font-normal text-fg-label">{d.sub}</span>}
            </button>
          ))}
        </div>
        <ul className="divide-y divide-line-subtle">
          {(() => {
            const list: { at: number; node: ReactNode; key: string }[] = shown.filter((i) => i.day === day).map((i) => ({
              at: hm(i.start), key: i.key,
              node: (
                <div className="grid grid-cols-[88px_minmax(0,1fr)] items-stretch gap-3 px-3 py-2.5">
                  <div className="tnum pt-1 text-[12.5px] font-medium text-fg-soft">{i.start}–{i.end}</div>
                  <Cell item={i} />
                </div>
              ),
            }))
            bands.forEach((b) => b.slots.filter((s) => !s.is_teaching_slot).forEach((s) => list.push({
              at: hm(s.start) + 0.5, key: `${b.code}-${s.id}`,
              node: (
                <div className="grid grid-cols-[88px_minmax(0,1fr)] gap-3 bg-track/40 px-3 py-1.5 text-[11.5px] text-fg-muted">
                  <div className="tnum">{s.start}–{s.end}</div>
                  <div className="font-semibold tracking-wide uppercase">{b.short_name} {s.slot_type.toLowerCase()}</div>
                </div>
              ),
            })))
            return (
              <>
                {list.sort((a, b) => a.at - b.at).map((l) => <li key={l.key}>{l.node}</li>)}
                {!shown.some((i) => i.day === day) && <li className="meta px-3 py-4">No classes on {days[day]?.label}.</li>}
              </>
            )
          })()}
        </ul>
      </div>

      {outside.length > 0 && (
        <div className="border-t border-line px-4 py-3 max-lg:hidden">
          <div className="th mb-1.5 text-[10.5px]">Outside the regular teaching day</div>
          <div className="flex flex-wrap gap-2">
            {outside.map((i) => <div key={i.key} className="w-56"><Cell item={{ ...i, meta: `${days[i.day]?.label ?? ''} ${i.start}–${i.end}${i.meta ? ` · ${i.meta}` : ''}` }} /></div>)}
          </div>
        </div>
      )}
      {shown.length === 0 && empty}
    </div>
  )
}
