import { Check, Clock, ExternalLink, Image as ImageIcon, Lock, MapPin, Sheet, TriangleAlert } from 'lucide-react'
import { Fragment, useState, type ReactNode } from 'react'
import { subjectColor, TimetableGrid, TimetableLegend, type GridItem } from '@/components/domain/TimetableGrid'
import { EmptyState, ErrorState, LoadingRows } from '@/components/feedback/States'
import { Segmented } from '@/components/forms/Fields'
import { PageHeader, useBreadcrumbs } from '@/components/layout/PageHeader'
import { FilterSelect, useAcademicOptions } from '@/components/tables/FilterBar'
import { Badge, StatusBadge, Tag } from '@/components/ui/Badge'
import { ButtonLink } from '@/components/ui/Button'
import { Metric, MetricStrip } from '@/components/ui/Display'
import { WeekNav } from '@/features/sprint/components/WeekNav'
import { useApi } from '@/hooks/useApi'
import { mondayOf } from '@/lib/api/sprint'
import { templateOf, type TimingTemplate } from '@/lib/api/timetable'
import { useNavigate, useSearchParams } from '@/lib/router'
import { EXECUTION_STATUS, fmt, todayISO, VERIFICATION_STATUS } from '@/lib/status'
import type { Paged } from '@/services/api'
import type { SprintRow, SprintWeekInfo, TimingStatus, UserBrief, UserScope, VerificationStatus } from '@/types/domain'
import { cn } from '@/utils/cn'

type Step = { status: VerificationStatus | null; remarks: string | null; by: string | null; at: string | null }
export type SheetRow = SprintRow & {
  blooms_taxonomy: string | null
  covered_topics: string[]
  remaining_topics: string[]
  notes: { title: string | null; url: string }[]
  assignment: { title: string; url: string | null } | null
  evidence_count: number
  shared_with_students: boolean | null
  professor_remarks: string | null
  recording_url?: string | null
  additional_topics?: string | null
  submitted_at: string | null
  clch: Step
  om: Step & { entry_time: string | null; exit_time: string | null; timing_status: TimingStatus | null; delay_minutes: number | null; state: string }
  final_status: 'FINAL_VERIFIED' | 'CORRECTION_REQUIRED' | 'PENDING'
  waiting_for: string | null
  my_verification_id: string | null
  latest_verification_id: string | null
}
type Sheet = {
  week: SprintWeekInfo
  today: string
  version: number
  scope: UserScope
  role: string
  summary: { total: number; submitted: number; clch_pending: number; clch_verified: number; om_pending: number; final_verified: number; correction_required: number }
  rows: SheetRow[]
  days: { date: string; lectures: SheetRow[] }[]
}

type Variant = 'verification' | 'om' | 'admin'
const COPY: Record<Variant, { crumbs: [string, string]; title: string; description: string }> = {
  verification: { crumbs: ['Verification', 'Sprint Plan'], title: 'Sprint Plan', description: 'The published weekly plan for every professor inside your scope, with what was taught and where each record stands.' },
  om: { crumbs: ['Live operations', 'Sprint Plan'], title: 'Sprint Plan', description: 'The published weekly plan for the classes inside your scope, with entry and exit timings and verification status.' },
  admin: { crumbs: ['Monitoring', 'Workflow Monitor'], title: 'Workflow Monitor', description: 'Every published lecture of the week: Professor → CL/CH → OM. Monitoring only - verification is done by CL/CH and OM.' },
}

const FINAL = {
  FINAL_VERIFIED: { label: 'Final verified', tone: 'success' as const },
  CORRECTION_REQUIRED: { label: 'Correction required', tone: 'danger' as const },
  PENDING: { label: 'Pending', tone: 'neutral' as const },
}

type Preset = 'all' | 'academic' | 'schedule' | 'execution' | 'verification' | 'operations'
const PRESETS: { value: Preset; label: string }[] = [
  { value: 'all', label: 'All' }, { value: 'academic', label: 'Academic' }, { value: 'schedule', label: 'Schedule' },
  { value: 'execution', label: 'Execution' }, { value: 'verification', label: 'Verification' }, { value: 'operations', label: 'Operations' },
]

