import { ArrowRight, CalendarDays, FlaskConical } from 'lucide-react'
import { subjectColor, TimetableGrid, TimetableLegend, type GridItem } from '@/components/domain/TimetableGrid'
import { EmptyState, ErrorState, LoadingRows } from '@/components/feedback/States'
import { PageHeader, useBreadcrumbs } from '@/components/layout/PageHeader'
import { Tag } from '@/components/ui/Badge'
import { buttonClass } from '@/components/ui/Button'
import { Metric, MetricStrip, ProgressBar } from '@/components/ui/Display'
import { WeekNav } from '@/features/sprint/components/WeekNav'
import { useApi } from '@/hooks/useApi'
import { DELIVERED, mondayOf, type ProfessorWeek } from '@/lib/api/sprint'
import { templateOf, type TimingTemplate } from '@/lib/api/timetable'
import { useInstNow } from '@/lib/date-time/institution'
import { Link, useNavigate, useSearchParams } from '@/lib/router'
import { fmt, LECTURE_TYPE_LABEL, todayISO } from '@/lib/status'
import { useTodayFeed } from '@/providers/ScheduleNotificationProvider'
import type { Paged } from '@/services/api'
import { cn } from '@/utils/cn'
import { StateBadge } from './components/parts'
import { nextIndex, rowState } from './rowState'

/**
 * The professor's own week: only their classes, each with the topic and subtopics the published sprint plan
 * gave it. Planning is read-only here; a class is opened to start it and record what was taught.
 */
