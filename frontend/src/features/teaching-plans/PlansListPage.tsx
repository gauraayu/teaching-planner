import type { ColumnDef } from '@tanstack/react-table'
import { ClipboardList, FileSpreadsheet, MoreHorizontal, Plus } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate } from '@/lib/router'
import { EmptyState } from '@/components/feedback/States'
import { Segmented } from '@/components/forms/Fields'
import { PageHeader, useBreadcrumbs } from '@/components/layout/PageHeader'
import { DataTable } from '@/components/tables/DataTable'
import { FilterBar, FilterSelect, useAcademicOptions } from '@/components/tables/FilterBar'
import { StatusBadge } from '@/components/ui/Badge'
import { Button, ButtonLink } from '@/components/ui/Button'
import { ProgressBar } from '@/components/ui/Display'
import { Menu } from '@/components/ui/Menu'
import { useApi } from '@/hooks/useApi'
import { fmt, PLAN_STATUS } from '@/lib/status'
import type { Paged } from '@/services/api'
import type { Metrics, PlanBrief, PlanStatus } from '@/types/domain'
import { startImport } from '@/features/imports/ImportsPage'

type PlanRow = PlanBrief & { lecture_count: number; metrics: (Metrics & { plan_id: string }) | null }

export function PlansListPage() {
  useBreadcrumbs([{ label: 'Teaching Management' }, { label: 'Teaching Plans' }])
  const navigate = useNavigate()
  const opts = useAcademicOptions()
  const [status, setStatus] = useState<'ALL' | PlanStatus>('ALL')
  const [semester, setSemester] = useState('')
  const [section, setSection] = useState('')
  const plans = useApi<Paged<PlanRow>>('/teaching-plans', { semester_id: semester, section_id: section })
  const rows = (plans.data?.items ?? []).filter((p) => status === 'ALL' || p.status === status)
  const count = (s: PlanStatus) => plans.data?.items.filter((p) => p.status === s).length ?? 0

  const columns = useMemo<ColumnDef<PlanRow>[]>(
    () => [
      {
        id: 'subject',
        header: 'Subject',
        accessorFn: (p) => `${p.subject.code} ${p.subject.name}`,
        cell: ({ row: { original: p } }) => (
          <div className="min-w-[220px]">
            <div className="font-medium text-fg">{p.subject.name}</div>
            <div className="meta">{p.subject.code} · {p.branch.code}</div>
          </div>
        ),
      },
      { id: 'class', header: 'Class', accessorFn: (p) => `${p.semester.name} ${p.section.name}`, cell: ({ row: { original: p } }) => <span className="whitespace-nowrap">{p.semester.name.replace('Semester', 'Sem')} · Section {p.section.name}</span> },
      { id: 'professor', header: 'Professor', accessorFn: (p) => p.professor.full_name },
      { id: 'lectures', header: 'Lectures', accessorFn: (p) => p.lecture_count, meta: { align: 'right', className: 'tnum' } },
      {
        id: 'progress',
        header: 'Execution',
        accessorFn: (p) => p.metrics?.execution_pct ?? -1,
        cell: ({ row: { original: p } }) =>
          p.metrics && p.status === 'PUBLISHED' ? (
            <div className="w-36">
              <div className="mb-1 flex justify-between text-[12px]"><span className="tnum font-medium text-fg">{p.metrics.execution_pct}%</span><span className="meta tnum">{p.metrics.completed}/{p.metrics.total}</span></div>
              <ProgressBar value={p.metrics.execution_pct} label={`${p.subject.name} execution`} />
            </div>
          ) : (
            <span className="meta">—</span>
          ),
      },
      { id: 'delayed', header: 'Delayed', accessorFn: (p) => p.metrics?.delayed ?? 0, meta: { align: 'right' }, cell: ({ getValue }) => <span className={`tnum ${getValue<number>() ? 'font-medium text-danger' : 'text-fg-muted'}`}>{getValue<number>()}</span> },
      { id: 'status', header: 'Status', accessorFn: (p) => p.status, cell: ({ getValue }) => <StatusBadge value={getValue<PlanStatus>()} map={PLAN_STATUS} /> },
      { id: 'updated', header: 'Updated', accessorFn: (p) => p.updated_at, cell: ({ getValue }) => <span className="meta whitespace-nowrap">{fmt.date(getValue<string>())}</span> },
      {
        id: 'actions',
        header: '',
        enableSorting: false,
        cell: ({ row: { original: p } }) => (
          <div onClick={(e) => e.stopPropagation()}>
            <Menu
              label="Plan actions"
              trigger={(t) => <Button size="icon" variant="ghost" aria-label={`Actions for ${p.name}`} {...t}><MoreHorizontal className="h-4 w-4" /></Button>}
              items={[
                { label: 'View plan', onSelect: () => navigate(`/admin/plans/${p.id}`) },
                { label: 'Import lectures', disabled: p.status === 'PUBLISHED' || p.status === 'ARCHIVED', onSelect: async () => navigate(`/admin/imports/${await startImport(p.id)}`) },
                { label: 'Activity', onSelect: () => navigate(`/admin/plans/${p.id}?tab=activity`) },
              ]}
            />
          </div>
        ),
      },
    ],
    [navigate],
  )

  return (
    <div>
      <PageHeader
        title="Teaching Plans"
        description="Manage semester teaching plans and faculty assignments."
        actions={
          <>
            <ButtonLink to="/admin/imports" icon={<FileSpreadsheet className="h-4 w-4" />}>Import Plan</ButtonLink>
            <ButtonLink to="/admin/plans/new" variant="primary" icon={<Plus className="h-4 w-4" />}>Create Plan</ButtonLink>
          </>
        }
      />
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <FilterBar onReset={() => { setSemester(''); setSection('') }} active={!!(semester || section)}>
          <FilterSelect label="Semester" value={semester} onChange={setSemester} options={opts.semesters} />
          <FilterSelect label="Section" value={section} onChange={setSection} options={opts.sections} width="w-52" />
        </FilterBar>
        <Segmented
          size="sm"
          ariaLabel="Plan status"
          value={status}
          onChange={setStatus}
          options={[
            { value: 'ALL', label: 'All', count: plans.data?.items.length ?? 0 },
            { value: 'PUBLISHED', label: 'Published', count: count('PUBLISHED') },
            { value: 'READY', label: 'Ready', count: count('READY') },
            { value: 'DRAFT', label: 'Draft', count: count('DRAFT') },
            { value: 'ARCHIVED', label: 'Archived', count: count('ARCHIVED') },
          ]}
        />
      </div>
      <div className="panel">
        <DataTable
          columns={columns}
          data={rows}
          loading={plans.loading}
          error={plans.error?.message}
          onRetry={plans.reload}
          searchPlaceholder="Search subject, code or professor…"
          onRowClick={(p) => navigate(`/admin/plans/${p.id}`)}
          empty={
            <EmptyState
              icon={<ClipboardList className="h-5 w-5" />}
              title="No teaching plans yet"
              description="Create or import your first teaching plan to begin semester planning."
              action={<ButtonLink variant="primary" to="/admin/plans/new">Create Teaching Plan</ButtonLink>}
            />
          }
        />
      </div>
    </div>
  )
}
