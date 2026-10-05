import { Clock3 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate, useParams } from '@/lib/router'
import { ExecutionSummary, MasterPlanPanel, Section, VerificationHistory } from '@/components/domain/LectureRecord'
import { ClassTimingPanel, VerificationTimeline } from '@/components/domain/VerificationTimeline'
import { ScheduleCalendar, monthRange } from '@/components/domain/ScheduleCalendar'
import { ErrorState, InlineAlert, PageLoading } from '@/components/feedback/States'
import { PageHeader, useBreadcrumbs } from '@/components/layout/PageHeader'
import { DataTable } from '@/components/tables/DataTable'
import { FilterBar, FilterSelect, useAcademicOptions } from '@/components/tables/FilterBar'
import { Badge, StatusBadge } from '@/components/ui/Badge'
import { Metric, MetricStrip } from '@/components/ui/Display'
import { Tabs } from '@/components/ui/Tabs'
import { SCHEDULE_LEGEND } from '@/features/professor/CoursePages'
import { queueColumns } from '@/features/verification/QueuePages'
import { useApi } from '@/hooks/useApi'
import { fmt, isoLocal, SUBMISSION_STATUS, type Tone } from '@/lib/status'
import type { Paged } from '@/services/api'
import type { FactRow, LectureDetail, QueueRow } from '@/types/domain'

export function AdminSchedulePage() {
  useBreadcrumbs([{ label: 'Teaching Management' }, { label: 'Schedule' }])
  const opts = useAcademicOptions()
  const [month, setMonth] = useState(() => new Date())
  const [subject, setSubject] = useState('')
  const [section, setSection] = useState('')
  const { start, end } = monthRange(month)
  const data = useApi<Paged<FactRow>>('/reports/lectures/completion', { date_from: isoLocal(start), date_to: isoLocal(end), subject_id: subject, section_id: section })
  const tone = (r: FactRow): { label: string; tone: Tone } =>
    r.bucket === 'completed' ? { label: 'Completed', tone: 'success' } : r.bucket === 'partial' ? { label: 'Partial', tone: 'warning' } : r.bucket === 'delayed' ? { label: 'Delayed', tone: 'danger' } : r.execution_status === 'RESCHEDULED' ? { label: 'Rescheduled', tone: 'info' } : { label: 'Scheduled', tone: 'neutral' }
  const items = (data.data?.items ?? []).filter((r) => r.planned_date).map((r) => {
    const t = tone(r)
    return { id: r.lecture_id, date: r.planned_date!, title: `${r.subject_short ?? r.subject_code}·${r.section} L${r.lecture_no} ${r.topic}`, subtitle: r.professor, time: fmt.clock(r.planned_start_time), status: t.label, tone: t.tone, href: `/admin/lectures/${r.lecture_id}` }
  })
  return (
    <div>
      <PageHeader title="Schedule" description="Published lecture schedule across all plans." />
      <div className="mb-4">
        <FilterBar onReset={() => { setSubject(''); setSection('') }} active={!!(subject || section)}>
          <FilterSelect label="Subject" value={subject} onChange={setSubject} options={opts.subjects} width="w-56" />
          <FilterSelect label="Section" value={section} onChange={setSection} options={opts.sections} />
        </FilterBar>
      </div>
      {data.error ? <ErrorState message={data.error.message} onRetry={data.reload} /> : <ScheduleCalendar month={month} onMonth={setMonth} items={items} legend={SCHEDULE_LEGEND} />}
    </div>
  )
}

type Tab = 'pending' | 'corrections' | 'all'

export function AdminVerificationPage() {
  useBreadcrumbs([{ label: 'Monitoring' }, { label: 'Verification' }])
  const navigate = useNavigate()
  const [tab, setTab] = useState<Tab>('pending')
  const queue = useApi<Paged<QueueRow>>(`/verifications/queue/${tab}`)
  const metrics = useApi<{ pending: number; verified: number; correction_required: number; todays_submissions: number; final_verified: number }>('/verifications/metrics')
  const cols = useMemo(() => queueColumns('all'), [])
  const m = metrics.data
  return (
    <div>
      <PageHeader title="Verification" description="Read-only oversight of the Professor → CL/CH → OM pipeline. Verification itself is done by CL/CH and OM accounts." />
      <MetricStrip className="mb-5">
        <Metric label="Pending (all levels)" value={m?.pending ?? '–'} tone={m?.pending ? 'warning' : undefined} />
        <Metric label="Verification steps completed" value={m?.verified ?? '–'} />
        <Metric label="Correction requests" value={m?.correction_required ?? '–'} tone={m?.correction_required ? 'danger' : undefined} />
        <Metric label="Today's submissions" value={m?.todays_submissions ?? '–'} />
        <Metric label="Final verified lectures" value={m?.final_verified ?? '–'} tone="success" />
      </MetricStrip>
      <Tabs className="mb-4" value={tab} onChange={setTab} items={[{ value: 'pending', label: 'Pending' }, { value: 'corrections', label: 'Correction requests' }, { value: 'all', label: 'All activity' }]} />
      <div className="panel">
        <DataTable columns={cols} data={queue.data?.items} loading={queue.loading} error={queue.error?.message} onRetry={queue.reload} onRowClick={(r) => navigate(`/admin/lectures/${r.lecture_id}`)} />
      </div>
    </div>
  )
}

