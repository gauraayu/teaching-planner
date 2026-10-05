import type { ColumnDef } from '@tanstack/react-table'
import { Download } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate } from '@/lib/router'
import { BucketLegend, BUCKET_SEGMENTS, MetricDefinitions, UnitProgressTable } from '@/components/domain/Progress'
import { ErrorState, LoadingRows } from '@/components/feedback/States'
import { PageHeader, useBreadcrumbs } from '@/components/layout/PageHeader'
import { DataTable } from '@/components/tables/DataTable'
import { FilterBar, FilterDate, FilterSelect, useAcademicOptions } from '@/components/tables/FilterBar'
import { StatusBadge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Metric, MetricStrip, ProgressBar, SegmentBar } from '@/components/ui/Display'
import { Tabs } from '@/components/ui/Tabs'
import { useAuth } from '@/features/auth/AuthContext'
import { queueColumns } from '@/features/verification/QueuePages'
import { useApi } from '@/hooks/useApi'
import { BUCKET, fmt, SUBMISSION_STATUS } from '@/lib/status'
import type { Paged } from '@/services/api'
import type { FactRow, Metrics, QueueRow, SubjectProgressRow, UnitRow, UserBrief } from '@/types/domain'
import { downloadCsv } from '@/utils/cn'

type FacultyRow = Metrics & { professor: { id: string; full_name: string }; subjects: string[] }
type ProgressReport = {
  summary: Metrics
  definitions: Record<string, string>
  subjects: SubjectProgressRow[]
  faculty: FacultyRow[]
  units: UnitRow[]
  adherence: { delivered: number; early: number; on_day: number; late: number; average_delay_days: number; adherence_pct: number }
}

const EMPTY = { academic_year_id: '', semester_id: '', branch_id: '', section_id: '', subject_id: '', professor_id: '', date_from: '', date_to: '' }

export function useReportFilters(extra?: { unit?: boolean }) {
  const opts = useAcademicOptions()
  const professors = useApi<Paged<UserBrief>>('/users', { role: 'PROFESSOR' })
  const [f, setF] = useState({ ...EMPTY, unit_no: '' })
  const set = (k: keyof typeof f) => (v: string) => setF((x) => ({ ...x, [k]: v }))
  const bar = (
    <FilterBar onReset={() => setF({ ...EMPTY, unit_no: '' })} active={Object.values(f).some(Boolean)}>
      <FilterSelect label="Academic year" value={f.academic_year_id} onChange={set('academic_year_id')} options={opts.years} width="w-32" />
      <FilterSelect label="Semester" value={f.semester_id} onChange={set('semester_id')} options={opts.semesters} width="w-36" />
      <FilterSelect label="Branch" value={f.branch_id} onChange={set('branch_id')} options={opts.branches} width="w-28" />
      <FilterSelect label="Section" value={f.section_id} onChange={set('section_id')} options={opts.sections} />
      <FilterSelect label="Subject" value={f.subject_id} onChange={set('subject_id')} options={opts.subjects} width="w-56" />
      <FilterSelect label="Professor" value={f.professor_id} onChange={set('professor_id')} options={professors.data?.items.map((p) => ({ value: p.id, label: p.full_name })) ?? []} />
      {extra?.unit && <FilterSelect label="Unit" value={f.unit_no} onChange={set('unit_no')} options={[1, 2, 3, 4, 5, 6].map((u) => ({ value: String(u), label: `Unit ${u}` }))} width="w-24" />}
      <FilterDate label="Planned from" value={f.date_from} onChange={set('date_from')} />
      <FilterDate label="Planned to" value={f.date_to} onChange={set('date_to')} />
    </FilterBar>
  )
  return { filters: f, bar }
}

