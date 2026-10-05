import type { ColumnDef } from '@tanstack/react-table'
import { ClipboardCheck } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate } from '@/lib/router'
import { EmptyState } from '@/components/feedback/States'
import { PageHeader, useBreadcrumbs } from '@/components/layout/PageHeader'
import { DataTable } from '@/components/tables/DataTable'
import { FilterBar, FilterDate, FilterSelect, useAcademicOptions } from '@/components/tables/FilterBar'
import { StatusBadge, Tag } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Metric, MetricStrip } from '@/components/ui/Display'
import { useAuth } from '@/features/auth/AuthContext'
import { useApi } from '@/hooks/useApi'
import { EXECUTION_STATUS, fmt, VERIFICATION_STATUS } from '@/lib/status'
import type { Paged } from '@/services/api'
import { levelName, ROLE_NAME, type QueueRow, type UserBrief, type UserScope } from '@/types/domain'

type View = 'pending' | 'verified' | 'corrections'

export function queueColumns(view: View | 'all'): ColumnDef<QueueRow>[] {
  return [
    { id: 'professor', header: 'Professor', accessorFn: (r) => r.professor.full_name, cell: ({ getValue }) => <span className="whitespace-nowrap font-medium text-fg">{getValue<string>()}</span> },
    { id: 'subject', header: 'Subject', accessorFn: (r) => r.subject.short_name ?? r.subject.code, cell: ({ getValue }) => <span className="whitespace-nowrap">{getValue<string>()}</span> },
    { id: 'semester', header: 'Semester', accessorFn: (r) => r.semester, cell: ({ getValue }) => <span className="whitespace-nowrap">{getValue<string>().replace('Semester', 'Sem')}</span> },
    { id: 'section', header: 'Section', accessorFn: (r) => r.section },
    { id: 'lecture', header: 'Lecture', accessorFn: (r) => r.lecture_no, meta: { className: 'tnum' } },
    {
      id: 'topic',
      header: 'Topic',
      accessorFn: (r) => r.topic,
      cell: ({ row: { original: r } }) => (
        <div className="min-w-[180px] max-w-[300px]">
          <div className="truncate text-fg">{r.topic}</div>
          <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
            <StatusBadge value={r.execution_status} map={EXECUTION_STATUS} />
            {r.is_resubmission && <Tag>Resubmitted · round {r.round}</Tag>}
          </div>
        </div>
      ),
    },
    {
      id: 'planned',
      header: 'Scheduled',
      accessorFn: (r) => r.planned_date ?? '',
      cell: ({ row: { original: r } }) => (
        <div className="whitespace-nowrap">
          {fmt.dateShort(r.planned_date)}
          {r.actual_date && r.actual_date !== r.planned_date && <div className={`text-[12px] ${r.planned_date && r.actual_date > r.planned_date ? 'font-medium text-warning' : 'text-fg-label'}`}>Held {fmt.dateShort(r.actual_date)}</div>}
        </div>
      ),
    },
    { id: 'submitted', header: 'Submitted', accessorFn: (r) => r.submitted_at ?? '', cell: ({ getValue }) => <span className="meta whitespace-nowrap">{fmt.dateTime(getValue<string>() || null)}</span> },
    {
      id: 'status',
      header: view === 'pending' ? 'Stage' : 'Status',
      accessorFn: (r) => r.status,
      cell: ({ row: { original: r } }) => (
        <div className="whitespace-nowrap">
          <StatusBadge value={r.status} map={VERIFICATION_STATUS} />
          <div className="meta mt-0.5">{levelName(r.level)}{r.verifier ? ` · ${r.verifier.full_name}` : r.prior_verifications.length ? ` · ${r.prior_verifications.map((p) => `${levelName(p.verification_level)} ✓`).join(' ')}` : ''}</div>
        </div>
      ),
    },
    { id: 'action', header: '', enableSorting: false, cell: () => <Button size="sm" variant={view === 'pending' ? 'primary' : 'secondary'}>{view === 'pending' ? 'Review' : 'Open'}</Button> },
  ]
}

function useQueueFilters() {
  const opts = useAcademicOptions()
  const professors = useApi<Paged<UserBrief>>('/users', { role: 'PROFESSOR' })
  const [f, setF] = useState({ subject_id: '', professor_id: '', section_id: '', semester_id: '', date_from: '', date_to: '' })
  const set = (k: keyof typeof f) => (v: string) => setF((x) => ({ ...x, [k]: v }))
  const active = Object.values(f).some(Boolean)
  const bar = (
    <FilterBar onReset={() => setF({ subject_id: '', professor_id: '', section_id: '', semester_id: '', date_from: '', date_to: '' })} active={active}>
      <FilterSelect label="Subject" value={f.subject_id} onChange={set('subject_id')} options={opts.subjects} width="w-52" />
      <FilterSelect label="Professor" value={f.professor_id} onChange={set('professor_id')} options={professors.data?.items.map((p) => ({ value: p.id, label: p.full_name })) ?? []} />
      <FilterSelect label="Semester" value={f.semester_id} onChange={set('semester_id')} options={opts.semesters} width="w-36" />
      <FilterSelect label="Section" value={f.section_id} onChange={set('section_id')} options={opts.sections} />
      <FilterDate label="Delivered from" value={f.date_from} onChange={set('date_from')} />
      <FilterDate label="Delivered to" value={f.date_to} onChange={set('date_to')} />
    </FilterBar>
  )
  return { filters: f, bar }
}

