import { ArrowRight, BookOpenCheck, CalendarClock, CheckCircle2, ClipboardList, Clock3, FileWarning, MapPin, PieChart, ShieldCheck, TriangleAlert, Users } from 'lucide-react'
import { VerificationTimeline } from '@/components/domain/VerificationTimeline'
import { EmptyState, ErrorState, LoadingRows } from '@/components/feedback/States'
import { PageHeader, useBreadcrumbs } from '@/components/layout/PageHeader'
import { InstitutionClock } from '@/components/shared/InstitutionClock'
import { Tag } from '@/components/ui/Badge'
import { ButtonLink, buttonClass } from '@/components/ui/Button'
import { ProgressBar } from '@/components/ui/Display'
import { useAuth } from '@/features/auth/AuthContext'
import { useApi } from '@/hooks/useApi'
import type { ActionItem, ProfessorDashboardData } from '@/lib/api/professor'
import { useInstNow } from '@/lib/date-time/institution'
import { Link } from '@/lib/router'
import { fmt, SUBMISSION_STATUS } from '@/lib/status'
import { useTodayFeed } from '@/providers/ScheduleNotificationProvider'
import type { Paged } from '@/services/api'
import type { TaskCard as Task } from '@/types/domain'
import { cn } from '@/utils/cn'
import { ProfStat } from './components/parts'
import { TodaySchedule } from './components/TodaySchedule'
import { nextIndex, rowState } from './rowState'
import { TaskCard } from './TaskCard'

const ACTION_STYLE: Record<ActionItem['kind'], { label: string; bar: string; text: string; icon: typeof FileWarning }> = {
  CORRECTION: { label: 'Correction required', bar: 'border-l-danger', text: 'text-danger', icon: FileWarning },
  PENDING_LOG: { label: 'Pending execution log', bar: 'border-l-warning', text: 'text-warning', icon: Clock3 },
  NOT_SUBMITTED: { label: 'Not submitted', bar: 'border-l-warning', text: 'text-warning', icon: ClipboardList },
  MISSING_ASSET: { label: 'Missing lecture notes', bar: 'border-l-accent', text: 'text-accent', icon: BookOpenCheck },
}

function ActionItems({ items }: { items: ActionItem[] }) {
  return (
    <section className="panel" aria-label="Action items">
      <div className="panel-header">
        <h2 className="flex items-center gap-2 text-[15px] font-semibold text-fg"><TriangleAlert className="h-4 w-4 text-fg-label" aria-hidden />Action items</h2>
        {items.length > 0 && <span className="rounded-sm bg-danger-soft px-1.5 py-0.5 text-[11px] font-semibold tracking-wide text-danger uppercase">{items.length} require attention</span>}
      </div>
      {items.length === 0 ? (
        <p className="meta px-4 py-6">Nothing needs your attention. New corrections and pending records appear here.</p>
      ) : (
        <ul className="space-y-2.5 p-3">
          {items.slice(0, 6).map((a) => {
            const s = ACTION_STYLE[a.kind]
            return (
              <li key={`${a.kind}-${a.lecture_id}`} className={cn('rounded-md border border-l-[3px] border-line bg-surface-2 p-3', s.bar)}>
                <div className="flex items-center justify-between gap-2">
                  <span className={cn('text-[11px] font-semibold tracking-[0.07em] uppercase', s.text)}>{s.label}</span>
                  {a.at && <span className="tnum text-[11.5px] text-fg-muted">{a.at.length > 10 ? fmt.dateTime(a.at) : fmt.dateShort(a.at)}</span>}
                </div>
                <div className="mt-1.5 text-[13.5px] font-semibold text-fg">{a.title} <span className="font-normal text-fg-label">({a.subject})</span></div>
                <p className="mt-1 text-[12.5px] leading-relaxed text-fg-secondary">{a.by && <span className={s.text}>{a.by}: </span>}{a.detail}</p>
                <div className="mt-2 text-right">
                  <Link to={`/professor/lectures/${a.lecture_id}`} className={buttonClass(a.kind === 'CORRECTION' ? 'danger' : 'secondary', 'sm')}>{a.action}</Link>
                </div>
              </li>
            )
          })}
          {items.length > 6 && <li className="meta px-1">+ {items.length - 6} more on the Sprint Plan and Correction Requests pages.</li>}
        </ul>
      )}
    </section>
  )
}

