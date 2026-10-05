import { CalendarPlus, CheckCircle2, ClipboardList, FlaskConical, Lock, Pencil, Plus, Send, Sparkles, Trash2, Undo2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { subjectColor, TimetableGrid, TimetableLegend, type GridItem } from '@/components/domain/TimetableGrid'
import { EmptyState, ErrorState, InlineAlert, LoadingRows, useToast } from '@/components/feedback/States'
import { PageHeader, useBreadcrumbs } from '@/components/layout/PageHeader'
import { Badge, StatusBadge, Tag } from '@/components/ui/Badge'
import { Segmented } from '@/components/forms/Fields'
import { Button, ButtonLink } from '@/components/ui/Button'
import { ConfirmDialog } from '@/components/ui/Dialog'
import { Metric, MetricStrip, ProgressBar } from '@/components/ui/Display'
import { Tabs } from '@/components/ui/Tabs'
import { useApi } from '@/hooks/useApi'
import { addDays, adminSprintApi, mondayOf, type AdminSprintRow, type AdminWeek, type CarryForward, type Generation } from '@/lib/api/sprint'
import { CONFLICT_TITLE, templateOf, type TimingTemplate } from '@/lib/api/timetable'
import { useSearchParams } from '@/lib/router'
import { EXECUTION_STATUS, fmt, todayISO, VERIFICATION_STATUS } from '@/lib/status'
import { ApiError, errorMessage, type Paged } from '@/services/api'
import type { SprintRevisionBrief, SprintWeekInfo } from '@/types/domain'
import { cn } from '@/utils/cn'
import { LectureDialog, type LectureDialogState } from './components/LectureDialog'
import { ReviewDialog } from './components/ReviewDialog'
import { RevisionDialog } from './SprintHistoryPage'
import { WeekNav, weekLabel } from './components/WeekNav'

function CarryForwardPanel({ items, week, editing, onAdd, onDecide }: { items: CarryForward[]; week: AdminWeek; editing: boolean; onAdd: (c: CarryForward) => void; onDecide: (c: CarryForward, status: 'DEFERRED' | 'RESOLVED') => void }) {
  const [all, setAll] = useState(false)
  const shown = all ? items : items.slice(0, 5)
  return (
    <section className="panel" aria-label="Carry-forward">
      <div className="panel-header">
        <h2 className="panel-title">Carry-forward from earlier weeks · {items.length} item{items.length === 1 ? '' : 's'}</h2>
        <span className="meta">Suggested from what professors recorded. Nothing is scheduled until you add and publish it.</span>
      </div>
      {items.length === 0 ? (
        <p className="meta px-4 py-5">No incomplete topics from earlier weeks.</p>
      ) : (
        <ul>
          {shown.map((c) => (
            <li key={c.lecture_id} className="grid grid-cols-1 gap-x-4 gap-y-2 border-b border-line-subtle px-4 py-3 last:border-0 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13.5px]">
                  <span className="font-semibold text-fg">{c.subject.short_name ?? c.subject.code} · Lecture {c.lecture_no}</span>
                  <span className="text-fg-secondary">{c.topic}</span>
                  <Badge tone={c.kind === 'PARTIAL' ? 'warning' : 'danger'}>{c.kind === 'PARTIAL' ? `${c.covered}/${c.total} covered` : 'Not conducted'}</Badge>
                  {c.status === 'DEFERRED' && <Badge tone="info">Rescheduled later</Badge>}
                  {c.draft_item_id && <Badge tone="success">Placed in this draft</Badge>}
                </div>
                <div className="mt-1 text-[13px] text-fg-soft">Remaining: {c.remaining.length ? c.remaining.join(' · ') : 'whole lecture'}</div>
                <div className="meta mt-0.5">{c.professor.full_name} · Sem {c.semester.replace('Semester ', '')}-{c.section} · was {fmt.weekday(c.date)} {fmt.dateShort(c.date)}{c.note ? ` · ${c.note}` : ''}</div>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <Button size="sm" variant="primary" disabled={!editing || !!c.draft_item_id || week.week.is_past} title={!editing ? 'Start the sprint meeting update first' : undefined} icon={<CalendarPlus className="h-3.5 w-3.5" />} onClick={() => onAdd(c)}>
                  Add to this week
                </Button>
                <Button size="sm" disabled={!!c.draft_item_id || c.status === 'DEFERRED'} onClick={() => onDecide(c, 'DEFERRED')}>Reschedule later</Button>
                <Button size="sm" variant="ghost" disabled={!!c.draft_item_id} onClick={() => onDecide(c, 'RESOLVED')}>Mark resolved</Button>
              </div>
            </li>
          ))}
          {items.length > 5 && (
            <li className="px-4 py-2.5"><Button variant="link" className="text-[12.5px]" onClick={() => setAll((a) => !a)}>{all ? 'Show fewer' : `Show all ${items.length} items`}</Button></li>
          )}
        </ul>
      )}
    </section>
  )
}

type TabKey = 'timetable' | 'table' | 'progress' | 'carry' | 'history'
const short = (name: string) => name.replace(/^(Dr\.|Prof\.|Mr\.|Ms\.|Mrs\.)\s*/i, '')
const DONE = ['COMPLETED', 'PARTIALLY_COMPLETED']

/** Per subject-section: what the week planned and what was delivered. */
function ProgressTab({ rows }: { rows: AdminSprintRow[] }) {
  const groups = useMemo(() => {
    const live = rows.filter((r) => !r.is_cancelled && r.draft?.change_type !== 'CANCEL')
    return [...new Set(live.map((r) => r.plan_id))].map((id) => {
      const mine = live.filter((r) => r.plan_id === id)
      const done = mine.filter((r) => DONE.includes(r.execution_status)).length
      const subs = mine.reduce((n, r) => n + r.subtopics.length, 0)
      const covered = mine.reduce((n, r) => n + r.subtopics_covered, 0)
      return { id, first: mine[0], total: mine.length, done, partial: mine.filter((r) => r.execution_status === 'PARTIALLY_COMPLETED').length,
        verified: mine.filter((r) => r.submission_status === 'FINAL_VERIFIED').length, carry: mine.filter((r) => r.origin === 'CARRY_FORWARD').length,
        subs, covered, pct: mine.length ? Math.round((done * 100) / mine.length) : 0 }
    })
  }, [rows])
  if (!groups.length) return <div className="panel"><EmptyState title="Nothing planned in this week" description="Make the weekly sprint plan, or move to another week." /></div>
  return (
    <div className="panel overflow-x-auto scroll-thin">
      <table className="w-full min-w-[860px] text-[13px]">
        <thead><tr className="border-b border-line bg-surface-2 text-left">{['Subject', 'Class', 'Professor', 'Classes', 'Delivered', 'Subtopics covered', 'Final verified', 'Execution'].map((h) => <th key={h} className="th px-3 py-2">{h}</th>)}</tr></thead>
        <tbody>
          {groups.map((g) => (
            <tr key={g.id} className="border-b border-line-subtle last:border-0">
              <td className="px-3 py-2.5"><span className="font-semibold text-fg">{g.first.subject.short_name ?? g.first.subject.code}</span> <span className="text-fg-secondary">{g.first.subject.name}</span></td>
              <td className="px-3 py-2.5 whitespace-nowrap">Sem {g.first.semester.replace('Semester ', '')}-{g.first.section}</td>
              <td className="px-3 py-2.5 whitespace-nowrap">{g.first.professor.full_name}</td>
              <td className="tnum px-3 py-2.5">{g.total}{g.carry ? <span className="text-warning"> · {g.carry} carry-forward</span> : null}</td>
              <td className="tnum px-3 py-2.5">{g.done}{g.partial ? <span className="text-fg-label"> · {g.partial} partial</span> : null}</td>
              <td className="tnum px-3 py-2.5">{g.covered}/{g.subs}</td>
              <td className="tnum px-3 py-2.5">{g.verified}/{g.total}</td>
              <td className="w-[180px] px-3 py-2.5"><div className="flex items-center gap-2"><ProgressBar value={g.pct} className="flex-1" label={`${g.first.subject.name} execution`} /><span className="tnum w-9 text-right text-[12px] font-semibold text-fg">{g.pct}%</span></div></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function HistoryTab() {
  const history = useApi<Paged<SprintRevisionBrief & { week: SprintWeekInfo }>>('/admin/sprint-plan/history')
  const [open, setOpen] = useState<string | null>(null)
  if (history.error) return <div className="panel"><ErrorState message={history.error.message} onRetry={history.reload} /></div>
  if (!history.data) return <div className="panel"><LoadingRows rows={4} /></div>
  return (
    <div className="panel">
      <div className="panel-header"><span className="panel-title">Sprint plan revisions</span><span className="meta">Published revisions are never edited or deleted.</span></div>
      {history.data.items.length === 0 ? <EmptyState title="No sprint plans yet" description="Make the weekly sprint plan and publish it; every published week is listed here." /> : (
        <ul className="divide-y divide-line-subtle">
          {history.data.items.map((r) => (
            <li key={r.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-[13px]">
              <span className="flex flex-wrap items-center gap-2.5">
                <span className="font-semibold text-fg">{r.week.number ? `Week ${r.week.number} · ` : ''}{weekLabel(r.week)}</span>
                <Badge tone={r.status === 'PUBLISHED' ? 'success' : 'warning'}>{r.status === 'PUBLISHED' ? `Published v${r.revision_number}` : 'Draft'}</Badge>
                <span className="text-fg-secondary">{r.change_count} class{r.change_count === 1 ? '' : 'es'} planned or changed</span>
              </span>
              <span className="flex items-center gap-3">
                <span className="meta">{r.published_by?.full_name ?? r.created_by?.full_name ?? '—'} · {fmt.dateTime(r.published_at ?? r.created_at)}</span>
                {r.status === 'PUBLISHED' ? <Button size="sm" onClick={() => setOpen(r.id)}>View</Button> : <ButtonLink size="sm" to={`/admin/sprint-plan?week=${r.week_start}`}>Continue</ButtonLink>}
              </span>
            </li>
          ))}
        </ul>
      )}
      <RevisionDialog revisionId={open} onClose={() => setOpen(null)} load={adminSprintApi.changes} />
    </div>
  )
}

const YEAR = ['', '1st', '2nd', '3rd', '4th', '5th', '6th']
const cellTh = 'th border-b border-line bg-surface-2 px-2.5 py-2 text-left whitespace-nowrap'
const cellTd = 'border-b border-line-subtle px-2.5 py-2 align-top text-[12.5px]'

/** The week as one Excel-like sheet: plan, topic, subtopics and where each class stands. */
function SprintTable({ w, editing, weekStart, onEdit, onCancel, onUndo, onAdd }: { w: AdminWeek; editing: boolean; weekStart: string; onEdit: (r: AdminSprintRow) => void; onCancel: (r: AdminSprintRow) => void; onUndo: (r: AdminSprintRow) => void; onAdd: () => void }) {
  const rows = w.days.flatMap((d) => d.lectures)
  const vs = (v: string | null | undefined) => (v ? <StatusBadge value={v as keyof typeof VERIFICATION_STATUS} map={VERIFICATION_STATUS} /> : <span className="text-fg-faint">—</span>)
  if (!rows.length) return <div className="panel"><EmptyState icon={<ClipboardList className="h-5 w-5" />} title="No classes planned for this week" description="Generate the semester sprint, or move to another week." /></div>
  return (
    <div className="panel overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2.5">
        <span className="meta">{rows.length} classes · scroll sideways for all columns</span>
        <div className="flex items-center gap-2">
          {editing && <Button size="sm" icon={<Plus className="h-3.5 w-3.5" />} onClick={onAdd}>Add class</Button>}
          <ButtonLink size="sm" variant="ghost" to={`/admin/monitor?week=${weekStart}`}>Notes, evidence and OM timings</ButtonLink>
        </div>
      </div>
      <div className="overflow-x-auto scroll-thin" tabIndex={0} role="region" aria-label="Weekly sprint table">
        <table className="w-full min-w-[1760px] border-separate border-spacing-0">
          <thead>
            <tr>
              {['Date', 'Day', 'Time', 'Professor', 'Subject', 'Year', 'Sem', 'Sec', 'Room', 'Lec', 'Unit', 'Topic', 'Subtopic 1', 'Subtopic 2', 'Subtopic 3', 'Carry fwd', 'Execution', 'CL/CH', 'OM', 'Final status'].map((h) => <th key={h} scope="col" className={cellTh}>{h}</th>)}
              <th scope="col" className={cn(cellTh, 'sticky right-0 z-[2] border-l text-right')}>{editing ? 'Actions' : 'Status'}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const d = r.draft
              const cancelled = r.is_cancelled || d?.change_type === 'CANCEL'
              return (
                <tr key={r.key} className={cn('group hover:bg-primary/[0.03]', cancelled && 'text-fg-muted line-through', d && 'bg-warning/[0.03]')}>
                  <td className={cn(cellTd, 'tnum whitespace-nowrap')}>{fmt.dateShort(r.date)}</td>
                  <td className={cellTd}>{fmt.weekday(r.date)}</td>
                  <td className={cn(cellTd, 'tnum whitespace-nowrap')}>{r.start}–{r.end ?? '?'}</td>
                  <td className={cn(cellTd, 'whitespace-nowrap text-fg-soft')}>{r.professor.full_name}</td>
                  <td className={cn(cellTd, 'whitespace-nowrap')}><span className="inline-flex items-center gap-1.5 font-medium text-fg"><span className="h-2 w-2 rounded-full" style={{ background: subjectColor(r.subject.code) }} aria-hidden />{r.subject.code}</span><div className="meta no-underline">{r.subject.name}</div></td>
                  <td className={cellTd}>{YEAR[Math.ceil((r.semester_number ?? 0) / 2)] || '—'}</td>
                  <td className={cellTd}>{r.semester.replace('Semester ', '')}</td>
                  <td className={cellTd}>{r.section}</td>
                  <td className={cn(cellTd, 'whitespace-nowrap')}>{r.room ?? '—'}</td>
                  <td className={cn(cellTd, 'tnum')}>{r.lecture_no ?? '—'}</td>
                  <td className={cn(cellTd, 'tnum')}>{r.unit_no ?? '—'}</td>
                  <td className={cellTd}><div className="max-w-[240px] min-w-[160px] text-fg">{r.topic}</div></td>
                  {[0, 1, 2].map((i) => <td key={i} className={cellTd}><div className="max-w-[170px] min-w-[110px] text-fg-secondary">{i === 2 && r.subtopics.length > 3 ? r.subtopics.slice(2).join(' · ') : r.subtopics[i] ?? '—'}</div></td>)}
                  <td className={cellTd}>{r.origin === 'CARRY_FORWARD' ? <Badge tone="warning" icon={false}>Carry forward</Badge> : <span className="text-fg-faint">—</span>}</td>
                  <td className={cn(cellTd, 'whitespace-nowrap')}><StatusBadge value={r.execution_status} map={EXECUTION_STATUS} />{r.subtopics.length > 0 && r.execution_status !== 'SCHEDULED' && <div className="meta tnum">{r.subtopics_covered}/{r.subtopics.length} subtopics</div>}</td>
                  <td className={cn(cellTd, 'whitespace-nowrap')}>{vs(r.verification?.CL_CH)}</td>
                  <td className={cn(cellTd, 'whitespace-nowrap')}>{vs(r.verification?.OM)}</td>
                  <td className={cn(cellTd, 'whitespace-nowrap')}>{r.submission_status === 'FINAL_VERIFIED' ? <Badge tone="success">Final verified</Badge> : r.submission_status === 'CORRECTION_REQUIRED' ? <Badge tone="danger">Correction required</Badge> : <span className="text-fg-label">Pending</span>}</td>
                  <td className={cn(cellTd, 'sticky right-0 z-[1] border-l border-l-line bg-surface no-underline group-hover:bg-surface-2')}>
                    <div className="flex items-center justify-end gap-1.5 whitespace-nowrap">
                      {d ? <Badge tone={d.change_type === 'CANCEL' ? 'danger' : d.change_type === 'ADD' ? 'success' : 'warning'} icon={false}>Draft</Badge> : r.released === false ? <Badge tone="warning" icon={false}>Not published</Badge> : !editing ? <Badge tone="success" icon={false}>Published</Badge> : null}
                      {editing && (d ? (
                        <>
                          {d.change_type !== 'CANCEL' && r.lecture_id && <Button size="sm" icon={<Pencil className="h-3.5 w-3.5" />} onClick={() => onEdit(r)}>Edit</Button>}
                          <Button size="sm" variant="ghost" icon={<Undo2 className="h-3.5 w-3.5" />} onClick={() => onUndo(r)}>Undo</Button>
                        </>
                      ) : r.locked ? <span className="inline-flex items-center gap-1 text-[12px] text-fg-muted" title={r.locked}><Lock className="h-3.5 w-3.5" /> Locked</span> : (
                        <>
                          <Button size="sm" icon={<Pencil className="h-3.5 w-3.5" />} onClick={() => onEdit(r)}>Edit</Button>
                          <Button size="sm" variant="ghost" aria-label={`Remove ${r.subject.name} class`} icon={<Trash2 className="h-3.5 w-3.5" />} onClick={() => onCancel(r)} />
                        </>
                      ))}
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/** Admin: the week's sprint plan. Made from the semester sprint plan, adjusted if needed, then published. */
export function AdminSprintPlanPage() {
  useBreadcrumbs([{ label: 'Teaching Management' }, { label: 'Weekly Sprint Plan' }])
  const toast = useToast()
  const [params, setParams] = useSearchParams()
  const thisWeek = mondayOf(todayISO())
  const weekStart = mondayOf(params.get('week') || todayISO())
  const tab = (params.get('tab') as TabKey) || 'timetable'
  const nav = (next: { week?: string; tab?: TabKey }) => {
    const week = next.week ?? weekStart, t = next.tab ?? tab
    setParams({ ...(week === thisWeek ? {} : { week }), ...(t === 'timetable' ? {} : { tab: t }) }, { replace: true })
  }
  const go = (monday: string) => nav({ week: monday })
  const week = useApi<AdminWeek>('/admin/sprint-plan/week', { week_start: weekStart })
  const templates = useApi<Paged<TimingTemplate>>('/timing-templates').data?.items.filter((t) => t.is_active) ?? []
  const w = week.data
  const [dialog, setDialog] = useState<LectureDialogState | null>(null)
  const [review, setReview] = useState(false)
  const [discard, setDiscard] = useState(false)
  const [make, setMake] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [generation, setGeneration] = useState<(Generation & { week: string }) | null>(null)
  const [view, setView] = useState('combined')
  const [busy, setBusy] = useState(false)
  const editing = !!w?.draft
  const rows = w?.days.flatMap((d) => d.lectures) ?? []
  const total = rows.length
  // "Make weekly sprint plan" plans the week on screen when it is still ahead, otherwise next week.
  const target = weekStart > thisWeek ? weekStart : addDays(thisWeek, 7)

  const apply = (next: AdminWeek, message?: string) => {
    week.setData(next)
    if (message) toast('success', message)
  }
  const run = async (fn: () => Promise<AdminWeek>, message?: string) => {
    setBusy(true)
    try {
      apply(await fn(), message)
    } catch (e) {
      toast('danger', errorMessage(e))
    } finally {
      setBusy(false)
    }
  }
  const decide = async (c: CarryForward, status: 'DEFERRED' | 'RESOLVED') => {
    try {
      await adminSprintApi.decideCarryForward(c.lecture_id, status)
      toast('success', status === 'RESOLVED' ? 'Marked resolved.' : 'Kept for a later week.')
      void week.reload(true)
    } catch (e) {
      toast('danger', errorMessage(e))
    }
  }
  const makePlan = async () => {
    setBusy(true)
    try {
      const r = await adminSprintApi.generate(target, true)
      setGeneration({ ...r.generation, week: target })
      if (target === weekStart) week.setData(r)
      else nav({ week: target, tab: 'timetable' })
      toast('success', `Sprint plan drafted for ${weekLabel(r.week)}. Review it, then publish.`)
      setMake(false)
    } catch (e) {
      toast('danger', e instanceof ApiError && e.code === 'NO_TIMETABLE' ? 'Generate the semester sprint first: Sprint Plans → open the plan → Generate Semester Sprint.' : errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const clashing = new Set((w?.conflicts ?? []).filter((c) => c.level === 'ERROR').flatMap((c) => c.keys ?? []))
  const items: GridItem[] = (w?.days ?? []).flatMap((day, di) => day.lectures.filter((r) => r.start && r.end).map((r) => {
    const cancelled = r.is_cancelled || r.draft?.change_type === 'CANCEL'
    const done = DONE.includes(r.execution_status)
    return {
      key: r.key, day: di, start: r.start!, end: r.end!, template: templateOf(templates, r.semester_number),
      title: `${r.subject.short_name ?? r.subject.code}${r.lecture_no ? ` · L${r.lecture_no}` : ''}`,
      subtitle: r.topic,
      meta: `${short(r.professor.full_name)}\n${r.semester.replace('Semester ', '')}-${r.section} · ${r.room ?? 'No room'}`,
      accent: subjectColor(r.subject.code),
      tone: clashing.has(r.key) ? 'conflict' : r.origin === 'CARRY_FORWARD' ? 'carry' : r.lecture_type === 'PRACTICAL' ? 'lab' : 'neutral',
      dim: cancelled,
      corner: r.submission_status === 'FINAL_VERIFIED' ? <CheckCircle2 className="h-3 w-3 shrink-0 text-primary" aria-label="Final verified" /> : r.lecture_type === 'PRACTICAL' ? <FlaskConical className="h-3 w-3 shrink-0 text-accent" aria-label="Lab" /> : r.origin === 'CARRY_FORWARD' ? <span className="shrink-0 rounded-[3px] bg-warning-soft px-1 text-[9.5px] font-bold text-warning">CF</span> : r.draft ? <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-warning" aria-label="Draft" /> : done ? <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" aria-label="Delivered" /> : undefined,
      hint: `${r.subject.name}${r.lecture_no ? ` · Lecture ${r.lecture_no}` : ''} · ${r.topic}${r.subtopics.length ? ` (${r.subtopics.join(', ')})` : ''} · ${r.professor.full_name} · ${fmt.timeRange(r.start, r.end)} · ${r.room ?? 'no room'}${r.origin === 'CARRY_FORWARD' ? ' · carry-forward' : ''}${r.draft ? ' · draft' : ''}${r.locked ? ` · ${r.locked}` : ''}`,
      onClick: editing && !cancelled && r.lecture_id && (r.draft || !r.locked) ? () => setDialog({ mode: 'edit', row: r }) : undefined,
    } satisfies GridItem
  }))
  const gridDays = (w?.days ?? []).map((d) => ({ label: fmt.weekday(d.date), sub: fmt.dateShort(d.date), today: d.date === w?.today }))
  const openCarry = w?.carry_forward.filter((c) => !c.draft_item_id).length ?? 0

  return (
    <div>
      <PageHeader
        title="Weekly Sprint Plan"
        description="The institution's timetable for one week of the sprint plan: every professor, every year group, with the topic of each class. Professors see a week after you publish it."
        actions={<Button variant="primary" icon={<Sparkles className="h-4 w-4" />} disabled={busy} onClick={() => setMake(true)}>Make weekly sprint plan</Button>}
      />
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <WeekNav week={w?.week} weekStart={weekStart} onChange={go} />
        {w && (
          <div className="flex flex-wrap items-center gap-2">
            {w.week.sprint_plan && <ButtonLink size="sm" variant="ghost" to={`/admin/sprint-plans/${w.week.sprint_plan.id}`}>{w.week.sprint_plan.name}</ButtonLink>}
            {w.unpublished > 0 ? <Badge tone="warning">Not published · {w.unpublished} class{w.unpublished === 1 ? '' : 'es'}</Badge>
              : total > 0 ? <Badge tone="success">Published{w.published ? ` · ${fmt.dateTime(w.published.published_at)}` : ''}</Badge> : <Tag>No classes</Tag>}
            {!editing && (
              <Button disabled={w.week.is_past || busy} title={w.week.is_past ? 'This week is over' : undefined} onClick={() => run(() => adminSprintApi.startMeeting(weekStart), 'Sprint meeting started. Changes stay in a draft until you publish.')}>
                Edit this week
              </Button>
            )}
            {!editing && w.unpublished > 0 && !w.week.is_past && (
              <Button variant="primary" icon={<Send className="h-4 w-4" />} disabled={busy} onClick={() => setPublishing(true)}>Publish week</Button>
            )}
          </div>
        )}
      </div>

      {week.error ? (
        <div className="panel"><ErrorState message={week.error.message} onRetry={week.reload} /></div>
      ) : !w ? (
        <div className="panel"><LoadingRows rows={6} /></div>
      ) : (
        <>
          {editing && (
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-md border border-warning-border bg-warning-soft px-4 py-3">
              <div className="min-w-0">
                <div className="text-[13.5px] font-semibold text-warning">Draft · {weekLabel(w.week)}</div>
                <div className="text-[13px] text-fg-soft">
                  {w.draft!.change_count} change{w.draft!.change_count === 1 ? '' : 's'} in this draft{w.unpublished ? ` · ${w.unpublished} class${w.unpublished === 1 ? '' : 'es'} not visible to professors yet` : ''}. Validate, then publish.
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button icon={<Plus className="h-4 w-4" />} onClick={() => setDialog({ mode: 'add' })}>Add lecture</Button>
                <Button variant="ghost" onClick={() => setDiscard(true)}>Discard draft</Button>
                <Button icon={<CheckCircle2 className="h-4 w-4" />} onClick={() => { void week.reload(true); toast((w.conflicts ?? []).some((c) => c.level === 'ERROR') ? 'danger' : 'success', (w.conflicts ?? []).some((c) => c.level === 'ERROR') ? 'Conflicts found. See the list under the timetable.' : 'No conflicts. This week is ready to publish.') }}>Validate</Button>
                <Button variant="primary" onClick={() => setReview(true)}>Review &amp; publish</Button>
              </div>
            </div>
          )}
          {generation && generation.week === weekStart && (
            <InlineAlert tone={generation.notes.length ? 'info' : 'success'} className="mb-4" title={`Next week drafted: ${generation.topics + generation.unchanged} topic${generation.topics + generation.unchanged === 1 ? '' : 's'} and ${generation.carry_forward} carry-forward item${generation.carry_forward === 1 ? '' : 's'}`}>
              Generated from the semester plan and last week&apos;s progress. {generation.notes.length ? generation.notes.join(' ') : 'Review the draft, then publish.'}
            </InlineAlert>
          )}
          {generation && generation.week === weekStart && generation.pace?.filter((x) => x.at_risk).map((x) => (
            <InlineAlert key={x.plan_id} tone="warning" className="mb-4" title={`At risk · ${x.subject.short_name ?? x.subject.code} Sem ${x.semester.replace('Semester ', '')}-${x.section}`}>
              {x.remaining} lectures left in {x.weeks_left} week{x.weeks_left === 1 ? '' : 's'}: required pace ≈ {Math.ceil(x.required_pace)} sessions/week, allocated {x.weekly_sessions}. {x.risk_message} Nothing is changed automatically.
            </InlineAlert>
          ))}

          <Tabs className="mb-4" value={tab} onChange={(t) => nav({ tab: t })}
            items={[{ value: 'timetable', label: 'Weekly Timetable' }, { value: 'table', label: 'Table View', count: total }, { value: 'progress', label: 'Progress' }, { value: 'carry', label: 'Carry Forward', count: openCarry }, { value: 'history', label: 'History' }]} />

          {tab === 'timetable' && (
            <div className="panel">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
                <Segmented ariaLabel="Timetable view" size="sm" value={view} onChange={setView} options={[{ value: 'combined', label: 'Combined' }, ...templates.map((t) => ({ value: t.code, label: t.name }))]} />
                <TimetableLegend extra={[{ label: 'Carry-forward', tone: 'carry' }, { label: 'Conflict', tone: 'conflict' }]} />
              </div>
              <TimetableGrid templates={templates} view={view} days={gridDays} items={items}
                empty={total === 0 ? (
                  <EmptyState icon={<ClipboardList className="h-5 w-5" />} title="No classes planned for this week"
                    description="Classes appear here once the semester sprint is generated. Open the sprint plan, add subjects and choose Generate Semester Sprint."
                    action={<ButtonLink to="/admin/sprint-plans">Open sprint plans</ButtonLink>} />
                ) : undefined} />
              {editing && <p className="meta border-t border-line px-4 py-2.5">Click a class to change its time, room, professor or topic. Use Table View to cancel a class or undo a change.</p>}
            </div>
          )}

          {tab === 'table' && (
            <SprintTable w={w} editing={editing} weekStart={weekStart}
              onEdit={(row) => setDialog({ mode: 'edit', row })} onCancel={(row) => setDialog({ mode: 'cancel', row })} onAdd={() => setDialog({ mode: 'add' })}
              onUndo={(row) => run(() => adminSprintApi.removeChange(w.draft!.id, row.draft!.id), 'Change removed from the draft.')} />
          )}

          {tab === 'progress' && (
            <>
              <MetricStrip className="mb-4">
                <Metric label="Lectures this week" value={w.summary.lectures_planned} tone="neutral" sub={w.summary.cancelled ? `${w.summary.cancelled} cancelled` : undefined} />
                <Metric label="Completed" value={w.summary.completed} sub={`${w.summary.partially_completed} partial`} />
                <Metric label="Not conducted" value={w.summary.not_conducted} tone={w.summary.not_conducted ? 'danger' : 'neutral'} />
                <Metric label="Upcoming" value={w.summary.upcoming} tone="neutral" />
                <Metric label="Subtopics covered" value={`${w.summary.subtopics_covered}/${w.summary.subtopics_planned}`} tone="neutral" sub={`${w.summary.subtopics_remaining} remaining`} />
                <Metric label="Last week" value={`${w.previous_week.completed + w.previous_week.partially_completed}/${w.previous_week.lectures_planned}`} tone="neutral" sub={`delivered · ${w.previous_week.subtopics_remaining} subtopics left`} />
              </MetricStrip>
              <ProgressTab rows={rows} />
            </>
          )}

          {tab === 'carry' && <CarryForwardPanel items={w.carry_forward} week={w} editing={editing} onAdd={(c) => setDialog({ mode: 'add', carry: c })} onDecide={decide} />}
          {tab === 'history' && <HistoryTab />}

          {editing && !!w.conflicts?.length && tab !== 'history' && (
            <div className="mt-4 space-y-2">
              {w.conflicts.map((c, i) => (
                <InlineAlert key={i} tone={c.level === 'ERROR' ? 'danger' : 'warning'} title={`${CONFLICT_TITLE[c.kind] ?? 'Schedule conflict'} · ${fmt.weekday(c.date)} ${fmt.dateShort(c.date)}`}>
                  {c.message}{c.level === 'ERROR' && ' This draft cannot be published until it is resolved.'}
                </InlineAlert>
              ))}
            </div>
          )}
          {!editing && w.week.is_past && tab !== 'history' && <InlineAlert tone="info" className="mt-4">This week is over, so it can no longer be revised. Incomplete topics appear under Carry Forward and are placed first in the next sprint plan.</InlineAlert>}

          <LectureDialog state={dialog} week={w} onClose={() => setDialog(null)} onSaved={apply} />
          <ReviewDialog
            open={review}
            week={w}
            onClose={() => setReview(false)}
            onRemoved={(next) => apply(next)}
            onPublished={(r) => {
              setReview(false)
              setGeneration(null)
              toast('success', `Published v${r.revision.revision_number} for ${weekLabel(w.week)}. Professors now see the updated schedule.`)
              void week.reload()
            }}
          />
          <ConfirmDialog open={discard} onClose={() => setDiscard(false)} tone="danger" title="Discard this draft?" confirmLabel="Discard draft"
            onConfirm={async () => { await run(() => adminSprintApi.discard(w.draft!.id), 'Draft discarded. The published schedule was not changed.'); setGeneration(null); setDiscard(false) }}>
            {w.draft?.change_count ?? 0} unpublished change{w.draft?.change_count === 1 ? '' : 's'} will be thrown away. The published schedule stays as it is.
          </ConfirmDialog>
        </>
      )}
      <ConfirmDialog open={publishing} onClose={() => setPublishing(false)} title="Publish this week?" confirmLabel="Publish week" loading={busy}
        onConfirm={async () => { await run(() => adminSprintApi.publishWeek(weekStart), 'Week published. Professors, CL/CH and OM now see these classes.'); setGeneration(null); setPublishing(false) }}>
        {w?.unpublished ?? 0} class{w?.unpublished === 1 ? '' : 'es'} of {w ? weekLabel(w.week) : ''} become visible to their professors, with topic and subtopics.
      </ConfirmDialog>
      <ConfirmDialog open={make} onClose={() => setMake(false)} title="Make weekly sprint plan" confirmLabel="Make draft" loading={busy} onConfirm={makePlan}>
        <span className="block">Week of <b className="font-semibold text-fg">{weekLabel({ start: target, end: addDays(target, 5) })}</b>.</span>
        <span className="mt-2 block">Built from the semester sprint plan and what was actually taught: unfinished and not-conducted topics come first, the remaining topics move on in order. Holidays are left out.</span>
        <span className="mt-2 block text-fg-label">The result is a draft. If that week already has a draft, it is replaced. Nothing reaches professors until you publish.</span>
      </ConfirmDialog>
    </div>
  )
}
