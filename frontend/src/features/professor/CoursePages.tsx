import { ChevronDown, GraduationCap } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from '@/lib/router'
import { BucketLegend, BUCKET_SEGMENTS, MetricDefinitions } from '@/components/domain/Progress'
import { ScheduleCalendar, monthRange } from '@/components/domain/ScheduleCalendar'
import { EmptyState, ErrorState, LoadingRows, PageLoading } from '@/components/feedback/States'
import { PageHeader, useBreadcrumbs } from '@/components/layout/PageHeader'
import { StatusBadge } from '@/components/ui/Badge'
import { ProgressBar, SegmentBar } from '@/components/ui/Display'
import { useApi } from '@/hooks/useApi'
import { EXECUTION_STATUS, fmt, isoLocal, SUBMISSION_STATUS, type Tone } from '@/lib/status'
import type { Paged } from '@/services/api'
import type { Metrics, PlanBrief, SubjectProgressRow, TaskCard, UnitRow } from '@/types/domain'
import { cn } from '@/utils/cn'

export function CoursesPage() {
  useBreadcrumbs([{ label: 'My Courses' }])
  const courses = useApi<{ items: SubjectProgressRow[] }>('/professor/courses')
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="My Courses" description="Teaching plans assigned to you this semester." />
      {courses.error ? (
        <ErrorState message={courses.error.message} onRetry={courses.reload} />
      ) : courses.loading && !courses.data ? (
        <div className="panel"><LoadingRows /></div>
      ) : !courses.data?.items.length ? (
        <div className="panel"><EmptyState icon={<GraduationCap className="h-5 w-5" />} title="No published plans yet" description="Plans appear here once the academic office publishes them." /></div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {courses.data.items.map((c) => (
            <Link key={c.plan_id} to={`/professor/courses/${c.plan_id}`} className="panel block p-4 transition-colors hover:border-line-strong">
              <div className="text-[12px] font-semibold tracking-wide text-primary uppercase">{c.subject_code} · Section {c.section}</div>
              <h2 className="mt-1 text-[15px] font-semibold text-fg">{c.subject_name}</h2>
              <div className="mt-3 flex items-baseline justify-between text-[13px]">
                <span className="tnum font-semibold text-fg">{c.execution_pct}% complete</span>
                <span className="meta tnum">{c.completed} of {c.total} lectures</span>
              </div>
              <ProgressBar value={c.execution_pct} className="mt-1.5" label={`${c.subject_name} progress`} />
              <div className="mt-3"><BucketLegend m={c} /></div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}

type Course = PlanBrief & { metrics: Metrics; units: UnitRow[]; definitions: Record<string, string>; lectures: TaskCard[] }

export function CourseDetailPage() {
  const { planId } = useParams()
  const course = useApi<Course>(`/professor/courses/${planId}`)
  const c = course.data
  useBreadcrumbs([{ label: 'My Courses', to: '/professor/courses' }, { label: c ? c.subject.short_name ?? c.subject.code : '…' }])
  const [open, setOpen] = useState<Record<string, boolean>>({})
  if (course.loading && !c) return <PageLoading />
  if (course.error || !c) return <ErrorState message={course.error?.message ?? 'Course not found'} onRetry={course.reload} />

  const units = new Map<number | null, TaskCard[]>()
  for (const l of c.lectures) units.set(l.unit_no, [...(units.get(l.unit_no) ?? []), l])

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title={c.subject.name} description={`${c.subject.code} · ${c.semester.name} · Section ${c.section.name} · ${c.academic_year.name}`} />
      <div className="panel mb-5 p-4">
        <div className="flex items-baseline justify-between">
          <span className="text-[13px] font-medium text-fg-secondary">Progress</span>
          <span className="tnum text-[22px] font-semibold text-fg">{c.metrics.execution_pct}%</span>
        </div>
        <SegmentBar segments={BUCKET_SEGMENTS(c.metrics)} className="mt-2 h-2.5" />
        <div className="mt-2.5"><BucketLegend m={c.metrics} /></div>
        <div className="mt-3"><MetricDefinitions definitions={c.definitions} /></div>
      </div>
      <div className="space-y-3">
        {[...units.entries()].map(([unit, lectures]) => {
          const key = String(unit)
          const u = c.units.find((x) => x.unit_no === unit)
          const expanded = open[key] ?? lectures.some((l) => l.is_overdue || (l.planned_date && l.planned_date >= isoLocal(new Date()) && l.execution_status !== 'COMPLETED'))
          return (
            <section key={key} className="panel">
              <button type="button" aria-expanded={expanded} onClick={() => setOpen((o) => ({ ...o, [key]: !expanded }))} className="flex w-full items-center gap-3 px-4 py-3 text-left">
                <ChevronDown className={cn('h-4 w-4 shrink-0 text-fg-muted transition-transform', !expanded && '-rotate-90')} />
                <span className="flex-1">
                  <span className="block text-[14px] font-semibold text-fg">{unit ? `Unit ${unit}` : 'Unassigned'} <span className="font-normal text-fg-label">– {lectures[0].content_topic}</span></span>
                  <span className="meta tnum">{u?.completed ?? 0} of {lectures.length} completed</span>
                </span>
                <span className="tnum w-12 text-right text-[14px] font-semibold text-fg">{u?.execution_pct ?? 0}%</span>
              </button>
              {expanded && (
                <ul className="border-t border-line-subtle">
                  {lectures.map((l) => (
                    <li key={l.id}>
                      <Link to={`/professor/lectures/${l.id}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line-subtle px-4 py-2.5 text-[13px] last:border-0 hover:bg-surface-2">
                        <span className="tnum w-9 text-fg-muted">L{l.lecture_no}</span>
                        <span className="min-w-0 flex-1 text-fg">{l.content_topic}</span>
                        <span className="meta w-24 whitespace-nowrap">{fmt.dateShort(l.planned_date)}</span>
                        <span className="w-40 text-right">
                          {l.submission_status && l.submission_status !== 'DRAFT' ? <StatusBadge value={l.submission_status} map={SUBMISSION_STATUS} /> : l.is_overdue ? <StatusBadge value="Overdue" map={{ Overdue: { label: 'Overdue', tone: 'danger' } }} /> : <StatusBadge value={l.execution_status} map={EXECUTION_STATUS} />}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )
        })}
      </div>
    </div>
  )
}

export function taskTone(t: TaskCard): { label: string; tone: Tone } {
  if (t.execution_status === 'COMPLETED') return { label: 'Completed', tone: 'success' }
  if (t.execution_status === 'PARTIALLY_COMPLETED') return { label: 'Partial', tone: 'warning' }
  if (t.execution_status === 'RESCHEDULED') return { label: 'Rescheduled', tone: 'info' }
  if (t.is_overdue) return { label: 'Delayed', tone: 'danger' }
  return { label: 'Scheduled', tone: 'neutral' }
}

export const SCHEDULE_LEGEND: { label: string; tone: Tone }[] = [
  { label: 'Scheduled', tone: 'neutral' },
  { label: 'Completed', tone: 'success' },
  { label: 'Partial', tone: 'warning' },
  { label: 'Delayed', tone: 'danger' },
  { label: 'Rescheduled', tone: 'info' },
]

export function ProfessorSchedulePage() {
  useBreadcrumbs([{ label: 'Schedule' }])
  const [month, setMonth] = useState(() => new Date())
  const { start, end } = monthRange(month)
  const data = useApi<Paged<TaskCard>>('/professor/schedule', { date_from: isoLocal(start), date_to: isoLocal(end) })
  const items = (data.data?.items ?? []).map((t) => {
    const s = taskTone(t)
    return { id: t.id, date: t.planned_date!, title: `${t.subject.short_name ?? t.subject.code} L${t.lecture_no} · ${t.content_topic}`, subtitle: `Section ${t.plan.section}`, time: fmt.timeRange(t.planned_start_time, t.planned_end_time), status: s.label, tone: s.tone, href: `/professor/lectures/${t.id}` }
  })
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Schedule" description="Your published lecture schedule. Planned dates are set by the academic office." />
      {data.error ? <ErrorState message={data.error.message} onRetry={data.reload} /> : <ScheduleCalendar month={month} onMonth={setMonth} items={items} legend={SCHEDULE_LEGEND} />}
    </div>
  )
}