export function AdminLectureRecordPage() {
  const { lectureId } = useParams()
  const d = useApi<LectureDetail>(`/lectures/${lectureId}`)
  const l = d.data
  useBreadcrumbs([{ label: 'Teaching Plans', to: '/admin/plans' }, { label: l ? l.subject.short_name ?? l.subject.code : '…', to: l ? `/admin/plans/${l.plan.id}` : undefined }, { label: l ? `Lecture ${l.lecture_no}` : '…' }])
  if (d.loading && !l) return <PageLoading />
  if (d.error || !l) return <ErrorState message={d.error?.message ?? 'Lecture not found'} onRetry={d.reload} />
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title={l.content_topic} description={`${l.subject.name} · Section ${l.plan.section} · Lecture ${l.lecture_no}`} meta={<StatusBadge value={l.submission_status} map={SUBMISSION_STATUS} />} />
      <InlineAlert tone="info" className="mb-4">Execution data belongs to the professor and verification data to CL/CH and OM. Administrators can correct master data from the plan's Lectures tab.</InlineAlert>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1.4fr)_minmax(300px,1fr)]">
        <div className="space-y-5">
          <MasterPlanPanel d={l} label="A" />
          <ExecutionSummary d={l} label="B" />
          <ClassTimingPanel session={l.class_session} label="C" />
        </div>
        <Section title="Verification" label="D">
          <div className="mb-5">
            <VerificationTimeline submitted={!!l.execution?.submitted_at} submissionStatus={l.submission_status} steps={l.verifications} chain={l.verification_chain} />
          </div>
          <VerificationHistory items={l.verifications} />
        </Section>
      </div>
    </div>
  )
}

export function SettingsPage() {
  useBreadcrumbs([{ label: 'System' }, { label: 'Settings' }])
  const rows: { area: string; status: 'active' | 'planned'; detail: string }[] = [
    { area: 'Account sign-in', status: 'active', detail: 'Email, username or employee ID with a password. Passwords are stored only as scrypt hashes; accounts are created in User Management.' },
    { area: 'Demo accounts on the sign-in page', status: 'active', detail: 'Shown only while DEMO_AUTH_ENABLED=true and the seeded demo accounts exist. Set it to false for real use.' },
    { area: 'Verification and operations scope', status: 'active', detail: 'Each CL/CH and OM account sees only the department, semesters, sections and subjects assigned to it.' },
    { area: 'Spreadsheet import', status: 'active', detail: 'Full-table paste, column-by-column paste, .xlsx and .csv upload. Dates are read day-first (DD/MM/YYYY).' },
    { area: 'In-app notifications', status: 'active', detail: 'Generated for submissions, verification steps, corrections and plan publishing.' },
    { area: 'Single sign-on (SSO)', status: 'planned', detail: 'Institutional SSO can replace the password check without changing roles or scopes.' },
    { area: 'File uploads for notes', status: 'planned', detail: 'S3-compatible storage with presigned uploads. Links are stored today.' },
    { area: 'Email / WhatsApp notifications', status: 'planned', detail: 'Delivery channels plug into the existing notification service.' },
    { area: 'HoI verification level', status: 'planned', detail: 'An additional level can be inserted into the CL/CH → OM chain.' },
  ]
  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader title="Settings" description="System capabilities in this deployment." />
      <div className="panel divide-y divide-line-subtle">
        {rows.map((r) => (
          <div key={r.area} className="flex items-start gap-4 px-4 py-3.5">
            <div className="flex-1">
              <div className="text-[13.5px] font-medium text-fg">{r.area}</div>
              <div className="meta mt-0.5">{r.detail}</div>
            </div>
            {r.status === 'active' ? <Badge tone="success">Active</Badge> : <Badge tone="neutral"><Clock3 className="hidden" />Planned</Badge>}
          </div>
        ))}
      </div>
    </div>
  )
}