export function subjectColumns(onOpen?: (r: SubjectProgressRow) => void): ColumnDef<SubjectProgressRow>[] {
  return [
    { id: 'subject', header: 'Subject', accessorFn: (r) => `${r.subject_code} ${r.subject_name}`, cell: ({ row: { original: r } }) => <div className="min-w-[200px]"><div className="font-medium text-fg">{r.subject_name}</div><div className="meta">{r.subject_code} · {r.semester.replace('Semester', 'Sem')} · Section {r.section}</div></div> },
    { id: 'professor', header: 'Professor', accessorFn: (r) => r.professor.full_name },
    { id: 'total', header: 'Lectures', accessorFn: (r) => r.total, meta: { align: 'right', className: 'tnum' } },
    { id: 'breakdown', header: 'Breakdown', enableSorting: false, cell: ({ row: { original: r } }) => <div className="w-52"><SegmentBar segments={BUCKET_SEGMENTS(r)} /><div className="meta tnum mt-1 whitespace-nowrap">{r.completed} done · {r.partial} partial · {r.delayed} delayed</div></div> },
    { id: 'exec', header: 'Execution', accessorFn: (r) => r.execution_pct, meta: { align: 'right' }, cell: ({ getValue }) => <span className="tnum font-semibold text-fg">{getValue<number>()}%</span> },
    { id: 'verified', header: 'Verified', accessorFn: (r) => r.verified_pct, meta: { align: 'right' }, cell: ({ getValue }) => <span className="tnum">{getValue<number>()}%</span> },
    { id: 'ontime', header: 'On time', accessorFn: (r) => r.on_time_pct, meta: { align: 'right' }, cell: ({ getValue }) => <span className="tnum">{getValue<number>()}%</span> },
    { id: 'delayed', header: 'Delayed', accessorFn: (r) => r.delayed, meta: { align: 'right' }, cell: ({ getValue }) => <span className={`tnum ${getValue<number>() ? 'font-semibold text-danger' : 'text-fg-muted'}`}>{getValue<number>()}</span> },
    ...(onOpen ? [] : []),
  ]
}

const facultyColumns: ColumnDef<FacultyRow>[] = [
  { id: 'professor', header: 'Professor', accessorFn: (r) => r.professor.full_name, cell: ({ row: { original: r } }) => <div><div className="font-medium text-fg">{r.professor.full_name}</div><div className="meta">{r.subjects.join(', ')}</div></div> },
  { id: 'total', header: 'Lectures', accessorFn: (r) => r.total, meta: { align: 'right', className: 'tnum' } },
  { id: 'exec', header: 'Execution', accessorFn: (r) => r.execution_pct, cell: ({ row: { original: r } }) => <div className="w-36"><div className="tnum mb-1 text-[12px] font-medium">{r.execution_pct}%</div><ProgressBar value={r.execution_pct} label={`${r.professor.full_name} execution`} /></div> },
  { id: 'verified', header: 'Verified', accessorFn: (r) => r.verified_pct, meta: { align: 'right' }, cell: ({ getValue }) => <span className="tnum">{getValue<number>()}%</span> },
  { id: 'ontime', header: 'On time', accessorFn: (r) => r.on_time_pct, meta: { align: 'right' }, cell: ({ getValue }) => <span className="tnum">{getValue<number>()}%</span> },
  { id: 'awaiting', header: 'Awaiting verification', accessorFn: (r) => r.awaiting_verification, meta: { align: 'right', className: 'tnum' } },
  { id: 'corr', header: 'Corrections', accessorFn: (r) => r.correction_required, meta: { align: 'right' }, cell: ({ getValue }) => <span className={`tnum ${getValue<number>() ? 'font-semibold text-danger' : 'text-fg-muted'}`}>{getValue<number>()}</span> },
  { id: 'delayed', header: 'Delayed', accessorFn: (r) => r.delayed, meta: { align: 'right' }, cell: ({ getValue }) => <span className={`tnum ${getValue<number>() ? 'font-semibold text-danger' : 'text-fg-muted'}`}>{getValue<number>()}</span> },
]

