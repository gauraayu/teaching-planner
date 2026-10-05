import { ArrowRight, CalendarRange, CheckCircle2, History, Info } from 'lucide-react'
import { useState } from 'react'
import { EmptyState, ErrorState, LoadingRows } from '@/components/feedback/States'
import { useBreadcrumbs } from '@/components/layout/PageHeader'
import { Badge, Tag } from '@/components/ui/Badge'
import { Button, buttonClass } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { ProgressBar } from '@/components/ui/Display'
import { ChangeDiff, describeSlot } from '@/features/sprint/components/ChangeDiff'
import { WeekNav, weekLabel } from '@/features/sprint/components/WeekNav'
import { RevisionDialog } from '@/features/sprint/SprintHistoryPage'
import { useApi } from '@/hooks/useApi'
import { mondayOf, type ProfessorWeek, type ProfessorWeekHistory, type RevisionChanges } from '@/lib/api/sprint'
import { hmToMinutes, useInstNow } from '@/lib/date-time/institution'
import { Link, useSearchParams } from '@/lib/router'
import { fmt, todayISO } from '@/lib/status'
import { useTodayFeed } from '@/providers/ScheduleNotificationProvider'
import { api, type Paged } from '@/services/api'
import type { SprintRow } from '@/types/domain'
import { cn } from '@/utils/cn'
import { AuditSequence, CohortVenue, ProfStat, slotLabel, StateBadge, SubjectTopic } from './components/parts'
import { nextIndex, rowState } from './rowState'

const two = (n: number) => String(n).padStart(2, '0')

function hours(rows: SprintRow[]) {
  const mins = rows.reduce((t, r) => t + (r.start && r.end ? hmToMinutes(r.end) - hmToMinutes(r.start) : 0), 0)
  return (mins / 60).toFixed(1)
}

function Revised({ row }: { row: SprintRow }) {
  const [open, setOpen] = useState(false)
  if (!row.revised) return null
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} title={`Previous: ${describeSlot(row.revised.old)} · ${row.revised.reason_label}`} className="inline-flex h-5 items-center gap-1 rounded-sm border border-info-border bg-info-soft px-1.5 text-[11px] font-semibold tracking-wide text-info uppercase hover:border-info">
        <Info className="h-3 w-3" aria-hidden />{row.revised.change_type === 'ADD' ? 'Added' : 'Updated'} · v{row.revised.revision_number}
      </button>
      <Dialog open={open} onClose={() => setOpen(false)} title="Updated during the sprint meeting" description={`Sprint revision v${row.revised.revision_number} · published ${fmt.dateTime(row.revised.published_at)}`} footer={<Button onClick={() => setOpen(false)}>Close</Button>}>
        <ChangeDiff c={row.revised} />
        <p className="meta mt-3">Schedule changes are made by the administrator in the weekly sprint meeting. This is for your information.</p>
      </Dialog>
    </>
  )
}