export function MySchedulePage() {
  useBreadcrumbs([{ label: 'Teaching' }, { label: 'My Schedule' }])
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const weekStart = mondayOf(params.get('week') || todayISO())
  const go = (monday: string) => setParams(monday === mondayOf(todayISO()) ? {} : { week: monday }, { replace: true })
  const week = useApi<ProfessorWeek>('/professor/sprint-plan', { week_start: weekStart })
  const all = useApi<Paged<TimingTemplate>>('/timing-templates').data?.items.filter((t) => t.is_active) ?? []
  const now = useInstNow(30_000)
  const { leadMinutes } = useTodayFeed()
  const w = week.data
  const m = w?.metrics
  const rows = w?.days.flatMap((d) => d.lectures) ?? []
  // Only the year groups this professor actually teaches get a band on the grid.
  const used = new Set(rows.map((r) => templateOf(all, r.semester_number)))
  const templates = all.some((t) => used.has(t.code)) ? all.filter((t) => used.has(t.code)) : all
  const todays = w?.days.find((d) => d.date === now.date)?.lectures ?? []
  const next = nextIndex(todays, now)

  const items: GridItem[] = (w?.days ?? []).flatMap((day, di) => day.lectures.filter((r) => r.start && r.end).map((r) => {
    const tpl = templateOf(all, r.semester_number)
    const done = DELIVERED.includes(r.execution_status)
    return {
      key: r.lecture_id!, day: di, start: r.start!, end: r.end!, template: tpl,
      title: `${r.subject.short_name ?? r.subject.code}${r.lecture_no ? ` · L${r.lecture_no}` : ''}`,
      subtitle: r.topic,
      meta: `Sem ${r.semester.replace('Semester ', '')}-${r.section} · ${r.room ?? 'No room'}`,
      accent: subjectColor(r.subject.code),
      tone: r.origin === 'CARRY_FORWARD' ? 'carry' : r.lecture_type === 'PRACTICAL' ? 'lab' : 'neutral',
      corner: r.lecture_type === 'PRACTICAL' ? <FlaskConical className="h-3 w-3 shrink-0 text-accent" aria-label="Lab" />
        : done ? <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" aria-label="Delivered" />
          : r.needs_update ? <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-warning" aria-label="Update pending" /> : undefined,
      hint: `${r.subject.name} · ${r.topic}${r.subtopics.length ? ` (${r.subtopics.join(', ')})` : ''} · ${fmt.timeRange(r.start, r.end)} · ${r.room ?? 'no room'}`,
      onClick: () => navigate(`/professor/lectures/${r.lecture_id}`),
    } satisfies GridItem
  }))
  const days = (w?.days ?? []).map((d) => ({ label: fmt.weekday(d.date), sub: fmt.dateShort(d.date), today: d.date === now.date }))

  return (
    <div className="mx-auto max-w-[1320px]">
      <PageHeader title="My Schedule" description="Your classes for the week, with the topic planned for each. The schedule is published by the administrator; open a class to start it and record what you taught." />
      <div className="mb-4"><WeekNav week={w?.week} weekStart={weekStart} onChange={go} /></div>
      {week.error ? (
        <div className="panel"><ErrorState message={week.error.message} onRetry={week.reload} /></div>
      ) : !w || !m ? (
        <div className="panel"><LoadingRows rows={6} /></div>
      ) : (
        <>
          <MetricStrip className="mb-4">
            <Metric label="Classes this week" value={m.total} tone="neutral" />
            <Metric label="Completed" value={m.delivered} sub={m.delivered - m.completed ? `${m.delivered - m.completed} partially` : undefined} />
            <Metric label="Upcoming" value={m.upcoming} tone="neutral" sub={m.today_open ? `${m.today_open} still today` : undefined} />
            <Metric label="Pending update" value={m.pending_action} tone={m.pending_action ? 'warning' : 'neutral'} sub={m.pending_action ? 'Record or submit' : 'Nothing waiting'} />
            <Metric label="Verified" value={m.verified ?? 0} tone="neutral" sub="CL/CH and OM" />
            <Metric label="Weekly execution" value={`${m.pace_pct}%`} sub={<ProgressBar value={m.pace_pct} className="mt-1.5" label="Weekly execution" />} />
          </MetricStrip>

          {m.total === 0 ? (
            <div className="panel"><EmptyState icon={<CalendarDays className="h-5 w-5" />} title="No classes published for this week" description="Your classes appear here once the administrator publishes the weekly sprint plan." /></div>
          ) : (
            <>
              <div className="panel">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
                  <span className="panel-title">Week at a glance</span>
                  <TimetableLegend extra={[{ label: 'Carry-forward', tone: 'carry' }]} />
                </div>
                <TimetableGrid templates={templates} all={all} view="combined" days={days} items={items} />
              </div>

              <div className="mt-5 space-y-4">
                {w.days.filter((d) => d.lectures.length).map((day) => {
                  const isToday = day.date === now.date
                  return (
                    <section key={day.date} className={cn('panel', isToday && 'border-primary-border')} aria-label={fmt.date(day.date)}>
                      <div className="panel-header">
                        <h2 className="flex items-center gap-2.5 text-[13px] font-semibold text-fg">
                          <span className={cn('rounded-sm px-1.5 py-0.5 text-[11px] tracking-wide uppercase', isToday ? 'bg-primary text-on-primary' : 'bg-surface-3 text-fg-secondary')}>{fmt.weekday(day.date)}</span>
                          {fmt.date(day.date)}
                        </h2>
                        <span className="meta">{day.lectures.length} class{day.lectures.length === 1 ? '' : 'es'}</span>
                      </div>
                      <ul>
                        {day.lectures.map((r, i) => {
                          const s = rowState(r, now, leadMinutes, isToday && i === next)
                          return (
                            <li key={r.lecture_id} className="grid grid-cols-1 gap-x-5 gap-y-2 border-b border-line-subtle px-4 py-3.5 last:border-0 lg:grid-cols-[130px_minmax(0,1fr)_150px_140px] lg:items-center">
                              <div>
                                <div className="tnum text-[13.5px] font-semibold whitespace-nowrap text-fg">{fmt.timeRange(r.start, r.end)}</div>
                                <div className="meta">{r.room ? `Room ${r.room}` : 'Room not set'}</div>
                              </div>
                              <div className="min-w-0">
                                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                                  <span className="text-[14px] font-semibold text-fg">{r.subject.short_name ?? r.subject.code}{r.lecture_no ? ` · Lecture ${r.lecture_no}` : ''}</span>
                                  <span className="text-[12.5px] text-fg-label">Sem {r.semester.replace('Semester ', '')}-{r.section}</span>
                                  {r.lecture_type !== 'THEORY' && <Tag>{LECTURE_TYPE_LABEL[r.lecture_type] ?? r.lecture_type}</Tag>}
                                  {r.origin === 'CARRY_FORWARD' && <Tag className="text-warning">Carry-forward</Tag>}
                                </div>
                                <div className="mt-0.5 text-[13.5px] text-fg-soft">{r.topic}</div>
                                {r.subtopics.length > 0 && (
                                  <ul className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[12.5px] text-fg-secondary">
                                    {r.subtopics.map((t, n) => <li key={n} className="inline-flex items-center gap-1.5"><span className="h-1 w-1 rounded-full bg-fg-muted" aria-hidden />{t}</li>)}
                                  </ul>
                                )}
                              </div>
                              <div><StateBadge state={s} /></div>
                              <Link to={`/professor/lectures/${r.lecture_id}`} className={cn(buttonClass(s.primary ? 'primary' : 'secondary', 'sm'), 'justify-center max-lg:h-10')}>
                                Open class <ArrowRight className="h-3.5 w-3.5" />
                              </Link>
                            </li>
                          )
                        })}
                      </ul>
                    </section>
                  )
                })}
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}
