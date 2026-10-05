import type { ColumnDef } from '@tanstack/react-table'
import { Plus } from 'lucide-react'
import { useState } from 'react'
import { InlineAlert, useToast } from '@/components/feedback/States'
import { FormField, Select } from '@/components/forms/Fields'
import { PageHeader, useBreadcrumbs } from '@/components/layout/PageHeader'
import { DataTable } from '@/components/tables/DataTable'
import { Badge, Tag } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { useAuth } from '@/features/auth/AuthContext'
import { useApi } from '@/hooks/useApi'
import { api, errorMessage, type Paged } from '@/services/api'
import type { ManagedUser, UserBrief } from '@/types/domain'
import { PROFESSOR_OPTIONS, professorParams } from '@/lib/api/users'
import { EntityManager } from './EntityManager'

type Subject = { id: string; code: string; name: string; short_name: string | null; branch_id: string; branch: string; branch_code: string; semester_number: number; credits: number | null; is_active: boolean }

export function SubjectsPage() {
  useBreadcrumbs([{ label: 'Academic Management' }, { label: 'Subjects' }])
  const { can } = useAuth()
  const branches = useApi<Paged<{ id: string; code: string; name: string }>>('/branches').data?.items ?? []
  return (
    <div>
      <PageHeader title="Subjects" description="Course catalogue by branch and semester." />
      <EntityManager<Subject>
        title="Subjects"
        addLabel="Add subject"
        endpoint="/subjects"
        canManage={can('academic.manage')}
        columns={[
          { header: 'Code', accessorKey: 'code', cell: ({ getValue }) => <Tag>{getValue<string>()}</Tag> },
          { header: 'Subject', accessorKey: 'name', cell: ({ row: { original: s } }) => <div><div className="font-medium text-fg">{s.name}</div>{s.short_name && <div className="meta">{s.short_name}</div>}</div> },
          { header: 'Branch', accessorKey: 'branch_code' },
          { header: 'Semester', accessorKey: 'semester_number', meta: { className: 'tnum' } },
          { header: 'Credits', accessorKey: 'credits', meta: { align: 'right', className: 'tnum' } },
          { header: 'Status', accessorKey: 'is_active', cell: ({ getValue }) => (getValue<boolean>() ? <Badge tone="success">Active</Badge> : <Badge>Inactive</Badge>) },
        ] as ColumnDef<Subject, unknown>[]}
        fields={[
          { name: 'code', label: 'Subject code', required: true, placeholder: 'CS506' },
          { name: 'short_name', label: 'Short name', placeholder: 'DSA' },
          { name: 'name', label: 'Subject name', required: true, span: true },
          { name: 'branch_id', label: 'Branch', type: 'select', required: true, options: branches.map((b) => ({ value: b.id, label: `${b.code} · ${b.name}` })) },
          { name: 'semester_number', label: 'Semester number', type: 'number', required: true },
          { name: 'credits', label: 'Credits', type: 'number' },
        ]}
        toForm={(s) => ({ code: s.code, short_name: s.short_name, name: s.name, branch_id: s.branch_id, semester_number: s.semester_number, credits: s.credits })}
      />
    </div>
  )
}

type Assignment = { id: string; professor: UserBrief; subject: { id: string; code: string; name: string }; section: { id: string; name: string; branch_code: string; semester: string }; is_primary: boolean }

export function FacultyMappingPage() {
  useBreadcrumbs([{ label: 'Academic Management' }, { label: 'Faculty Mapping' }])
  const { can } = useAuth()
  const toast = useToast()
  const data = useApi<Paged<Assignment>>('/faculty-assignments')
  const professors = useApi<Paged<ManagedUser>>(PROFESSOR_OPTIONS, professorParams()).data?.items ?? []
  const subjects = useApi<Paged<{ id: string; code: string; name: string; branch_id: string; semester_number: number }>>('/subjects').data?.items ?? []
  const sections = useApi<Paged<{ id: string; name: string; branch_id: string; branch_code: string; semester: string }>>('/sections').data?.items ?? []
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ professor_id: '', subject_id: '', section_id: '' })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const subject = subjects.find((s) => s.id === form.subject_id)
  const eligibleSections = sections.filter((s) => !subject || s.branch_id === subject.branch_id)

  const columns: ColumnDef<Assignment, unknown>[] = [
    { header: 'Professor', accessorFn: (a) => a.professor.full_name, cell: ({ row: { original: a } }) => <div><div className="font-medium text-fg">{a.professor.full_name}</div><div className="meta">{a.professor.designation}</div></div> },
    { header: 'Subject', accessorFn: (a) => `${a.subject.code} ${a.subject.name}`, cell: ({ row: { original: a } }) => <span><Tag>{a.subject.code}</Tag> {a.subject.name}</span> },
    { header: 'Class', accessorFn: (a) => `${a.section.branch_code} ${a.section.semester} ${a.section.name}`, cell: ({ row: { original: a } }) => `${a.section.branch_code} · ${a.section.semester} · Section ${a.section.name}` },
    { header: 'Role', accessorKey: 'is_primary', cell: ({ getValue }) => (getValue<boolean>() ? 'Primary' : 'Supporting') },
  ]

  return (
    <div>
      <PageHeader
        title="Faculty Mapping"
        description="Who teaches which subject to which section. Mappings are also created automatically when a plan is published."
        actions={can('academic.manage') && <Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setOpen(true)}>Map faculty</Button>}
      />
      <div className="panel">
        <DataTable columns={columns} data={data.data?.items} loading={data.loading} error={data.error?.message} onRetry={data.reload} searchPlaceholder="Search professor or subject…" />
      </div>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title="Map faculty to a subject"
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              variant="primary"
              loading={busy}
              disabled={!form.professor_id || !form.subject_id || !form.section_id}
              onClick={async () => {
                setBusy(true)
                setError(null)
                try {
                  await api.post('/faculty-assignments', form)
                  toast('success', 'Faculty mapped.')
                  setOpen(false)
                  setForm({ professor_id: '', subject_id: '', section_id: '' })
                  void data.reload(true)
                } catch (e) {
                  setError(errorMessage(e))
                } finally {
                  setBusy(false)
                }
              }}
            >
              Save mapping
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {error && <InlineAlert tone="danger">{error}</InlineAlert>}
          <FormField label="Professor" required>
            <Select value={form.professor_id} onChange={(e) => setForm((f) => ({ ...f, professor_id: e.target.value }))}>
              <option value="">Select…</option>
              {professors.map((p) => <option key={p.id} value={p.id}>{p.full_name}</option>)}
            </Select>
          </FormField>
          <FormField label="Subject" required>
            <Select value={form.subject_id} onChange={(e) => setForm((f) => ({ ...f, subject_id: e.target.value, section_id: '' }))}>
              <option value="">Select…</option>
              {subjects.map((s) => <option key={s.id} value={s.id}>{s.code} · {s.name}</option>)}
            </Select>
          </FormField>
          <FormField label="Section" required hint={subject ? 'Only sections of the subject’s branch are listed.' : undefined}>
            <Select value={form.section_id} onChange={(e) => setForm((f) => ({ ...f, section_id: e.target.value }))} disabled={!subject}>
              <option value="">Select…</option>
              {eligibleSections.map((s) => <option key={s.id} value={s.id}>{s.branch_code} · {s.semester} · Section {s.name}</option>)}
            </Select>
          </FormField>
        </div>
      </Dialog>
    </div>
  )
}
