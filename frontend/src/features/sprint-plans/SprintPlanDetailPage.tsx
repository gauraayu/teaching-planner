import { AlertTriangle, FileSpreadsheet, Pencil, Plus, Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'
import { subjectColor } from '@/components/domain/TimetableGrid'
import { EmptyState, ErrorState, InlineAlert, LoadingRows, useToast } from '@/components/feedback/States'
import { FormField, Input, Select } from '@/components/forms/Fields'
import { PageHeader, useBreadcrumbs } from '@/components/layout/PageHeader'
import { Badge, Tag } from '@/components/ui/Badge'
import { Button, ButtonLink } from '@/components/ui/Button'
import { ConfirmDialog, Dialog } from '@/components/ui/Dialog'
import { Metric, MetricStrip, ProgressBar } from '@/components/ui/Display'
import { startImport } from '@/features/imports/ImportsPage'
import { useApi } from '@/hooks/useApi'
import { SPRINT_STATUS, sprintPlansApi, type SprintPlanDetail, type SprintSubject } from '@/lib/api/sprintPlans'
import { timetableApi, type Room } from '@/lib/api/timetable'
import { Link, useNavigate, useParams } from '@/lib/router'
import { fmt } from '@/lib/status'
import { errorMessage, type Paged } from '@/services/api'
import type { PlanBrief } from '@/types/domain'
import { cn } from '@/utils/cn'
import { useSprintPlanActions } from './SprintPlansPage'

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const WEEK_STATE = { PUBLISHED: { label: 'Published', tone: 'success' as const }, DRAFT: { label: 'Not published', tone: 'warning' as const }, EMPTY: { label: 'No classes', tone: 'neutral' as const } }

function SessionsDialog({ subject, rooms, onClose, onSaved }: { subject: SprintSubject | null; rooms: Room[]; onClose: () => void; onSaved: () => void }) {
  const toast = useToast()
  const [f, setF] = useState({ classes: 0, labs: 0, room: '', lab_room: '' })
  const [busy, setBusy] = useState(false)
  useEffect(() => { if (subject) setF({ classes: subject.classes_per_week, labs: subject.labs_per_week, room: subject.room ?? '', lab_room: subject.lab_room ?? '' }) }, [subject])
  if (!subject) return null
  const save = async () => {
    setBusy(true)
    try {
      await timetableApi.setAllocation(subject.plan_id, { classes_per_week: f.classes, labs_per_week: f.labs, room: f.room.trim() || null, lab_room: f.lab_room.trim() || null })
      toast('success', 'Weekly sessions saved. Generate the semester sprint to apply them.')
      onSaved()
      onClose()
    } catch (e) {
      toast('danger', errorMessage(e))
    } finally {
      setBusy(false)
    }
  }
  const roomSelect = (id: string, key: 'room' | 'lab_room', type: Room['room_type'], any: string) => (
    <Select id={id} value={f[key]} onChange={(e) => setF((x) => ({ ...x, [key]: e.target.value }))}>
      <option value="">{any}</option>
      {f[key] && !rooms.some((r) => r.name === f[key]) && <option value={f[key]}>{f[key]}</option>}
      {rooms.filter((r) => r.room_type === type && r.is_active).map((r) => <option key={r.id} value={r.name}>{r.name}</option>)}
    </Select>
  )
  return (
    <Dialog open onClose={onClose} title="Weekly sessions" description={`${subject.subject.code} ${subject.subject.name} · Sem ${subject.semester.replace('Semester ', '')}-${subject.section} · ${subject.professor.full_name}`}
      footer={<><Button onClick={onClose} disabled={busy}>Cancel</Button><Button variant="primary" loading={busy} onClick={save}>Save</Button></>}>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <FormField label="Class sessions per week" htmlFor="ws-c"><Input id="ws-c" type="number" min={0} max={12} className="tnum" value={f.classes} onChange={(e) => setF((x) => ({ ...x, classes: Number(e.target.value) }))} /></FormField>
        <FormField label="Lab sessions per week" htmlFor="ws-l" hint="Each lab takes two periods in a row"><Input id="ws-l" type="number" min={0} max={6} className="tnum" value={f.labs} onChange={(e) => setF((x) => ({ ...x, labs: Number(e.target.value) }))} /></FormField>
        <FormField label="Preferred room" htmlFor="ws-r">{roomSelect('ws-r', 'room', 'CLASSROOM', 'Any free classroom')}</FormField>
        <FormField label="Preferred lab" htmlFor="ws-lr">{roomSelect('ws-lr', 'lab_room', 'LAB', 'Any free lab')}</FormField>
      </div>
      {subject.remaining > 0 && subject.weeks_left > 0 && <p className="meta mt-4">{subject.remaining} lectures left in {subject.weeks_left} weeks: about {Math.ceil(subject.required_pace)} session{Math.ceil(subject.required_pace) === 1 ? '' : 's'} a week are needed to finish by the end date.</p>}
    </Dialog>
  )
}

/** One semester sprint plan: dates and calendar arithmetic, subjects with their pace, and every week of the semester. */
export function SprintPlanDetailPage() {
  const { planId } = useParams<{ planId: string }>()
  const toast = useToast()
  const navigate = useNavigate()
  const sp = useApi<SprintPlanDetail>(planId ? `/sprint-plans/${planId}` : null)
  const rooms = useApi<Paged<Room>>('/rooms').data?.items ?? []
  const loose = useApi<Paged<PlanBrief>>('/teaching-plans')
  const d = sp.data
  useBreadcrumbs([{ label: 'Sprint Plans', to: '/admin/sprint-plans' }, { label: d?.name ?? 'Sprint plan' }])
  const [sessions, setSessions] = useState<SprintSubject | null>(null)
  const [confirm, setConfirm] = useState(false)
  const [attach, setAttach] = useState(false)
  const [attachId, setAttachId] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<SprintPlanDetail['generation'] | null>(null)
  const { menu, dialogs } = useSprintPlanActions(() => void sp.reload(true))
  if (sp.error) return <div className="panel"><ErrorState message={sp.error.message} onRetry={sp.reload} /></div>
  if (!d) return <div className="panel"><LoadingRows rows={8} /></div>
  const archived = d.status === 'ARCHIVED'
  const available = (loose.data?.items ?? []).filter((p) => !p.sprint_plan && p.status !== 'ARCHIVED')
  const generate = async () => {
    setBusy(true)
    try {
      const r = await sprintPlansApi.generate(d.id)
      sp.setData(r)
      setResult(r.generation ?? null)
      toast('success', `Semester sprint generated: ${r.generation?.scheduled ?? 0} classes scheduled.`)
      setConfirm(false)
    } catch (e) {
      toast('danger', errorMessage(e))
    } finally {
      setBusy(false)
    }
  }
  const t = d.totals
  const missing = [...d.ready.without_curriculum.map((c) => `${c}: no topics imported`), ...d.ready.without_sessions.map((c) => `${c}: weekly sessions are 0`)]

  return (
    <div>
      <PageHeader title={d.name}
        description={<span className="tnum">{fmt.date(d.start_date)} → {fmt.date(d.end_date)} · {d.academic_year.name} · {d.working_days.map((x) => DAYS[x]).join(', ')}</span>}
        meta={<><Badge tone={SPRINT_STATUS[d.status].tone}>{SPRINT_STATUS[d.status].label}</Badge>{d.is_current && <Badge tone="info" icon={false}>Running now</Badge>}{d.generated_at && <span className="meta">Generated {fmt.dateTime(d.generated_at)}</span>}</>}
        actions={<div className="flex items-center gap-2">
          {!archived && <Button variant="primary" icon={<Sparkles className="h-4 w-4" />} disabled={busy || !d.subjects.length} onClick={() => setConfirm(true)}>{d.status === 'ACTIVE' ? 'Regenerate semester sprint' : 'Generate semester sprint'}</Button>}
          {menu(d)}
        </div>} />

      <MetricStrip className="mb-4">
        <Metric label="Total weeks" value={d.calendar.total_weeks} tone="neutral" sub={`${d.calendar.calendar_days} calendar days`} />
        <Metric label="Teaching days" value={d.calendar.teaching_days} tone="neutral" sub={`${d.calendar.working_days} working · ${d.calendar.holidays.length} holiday${d.calendar.holidays.length === 1 ? '' : 's'}`} />
        <Metric label="Topics" value={t.topics} tone="neutral" sub={`${t.subtopics} subtopics`} />
        <Metric label="Planned lectures" value={t.planned_lectures} tone="neutral" sub={`${t.weekly_sessions} sessions a week`} />
        <Metric label="Required weekly pace" value={t.required_pace} tone="neutral" sub={`${t.remaining} left in ${t.weeks_left} week${t.weeks_left === 1 ? '' : 's'}`} />
        <Metric label="Projected completion" value={t.projected_completion ? fmt.dateShort(t.projected_completion) : t.at_risk ? 'At risk' : '—'} tone={t.at_risk ? 'warning' : 'success'} sub={t.at_risk ? `${t.at_risk} subject${t.at_risk === 1 ? '' : 's'} at risk` : `${t.completion_pct}% completed`} />
      </MetricStrip>

      {result && (
        <InlineAlert tone={result.notes.length ? 'warning' : 'success'} className="mb-4" title={`Generated: ${result.scheduled} classes for ${result.subjects} subject${result.subjects === 1 ? '' : 's'}`}>
          {result.notes.length ? result.notes.join(' ') : 'Every topic has a date before the end date. Open a week, review it and publish.'}
        </InlineAlert>
      )}
      {d.subjects.filter((s) => s.at_risk).map((s) => (
        <InlineAlert key={s.plan_id} tone="warning" className="mb-3" title={`At risk · ${s.subject.code} ${s.subject.name}`} action={!archived ? <Button size="sm" onClick={() => setSessions(s)}>Change weekly sessions</Button> : undefined}>
          Required pace ≈ {Math.ceil(s.required_pace)} session{Math.ceil(s.required_pace) === 1 ? '' : 's'}/week, allocated {s.weekly_sessions}. {s.risk_message} The schedule is not changed until you decide.
        </InlineAlert>
      ))}

      <section className="panel mb-5" aria-label="Subjects">
        <div className="panel-header">
          <div><span className="panel-title">Subjects, professors and weekly sessions</span><div className="meta mt-0.5">Each row is one subject for one section. Import its topics once; the plan spreads them over the semester.</div></div>
          {!archived && (
            <div className="flex items-center gap-2">
              {available.length > 0 && <Button size="sm" onClick={() => { setAttachId(''); setAttach(true) }}>Add existing subject</Button>}
              <ButtonLink size="sm" variant="primary" icon={<Plus className="h-3.5 w-3.5" />} to={`/admin/plans/new?sprint=${d.id}`}>Add subject</ButtonLink>
            </div>
          )}
        </div>
        {d.subjects.length === 0 ? <EmptyState title="No subjects yet" description="Add a subject: choose semester, section, subject, professor and the sessions it needs every week. Then import its topics." /> : (
          <div className="overflow-x-auto scroll-thin">
            <table className="w-full min-w-[1040px] text-[13px]">
              <thead><tr className="border-b border-line bg-surface-2 text-left">{['Subject', 'Year · Sem · Sec', 'Professor', 'Weekly sessions', 'Topics', 'Required pace', 'Projected completion', 'Progress', ''].map((h) => <th key={h} className="th px-3 py-2">{h}</th>)}</tr></thead>
              <tbody>
                {d.subjects.map((s) => (
                  <tr key={s.plan_id} className="border-b border-line-subtle last:border-0">
                    <td className="px-3 py-2.5">
                      <div className="flex items-center gap-2"><span className="h-6 w-[3px] rounded-full" style={{ background: subjectColor(s.subject.code) }} aria-hidden /><div><Link to={`/admin/plans/${s.plan_id}`} className="font-semibold text-fg hover:text-primary">{s.subject.code}</Link><div className="text-fg-secondary">{s.subject.name}</div></div></div>
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap">{s.year_group ?? <span className="text-warning">No timing template</span>}<div className="meta">Sem {s.semester.replace('Semester ', '')}-{s.section}{s.room ? ` · Room ${s.room}` : ''}</div></td>
                    <td className="px-3 py-2.5 whitespace-nowrap">{s.professor.full_name}</td>
                    <td className="tnum px-3 py-2.5 whitespace-nowrap"><span className="font-semibold text-fg">{s.weekly_sessions}</span>/week{s.labs_per_week ? <span className="meta"> · {s.labs_per_week} lab</span> : null}</td>
                    <td className="tnum px-3 py-2.5 whitespace-nowrap">{s.topics ? <>{s.topics}<span className="meta"> · {s.remaining} left</span></> : <span className="text-warning">Not imported</span>}</td>
                    <td className="tnum px-3 py-2.5 whitespace-nowrap">{s.remaining ? <span className={cn(s.at_risk && 'font-semibold text-warning')}>{s.required_pace}/week{s.at_risk && <AlertTriangle className="ml-1 inline h-3.5 w-3.5" aria-label="At risk" />}</span> : '—'}</td>
                    <td className="px-3 py-2.5 whitespace-nowrap">{s.projected_completion ? fmt.date(s.projected_completion) : s.at_risk ? <Badge tone="warning">At risk</Badge> : <span className="meta">{d.status === 'ACTIVE' ? '—' : 'After generating'}</span>}</td>
                    <td className="w-[140px] px-3 py-2.5"><div className="flex items-center gap-2"><ProgressBar value={s.completion_pct} className="flex-1" label={`${s.subject.name} completed`} /><span className="tnum w-8 text-right text-[12px] text-fg-secondary">{s.completion_pct}%</span></div></td>
                    <td className="px-3 py-2.5 text-right whitespace-nowrap">
                      {!archived && (
                        <div className="flex justify-end gap-1.5">
                          {!s.topics && <Button size="sm" variant="primary" icon={<FileSpreadsheet className="h-3.5 w-3.5" />} onClick={async () => navigate(`/admin/imports/${await startImport(s.plan_id)}`)}>Import topics</Button>}
                          <Button size="sm" icon={<Pencil className="h-3.5 w-3.5" />} onClick={() => setSessions(s)}>Sessions</Button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel" aria-label="Weeks">
        <div className="panel-header"><span className="panel-title">Weekly sprint plans</span><span className="meta">Open a week to see the full timetable, adjust it and publish. Professors see published weeks only.</span></div>
        {d.status === 'DRAFT' ? <p className="meta px-4 py-5">Weeks appear after you generate the semester sprint.</p> : (
          <ul className="grid grid-cols-1 gap-px bg-line-subtle sm:grid-cols-2 xl:grid-cols-3">
            {d.weeks.map((w) => (
              <li key={w.week_start} className="bg-surface">
                <Link to={`/admin/sprint-plan?week=${w.week_start}`} className={cn('flex items-center justify-between gap-3 px-4 py-3 hover:bg-surface-2', w.is_current && 'border-l-2 border-l-primary')}>
                  <div className="min-w-0">
                    <div className="text-[13px] font-semibold text-fg">Week {w.number}{w.is_current && <span className="ml-2 text-[11px] font-semibold tracking-wide text-primary uppercase">Current</span>}</div>
                    <div className="tnum meta">{fmt.dateShort(w.start)} – {fmt.dateShort(w.end)} · {w.classes} class{w.classes === 1 ? '' : 'es'}{w.delivered ? ` · ${w.delivered} delivered` : ''}</div>
                  </div>
                  <Badge tone={w.is_past && w.status === 'DRAFT' ? 'neutral' : WEEK_STATE[w.status].tone} icon={false}>{w.has_draft ? 'Draft in review' : w.is_past && w.status === 'DRAFT' ? 'Not published' : WEEK_STATE[w.status].label}</Badge>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
      {d.calendar.holidays.length > 0 && <p className="meta mt-3">Holidays left out: {d.calendar.holidays.map((h) => `${fmt.dateShort(h.date)} ${h.name}`).join(' · ')}. <Link to="/admin/academic-setup?tab=holidays" className="link">Manage holidays</Link></p>}

      <SessionsDialog subject={sessions} rooms={rooms} onClose={() => setSessions(null)} onSaved={() => void sp.reload(true)} />
      <ConfirmDialog open={confirm} onClose={() => setConfirm(false)} title={d.status === 'ACTIVE' ? 'Regenerate semester sprint?' : 'Generate semester sprint?'} confirmLabel="Generate" loading={busy} onConfirm={generate}>
        <span className="block">Every topic gets a date, time and room between {fmt.date(d.start_date)} and {fmt.date(d.end_date)}, in lecture order, at each subject&apos;s weekly sessions.</span>
        <span className="mt-2 block">Checked while placing: professor, room and section free at that real time; each year group on its own timings and never in its own lunch; no holidays.</span>
        {missing.length > 0 && <span className="mt-2 block text-warning">Not ready, will be skipped: {missing.join('; ')}.</span>}
        {d.status === 'ACTIVE' && <span className="mt-2 block text-fg-label">Published weeks and recorded classes are not moved. Only weeks that are not published yet are planned again.</span>}
      </ConfirmDialog>
      <Dialog open={attach} onClose={() => setAttach(false)} title="Add existing subject" description="A subject plan that already has its topics imported."
        footer={<><Button onClick={() => setAttach(false)}>Cancel</Button><Button variant="primary" disabled={!attachId} onClick={async () => { try { sp.setData(await sprintPlansApi.attach(d.id, attachId)); void loose.reload(true); setAttach(false) } catch (e) { toast('danger', errorMessage(e)) } }}>Add to sprint plan</Button></>}>
        <FormField label="Subject plan" htmlFor="at-plan">
          <Select id="at-plan" value={attachId} onChange={(e) => setAttachId(e.target.value)}>
            <option value="">Select</option>
            {available.map((p) => <option key={p.id} value={p.id}>{p.subject.code} · {p.subject.name} · {p.semester.name} Section {p.section.name} · {p.professor.full_name}</option>)}
          </Select>
        </FormField>
        <p className="meta mt-3">Classes of it that were already held or recorded stay as they are. The rest is planned by this sprint plan. <Tag>Weekly sessions</Tag> can be set afterwards.</p>
      </Dialog>
      {dialogs}
    </div>
  )
}