const TITLES: Record<View, { title: string; description: string; crumb: string }> = {
  pending: { title: 'Pending Verification', description: 'Professor submissions inside your scope that are waiting for your review, oldest first.', crumb: 'Pending Verification' },
  verified: { title: 'Verified Records', description: 'Records verified at your step.', crumb: 'Verified Records' },
  corrections: { title: 'Correction Requests', description: 'Records sent back to professors from your step.', crumb: 'Correction Requests' },
}

export function QueuePage({ view, reviewBase = '/verification/review' }: { view: View; reviewBase?: string }) {
  const t = TITLES[view]
  useBreadcrumbs([{ label: 'Verification' }, { label: t.crumb }])
  const navigate = useNavigate()
  const { session } = useAuth()
  const { filters, bar } = useQueueFilters()
  const queue = useApi<Paged<QueueRow>>(`/verifications/queue/${view}`, filters)
  const columns = useMemo(() => queueColumns(view), [view])
  return (
    <div>
      <PageHeader title={t.title} description={t.description} meta={session?.scope ? <Tag title="Your assigned scope">Scope: {session.scope.label}</Tag> : undefined} />
      <div className="mb-4">{bar}</div>
      <div className="panel">
        <DataTable
          columns={columns}
          data={queue.data?.items}
          loading={queue.loading}
          error={queue.error?.message}
          onRetry={queue.reload}
          searchPlaceholder="Search topic, professor, subject…"
          onRowClick={(r) => navigate(`${reviewBase}/${r.id}`)}
          empty={<EmptyState icon={<ClipboardCheck className="h-5 w-5" />} title={view === 'pending' ? 'Nothing waiting for you' : 'No records yet'} description={view === 'pending' ? (session?.role === 'OM' ? 'Records appear here once CL/CH has verified them.' : 'New professor submissions inside your scope appear here.') : undefined} />}
        />
      </div>
    </div>
  )
}

type VMetrics = { level: string; level_label: string | null; scope: UserScope; pending: number; verified: number; correction_required: number; todays_submissions: number; final_verified: number }

export function VerificationDashboard() {
  useBreadcrumbs([{ label: 'Dashboard' }])
  const navigate = useNavigate()
  const { session } = useAuth()
  const metrics = useApi<VMetrics>('/verifications/metrics')
  const pending = useApi<Paged<QueueRow>>('/verifications/queue/pending')
  const columns = useMemo(() => queueColumns('pending'), [])
  const m = metrics.data
  return (
    <div>
      <PageHeader
        title="CL/CH Verification"
        description="Review faculty teaching execution, lecture notes, assignments and academic completion records. OM gives the final verification after you."
        meta={<Tag title="Set by the administrator in User Management">Scope: {m?.scope.label ?? session?.scope?.label ?? '…'}</Tag>}
      />
      <MetricStrip className="mb-5">
        <Metric label="Pending verification" value={m?.pending ?? '–'} tone={m?.pending ? 'warning' : undefined} sub="Waiting for your review" />
        <Metric label="Verified" value={m?.verified ?? '–'} sub={`By ${session ? ROLE_NAME[session.role] : 'CL/CH'}`} />
        <Metric label="Correction required" value={m?.correction_required ?? '–'} tone={m?.correction_required ? 'danger' : undefined} sub="Sent back to professors" />
        <Metric label="Today's submissions" value={m?.todays_submissions ?? '–'} sub="Inside your scope" />
      </MetricStrip>
      <div className="panel">
        <div className="panel-header">
          <span className="panel-title">Waiting for your review</span>
          <Button size="sm" variant="link" onClick={() => navigate('/verification/pending')}>Open full queue</Button>
        </div>
        <DataTable
          columns={columns}
          data={pending.data?.items}
          loading={pending.loading}
          error={pending.error?.message}
          onRetry={pending.reload}
          pageSize={10}
          searchPlaceholder="Search…"
          onRowClick={(r) => navigate(`/verification/review/${r.id}`)}
          empty={<EmptyState icon={<ClipboardCheck className="h-5 w-5" />} title="You're all caught up" description="New submissions will appear here." />}
        />
      </div>
    </div>
  )
}