const factColumns = (kind: string): ColumnDef<FactRow>[] => [
  { id: 'subject', header: 'Subject', accessorFn: (r) => `${r.subject_short ?? r.subject_code} ${r.section}`, cell: ({ row: { original: r } }) => <span className="whitespace-nowrap">{r.subject_short ?? r.subject_code} <span className="meta">· {r.section}</span></span> },
  { id: 'professor', header: 'Professor', accessorFn: (r) => r.professor },
  { id: 'no', header: 'Lecture', accessorFn: (r) => r.lecture_no, meta: { className: 'tnum' } },
  { id: 'unit', header: 'Unit', accessorFn: (r) => r.unit_no ?? '', meta: { className: 'tnum' } },
  { id: 'topic', header: 'Topic', accessorFn: (r) => r.topic, cell: ({ getValue }) => <span className="block max-w-[320px] truncate text-fg">{getValue<string>()}</span> },
  { id: 'planned', header: 'Planned', accessorFn: (r) => r.planned_date ?? '', cell: ({ getValue }) => <span className="whitespace-nowrap">{fmt.date(getValue<string>() || null)}</span> },
  ...(kind === 'pending' || kind === 'upcoming' ? [] : [{ id: 'actual', header: 'Actual', accessorFn: (r: FactRow) => r.actual_date ?? '', cell: ({ getValue }: { getValue: () => unknown }) => <span className="whitespace-nowrap">{fmt.date((getValue() as string) || null)}</span> } as ColumnDef<FactRow>]),
  ...(kind === 'delayed' || kind === 'planned_vs_actual' ? [{ id: 'delay', header: kind === 'delayed' ? 'Days overdue' : 'Delay (days)', accessorFn: (r: FactRow) => r.delay_days ?? 0, meta: { align: 'right' as const }, cell: ({ getValue }: { getValue: () => unknown }) => { const n = getValue() as number; return <span className={`tnum ${n > 0 ? 'font-semibold text-danger' : n < 0 ? 'text-primary' : ''}`}>{n > 0 ? `+${n}` : n}</span> } } as ColumnDef<FactRow>] : []),
  { id: 'bucket', header: 'Status', accessorFn: (r) => r.bucket, cell: ({ getValue }) => <StatusBadge value={getValue<FactRow['bucket']>()} map={BUCKET} /> },
  { id: 'verification', header: 'Verification', accessorFn: (r) => r.submission_status ?? '', cell: ({ row: { original: r } }) => <StatusBadge value={r.submission_status} map={SUBMISSION_STATUS} /> },
]

type ReportKey = 'subject' | 'faculty' | 'unit' | 'completion' | 'planned_vs_actual' | 'adherence' | 'delayed' | 'pending' | 'vpending' | 'corrections'

const REPORTS: { value: ReportKey; label: string }[] = [
  { value: 'subject', label: 'Subject Progress' },
  { value: 'faculty', label: 'Faculty Progress' },
  { value: 'unit', label: 'Unit Progress' },
  { value: 'completion', label: 'Lecture Completion' },
  { value: 'planned_vs_actual', label: 'Planned vs Actual' },
  { value: 'adherence', label: 'Schedule Adherence' },
  { value: 'delayed', label: 'Delayed Lectures' },
  { value: 'pending', label: 'Pending Lectures' },
  { value: 'vpending', label: 'Verification Pending' },
  { value: 'corrections', label: 'Correction Requests' },
]