function Pipeline({ d }: { d: ProfessorDashboardData }) {
  const p = d.pipeline
  return (
    <section className="panel" aria-label="Verification pipeline">
      <div className="panel-header">
        <h2 className="flex items-center gap-2 text-[15px] font-semibold text-fg"><ShieldCheck className="h-4 w-4 text-fg-label" aria-hidden />Verification pipeline</h2>
        <span className="meta">Latest submission</span>
      </div>
      {!p ? (
        <p className="meta px-4 py-6">No lecture has been submitted yet. After you submit a record it moves through CL/CH and OM here.</p>
      ) : (
        <div className="p-4">
          <div className="rounded-md border border-line bg-surface-2 p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="th text-[10.5px]">Active submission</span>
              <span className={cn('text-[11px] font-semibold tracking-wide uppercase', p.submission_status === 'FINAL_VERIFIED' ? 'text-primary' : p.submission_status === 'CORRECTION_REQUIRED' ? 'text-danger' : 'text-info')}>{SUBMISSION_STATUS[p.submission_status].label}</span>
            </div>
            <Link to={`/professor/lectures/${p.lecture_id}`} className="mt-1 block text-[14px] font-semibold text-fg hover:text-primary">Lecture {p.lecture_no} ({p.subject}) – {p.topic}</Link>
            <div className="meta mt-0.5">Submitted {fmt.dateTime(p.submitted_at)}{p.round > 1 ? ` · round ${p.round}` : ''}</div>
          </div>
          <div className="mt-4"><VerificationTimeline submitted submissionStatus={p.submission_status} steps={p.steps} chain={p.chain} round={p.round} /></div>
          {d.recent.length > 0 && (
            <>
              <div className="th mt-5 mb-1.5 text-[10.5px]">Recent activity</div>
              <ul className="space-y-1.5">
                {d.recent.slice(0, 4).map((a) => (
                  <li key={a.id} className="flex items-start justify-between gap-3 text-[12.5px]">
                    <span className="flex min-w-0 items-start gap-1.5 text-fg-soft"><CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" aria-hidden /><span className="truncate">{a.summary}</span></span>
                    <span className="shrink-0 text-fg-muted">{fmt.relative(a.created_at)}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </section>
  )
}

function Syllabus({ d }: { d: ProfessorDashboardData }) {
  return (
    <section className="panel" aria-label="Syllabus completion">
      <div className="panel-header">
        <div>
          <h2 className="flex items-center gap-2 text-[15px] font-semibold text-fg"><PieChart className="h-4 w-4 text-fg-label" aria-hidden />Syllabus completion &amp; course audit</h2>
          <p className="meta mt-0.5">Completed lectures against the semester plan, by unit.</p>
        </div>
        <Link to="/professor/courses" className="link text-[12.5px]">Course progress</Link>
      </div>
      {d.syllabus.length === 0 ? (
        <EmptyState title="No course assigned yet" description="Your syllabus progress appears once an administrator publishes a teaching plan for you." />
      ) : (
        <div className="divide-y divide-line-subtle">
          {d.syllabus.map((c) => (
            <div key={c.plan_id} className="p-4">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <Link to={`/professor/courses/${c.plan_id}`} className="flex items-center gap-2 text-[14.5px] font-semibold text-fg hover:text-primary">
                  <Tag>{c.subject_code}</Tag>{c.subject_name} <span className="text-[12.5px] font-normal text-fg-label">· Section {c.section}</span>
                </Link>
                <div className="tnum text-[13px] text-fg-secondary"><span className="text-[17px] font-semibold text-primary">{c.execution_pct}%</span> ({c.completed} / {c.total} lectures)</div>
              </div>
              <ProgressBar value={c.execution_pct} className="mt-2 h-2" label={`${c.subject_name} completion`} />
              <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
                {c.units.map((u) => (
                  <div key={u.unit_no ?? 'none'} className="rounded-md border border-line bg-surface-2 px-2.5 py-2" title={u.first_topic}>
                    <div className="flex items-baseline justify-between text-[11.5px]"><span className="text-fg-label">{u.unit_no ? `Unit ${u.unit_no}` : 'No unit'}</span><span className="tnum font-semibold text-primary">{u.execution_pct}%</span></div>
                    <div className="tnum mt-0.5 text-[13px] font-semibold text-fg">{u.completed}/{u.total}</div>
                    <ProgressBar value={u.execution_pct} className="mt-1.5" label={`Unit ${u.unit_no ?? ''} completion`} />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

/** Professor home. Every number on it is computed from stored records by /professor/dashboard. */
export function ProfessorDashboard() {
  useBreadcrumbs([{ label: 'Dashboard' }])
  const { session } = useAuth()
  const dash = useApi<ProfessorDashboardData>('/professor/dashboard')
  const upcoming = useApi<Paged<Task>>('/professor/tasks/upcoming', { days: 14 })
  const now = useInstNow(15_000)
  const { leadMinutes } = useTodayFeed()
  const d = dash.data
  const c = d?.counts
  const rows = d?.schedule_today ?? []
  const ni = nextIndex(rows, now)
  const next = ni >= 0 ? rows[ni] : null
  const state = next ? rowState(next, now, leadMinutes, true) : null
  const later = upcoming.data?.items[0]
  const greeting = now.h < 12 ? 'Good morning' : now.h < 17 ? 'Good afternoon' : 'Good evening'
  const corrections = d?.action_items.filter((a) => a.kind === 'CORRECTION').length ?? 0

  if (dash.error) return <ErrorState message={dash.error.message} onRetry={dash.reload} />

  return (
    <div className="mx-auto max-w-[1280px]">
      <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[11px] font-semibold tracking-[0.1em] text-primary uppercase">
            <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-hidden />Faculty workspace active
            {session?.user.employee_code && <span className="text-fg-muted">· {session.user.employee_code}</span>}
          </div>
          <h1 className="mt-2 text-[26px] leading-tight font-semibold tracking-tight text-fg sm:text-[30px]">
            <span suppressHydrationWarning>{greeting}</span>, <span className="text-primary">{session?.user.full_name}</span>
          </h1>
          <p className="mt-1.5 max-w-xl text-[13.5px] leading-relaxed text-fg-secondary">Here is your institutional teaching schedule, delivery progress and academic verification status for today.</p>
        </div>
        <div className="flex flex-wrap items-center gap-3 lg:flex-col lg:items-end">
          <div className="rounded-md border border-line bg-surface px-3 py-1.5"><InstitutionClock /></div>
          <ButtonLink to="/professor/sprint-plan">View full schedule <ArrowRight className="h-4 w-4" /></ButtonLink>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <ProfStat label="Today's classes" accent="primary" icon={<Users className="h-3.5 w-3.5" />} value={c?.today ?? '–'} unit={c ? `${c.today_completed} completed` : undefined}>
          <ProgressBar value={c?.today ? (c.today_completed * 100) / c.today : 0} className="mt-2.5" label="Today's classes completed" />
        </ProfStat>
        <ProfStat label="Next class" accent="info" icon={<CalendarClock className="h-3.5 w-3.5" />}
          value={next ? fmt.clock(next.start).replace(/\s?(am|pm)$/i, '') : later ? fmt.clock(later.planned_start_time).replace(/\s?(am|pm)$/i, '') || '—' : '—'}
          unit={next ? fmt.clock(next.start).match(/(am|pm)$/i)?.[0].toUpperCase() : later ? `${fmt.weekday(later.effective_date ?? later.planned_date)} ${fmt.dateShort(later.effective_date ?? later.planned_date)}` : undefined}
          sub={next ? `${next.subject.short_name ?? next.subject.code} · ${next.room ? `Room ${next.room}` : 'Room not set'}` : later ? `${later.subject.short_name ?? later.subject.code} · ${later.room ? `Room ${later.room}` : 'Room not set'}` : d ? 'Nothing scheduled' : undefined} />
        <ProfStat label="Course progress" accent="primary" icon={<PieChart className="h-3.5 w-3.5" />} value={c ? `${c.course_progress_pct}%` : '–'} sub={c ? `${c.completed} / ${c.total} lectures covered` : undefined} />
        <ProfStat label="Pending updates" accent={c?.pending_updates ? 'warning' : 'neutral'} icon={<ClipboardList className="h-3.5 w-3.5" />} value={c?.pending_updates ?? '–'} unit={c?.pending_updates ? 'Needs action' : undefined}
          sub={c ? (c.pending_updates ? `${corrections} correction${corrections === 1 ? '' : 's'}, ${c.pending_updates - corrections} to record` : 'All records up to date') : undefined} />
        <ProfStat label="Verified" accent="primary" icon={<CheckCircle2 className="h-3.5 w-3.5" />} value={c?.verified ?? '–'} unit="Final verified" sub={c ? `${c.awaiting_verification} awaiting verification` : undefined} />
      </div>

      {/* Prominent next class */}
      <section className="mt-5 rounded-md border border-line bg-surface-2 p-5" aria-label="Next class">
        {!d ? <LoadingRows rows={2} /> : next && state ? (
          <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2 text-[11px] font-semibold tracking-[0.08em] uppercase">
                <span className={cn('inline-flex items-center gap-1.5 rounded-sm px-2 py-1', state.key === 'LIVE' ? 'bg-primary-soft text-primary' : 'bg-info-soft text-info')}>
                  {state.key === 'LIVE' ? <><span className="live-dot" aria-hidden />Class in progress · started {fmt.clock(next.started_at)}</> : <>Next class{state.countdown ? ` · ${state.countdown}` : ''}</>}
                </span>
                <span className="tnum rounded-sm border border-line px-2 py-1 text-fg-secondary">Scheduled window: {fmt.timeRange(next.start, next.end)}</span>
              </div>
              <h2 className="mt-3 flex flex-wrap items-center gap-2 text-[22px] leading-tight font-semibold text-fg">{next.subject.name} <Tag>{next.subject.code}</Tag></h2>
              <p className="mt-1 text-[14px] text-fg-soft">{next.unit_no ? <span className="text-fg-label">Unit {next.unit_no}: </span> : null}{next.topic}{next.subtopics.length ? <span className="text-fg-secondary"> – {next.subtopics.join(', ')}</span> : null}</p>
              <div className="mt-3 flex flex-wrap gap-2 text-[12.5px] text-fg-secondary">
                <span className="inline-flex items-center gap-1.5 rounded-sm border border-line px-2 py-1"><Users className="h-3.5 w-3.5 text-fg-muted" aria-hidden />Sem {next.semester.replace('Semester ', '')} · Section {next.section}</span>
                <span className="inline-flex items-center gap-1.5 rounded-sm border border-line px-2 py-1"><MapPin className="h-3.5 w-3.5 text-fg-muted" aria-hidden />{next.room ? `Room ${next.room}` : 'Room not set'}</span>
                <span className="tnum inline-flex items-center gap-1.5 rounded-sm border border-line px-2 py-1">Lecture {next.lecture_no}</span>
              </div>
            </div>
            <ButtonLink to={`/professor/lectures/${next.lecture_id}`} variant="primary" size="lg" className="shrink-0 justify-center lg:min-w-[220px]">
              {state.key === 'AWAITING_START' ? 'Start class' : 'Open class'} <ArrowRight className="h-4 w-4" />
            </ButtonLink>
          </div>
        ) : (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="th">{rows.length ? 'No more classes today' : 'No classes scheduled today'}</div>
              <p className="mt-1 text-[14px] text-fg-soft">
                {later ? <>Next: <span className="font-medium text-fg">{later.subject.name}</span> on {fmt.weekday(later.effective_date ?? later.planned_date)}, {fmt.date(later.effective_date ?? later.planned_date)} at {fmt.clock(later.planned_start_time) || 'time not set'}.</> : 'Nothing is scheduled in the next two weeks.'}
              </p>
            </div>
            <ButtonLink to="/professor/sprint-plan">Open Sprint Plan</ButtonLink>
          </div>
        )}
      </section>

      <div className="mt-5 grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.9fr)_minmax(0,1fr)]">
        <div className="space-y-5">
          <section className="panel" aria-label="Today's teaching schedule">
            <div className="panel-header">
              <h2 className="flex items-center gap-2 text-[15px] font-semibold text-fg"><CalendarClock className="h-4 w-4 text-fg-label" aria-hidden />Today&apos;s teaching schedule</h2>
              <span className="th rounded-sm border border-line px-2 py-0.5 text-[10.5px]">{rows.length} session{rows.length === 1 ? '' : 's'}</span>
            </div>
            {!d ? <LoadingRows rows={3} /> : <TodaySchedule rows={rows} />}
          </section>
          {d ? <Syllabus d={d} /> : <div className="panel"><LoadingRows rows={4} /></div>}
        </div>
        <div className="space-y-5">
          {d ? <><ActionItems items={d.action_items} /><Pipeline d={d} /></> : <div className="panel"><LoadingRows rows={5} /></div>}
        </div>
      </div>
    </div>
  )
}

/** Today's Classes: the same schedule table on its own page. */
export function TodayClassesPage() {
  useBreadcrumbs([{ label: 'Teaching' }, { label: "Today's Classes" }])
  const dash = useApi<ProfessorDashboardData>('/professor/dashboard')
  const now = useInstNow(60_000)
  return (
    <div className="mx-auto max-w-[1280px]">
      <PageHeader title="Today's Classes" description={`${fmt.weekday(now.date)}, ${fmt.date(now.date)} · open a class to start it, record what was covered and submit.`} actions={<InstitutionClock showDate={false} />} />
      <div className="panel">
        {dash.error ? <ErrorState message={dash.error.message} onRetry={dash.reload} /> : !dash.data ? <LoadingRows rows={4} /> : <TodaySchedule rows={dash.data.schedule_today} />}
      </div>
    </div>
  )
}

export function CorrectionsPage() {
  useBreadcrumbs([{ label: 'Correction Requests' }])
  const items = useApi<Paged<Task>>('/professor/tasks/corrections')
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="Correction requests" description="Records a verifier sent back. Open each one to read the remarks, fix the record and resubmit." />
      {items.loading && !items.data ? (
        <div className="panel"><LoadingRows /></div>
      ) : items.error ? (
        <div className="panel"><ErrorState message={items.error.message} onRetry={items.reload} /></div>
      ) : items.data?.items.length ? (
        <div className="grid gap-3 sm:grid-cols-2">{items.data.items.map((t) => <TaskCard key={t.id} t={t} showDate />)}</div>
      ) : (
        <div className="panel"><EmptyState title="No corrections pending" description="Anything a verifier sends back will appear here." /></div>
      )}
    </div>
  )
}