/** Professor's week: Monday to Saturday on one page, always the latest PUBLISHED revision. Read-only for planning. */
export function ProfessorSprintPlanPage() {
  useBreadcrumbs([{ label: 'Teaching' }, { label: 'Sprint Plan' }])
  const [params, setParams] = useSearchParams()
  const weekStart = mondayOf(params.get('week') || todayISO())
  const go = (monday: string) => setParams(monday === mondayOf(todayISO()) ? {} : { week: monday }, { replace: true })
  const week = useApi<ProfessorWeek>('/professor/sprint-plan', { week_start: weekStart })
  const history = useApi<Paged<ProfessorWeekHistory>>('/professor/sprint-plan/history')
  const [historyOpen, setHistoryOpen] = useState(false)
  const [changes, setChanges] = useState<string | null>(params.get('changes'))
  const now = useInstNow(15_000)
  const { leadMinutes } = useTodayFeed()
  const w = week.data
  const m = w?.metrics
  const todays = w?.days.find((d) => d.date === now.date)?.lectures ?? []
  const next = nextIndex(todays, now)

  return (
    <div className="mx-auto max-w-[1280px]">
      <div className="mb-5 flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md border border-line bg-surface-2 text-fg-secondary" aria-hidden><CalendarRange className="h-5 w-5" /></div>
          <div className="min-w-0">
            <h1 className="flex flex-wrap items-center gap-2.5 text-[26px] leading-tight font-semibold tracking-tight text-fg uppercase sm:text-[30px]">
              Sprint Plan <span className="th rounded-sm border border-line px-2 py-0.5 text-[10.5px]">Faculty operations</span>
            </h1>
            <p className="mt-1 text-[13.5px] text-fg-secondary">Weekly teaching schedule and execution pipeline. Planned by the administrator; you record what was taught.</p>
          </div>
        </div>
        <WeekNav week={w?.week} weekStart={weekStart} onChange={go}>
          <Button size="sm" icon={<History className="h-3.5 w-3.5" />} onClick={() => setHistoryOpen(true)}>Sprint history</Button>
        </WeekNav>
      </div>

      {week.error ? (
        <div className="panel"><ErrorState message={week.error.message} onRetry={week.reload} /></div>
      ) : !w || !m ? (
        <div className="panel"><LoadingRows rows={6} /></div>
      ) : (
        <>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-md border border-line bg-surface px-4 py-2.5 text-[12.5px] text-fg-secondary">
            <span className="inline-flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-primary" aria-hidden />
              {w.version === 1 ? 'Following the semester master plan for this week.' : <>Sprint revision <b className="font-semibold text-fg">v{w.version}</b> · published {fmt.dateTime(w.revision?.published_at)}{w.changed_for_me ? ` · ${w.changed_for_me} of your lectures changed` : ''}</>}
            </span>
            {w.revision && <Button size="sm" variant="link" className="text-[12.5px]" onClick={() => setChanges(w.revision!.id)}>View changes</Button>}
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
            <ProfStat label="Total sessions" value={two(m.total)} unit="lectures" sub="Planned this week" />
            <ProfStat label="Completed" accent="primary" value={two(m.delivered)} unit="delivered" sub={m.delivered - m.completed ? `${m.delivered - m.completed} partially` : 'Execution recorded'} />
            <ProfStat label="Live · next" accent="info" value={two(m.today_open)} unit="pending today" sub={w.week.is_current ? 'Still to teach today' : 'Not the current week'} />
            <ProfStat label="Upcoming" value={two(m.upcoming)} unit="scheduled" sub="Later this week" />
            <ProfStat label="Pending action" accent={m.pending_action ? 'danger' : 'neutral'} value={two(m.pending_action)} unit={m.pending_action ? 'to update' : undefined} sub={m.pending_action ? 'Record or submit needed' : 'Nothing overdue'} />
            <ProfStat label="Weekly pace" accent="primary" value={`${m.pace_pct}%`} sub={`${m.delivered} of ${m.total} delivered`}><ProgressBar value={m.pace_pct} className="mt-2" label="Weekly pace" /></ProfStat>
          </div>

          {m.total === 0 ? (
            <div className="panel mt-5"><EmptyState icon={<CalendarRange className="h-5 w-5" />} title="No classes scheduled for this week" description="When the administrator publishes lectures for this week they appear here." /></div>
          ) : (
            <div className="mt-5 space-y-4">
              {w.days.map((day) => {
                const isToday = day.date === now.date
                const past = day.date < now.date
                return (
                  <section key={day.date} className={cn('panel overflow-hidden', isToday && 'border-primary-border')} aria-label={fmt.date(day.date)}>
                    <div className={cn('flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-line px-4 py-2.5', isToday && 'border-t-2 border-t-primary bg-primary/[0.04]')}>
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                        <span className={cn('rounded-sm px-1.5 py-0.5 text-[11px] font-semibold tracking-wide uppercase', isToday ? 'bg-primary text-on-primary' : 'bg-surface-3 text-fg-secondary')}>{fmt.weekday(day.date)}</span>
                        <span className="text-[15px] font-semibold text-fg uppercase">{fmt.date(day.date)}</span>
                        {isToday && <span className="inline-flex items-center gap-1.5 rounded-sm bg-primary-soft px-1.5 py-0.5 text-[11px] font-semibold tracking-wide text-primary uppercase"><span className="h-1.5 w-1.5 rounded-full bg-primary" aria-hidden />Today · active execution window</span>}
                        <span className="tnum text-[12.5px] text-fg-label">{day.lectures.length} lecture{day.lectures.length === 1 ? '' : 's'} scheduled{day.lectures.length ? ` · total ${hours(day.lectures)} hrs` : ''}</span>
                      </div>
                      <span className={cn('text-[12px] font-medium', past ? 'text-primary' : 'text-fg-label')}>{isToday ? `Session ${Math.min(day.lectures.length, (next < 0 ? day.lectures.length : next) + 1)} of ${day.lectures.length}` : past ? 'Day concluded' : 'Upcoming execution'}</span>
                    </div>
                    {day.lectures.length === 0 ? (
                      <p className="meta px-4 py-4">No lectures.</p>
                    ) : (
                      <ul>
                        {day.lectures.map((row, i) => {
                          const s = rowState(row, now, leadMinutes, isToday && i === next)
                          const highlight = s.key === 'NEXT' || s.key === 'LIVE' || s.key === 'AWAITING_START'
                          return (
                            <li key={row.lecture_id} className={cn('grid grid-cols-1 gap-x-5 gap-y-2.5 border-b border-line-subtle px-4 py-3.5 last:border-0 lg:grid-cols-[140px_minmax(0,1.7fr)_minmax(0,0.9fr)_150px_190px_130px] lg:items-center', highlight && 'bg-primary/[0.05]')}>
                              <div>
                                <div className={cn('tnum text-[14px] font-semibold whitespace-nowrap', highlight ? 'text-primary' : 'text-fg')}>{slotLabel(row)}</div>
                                <div className={cn('text-[12px]', s.countdown ? 'font-medium text-info' : 'text-fg-label')}>{s.countdown || (row.start && row.end ? `${hmToMinutes(row.end) - hmToMinutes(row.start)} mins` : '')}</div>
                              </div>
                              <div className="min-w-0">
                                <SubjectTopic row={row} />
                                {row.revised && <div className="mt-1.5"><Revised row={row} /></div>}
                              </div>
                              <CohortVenue row={row} />
                              <div><StateBadge state={s} /></div>
                              <AuditSequence row={row} />
                              <Link to={`/professor/lectures/${row.lecture_id}`} className={cn(buttonClass(s.primary ? 'primary' : 'secondary', 'sm'), 'justify-center max-lg:h-10')}>
                                {s.action} {s.primary && <ArrowRight className="h-3.5 w-3.5" />}
                              </Link>
                            </li>
                          )
                        })}
                      </ul>
                    )}
                  </section>
                )
              })}
            </div>
          )}

          {w.courses.length > 0 && (
            <section className="mt-7" aria-label="Weekly course progress">
              <h2 className="mb-3 text-[16px] font-semibold text-fg">Weekly course progress &amp; audit readiness</h2>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                {w.courses.map((c) => (
                  <div key={c.plan_id} className="panel p-4">
                    <div className="flex items-center justify-between gap-2"><Tag>{c.subject.code}</Tag><span className="tnum text-[12px] font-semibold text-primary">{c.sprint_pct}% this week</span></div>
                    <div className="mt-2 text-[14.5px] font-semibold text-fg">{c.subject.name}</div>
                    <div className="meta">Section {c.section} · {c.scheduled} lecture{c.scheduled === 1 ? '' : 's'} scheduled this sprint · {c.delivered} delivered</div>
                    <div className="mt-3 flex items-baseline justify-between text-[12px] text-fg-label"><span>Sprint execution ({c.delivered}/{c.scheduled})</span><span className="tnum font-semibold text-fg">{c.sprint_pct}%</span></div>
                    <ProgressBar value={c.sprint_pct} className="mt-1" label={`${c.subject.name} sprint execution`} />
                    <div className="mt-2.5 flex items-baseline justify-between text-[12px] text-fg-label"><span>Semester syllabus ({c.semester_completed}/{c.semester_total})</span><span className="tnum font-semibold text-fg">{c.semester_pct}%</span></div>
                    <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-track" role="progressbar" aria-valuenow={c.semester_pct} aria-valuemin={0} aria-valuemax={100} aria-label={`${c.subject.name} semester syllabus`}>
                      <div className="h-full rounded-full bg-info" style={{ width: `${c.semester_pct}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}
          <p className="meta mt-5">The schedule is locked by the administrator. You can open a lecture to start the class, record what was covered, add notes and submit it for CL/CH → OM verification.</p>
        </>
      )}

      <Dialog open={historyOpen} onClose={() => setHistoryOpen(false)} title="Sprint history" description="Your earlier weeks. Past sprint plans are read-only." footer={<Button onClick={() => setHistoryOpen(false)}>Close</Button>}>
        {history.error ? <ErrorState message={history.error.message} onRetry={history.reload} /> : !history.data ? <LoadingRows rows={4} /> : history.data.items.length === 0 ? (
          <EmptyState title="No weeks yet" description="Weeks appear once lectures are scheduled for you." />
        ) : (
          <ul className="divide-y divide-line-subtle">
            {history.data.items.map((h) => (
              <li key={h.week.start}>
                <button type="button" onClick={() => { go(h.week.start); setHistoryOpen(false) }} className={cn('flex w-full items-center justify-between gap-3 px-1 py-2.5 text-left text-[13px] hover:bg-surface-2', h.week.start === weekStart && 'text-primary')}>
                  <span><span className="font-semibold text-fg">{h.week.number ? `Week ${h.week.number}` : 'Week'}</span> <span className="text-fg-secondary">· {weekLabel(h.week)}</span>{h.week.is_current && <Badge tone="success" icon={false} className="ml-2">Current</Badge>}</span>
                  <span className="tnum shrink-0 text-fg-label">{h.delivered}/{h.lectures} delivered · v{h.version}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Dialog>
      <RevisionDialog revisionId={changes} onClose={() => setChanges(null)} load={(id) => api.get<RevisionChanges>(`/professor/sprint-plan/${id}/changes`).then((r) => r.data)} />
    </div>
  )
}
