import type { ColumnDef } from '@tanstack/react-table'
import { FileSpreadsheet, Plus } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from '@/lib/router'
import { EmptyState, InlineAlert } from '@/components/feedback/States'
import { FormField, Select } from '@/components/forms/Fields'
import { PageHeader, useBreadcrumbs } from '@/components/layout/PageHeader'
import { DataTable } from '@/components/tables/DataTable'
import { StatusBadge } from '@/components/ui/Badge'
import { Button, ButtonLink } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { useApi } from '@/hooks/useApi'
import { fmt, IMPORT_MODE_LABEL, IMPORT_STATUS } from '@/lib/status'
import { api, errorMessage, type Paged } from '@/services/api'
import type { PlanBrief } from '@/types/domain'
import type { ImportSessionView } from './types'

export async function startImport(planId: string): Promise<string> {
  const { data } = await api.post<ImportSessionView>('/imports/session', { teaching_plan_id: planId, resume: true })
  return data.id
}

export function ImportsPage() {
  useBreadcrumbs([{ label: 'Teaching Management' }, { label: 'Import Plan' }])
  const navigate = useNavigate()
  const [query] = useSearchParams()
  const saved = query.get('saved')
  const sessions = useApi<Paged<ImportSessionView>>('/imports')
  const [open, setOpen] = useState(false)

  const active = sessions.data?.items.filter((s) => s.status !== 'IMPORTED') ?? []
  const history = sessions.data?.items.filter((s) => s.status === 'IMPORTED') ?? []

  const columns = useMemo<ColumnDef<ImportSessionView>[]>(
    () => [
      { id: 'plan', header: 'Teaching plan', accessorFn: (s) => s.teaching_plan.name, cell: ({ row: { original: s } }) => <div><div className="font-medium text-fg">{s.teaching_plan.subject.name}</div><div className="meta">{s.teaching_plan.semester.name} · Section {s.teaching_plan.section.name} · {s.teaching_plan.professor.full_name}</div></div> },
      { id: 'mode', header: 'Method', accessorFn: (s) => (s.import_mode ? IMPORT_MODE_LABEL[s.import_mode] : 'Not chosen'), cell: ({ row: { original: s } }) => <div>{s.import_mode ? IMPORT_MODE_LABEL[s.import_mode] : <span className="meta">Not chosen</span>}{s.source_name && <div className="meta truncate">{s.source_name}</div>}</div> },
      { id: 'rows', header: 'Rows', accessorFn: (s) => s.summary?.lectures ?? s.row_count, meta: { align: 'right', className: 'tnum' } },
      { id: 'status', header: 'Status', accessorFn: (s) => s.status, cell: ({ getValue }) => <StatusBadge value={getValue<ImportSessionView['status']>()} map={IMPORT_STATUS} /> },
      { id: 'updated', header: 'Last updated', accessorFn: (s) => s.committed_at ?? s.updated_at, cell: ({ getValue }) => <span className="meta whitespace-nowrap">{fmt.dateTime(getValue<string>())}</span> },
    ],
    [],
  )

  return (
    <div>
      <PageHeader
        title="Import Plan"
        description="Bring a semester teaching plan in from Google Sheets or Excel - by full-table paste, column by column, or file upload."
        actions={
          <>
            <ButtonLink to="/admin/plans/new" icon={<Plus className="h-4 w-4" />}>Create plan</ButtonLink>
            <Button variant="primary" icon={<FileSpreadsheet className="h-4 w-4" />} onClick={() => setOpen(true)}>
              Start import
            </Button>
          </>
        }
      />
      {saved && <InlineAlert tone="success" className="mb-4">Draft saved for {saved}. Resume it any time from the list below.</InlineAlert>}

      <div className="panel mb-6">
        <div className="panel-header">
          <span className="panel-title">Imports in progress</span>
          <span className="meta">Drafts are saved automatically at every step.</span>
        </div>
        <DataTable
          columns={columns}
          data={active}
          loading={sessions.loading}
          error={sessions.error?.message}
          onRetry={sessions.reload}
          searchable={false}
          onRowClick={(s) => navigate(`/admin/imports/${s.id}`)}
          empty={<EmptyState icon={<FileSpreadsheet className="h-5 w-5" />} title="No imports in progress" description="Start an import for a draft teaching plan, or create a plan first." action={<Button variant="primary" onClick={() => setOpen(true)}>Start import</Button>} />}
        />
      </div>

      <div className="panel">
        <div className="panel-header"><span className="panel-title">Completed imports</span></div>
        <DataTable columns={columns} data={history} loading={sessions.loading} searchable={false} onRowClick={(s) => navigate(`/admin/plans/${s.teaching_plan.id}`)} empty={<EmptyState title="No completed imports yet" />} />
      </div>

      <StartImportDialog open={open} onClose={() => setOpen(false)} />
    </div>
  )
}

function StartImportDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate()
  const plans = useApi<Paged<PlanBrief & { lecture_count: number }>>(open ? '/teaching-plans' : null, { status: 'DRAFT,READY' })
  const [planId, setPlanId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const drafts = plans.data?.items ?? []
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Start an import"
      description="Lectures are imported into a draft teaching plan."
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            disabled={!planId}
            loading={busy}
            onClick={async () => {
              setBusy(true)
              setError(null)
              try {
                navigate(`/admin/imports/${await startImport(planId)}`)
              } catch (e) {
                setError(errorMessage(e))
                setBusy(false)
              }
            }}
          >
            Continue
          </Button>
        </>
      }
    >
      {error && <InlineAlert tone="danger" className="mb-3">{error}</InlineAlert>}
      {plans.data && drafts.length === 0 ? (
        <EmptyState title="No draft plans" description="Create a teaching plan for the subject and section first." action={<ButtonLink variant="primary" to="/admin/plans/new">Create teaching plan</ButtonLink>} className="py-6" />
      ) : (
        <FormField label="Draft teaching plan" required hint="Only plans that are not yet published are listed.">
          <Select value={planId} onChange={(e) => setPlanId(e.target.value)}>
            <option value="">— Select a plan —</option>
            {drafts.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} · {p.professor.full_name}
              </option>
            ))}
          </Select>
        </FormField>
      )}
    </Dialog>
  )
}