const th = 'th border-b border-line bg-surface-2 px-3 py-2 text-left whitespace-nowrap'
const td = 'border-b border-line-subtle px-3 py-2.5 align-top text-[13px]'

function StepCell({ step, pendingLabel = 'Pending' }: { step: Step; pendingLabel?: string }) {
  if (!step.status) return <span className="text-fg-faint">—</span>
  return (
    <div className="whitespace-nowrap">
      {step.status === 'PENDING' ? <Badge tone="warning">{pendingLabel}</Badge> : <StatusBadge value={step.status} map={VERIFICATION_STATUS} />}
      {step.by && <div className="meta mt-0.5">{step.by}{step.at ? ` · ${fmt.dateShort(step.at.slice(0, 10))}` : ''}</div>}
    </div>
  )
}

/** Professor · CL/CH · OM at a glance. Lives in the pinned right column so the state is visible without scrolling. */
function Chain({ r }: { r: SheetRow }) {
  const submitted = !!r.submission_status && r.submission_status !== 'DRAFT'
  const mark = (s: VerificationStatus | 'DONE' | null) =>
    s === 'DONE' || s === 'VERIFIED' ? <Check className="h-3 w-3 text-primary" strokeWidth={3} aria-label="done" />
      : s === 'PENDING' ? <Clock className="h-3 w-3 text-warning" aria-label="pending" />
        : s === 'CORRECTION_REQUIRED' ? <TriangleAlert className="h-3 w-3 text-danger" aria-label="correction required" />
          : <span className="text-fg-faint" aria-label="not reached">–</span>
  return (
    <div className="flex items-center gap-2 text-[11.5px] whitespace-nowrap text-fg-secondary">
      <span className="inline-flex items-center gap-1">Prof {mark(submitted ? 'DONE' : null)}</span>
      <span className="inline-flex items-center gap-1">CL/CH {mark(r.clch.status)}</span>
      <span className="inline-flex items-center gap-1">OM {mark(r.om.status)}</span>
    </div>
  )
}

function Clip({ children, title, w = 'max-w-[220px]' }: { children: ReactNode; title?: string; w?: string }) {
  return <div className={cn('line-clamp-2 min-w-[120px]', w)} title={title}>{children}</div>
}

/**
 * One week of the published Sprint Plan as a single sheet - the same rows the admin plans and the professor
 * teaches, shown to CL/CH, OM and Admin. Planning columns are locked here; nothing on this page edits data.
 */