export function ReportsPage() {
  useBreadcrumbs([{ label: 'Monitoring' }, { label: 'Reports' }])
  const { session } = useAuth()
  const navigate = useNavigate()
  const [report, setReport] = useState<ReportKey>('subject')
  const { filters, bar } = useReportFilters({ unit: true })
  const isFact = ['completion', 'planned_vs_actual', 'delayed', 'pending'].includes(report)
  const isVerif = report === 'vpending' || report === 'corrections'
  const progress = useApi<ProgressReport>(!isFact && !isVerif ? '/reports/progress' : null, filters)
  const facts = useApi<Paged<FactRow>>(isFact ? `/reports/lectures/${report}` : null, filters)
  const verif = useApi<Paged<QueueRow>>(isVerif ? `/reports/verification/${report === 'vpending' ? 'pending' : 'corrections'}` : null)
  const vcols = useMemo(() => queueColumns('all'), [])
  const fcols = useMemo(() => factColumns(report), [report])
  const sCols = useMemo(() => subjectColumns(), [])
  const base = session?.role === 'ADMIN' ? '/admin' : '/verification'

  const exportCsv = () => {
    const name = `${report}-${new Date().toISOString().slice(0, 10)}.csv`
    if (report === 'subject' && progress.data)
      downloadCsv(name, ['Subject code', 'Subject', 'Section', 'Professor', 'Lectures', 'Completed', 'Partial', 'Delayed', 'Pending', 'Execution %', 'Verified %', 'On-time %'],
        progress.data.subjects.map((r) => [r.subject_code, r.subject_name, r.section, r.professor.full_name, r.total, r.completed, r.partial, r.delayed, r.pending, r.execution_pct, r.verified_pct, r.on_time_pct]))
    else if (report === 'faculty' && progress.data)
      downloadCsv(name, ['Professor', 'Subjects', 'Lectures', 'Completed', 'Delayed', 'Execution %', 'Verified %', 'On-time %', 'Awaiting verification', 'Corrections'],
        progress.data.faculty.map((r) => [r.professor.full_name, r.subjects.join('; '), r.total, r.completed, r.delayed, r.execution_pct, r.verified_pct, r.on_time_pct, r.awaiting_verification, r.correction_required]))
    else if (report === 'unit' && progress.data)
      downloadCsv(name, ['Unit', 'Lectures', 'Completed', 'Partial', 'Delayed', 'Pending', 'Execution %'], progress.data.units.map((u) => [u.unit_no, u.total, u.completed, u.partial, u.delayed, u.pending, u.execution_pct]))
    else if (isFact && facts.data)
      downloadCsv(name, ['Subject', 'Section', 'Professor', 'Lecture', 'Unit', 'Topic', 'Planned', 'Actual', 'Delay days', 'Status', 'Verification'],
        facts.data.items.map((r) => [r.subject_code, r.section, r.professor, r.lecture_no, r.unit_no, r.topic, r.planned_date, r.actual_date, r.delay_days, r.bucket, r.submission_status]))
    else if (isVerif && verif.data)
      downloadCsv(name, ['Professor', 'Subject', 'Section', 'Lecture', 'Topic', 'Level', 'Status', 'Planned', 'Actual', 'Submitted', 'Remarks'],
        verif.data.items.map((r) => [r.professor.full_name, r.subject.code, r.section, r.lecture_no, r.topic, r.level, r.status, r.planned_date, r.actual_date, r.submitted_at, r.remarks]))
  }

  const p = progress.data
  return (
    <div>
      <PageHeader title="Reports" description="Academic delivery reports across plans, faculty and units." actions={<Button icon={<Download className="h-4 w-4" />} onClick={exportCsv}>Export CSV</Button>} />
      {!isVerif && <div className="mb-4">{bar}</div>}
      <Tabs className="mb-5" value={report} onChange={setReport} items={REPORTS} />

      {(progress.error || facts.error || verif.error) && <ErrorState message={(progress.error ?? facts.error ?? verif.error)!.message} />}

      {!isFact && !isVerif && (!p ? (
        <div className="panel"><LoadingRows /></div>
      ) : (
        <div className="space-y-5">
          <MetricStrip>
            <Metric label="Planned lectures" value={p.summary.total} />
            <Metric label="Execution completion" value={`${p.summary.execution_pct}%`} sub={`${p.summary.completed} completed`} />
            <Metric label="Verified completion" value={`${p.summary.verified_pct}%`} sub={`${p.summary.verified} final verified`} />
            <Metric label="On-time completion" value={`${p.summary.on_time_pct}%`} />
            <Metric label="Delayed" value={p.summary.delayed} tone={p.summary.delayed ? 'danger' : undefined} />
          </MetricStrip>
          <div className="panel px-4 py-3"><MetricDefinitions definitions={p.definitions} /></div>
          {report === 'subject' && <div className="panel"><DataTable columns={sCols} data={p.subjects} onRowClick={session?.role === 'ADMIN' ? (r) => navigate(`/admin/plans/${r.plan_id}`) : undefined} /></div>}
          {report === 'faculty' && <div className="panel"><DataTable columns={facultyColumns} data={p.faculty} /></div>}
          {report === 'unit' && (
            <div className="panel">
              <div className="panel-header"><span className="panel-title">Unit progress</span>{!filters.subject_id && !filters.section_id && <span className="meta">Choose a subject or section above to see its units.</span>}</div>
              {p.units.length ? <UnitProgressTable units={p.units} /> : <p className="meta px-4 py-6">Select a subject or section to break progress down by unit.</p>}
            </div>
          )}
          {report === 'adherence' && (
            <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_1fr]">
              <div className="panel">
                <div className="panel-header"><span className="panel-title">Schedule adherence</span></div>
                <dl className="grid grid-cols-2 gap-4 p-4 sm:grid-cols-3">
                  {[['Delivered', p.adherence.delivered], ['Before plan', p.adherence.early], ['On planned day', p.adherence.on_day], ['Late', p.adherence.late], ['Average delay', `${p.adherence.average_delay_days} d`], ['Adherence', `${p.adherence.adherence_pct}%`]].map(([l, v]) => (
                    <div key={l as string}><dt className="meta">{l}</dt><dd className="tnum text-[20px] font-semibold text-fg">{v}</dd></div>
                  ))}
                </dl>
                <p className="meta px-4 pb-4">Adherence = lectures delivered on or before their original planned date ÷ lectures delivered.</p>
              </div>
              <div className="panel">
                <div className="panel-header"><span className="panel-title">Delivery status</span></div>
                <div className="space-y-3 p-4"><SegmentBar segments={BUCKET_SEGMENTS(p.summary)} className="h-3" /><BucketLegend m={p.summary} /></div>
              </div>
            </div>
          )}
        </div>
      ))}

      {isFact && (
        <div className="panel">
          <DataTable columns={fcols} data={facts.data?.items} loading={facts.loading} pageSize={50} searchPlaceholder="Search topic, subject, professor…" columnToggle onRowClick={session?.role === 'ADMIN' ? (r) => navigate(`/admin/lectures/${r.lecture_id}`) : undefined} />
        </div>
      )}
      {isVerif && (
        <div className="panel">
          <DataTable columns={vcols} data={verif.data?.items} loading={verif.loading} pageSize={50} onRowClick={(r) => navigate(`${base === '/admin' ? '/admin/lectures/' + r.lecture_id : '/verification/review/' + r.id}`)} />
        </div>
      )}
    </div>
  )
}

