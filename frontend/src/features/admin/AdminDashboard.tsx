import { AlertTriangle, ArrowRight, CalendarClock, FileSpreadsheet, Plus } from 'lucide-react'
import { Link, useNavigate } from '@/lib/router'
import { ActivityTimeline, BUCKET_SEGMENTS } from '@/components/domain/Progress'
import { ErrorState, LoadingRows } from '@/components/feedback/States'
import { PageHeader, useBreadcrumbs } from '@/components/layout/PageHeader'
import { FilterBar, FilterSelect, useAcademicOptions } from '@/components/tables/FilterBar'
import { StatusBadge } from '@/components/ui/Badge'
import { ButtonLink } from '@/components/ui/Button'
import { Metric, MetricStrip, SegmentBar } from '@/components/ui/Display'
import { useApi } from '@/hooks/useApi'
import { fmt, IMPORT_MODE_LABEL, IMPORT_STATUS } from '@/lib/status'
import { useState } from 'react'
import type { AuditEntry, FactRow, SubjectProgressRow } from '@/types/domain'
import type { ImportSessionView } from '@/features/imports/types'

type Dashboard = {
  metrics: {
    active_subjects: number; active_plans: number; total_lectures: number; completed: number; partial: number; pending: number; delayed: number
    verification_pending: number; verification_pending_by_level: Record<string, number>; execution_pct: number; verified_pct: number; on_time_pct: number
  }
  subject_progress: SubjectProgressRow[]
  upcoming: FactRow[]
  delayed: FactRow[]
  recent_activity: AuditEntry[]
  recent_imports: ImportSessionView[]
  draft_imports: ImportSessionView[]
  plan_status_counts: Record<string, number>
}

type SprintOverview = {
  sprint: { id: string; name: string; start_date: string; end_date: string } | null
  current_week?: { number: number; of: number; classes: number; delivered: number; status: string; week_start: string } | null
  completion_pct?: number
  topics?: number
  remaining?: number
  carry_forward?: number
  at_risk?: { code: string; name: string; message: string | null }[]
}

