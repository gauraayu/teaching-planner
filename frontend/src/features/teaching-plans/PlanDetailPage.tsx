import type { ColumnDef } from '@tanstack/react-table'
import { Archive, FileSpreadsheet, MoreHorizontal, Pencil, Send } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from '@/lib/router'
import { ActivityTimeline, BucketLegend, BUCKET_SEGMENTS, MetricDefinitions, UnitProgressTable } from '@/components/domain/Progress'
import { ErrorState, InlineAlert, PageLoading, useToast } from '@/components/feedback/States'
import { FormField, Input, Select, Textarea } from '@/components/forms/Fields'
import { PageHeader, useBreadcrumbs } from '@/components/layout/PageHeader'
import { DataTable } from '@/components/tables/DataTable'
import { StatusBadge, Tag } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { ConfirmDialog, Dialog } from '@/components/ui/Dialog'
import { Metric, MetricStrip, SegmentBar } from '@/components/ui/Display'
import { Menu } from '@/components/ui/Menu'
import { Tabs } from '@/components/ui/Tabs'
import { useApi } from '@/hooks/useApi'
import { BLOOM_LABEL, EXECUTION_STATUS, fmt, IMPORT_MODE_LABEL, IMPORT_STATUS, isoLocal, LECTURE_TYPE_LABEL, parseDate, PLAN_STATUS, SUBMISSION_STATUS, todayISO } from '@/lib/status'
import { api, errorMessage, type Paged } from '@/services/api'
import type { AuditEntry, Lecture, ManagedUser, Metrics, PlanBrief, UnitRow } from '@/types/domain'
import { PROFESSOR_OPTIONS, professorLabel, professorParams } from '@/lib/api/users'
import { startImport } from '@/features/imports/ImportsPage'
import type { ImportSessionView } from '@/features/imports/types'

type PlanDetail = PlanBrief & {
  metrics: Metrics
  units: UnitRow[]
  adherence: { delivered: number; early: number; on_day: number; late: number; average_delay_days: number; adherence_pct: number }
  definitions: Record<string, string>
  import_sessions: ImportSessionView[]
}

type Tab = 'overview' | 'lectures' | 'schedule' | 'progress' | 'verification' | 'activity'

export function lectureState(l: Lecture) {
  const today = todayISO()
  const ex = l.progress?.execution_status
  if (ex === 'COMPLETED') return { label: 'Completed', tone: 'success' as const }
  if (ex === 'PARTIALLY_COMPLETED') return { label: 'Partial', tone: 'warning' as const }
  if (l.planned_date && l.planned_date < today) return { label: 'Delayed', tone: 'danger' as const }
  if (ex === 'RESCHEDULED') return { label: 'Rescheduled', tone: 'info' as const }
  return { label: 'Scheduled', tone: 'neutral' as const }
}