/** Subject or faculty progress page (Admin "Progress", CL/CH "Subjects" and "Faculty Progress"). */
export function ProgressPage({ focus, title, crumb }: { focus: 'subjects' | 'faculty' | 'both'; title: string; crumb: string }) {
  useBreadcrumbs([{ label: 'Monitoring' }, { label: crumb }])
  const navigate = useNavigate()
  const { session } = useAuth()
  const { filters, bar } = useReportFilters()
  const data = useApi<ProgressReport>('/reports/progress', filters)
  const sCols = useMemo(() => subjectColumns(), [])
  const p = data.data
  return (
    <div>
      <PageHeader title={title} description="Live delivery progress computed from the published schedule and professor updates." />
      <div className="mb-4">{bar}</div>
      {data.error ? (
        <ErrorState message={data.error.message} onRetry={data.reload} />
      ) : !p ? (
        <div className="panel"><LoadingRows /></div>
      ) : (
        <div className="space-y-5">
          <MetricStrip>
            <Metric label="Planned lectures" value={p.summary.total} />
            <Metric label="Completed" value={p.summary.completed} sub={`${p.summary.execution_pct}% execution`} tone="success" />
            <Metric label="Partial" value={p.summary.partial} />
            <Metric label="Delayed" value={p.summary.delayed} tone={p.summary.delayed ? 'danger' : undefined} />
            <Metric label="Awaiting verification" value={p.summary.awaiting_verification} />
            <Metric label="Final verified" value={`${p.summary.verified_pct}%`} />
          </MetricStrip>
          <div className="panel px-4 py-3"><MetricDefinitions definitions={p.definitions} /></div>
          {(focus === 'subjects' || focus === 'both') && (
            <div className="panel">
              <div className="panel-header"><span className="panel-title">Subject progress</span></div>
              <DataTable columns={sCols} data={p.subjects} onRowClick={session?.role === 'ADMIN' ? (r) => navigate(`/admin/plans/${r.plan_id}`) : undefined} />
            </div>
          )}
          {(focus === 'faculty' || focus === 'both') && (
            <div className="panel">
              <div className="panel-header"><span className="panel-title">Faculty progress</span></div>
              <DataTable columns={facultyColumns} data={p.faculty} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