export function AdminDashboard() {
  useBreadcrumbs([{ label: 'Dashboard' }])
  const navigate = useNavigate()
  const opts = useAcademicOptions()
  const [f, setF] = useState({ academic_year_id: '', semester_id: '', branch_id: '', section_id: '' })
  const set = (k: keyof typeof f) => (v: string) => setF((x) => ({ ...x, [k]: v }))
  const dash = useApi<Dashboard>('/admin/dashboard', f)
  const sprint = useApi<SprintOverview>('/admin/sprint-overview').data
  const d = dash.data
  const m = d?.metrics

  return (
    <div>
      <PageHeader
        title="Academic delivery overview"
        description={`As of ${fmt.date(new Date().toISOString())} · published plans only`}
        actions={
          <>
            <ButtonLink to="/admin/imports" icon={<FileSpreadsheet className="h-4 w-4" />}>Import curriculum</ButtonLink>
            <ButtonLink to="/admin/sprint-plans" variant="primary" icon={<Plus className="h-4 w-4" />}>Sprint plans</ButtonLink>
          </>
        }
      />
      <div className="mb-4">
        <FilterBar onReset={() => setF({ academic_year_id: '', semester_id: '', branch_id: '', section_id: '' })} active={Object.values(f).some(Boolean)}>
          <FilterSelect label="Academic year" value={f.academic_year_id} onChange={set('academic_year_id')} options={opts.years} width="w-36" />
          <FilterSelect label="Semester" value={f.semester_id} onChange={set('semester_id')} options={opts.semesters} width="w-36" />
          <FilterSelect label="Branch" value={f.branch_id} onChange={set('branch_id')} options={opts.branches} width="w-32" />
          <FilterSelect label="Section" value={f.section_id} onChange={set('section_id')} options={opts.sections} />
        </FilterBar>
      </div>

      {dash.error ? (
        <ErrorState message={dash.error.message} onRetry={dash.reload} />
      ) : (
        <>
          {sprint?.sprint ? (
            <section className="panel mb-5" aria-label="Active sprint">
              <div className="panel-header">
                <div className="min-w-0"><span className="panel-title">Active sprint · {sprint.sprint.name}</span><div className="meta tnum mt-0.5">{fmt.date(sprint.sprint.start_date)} → {fmt.date(sprint.sprint.end_date)}</div></div>
                <div className="flex items-center gap-2"><ButtonLink size="sm" to={`/admin/sprint-plans/${sprint.sprint.id}`}>Open sprint plan</ButtonLink><ButtonLink size="sm" variant="primary" to="/admin/sprint-plan">This week</ButtonLink></div>
              </div>
              <div className="grid grid-cols-2 gap-px bg-line-subtle sm:grid-cols-3 xl:grid-cols-5">
                {[
                  { label: 'Current week', value: sprint.current_week ? `${sprint.current_week.number} of ${sprint.current_week.of}` : '—', sub: sprint.current_week ? (sprint.current_week.status === 'PUBLISHED' ? 'Published' : 'Not published yet') : 'Outside the sprint dates' },
                  { label: 'Classes this week', value: sprint.current_week?.classes ?? 0, sub: `${sprint.current_week?.delivered ?? 0} delivered` },
                  { label: 'Completion', value: `${sprint.completion_pct ?? 0}%`, sub: `${sprint.remaining ?? 0} of ${sprint.topics ?? 0} topics left` },
                  { label: 'Carry forward', value: sprint.carry_forward ?? 0, sub: 'Waiting for next week', tone: sprint.carry_forward ? 'text-warning' : '' },
                  { label: 'At-risk subjects', value: sprint.at_risk?.length ?? 0, sub: sprint.at_risk?.length ? sprint.at_risk.map((a) => a.code).join(', ') : 'All on pace', tone: sprint.at_risk?.length ? 'text-warning' : '' },
                ].map((x) => (
                  <div key={x.label} className="bg-surface px-4 py-3">
                    <div className="th text-[10.5px]">{x.label}</div>
                    <div className={`tnum mt-1 text-[20px] leading-tight font-semibold ${x.tone || 'text-fg'}`}>{x.value}</div>
                    <div className="meta truncate">{x.sub}</div>
                  </div>
                ))}
              </div>
            </section>
          ) : sprint ? (
            <div className="panel mb-5 flex flex-wrap items-center justify-between gap-3 px-4 py-3">
              <span className="text-[13px] text-fg-secondary">No sprint plan is running. Create the semester&apos;s sprint plan to schedule classes.</span>
              <ButtonLink size="sm" variant="primary" to="/admin/sprint-plans">Create sprint plan</ButtonLink>
            </div>
          ) : null}
          <MetricStrip className="mb-5">
            <Metric label="Active subjects" value={m?.active_subjects ?? '–'} sub={m ? `${m.active_plans} published plans` : undefined} />
            <Metric label="Total lectures" value={m?.total_lectures ?? '–'} tone="neutral" />
            <Metric label="Completed" value={m?.completed ?? '–'} sub={m ? `${m.execution_pct}% execution` : undefined} tone="success" />
            <Metric label="Pending" value={m?.pending ?? '–'} sub={m ? `${m.partial} partial` : undefined} tone="neutral" />
            <Metric label="Delayed" value={m?.delayed ?? '–'} tone={m?.delayed ? 'danger' : 'neutral'} sub="Planned date passed" />
            <Metric label="Verification pending" value={m?.verification_pending ?? '–'} tone={m?.verification_pending ? 'warning' : 'neutral'} sub={m ? `CL/CH ${m.verification_pending_by_level.CL_CH ?? 0} · OM ${m.verification_pending_by_level.OM ?? 0}` : undefined} />
          </MetricStrip>

          <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
            <div className="space-y-5">
              <section className="panel">
                <div className="panel-header">
                  <h2 className="panel-title">Teaching progress by subject</h2>
                  <Link to="/admin/progress" className="text-[12.5px] text-primary hover:underline">All progress</Link>
                </div>
                {!d ? <LoadingRows /> : (
                  <div className="overflow-x-auto scroll-thin">
                    <table className="w-full min-w-[620px] text-[13px]">
                      <thead>
                        <tr className="border-b border-line bg-surface-2 text-left text-[11.5px] font-semibold tracking-wide text-fg-label uppercase">
                          <th className="px-4 py-2">Subject</th><th className="px-3 py-2">Professor</th><th className="w-[30%] px-3 py-2">Progress</th><th className="px-3 py-2 text-right">Done</th><th className="px-3 py-2 text-right">Delayed</th>
                        </tr>
                      </thead>
                      <tbody>
                        {d.subject_progress.map((r) => (
                          <tr key={r.plan_id} onClick={() => navigate(`/admin/plans/${r.plan_id}`)} className="cursor-pointer border-b border-line-subtle last:border-0 hover:bg-surface-2">
                            <td className="px-4 py-2.5"><div className="font-medium text-fg">{r.subject_short ?? r.subject_code} <span className="font-normal text-fg-label">· Section {r.section}</span></div><div className="meta truncate">{r.subject_name}</div></td>
                            <td className="px-3 py-2.5 whitespace-nowrap text-fg-soft">{r.professor.full_name}</td>
                            <td className="px-3 py-2.5"><SegmentBar segments={BUCKET_SEGMENTS(r)} /><div className="meta tnum mt-1">{r.completed}/{r.total} lectures</div></td>
                            <td className="tnum px-3 py-2.5 text-right font-semibold">{r.execution_pct}%</td>
                            <td className={`tnum px-3 py-2.5 text-right ${r.delayed ? 'font-semibold text-danger' : 'text-fg-muted'}`}>{r.delayed}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
                <section className="panel">
                  <div className="panel-header"><h2 className="panel-title flex items-center gap-1.5"><AlertTriangle className="h-3.5 w-3.5 text-danger" />Delayed lectures</h2><Link to="/admin/reports" className="text-[12.5px] text-primary hover:underline">Report</Link></div>
                  <ul className="divide-y divide-line-subtle">
                    {d?.delayed.length === 0 && <li className="meta px-4 py-5">No delayed lectures.</li>}
                    {d?.delayed.map((r) => (
                      <li key={r.lecture_id} className="flex items-center gap-3 px-4 py-2 text-[13px]">
                        <span className="w-12 shrink-0 font-semibold text-primary">{r.subject_short ?? r.subject_code}</span>
                        <span className="min-w-0 flex-1"><span className="block truncate text-fg">L{r.lecture_no} · {r.topic}</span><span className="meta">{r.professor} · Section {r.section}</span></span>
                        <span className="tnum shrink-0 text-[12px] font-semibold text-danger">{r.delay_days} d</span>
                      </li>
                    ))}
                  </ul>
                </section>
                <section className="panel">
                  <div className="panel-header"><h2 className="panel-title flex items-center gap-1.5"><CalendarClock className="h-3.5 w-3.5 text-fg-label" />Upcoming lectures</h2><Link to="/admin/schedule" className="text-[12.5px] text-primary hover:underline">Schedule</Link></div>
                  <ul className="divide-y divide-line-subtle">
                    {d?.upcoming.length === 0 && <li className="meta px-4 py-5">Nothing scheduled.</li>}
                    {d?.upcoming.map((r) => (
                      <li key={r.lecture_id} className="flex items-center gap-3 px-4 py-2 text-[13px]">
                        <span className="w-16 shrink-0 text-fg-secondary">{fmt.weekday(r.planned_date)} {fmt.dateShort(r.planned_date)}</span>
                        <span className="min-w-0 flex-1 truncate"><b className="font-semibold text-primary">{r.subject_short ?? r.subject_code}</b> <span className="text-fg">{r.topic}</span></span>
                        <span className="meta shrink-0">{fmt.clock(r.planned_start_time)}</span>
                      </li>
                    ))}
                  </ul>
                </section>
              </div>
            </div>

            <div className="space-y-5">
              <section className="panel">
                <div className="panel-header"><h2 className="panel-title">Pending verification</h2><Link to="/admin/monitor" className="text-[12.5px] text-primary hover:underline">Workflow monitor</Link></div>
                <div className="grid grid-cols-2 divide-x divide-line">
                  <Metric label="At CL/CH" value={m?.verification_pending_by_level.CL_CH ?? 0} sub="Academic verification" tone="neutral" />
                  <Metric label="At OM" value={m?.verification_pending_by_level.OM ?? 0} sub="Final verification" tone="neutral" />
                </div>
              </section>
              <section className="panel">
                <div className="panel-header"><h2 className="panel-title">Imports</h2><Link to="/admin/imports" className="text-[12.5px] text-primary hover:underline">Import plan</Link></div>
                <ul className="divide-y divide-line-subtle">
                  {[...(d?.draft_imports ?? []), ...(d?.recent_imports ?? [])].slice(0, 6).map((s) => (
                    <li key={s.id}>
                      <Link to={s.status === 'IMPORTED' ? `/admin/plans/${s.teaching_plan.id}` : `/admin/imports/${s.id}`} className="flex items-center justify-between gap-3 px-4 py-2.5 text-[13px] hover:bg-surface-2">
                        <span className="min-w-0"><span className="block truncate font-medium text-fg">{s.teaching_plan.subject.short_name ?? s.teaching_plan.subject.code} · {s.teaching_plan.semester.name.replace('Semester', 'Sem')} {s.teaching_plan.section.name}</span><span className="meta">{s.import_mode ? IMPORT_MODE_LABEL[s.import_mode] : 'Method not chosen'} · {fmt.relative(s.committed_at ?? s.updated_at)}</span></span>
                        <StatusBadge value={s.status} map={IMPORT_STATUS} />
                      </Link>
                    </li>
                  ))}
                  {d && d.draft_imports.length + d.recent_imports.length === 0 && <li className="meta px-4 py-5">No imports yet.</li>}
                </ul>
              </section>
              <section className="panel">
                <div className="panel-header"><h2 className="panel-title">Recent activity</h2></div>
                {d ? <ActivityTimeline items={d.recent_activity} /> : <LoadingRows rows={4} />}
                <div className="border-t border-line-subtle px-4 py-2"><Link to="/admin/reports" className="inline-flex items-center gap-1 text-[12.5px] text-primary hover:underline">Reports <ArrowRight className="h-3 w-3" /></Link></div>
              </section>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