export function PlanDetailPage() {
  const { planId } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const [params, setParams] = useSearchParams()
  const tab = (params.get('tab') as Tab) || 'overview'
  const plan = useApi<PlanDetail>(`/teaching-plans/${planId}`)
  const lectures = useApi<Paged<Lecture>>(`/teaching-plans/${planId}/lectures`)
  const activity = useApi<Paged<AuditEntry>>(tab === 'activity' || tab === 'overview' ? `/teaching-plans/${planId}/activity` : null)
  const [editing, setEditing] = useState<Lecture | null>(null)
  const [archiveOpen, setArchiveOpen] = useState(false)
  const [archiveReason, setArchiveReason] = useState('')
  const [publishOpen, setPublishOpen] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  useBreadcrumbs([{ label: 'Teaching Plans', to: '/admin/plans' }, { label: plan.data?.subject.short_name ?? plan.data?.subject.code ?? '…' }, { label: plan.data ? `${plan.data.semester.name} · Section ${plan.data.section.name}` : '…' }])

  const lectureColumns = useMemo<ColumnDef<Lecture>[]>(
    () => [
      { id: 'no', header: 'No.', accessorFn: (l) => l.lecture_no, meta: { className: 'tnum w-12 font-medium text-fg' } },
      { id: 'unit', header: 'Unit', accessorFn: (l) => l.unit_no ?? 0, cell: ({ getValue }) => <span className="tnum">{getValue<number>() || '—'}</span> },
      {
        id: 'topic',
        header: 'Topic',
        accessorFn: (l) => `${l.content_topic} ${l.subtopics.map((s) => s.title).join(' ')}`,
        cell: ({ row: { original: l } }) => (
          <div className="min-w-[260px] max-w-[460px]">
            <div className="font-medium text-fg">{l.content_topic}</div>
            {l.subtopics.length > 0 && <div className="meta mt-0.5 line-clamp-1">{l.subtopics.map((s) => s.title).join(' · ')}</div>}
          </div>
        ),
      },
      { id: 'type', header: 'Type', accessorFn: (l) => LECTURE_TYPE_LABEL[l.lecture_type] ?? l.lecture_type },
      { id: 'bloom', header: 'Bloom', accessorFn: (l) => l.blooms_taxonomy ?? '', cell: ({ getValue }) => (getValue<string>() ? <Tag title={BLOOM_LABEL[getValue<string>()]}>{getValue<string>()}</Tag> : '—') },
      { id: 'planned', header: 'Planned', accessorFn: (l) => l.planned_date ?? '', cell: ({ row: { original: l } }) => <div className="whitespace-nowrap">{fmt.date(l.planned_date)}<div className="meta">{fmt.timeRange(l.planned_start_time, l.planned_end_time)}</div></div> },
      {
        id: 'professor',
        header: 'Professor',
        accessorFn: (l) => l.professor?.full_name ?? '',
        cell: ({ row: { original: l } }) => (
          <div className="whitespace-nowrap">
            <span className="text-fg-soft">{l.professor?.full_name ?? '—'}</span>
            {l.is_substitute && <Tag className="ml-1.5 text-info" title="Allocated to a different professor than the rest of the plan">Reassigned</Tag>}
            {l.room && <div className="meta">Room {l.room}</div>}
          </div>
        ),
      },
      { id: 'actual', header: 'Actual', accessorFn: (l) => l.progress?.actual_completion_date ?? '', cell: ({ getValue }) => <span className="whitespace-nowrap">{fmt.date(getValue<string>() || null)}</span> },
      { id: 'state', header: 'Status', accessorFn: (l) => lectureState(l).label, cell: ({ row: { original: l } }) => { const s = lectureState(l); return <StatusBadge value={s.label} map={{ [s.label]: s }} /> } },
      { id: 'verification', header: 'Verification', accessorFn: (l) => l.progress?.submission_status ?? '', cell: ({ row: { original: l } }) => <StatusBadge value={l.progress?.submission_status} map={SUBMISSION_STATUS} /> },
      {
        id: 'actions',
        header: '',
        enableSorting: false,
        cell: ({ row: { original: l } }) => (
          <Menu
            label="Lecture actions"
            trigger={(t) => <Button size="icon" variant="ghost" aria-label={`Actions for lecture ${l.lecture_no}`} {...t}><MoreHorizontal className="h-4 w-4" /></Button>}
            items={[
              { label: 'Edit / assign professor', icon: <Pencil className="h-3.5 w-3.5" />, onSelect: () => setEditing(l) },
              { label: 'View execution record', onSelect: () => navigate(`/admin/lectures/${l.id}`) },
            ]}
          />
        ),
      },
    ],
    [navigate],
  )

  if (plan.loading && !plan.data) return <PageLoading />
  if (plan.error || !plan.data) return <ErrorState message={plan.error?.message ?? 'Plan not found'} onRetry={plan.reload} />
  const p = plan.data
  const m = p.metrics
  const draftLike = p.status === 'DRAFT' || p.status === 'READY'

  const changeStatus = async (status: 'PUBLISHED' | 'ARCHIVED', reason?: string) => {
    setActionError(null)
    try {
      await api.post(`/teaching-plans/${p.id}/status`, { status, reason })
      toast('success', status === 'PUBLISHED' ? 'Plan published. The professor can now see the lectures.' : 'Plan archived.')
      setPublishOpen(false)
      setArchiveOpen(false)
      void plan.reload()
    } catch (e) {
      setActionError(errorMessage(e))
    }
  }

  const items = lectures.data?.items ?? []
  const byState = (label: string) => items.filter((l) => lectureState(l).label === label)

  return (
    <div>
      <PageHeader
        title={p.subject.name}
        description={`${p.subject.code} · ${p.branch.name}`}
        meta={
          <>
            <StatusBadge value={p.status} map={PLAN_STATUS} />
            <span className="meta">{p.semester.name}</span>
            <span className="meta">· Section {p.section.name}</span>
            <span className="meta">· {p.professor.full_name}</span>
            <span className="meta">· {p.academic_year.name}</span>
          </>
        }
        actions={
          <>
            {draftLike && (
              <Button icon={<FileSpreadsheet className="h-4 w-4" />} onClick={async () => navigate(`/admin/imports/${await startImport(p.id)}`)}>
                {m.total ? 'Re-import lectures' : 'Import lectures'}
              </Button>
            )}
            {p.status === 'READY' && (
              <Button variant="primary" icon={<Send className="h-4 w-4" />} onClick={() => setPublishOpen(true)}>
                Publish
              </Button>
            )}
            {p.status !== 'ARCHIVED' && (
              <Menu
                label="More plan actions"
                trigger={(t) => <Button size="icon" aria-label="More actions" {...t}><MoreHorizontal className="h-4 w-4" /></Button>}
                items={[{ label: 'Archive plan', icon: <Archive className="h-3.5 w-3.5" />, danger: true, onSelect: () => setArchiveOpen(true) }]}
              />
            )}
          </>
        }
      />
      {actionError && <InlineAlert tone="danger" className="mb-4">{actionError}</InlineAlert>}
      {p.status === 'DRAFT' && m.total === 0 && (
        <InlineAlert tone="info" className="mb-4" title="This plan has no lectures yet" action={<Button size="sm" variant="primary" onClick={async () => navigate(`/admin/imports/${await startImport(p.id)}`)}>Import lectures</Button>}>
          Import the semester plan from a spreadsheet to publish it to {p.professor.full_name}.
        </InlineAlert>
      )}

      <MetricStrip className="mb-5">
        <Metric label="Lectures" value={m.total} />
        <Metric label="Completed" value={m.completed} sub={`${m.execution_pct}% execution`} tone="success" />
        <Metric label="Pending" value={m.pending} />
        <Metric label="Delayed" value={m.delayed} tone={m.delayed ? 'danger' : undefined} />
        <Metric label="Partial" value={m.partial} tone={m.partial ? 'warning' : undefined} />
        <Metric label="Final verified" value={m.verified} sub={`${m.verified_pct}% of plan`} />
      </MetricStrip>

      <Tabs
        className="mb-5"
        value={tab}
        onChange={(t) => setParams({ tab: t }, { replace: true })}
        items={[
          { value: 'overview', label: 'Overview' },
          { value: 'lectures', label: 'Lectures', count: items.length },
          { value: 'schedule', label: 'Schedule' },
          { value: 'progress', label: 'Progress' },
          { value: 'verification', label: 'Verification', count: m.awaiting_verification },
          { value: 'activity', label: 'Activity' },
        ]}
      />

      {tab === 'overview' && (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_380px]">
          <div className="space-y-5">
            <div className="panel">
              <div className="panel-header"><span className="panel-title">Delivery progress</span><span className="meta tnum">{m.completed} of {m.total} completed</span></div>
              <div className="space-y-3 p-4">
                <SegmentBar segments={BUCKET_SEGMENTS(m)} className="h-2.5" />
                <BucketLegend m={m} />
                <MetricDefinitions definitions={p.definitions} />
              </div>
            </div>
            <div className="panel">
              <div className="panel-header"><span className="panel-title">Progress by unit</span></div>
              <UnitProgressTable units={p.units} />
            </div>
          </div>
          <div className="space-y-5">
            <div className="panel">
              <div className="panel-header"><span className="panel-title">Schedule adherence</span></div>
              <dl className="grid grid-cols-2 gap-3 p-4 text-[13px]">
                <div><dt className="meta">Delivered</dt><dd className="tnum text-lg font-semibold">{p.adherence.delivered}</dd></div>
                <div><dt className="meta">On or before plan</dt><dd className="tnum text-lg font-semibold text-primary">{p.adherence.adherence_pct}%</dd></div>
                <div><dt className="meta">Delivered late</dt><dd className="tnum text-lg font-semibold">{p.adherence.late}</dd></div>
                <div><dt className="meta">Average delay</dt><dd className="tnum text-lg font-semibold">{p.adherence.average_delay_days} d</dd></div>
              </dl>
            </div>
            <div className="panel">
              <div className="panel-header"><span className="panel-title">Imports</span></div>
              <ul className="divide-y divide-line-subtle">
                {p.import_sessions.length === 0 && <li className="meta px-4 py-4">No imports yet.</li>}
                {p.import_sessions.map((s) => (
                  <li key={s.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-[13px]">
                    <div>
                      <div className="text-fg">{s.import_mode ? IMPORT_MODE_LABEL[s.import_mode] : 'Method not chosen'}</div>
                      <div className="meta">{fmt.dateTime(s.committed_at ?? s.updated_at)}{s.summary ? ` · ${s.summary.lectures} lectures` : ''}</div>
                    </div>
                    <StatusBadge value={s.status} map={IMPORT_STATUS} />
                  </li>
                ))}
              </ul>
            </div>
            <div className="panel">
              <div className="panel-header"><span className="panel-title">Recent activity</span><Button variant="link" onClick={() => setParams({ tab: 'activity' })}>View all</Button></div>
              <ActivityTimeline items={(activity.data?.items ?? []).slice(0, 6)} />
            </div>
          </div>
        </div>
      )}

      {tab === 'lectures' && (
        <div className="panel">
          <DataTable columns={lectureColumns} data={items} loading={lectures.loading} error={lectures.error?.message} onRetry={lectures.reload} pageSize={50} searchPlaceholder="Search topics and subtopics…" columnToggle />
        </div>
      )}

      {tab === 'schedule' && <ScheduleAgenda lectures={items} />}

      {tab === 'progress' && (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          {(['Delayed', 'Partial', 'Scheduled', 'Completed'] as const).map((label) => (
            <div key={label} className="panel">
              <div className="panel-header"><span className="panel-title">{label}</span><span className="meta tnum">{byState(label).length}</span></div>
              <ul className="max-h-80 divide-y divide-line-subtle overflow-y-auto scroll-thin">
                {byState(label).length === 0 && <li className="meta px-4 py-4">None.</li>}
                {byState(label).map((l) => (
                  <li key={l.id} className="flex items-center gap-3 px-4 py-2 text-[13px]">
                    <span className="tnum w-8 text-fg-muted">L{l.lecture_no}</span>
                    <span className="min-w-0 flex-1 truncate text-fg">{l.content_topic}</span>
                    <span className="meta whitespace-nowrap">{fmt.dateShort(l.planned_date)}{l.progress?.actual_completion_date && l.progress.actual_completion_date !== l.planned_date ? ` → ${fmt.dateShort(l.progress.actual_completion_date)}` : ''}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      {tab === 'verification' && (
        <div className="panel">
          <DataTable
            columns={[
              lectureColumns[0], lectureColumns[2], lectureColumns[6],
              { id: 'exec', header: 'Execution', accessorFn: (l: Lecture) => l.progress?.execution_status ?? '', cell: ({ row: { original: l } }) => <StatusBadge value={l.progress?.execution_status} map={EXECUTION_STATUS} /> },
              lectureColumns[8],
              { id: 'submitted', header: 'Submitted', accessorFn: (l: Lecture) => l.progress?.submitted_at ?? '', cell: ({ getValue }) => <span className="meta whitespace-nowrap">{fmt.dateTime(getValue<string>() || null)}</span> },
            ]}
            data={items.filter((l) => l.progress)}
            searchPlaceholder="Search lectures…"
          />
        </div>
      )}

      {tab === 'activity' && (
        <div className="panel">
          <ActivityTimeline items={activity.data?.items ?? []} />
        </div>
      )}

      {editing && <CorrectLectureDialog lecture={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); void lectures.reload(true); toast('success', `Lecture ${editing.lecture_no} updated and logged.`) }} />}
      <ConfirmDialog open={publishOpen} onClose={() => setPublishOpen(false)} title="Publish teaching plan?" confirmLabel="Publish" onConfirm={() => changeStatus('PUBLISHED')}>
        {m.total} lectures become visible to {p.professor.full_name}. After publishing, master data can only be changed through audited corrections.
      </ConfirmDialog>
      <Dialog
        open={archiveOpen}
        onClose={() => setArchiveOpen(false)}
        title="Archive teaching plan"
        size="sm"
        footer={<><Button onClick={() => setArchiveOpen(false)}>Cancel</Button><Button variant="danger" disabled={archiveReason.trim().length < 5} onClick={() => changeStatus('ARCHIVED', archiveReason)}>Archive plan</Button></>}
      >
        <p className="mb-3 text-[13px] text-fg-secondary">Archived plans leave every task list and report. Their history is kept.</p>
        <FormField label="Reason" required>
          <Textarea value={archiveReason} onChange={(e) => setArchiveReason(e.target.value)} rows={3} />
        </FormField>
      </Dialog>
    </div>
  )
}

function ScheduleAgenda({ lectures }: { lectures: Lecture[] }) {
  const today = todayISO()
  const weeks = useMemo(() => {
    const map = new Map<string, Lecture[]>()
    for (const l of lectures.filter((x) => x.planned_date).sort((a, b) => a.planned_date!.localeCompare(b.planned_date!))) {
      const d = parseDate(l.planned_date!)
      d.setDate(d.getDate() - ((d.getDay() + 6) % 7))
      const key = isoLocal(d)
      map.set(key, [...(map.get(key) ?? []), l])
    }
    return [...map.entries()]
  }, [lectures])
  return (
    <div className="space-y-4">
      {weeks.map(([week, ls]) => (
        <div key={week} className="panel">
          <div className="panel-header"><span className="panel-title">Week of {fmt.date(week)}</span><span className="meta">{ls.length} lectures</span></div>
          <ul className="divide-y divide-line-subtle">
            {ls.map((l) => {
              const s = lectureState(l)
              return (
                <li key={l.id} className={`flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2.5 text-[13px] ${l.planned_date === today ? 'bg-primary/5' : ''}`}>
                  <span className="w-24 shrink-0 text-fg-secondary">{fmt.weekday(l.planned_date)} {fmt.dateShort(l.planned_date)}</span>
                  <span className="meta w-32 shrink-0">{fmt.timeRange(l.planned_start_time, l.planned_end_time)}</span>
                  <span className="tnum w-10 shrink-0 text-fg-muted">L{l.lecture_no}</span>
                  <span className="min-w-0 flex-1 truncate text-fg">{l.content_topic}</span>
                  <StatusBadge value={s.label} map={{ [s.label]: s }} />
                </li>
              )
            })}
          </ul>
        </div>
      ))}
    </div>
  )
}

function CorrectLectureDialog({ lecture, onClose, onSaved }: { lecture: Lecture; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({
    content_topic: lecture.content_topic,
    unit_no: String(lecture.unit_no ?? ''),
    blooms_taxonomy: lecture.blooms_taxonomy ?? '',
    lecture_type: lecture.lecture_type,
    planned_date: lecture.planned_date ?? '',
    planned_start_time: lecture.planned_start_time ?? '',
    planned_end_time: lecture.planned_end_time ?? '',
    subtopics: lecture.subtopics.map((s) => s.title).join('\n'),
    professor_id: lecture.professor?.id ?? '',
    room: lecture.room ?? '',
    reason: '',
  })
  // Real, active professor accounts - never a typed name.
  const professors = useApi<Paged<ManagedUser>>(PROFESSOR_OPTIONS, professorParams())
  const started = !!lecture.progress && lecture.progress.submission_status !== 'DRAFT'
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const save = async () => {
    setBusy(true)
    setError(null)
    const body: Record<string, unknown> = { reason: form.reason }
    if (form.content_topic !== lecture.content_topic) body.content_topic = form.content_topic
    if (form.unit_no !== String(lecture.unit_no ?? '')) body.unit_no = form.unit_no ? Number(form.unit_no) : null
    if (form.blooms_taxonomy !== (lecture.blooms_taxonomy ?? '')) body.blooms_taxonomy = form.blooms_taxonomy || null
    if (form.lecture_type !== lecture.lecture_type) body.lecture_type = form.lecture_type
    if (form.planned_date !== (lecture.planned_date ?? '')) body.planned_date = form.planned_date || null
    if (form.planned_start_time !== (lecture.planned_start_time ?? '')) body.planned_start_time = form.planned_start_time || null
    if (form.planned_end_time !== (lecture.planned_end_time ?? '')) body.planned_end_time = form.planned_end_time || null
    if (form.professor_id && form.professor_id !== (lecture.professor?.id ?? '')) body.professor_id = form.professor_id
    if (form.room.trim() !== (lecture.room ?? '')) body.room = form.room.trim() || null
    const subs = form.subtopics.split('\n').map((s) => s.trim()).filter(Boolean)
    if (subs.join('\n') !== lecture.subtopics.map((s) => s.title).join('\n')) body.subtopics = subs
    try {
      await api.patch(`/lectures/${lecture.id}`, body)
      onSaved()
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={`Lecture ${lecture.lecture_no} · plan and allocation`}
      description="Every change is logged with your reason and the before/after values, and the professors concerned are notified."
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} disabled={form.reason.trim().length < 5} onClick={save}>Save correction</Button></>}
    >
      {error && <InlineAlert tone="danger" className="mb-4">{error}</InlineAlert>}
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField label="Content topic" className="sm:col-span-2"><Input value={form.content_topic} onChange={set('content_topic')} /></FormField>
        <FormField label="Unit"><Input type="number" min={1} value={form.unit_no} onChange={set('unit_no')} /></FormField>
        <FormField label="Bloom's level">
          <Select value={form.blooms_taxonomy} onChange={set('blooms_taxonomy')}>
            <option value="">Not set</option>
            {Object.entries(BLOOM_LABEL).map(([k, v]) => <option key={k} value={k}>{k} · {v}</option>)}
          </Select>
        </FormField>
        <FormField label="Lecture type">
          <Select value={form.lecture_type} onChange={set('lecture_type')}>
            {Object.entries(LECTURE_TYPE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
        </FormField>
        <FormField label="Planned date"><Input type="date" value={form.planned_date} onChange={set('planned_date')} /></FormField>
        <FormField label="Start time"><Input type="time" value={form.planned_start_time} onChange={set('planned_start_time')} /></FormField>
        <FormField label="End time"><Input type="time" value={form.planned_end_time} onChange={set('planned_end_time')} /></FormField>
        <FormField label="Assigned professor" hint={started ? 'Already submitted by the professor, so it can no longer be reassigned.' : 'The lecture appears only on this professor\'s dashboard. A clash with another class is refused.'}>
          <Select value={form.professor_id} onChange={set('professor_id')} disabled={started}>
            {professors.data?.items.map((p) => <option key={p.id} value={p.id}>{professorLabel(p)}</option>)}
            {lecture.professor && !professors.data?.items.some((p) => p.id === lecture.professor?.id) && <option value={lecture.professor.id}>{lecture.professor.full_name}{professors.data ? ' (inactive)' : ''}</option>}
          </Select>
        </FormField>
        <FormField label="Room"><Input value={form.room} onChange={set('room')} maxLength={40} placeholder="C-204" /></FormField>
        <FormField label="Subtopics" hint="One per line. Renaming keeps the professor's coverage ticks." className="sm:col-span-2"><Textarea rows={4} value={form.subtopics} onChange={set('subtopics')} /></FormField>
        <FormField label="Reason for correction" required className="sm:col-span-2"><Textarea rows={2} value={form.reason} onChange={set('reason')} placeholder="e.g. Syllabus revision approved by the Board of Studies" /></FormField>
      </div>
    </Dialog>
  )
}