export function SprintSheetPage({ variant }: { variant: Variant }) {
  const copy = COPY[variant]
  useBreadcrumbs([{ label: copy.crumbs[0] }, { label: copy.crumbs[1] }])
  const [params, setParams] = useSearchParams()
  const weekStart = mondayOf(params.get('week') || todayISO())
  const go = (monday: string) => setParams(monday === mondayOf(todayISO()) ? {} : { week: monday }, { replace: true })
  const opts = useAcademicOptions()
  const professors = useApi<Paged<UserBrief>>('/users', { role: 'PROFESSOR' })
  const [professor, setProfessor] = useState('')
  const [subject, setSubject] = useState('')
  const [preset, setPreset] = useState<Preset>('all')
  const [mode, setMode] = useState<'timetable' | 'table'>(variant === 'om' ? 'timetable' : 'table')
  const [gridView, setGridView] = useState('combined')
  const navigate = useNavigate()
  const templates = useApi<Paged<TimingTemplate>>('/timing-templates').data?.items.filter((t) => t.is_active) ?? []
  const sheet = useApi<Sheet>('/sprint-plan/sheet', { week_start: weekStart, professor_id: professor, subject_id: subject })
  const s = sheet.data
  const m = s?.summary

  const link = (r: SheetRow): { to: string; label: string; primary: boolean } | null => {
    if (variant === 'admin') return r.lecture_id ? { to: `/admin/lectures/${r.lecture_id}`, label: 'Open', primary: false } : null
    const base = variant === 'om' ? '/om/review' : '/verification/review'
    if (r.my_verification_id) return { to: `${base}/${r.my_verification_id}`, label: variant === 'om' ? 'Final Verify' : 'Review', primary: true }
    if (r.latest_verification_id) return { to: `${base}/${r.latest_verification_id}`, label: 'Open', primary: false }
    return null
  }

  return (
    <div>
      <PageHeader
        title={copy.title}
        description={copy.description}
        meta={<>
          {s && variant !== 'admin' && <Tag title="Set by the administrator in User Management">Scope: {s.scope.label}</Tag>}
          {s && <Tag>Sprint v{s.version}</Tag>}
          <span className="inline-flex items-center gap-1 text-[12px] text-fg-label"><Lock className="h-3.5 w-3.5" aria-hidden />Read-only · planned by Admin, recorded by the professor</span>
        </>}
      />
      <MetricStrip className="mb-4">
        <Metric label="Lectures this week" value={m?.total ?? '–'} tone="neutral" />
        <Metric label="Submitted" value={m?.submitted ?? '–'} tone="neutral" sub="By professors" />
        <Metric label="CL/CH pending" value={m?.clch_pending ?? '–'} tone={m?.clch_pending ? 'warning' : 'neutral'} />
        <Metric label="OM pending" value={m?.om_pending ?? '–'} tone={m?.om_pending ? 'warning' : 'neutral'} sub="CL/CH verified" />
        <Metric label="Correction required" value={m?.correction_required ?? '–'} tone={m?.correction_required ? 'danger' : 'neutral'} />
        <Metric label="Final verified" value={m?.final_verified ?? '–'} tone="success" />
      </MetricStrip>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <WeekNav week={s?.week} weekStart={weekStart} onChange={go} />
        <div className="flex flex-wrap items-end gap-3">
          <FilterSelect label="Professor" value={professor} onChange={setProfessor} allLabel="All professors" options={professors.data?.items.map((p) => ({ value: p.id, label: p.full_name })) ?? []} />
          <FilterSelect label="Subject" value={subject} onChange={setSubject} allLabel="All subjects" options={opts.subjects} width="w-52" />
        </div>
      </div>

      <div className="mb-3"><Segmented ariaLabel="View" size="sm" value={mode} onChange={setMode} options={[{ value: 'timetable', label: 'Timetable view' }, { value: 'table', label: 'Table view' }]} /></div>
      {mode === 'timetable' && s && s.rows.length > 0 && (
        <div className="panel mb-4">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
            <Segmented ariaLabel="Timetable view" size="sm" value={gridView} onChange={setGridView} options={[{ value: 'combined', label: 'Combined' }, ...templates.map((t) => ({ value: t.code, label: t.name }))]} />
            <TimetableLegend extra={[{ label: 'Carry-forward', tone: 'carry' }]} />
          </div>
          <TimetableGrid templates={templates} view={gridView}
            days={s.days.map((d) => ({ label: fmt.weekday(d.date), sub: fmt.dateShort(d.date), today: d.date === s.today }))}
            items={s.days.flatMap((d, di) => d.lectures.filter((r) => r.start && r.end).map((r) => {
              const a = link(r)
              return {
                key: r.lecture_id!, day: di, start: r.start!, end: r.end!, template: templateOf(templates, r.semester_number),
                title: `${r.subject.short_name ?? r.subject.code}${r.lecture_no ? ` · L${r.lecture_no}` : ''}`,
                subtitle: r.topic,
                meta: `${r.professor.full_name.replace(/^(Dr\.|Prof\.)\s*/i, '')}\n${r.semester.replace('Semester ', '')}-${r.section} · ${r.room ?? 'No room'}${r.om.entry_time ? ` · in ${r.om.entry_time}` : ''}`,
                accent: subjectColor(r.subject.code),
                tone: r.origin === 'CARRY_FORWARD' ? 'carry' : r.lecture_type === 'PRACTICAL' ? 'lab' : 'neutral',
                corner: r.final_status === 'FINAL_VERIFIED' ? <Check className="h-3 w-3 shrink-0 text-primary" strokeWidth={3} aria-label="Final verified" /> : r.my_verification_id ? <Clock className="h-3 w-3 shrink-0 text-warning" aria-label="Waiting for you" /> : undefined,
                onClick: a ? () => navigate(a.to) : undefined,
              } satisfies GridItem
            }))} />
        </div>
      )}
      <div className={cn('panel overflow-hidden', mode === 'timetable' && s && s.rows.length > 0 && 'hidden')}>
        {sheet.error ? <ErrorState message={sheet.error.message} onRetry={sheet.reload} />
          : sheet.loading && !s ? <LoadingRows rows={8} />
          : !s?.rows.length ? (
            <EmptyState icon={<Sheet className="h-5 w-5" />} title="No published lectures in this week"
              description={variant === 'admin' ? 'Publish this week in the Weekly Sprint Plan, or move to another week.' : 'Nothing inside your scope is scheduled in this week. Try another week, or ask the administrator to check your scope.'} />
          ) : (
            <>
            {/* Phones and tablets: one card per lecture. The full sheet needs width, so it starts at the lg breakpoint. */}
            <div className="divide-y divide-line lg:hidden">
              {s.days.filter((d) => d.lectures.length).map((day) => (
                <section key={day.date} aria-label={fmt.date(day.date)}>
                  <h2 className={cn('px-4 py-1.5 text-[11.5px] font-semibold tracking-wide uppercase', day.date === s.today ? 'bg-primary-soft text-primary' : 'bg-surface-2 text-fg-secondary')}>
                    {fmt.weekday(day.date)}, {fmt.date(day.date)}{day.date === s.today && ' · Today'}
                  </h2>
                  <ul className="divide-y divide-line-subtle">
                    {day.lectures.map((r) => {
                      const a = link(r)
                      return (
                        <li key={r.lecture_id} className="px-4 py-3.5">
                          <div className="flex items-start justify-between gap-3">
                            <div className="text-[12px] font-semibold tracking-wide text-primary uppercase">{r.subject.short_name ?? r.subject.code} <span className="font-normal text-fg-muted normal-case">· {r.semester.replace('Semester', 'Sem')}-{r.section} · Lecture {r.lecture_no}</span></div>
                            <StatusBadge value={r.execution_status} map={EXECUTION_STATUS} />
                          </div>
                          <h3 className="mt-1 text-[14.5px] leading-snug font-semibold text-fg">{r.topic}</h3>
                          <p className="meta mt-0.5">{r.professor.full_name}</p>
                          <p className="tnum mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[13px] text-fg-secondary">
                            <span>{fmt.timeRange(r.start, r.end) || 'Time not set'}</span>
                            <span className="inline-flex items-center gap-1"><MapPin className="h-3.5 w-3.5 text-fg-muted" aria-hidden />{r.room ?? 'Room not set'}</span>
                            {r.subtopics.length > 0 && <span>{r.covered_topics.length}/{r.subtopics.length} topics covered</span>}
                          </p>
                          {(r.om.entry_time || r.clch.remarks) && (
                            <p className="mt-1.5 text-[12.5px] text-fg-secondary">
                              {r.om.entry_time && <span className="tnum">OM entry {fmt.clock(r.om.entry_time)}{r.om.exit_time ? ` · exit ${fmt.clock(r.om.exit_time)}` : ''}</span>}
                              {r.clch.remarks && <span className="block">CL/CH: “{r.clch.remarks}”</span>}
                            </p>
                          )}
                          <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2">
                            <div>
                              <Chain r={r} />
                              {r.final_status === 'FINAL_VERIFIED' ? <div className="mt-0.5 text-[12px] font-semibold text-primary">Final verified</div> : r.waiting_for && <div className="meta mt-0.5">{r.waiting_for}</div>}
                            </div>
                            {a && <ButtonLink to={a.to} variant={a.primary ? 'primary' : 'secondary'} className="h-10 px-4">{a.label}</ButtonLink>}
                          </div>
                        </li>
                      )
                    })}
                  </ul>
                </section>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-2.5 max-lg:hidden">
              <span className="th text-[10.5px]">Columns</span>
              <Segmented ariaLabel="Column preset" size="sm" value={preset} onChange={setPreset} options={PRESETS} />
            </div>
            <div className="overflow-x-auto scroll-thin max-lg:hidden lg:block" tabIndex={0} role="region" aria-label="Sprint plan sheet">
              <table data-preset={preset} className={cn('sheet w-full border-separate border-spacing-0', preset === 'all' && 'min-w-[1880px]')}>
                <caption className="sr-only">Sprint plan for the week of {fmt.date(weekStart)}</caption>
                <thead>
                  <tr className={cn('text-[10.5px] font-semibold tracking-[0.1em] uppercase', preset !== 'all' && 'hidden')}>
                    <th colSpan={8} scope="colgroup" className="border-b border-line bg-surface-3 px-3 py-1.5 text-left text-fg-label">Plan · Admin</th>
                    <th colSpan={6} scope="colgroup" className="border-b border-l border-line bg-surface-3 px-3 py-1.5 text-left text-info">Execution · Professor</th>
                    <th colSpan={2} scope="colgroup" className="border-b border-l border-line bg-surface-3 px-3 py-1.5 text-left text-primary">CL/CH</th>
                    <th colSpan={3} scope="colgroup" className="border-b border-l border-line bg-surface-3 px-3 py-1.5 text-left text-warning">OM</th>
                    <th colSpan={2} scope="colgroup" className="border-b border-l border-line bg-surface-3 px-3 py-1.5 text-left text-fg-label">Final</th>
                  </tr>
                  <tr>
                    <th scope="col" data-p="id" className={cn(th, 'sticky left-0 z-[2]')}>Lec</th>
                    <th scope="col" data-p="id" className={th}>Subject</th>
                    <th scope="col" data-p="id" className={th}>Professor</th>
                    <th scope="col" data-p="academic" className={th}>Unit</th>
                    <th scope="col" data-p="academic execution" className={th}>Topic · Subtopics</th>
                    <th scope="col" data-p="academic" className={th}>Bloom</th>
                    <th scope="col" data-p="schedule operations" className={th}>Scheduled time</th>
                    <th scope="col" data-p="schedule operations" className={th}>Room</th>
                    <th scope="col" data-p="execution" className={cn(th, 'border-l')}>Teaching status</th>
                    <th scope="col" data-p="execution" className={th}>Topics covered</th>
                    <th scope="col" data-p="execution" className={th}>Notes</th>
                    <th scope="col" data-p="execution" className={th}>Assignment</th>
                    <th scope="col" data-p="execution" className={th}>Evidence</th>
                    <th scope="col" data-p="execution" className={th}>Professor remarks</th>
                    <th scope="col" data-p="verification" className={cn(th, 'border-l')}>CL/CH verification</th>
                    <th scope="col" data-p="verification" className={th}>CL/CH remarks</th>
                    <th scope="col" data-p="operations" className={cn(th, 'border-l')}>OM entry</th>
                    <th scope="col" data-p="operations" className={th}>OM exit</th>
                    <th scope="col" data-p="operations verification" className={th}>OM status</th>
                    <th scope="col" data-p="verification" className={cn(th, 'border-l')}>Final status</th>
                    <th scope="col" data-p="id" className={cn(th, 'sticky right-0 z-[2] border-l text-right')}>Pipeline</th>
                  </tr>
                </thead>
                <tbody>
                  {s.days.filter((d) => d.lectures.length).map((day) => (
                    <Fragment key={day.date}>
                      <tr>
                        <th colSpan={21} scope="rowgroup" className={cn('border-b border-line px-3 py-1.5 text-left text-[11.5px] font-semibold tracking-wide uppercase', day.date === s.today ? 'bg-primary-soft text-primary' : 'bg-surface text-fg-secondary')}>
                          <span className="sticky left-3">{fmt.weekday(day.date)}, {fmt.date(day.date)}{day.date === s.today && ' · Today'} <span className="font-normal text-fg-muted normal-case">· {day.lectures.length} lecture{day.lectures.length === 1 ? '' : 's'}</span></span>
                        </th>
                      </tr>
                      {day.lectures.map((r) => {
                        const a = link(r)
                        const final = FINAL[r.final_status]
                        return (
                          <tr key={r.lecture_id} className="group hover:bg-primary/[0.03]">
                            <td data-p="id" className={cn(td, 'tnum sticky left-0 z-[1] bg-surface font-semibold text-fg group-hover:bg-surface-2')}>{r.lecture_no}</td>
                            <td data-p="id" className={cn(td, 'whitespace-nowrap')}>
                              <div className="font-medium text-fg">{r.subject.short_name ?? r.subject.code}</div>
                              <div className="meta">{r.semester.replace('Semester', 'Sem')}-{r.section}</div>
                            </td>
                            <td data-p="id" className={cn(td, 'whitespace-nowrap text-fg-soft')}>{r.professor.full_name}</td>
                            <td data-p="academic" className={cn(td, 'tnum')}>{r.unit_no ?? '—'}</td>
                            <td data-p="academic execution" className={td}>
                              <div className="max-w-[280px] min-w-[200px]">
                                <div className="text-fg">{r.topic}{r.origin === 'CARRY_FORWARD' && <Tag className="ml-1.5 text-info">Carry-forward</Tag>}</div>
                                {r.subtopics.length > 0 && <div className="meta mt-0.5 line-clamp-2" title={r.subtopics.join(' · ')}>{r.subtopics.join(' · ')}</div>}
                              </div>
                            </td>
                            <td data-p="academic" className={td}>{r.blooms_taxonomy ?? '—'}</td>
                            <td data-p="schedule operations" className={cn(td, 'tnum whitespace-nowrap')}>{fmt.timeRange(r.start, r.end) || '—'}</td>
                            <td data-p="schedule operations" className={cn(td, 'whitespace-nowrap')}>{r.room ?? '—'}</td>

                            <td data-p="execution" className={cn(td, 'border-l border-l-line-subtle whitespace-nowrap')}>
                              <StatusBadge value={r.execution_status} map={EXECUTION_STATUS} />
                              {r.started_at && <div className="meta tnum mt-0.5">{fmt.clock(r.started_at)} – {r.ended_at ? fmt.clock(r.ended_at) : '…'}</div>}
                            </td>
                            <td data-p="execution" className={td}>
                              {r.subtopics.length === 0 ? <span className="text-fg-faint">—</span> : (
                                <Clip title={[...r.covered_topics.map((t) => `✓ ${t}`), ...r.remaining_topics.map((t) => `○ ${t}`)].join('\n')}>
                                  <span className={cn('tnum font-medium', r.covered_topics.length === r.subtopics.length ? 'text-primary' : r.covered_topics.length ? 'text-warning' : 'text-fg-muted')}>{r.covered_topics.length}/{r.subtopics.length}</span>
                                  {r.remaining_topics.length > 0 && r.covered_topics.length > 0 && <span className="meta"> · left: {r.remaining_topics.join(', ')}</span>}
                                </Clip>
                              )}
                            </td>
                            <td data-p="execution" className={cn(td, 'whitespace-nowrap')}>
                              {r.notes.length ? r.notes.slice(0, 2).map((n, i) => (
                                <a key={i} href={n.url} target="_blank" rel="noreferrer" className="link flex items-center gap-1"><ExternalLink className="h-3.5 w-3.5" aria-hidden />{r.notes.length > 1 ? `Notes ${i + 1}` : 'Open notes'}</a>
                              )) : <span className={r.submitted_at ? 'text-accent' : 'text-fg-faint'}>{r.submitted_at ? 'Missing' : '—'}</span>}
                              {r.recording_url && <a href={r.recording_url} target="_blank" rel="noreferrer" className="link flex items-center gap-1"><ExternalLink className="h-3.5 w-3.5" aria-hidden />Recording</a>}
                            </td>
                            <td data-p="execution" className={cn(td, 'whitespace-nowrap')}>
                              {r.assignment ? (r.assignment.url
                                ? <a href={r.assignment.url} target="_blank" rel="noreferrer" className="link flex items-center gap-1" title={r.assignment.title}><ExternalLink className="h-3.5 w-3.5" aria-hidden />Open</a>
                                : <span title={r.assignment.title}>Added</span>) : <span className="text-fg-faint">—</span>}
                            </td>
                            <td data-p="execution" className={cn(td, 'whitespace-nowrap')}>
                              {r.evidence_count ? <span className="inline-flex items-center gap-1 text-fg-soft"><ImageIcon className="h-3.5 w-3.5 text-fg-muted" aria-hidden />{r.evidence_count} photo{r.evidence_count === 1 ? '' : 's'}</span> : <span className="text-fg-faint">—</span>}
                            </td>
                            <td data-p="execution" className={td}>{r.professor_remarks || r.additional_topics ? <Clip title={[r.professor_remarks, r.additional_topics && `Also covered: ${r.additional_topics}`].filter(Boolean).join('\n')}>{r.professor_remarks}{r.additional_topics && <span className="meta block">Also covered: {r.additional_topics}</span>}</Clip> : <span className="text-fg-faint">—</span>}</td>

                            <td data-p="verification" className={cn(td, 'border-l border-l-line-subtle')}><StepCell step={r.clch} /></td>
                            <td data-p="verification" className={td}>{r.clch.remarks ? <Clip title={r.clch.remarks} w="max-w-[200px]">“{r.clch.remarks}”</Clip> : <span className="text-fg-faint">—</span>}</td>

                            <td data-p="operations" className={cn(td, 'tnum border-l border-l-line-subtle whitespace-nowrap')}>
                              {r.om.entry_time ? <>{fmt.clock(r.om.entry_time)}{r.om.timing_status === 'DELAYED' && <div className="text-[12px] font-medium text-warning">+{r.om.delay_minutes} min</div>}</> : <span className="text-fg-faint">—</span>}
                            </td>
                            <td data-p="operations" className={cn(td, 'tnum whitespace-nowrap')}>{r.om.exit_time ? fmt.clock(r.om.exit_time) : <span className="text-fg-faint">—</span>}</td>
                            <td data-p="operations verification" className={td}>
                              {r.om.status ? <StepCell step={r.om} pendingLabel="Final verification pending" /> : <span className="meta block max-w-[170px]">{r.waiting_for ?? 'Waiting'}</span>}
                            </td>

                            <td data-p="verification" className={cn(td, 'border-l border-l-line-subtle whitespace-nowrap')}>
                              {r.final_status === 'FINAL_VERIFIED' ? <span className="inline-flex items-center gap-1 font-semibold text-primary"><Check className="h-4 w-4" strokeWidth={3} aria-hidden />Final verified</span> : <Badge tone={final.tone}>{final.label}</Badge>}
                            </td>
                            <td data-p="id" className={cn(td, 'sticky right-0 z-[1] border-l border-l-line bg-surface group-hover:bg-surface-2')}>
                              <div className="flex flex-col items-end gap-1.5">
                                <Chain r={r} />
                                {a && <ButtonLink to={a.to} size="sm" variant={a.primary ? 'primary' : 'secondary'}>{a.label}</ButtonLink>}
                              </div>
                            </td>
                          </tr>
                        )
                      })}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
            </>
          )}
      </div>
    </div>
  )
}
