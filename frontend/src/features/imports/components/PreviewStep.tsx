import type { ColumnDef } from '@tanstack/react-table'
import { MoreHorizontal, Pencil, Trash2, Undo2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate } from '@/lib/router'
import { InlineAlert } from '@/components/feedback/States'
import { FormField, Input, Select, Textarea, Segmented } from '@/components/forms/Fields'
import { DataTable } from '@/components/tables/DataTable'
import { StatusBadge, Tag } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { DefinitionList } from '@/components/ui/Display'
import { Dialog } from '@/components/ui/Dialog'
import { Menu } from '@/components/ui/Menu'
import { fmt, LECTURE_TYPE_LABEL, ROW_STATUS } from '@/lib/status'
import { useApi } from '@/hooks/useApi'
import { PROFESSOR_OPTIONS, professorLabel, professorParams } from '@/lib/api/users'
import { api, errorMessage, type Paged } from '@/services/api'
import type { ManagedUser } from '@/types/domain'
import { cn } from '@/utils/cn'
import type { ImportSessionView, PreviewData, PreviewRow } from '../types'

type Filter = 'ALL' | 'ERROR' | 'WARNING' | 'VALID' | 'EXCLUDED'

const excluded = (r: PreviewRow) => r.status === 'REMOVED' || r.status === 'EMPTY'

export function PreviewStep({ session, preview, initialFilter, onPreview, onBack, onContinue }: { session: ImportSessionView; preview: PreviewData; initialFilter?: string; onPreview: (s: ImportSessionView, p: PreviewData) => void; onBack: () => void; onContinue: () => void }) {
  const navigate = useNavigate()
  const [filter, setFilter] = useState<Filter>((initialFilter as Filter) || 'ALL')
  const [editing, setEditing] = useState<PreviewRow | null>(null)
  const [error, setError] = useState<string | null>(null)
  const plan = session.teaching_plan
  const s = preview.summary

  const rows = useMemo(() => {
    const all = preview.rows
    switch (filter) {
      case 'ERROR': return all.filter((r) => r.status === 'ERROR')
      case 'WARNING': return all.filter((r) => r.status === 'WARNING')
      case 'VALID': return all.filter((r) => r.status === 'VALID')
      case 'EXCLUDED': return all.filter((r) => r.status === 'EMPTY' || r.status === 'REMOVED')
      default: return all
    }
  }, [preview.rows, filter])

  const setRemoved = async (row: PreviewRow, removed: boolean) => {
    setError(null)
    try {
      const { data } = await api.put<{ session: ImportSessionView; preview: PreviewData }>(`/imports/${session.id}/rows/${row.index}/removed`, { removed })
      onPreview(data.session, data.preview)
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  const columns = useMemo<ColumnDef<PreviewRow>[]>(
    () => [
      { id: 'row', header: 'Row', accessorFn: (r) => r.row_number, meta: { className: 'tnum text-fg-muted w-12', align: 'right' } },
      { id: 'lecture_no', header: 'Lecture', accessorFn: (r) => r.values.lecture_no ?? r.raw.lecture_no ?? '', cell: ({ row: { original: r } }) => <span className="tnum font-medium text-fg">{r.values.lecture_no ?? (excluded(r) ? r.raw.lecture_no || '—' : <span className="text-danger">{r.raw.lecture_no || '—'}</span>)}</span> },
      { id: 'type', header: 'Type', accessorFn: (r) => r.values.lecture_type ?? '', cell: ({ getValue }) => LECTURE_TYPE_LABEL[getValue<string>()] ?? '—' },
      { id: 'unit', header: 'Unit', accessorFn: (r) => r.values.unit_no ?? '', cell: ({ getValue }) => <span className="tnum">{getValue<number>() || '—'}</span> },
      {
        id: 'topic',
        header: 'Topic',
        accessorFn: (r) => `${r.values.content_topic ?? ''} ${(r.values.subtopics ?? []).join(' ')}`,
        cell: ({ row: { original: r } }) => (
          <div className="min-w-[240px] max-w-[420px]">
            {excluded(r) ? (
              <div className="text-fg-label line-through decoration-line-strong">{r.raw.content_topic || 'Empty row'}</div>
            ) : (
              <div className={cn('font-medium', r.values.content_topic ? 'text-fg' : 'text-danger')}>{r.values.content_topic ?? 'Missing topic'}</div>
            )}
            {!!r.values.subtopics?.length && <div className="meta mt-0.5 line-clamp-2">{r.values.subtopics.join(' · ')}</div>}
          </div>
        ),
      },
      { id: 'bloom', header: 'Bloom', accessorFn: (r) => r.values.blooms_taxonomy ?? '', cell: ({ getValue }) => (getValue<string>() ? <Tag>{getValue<string>()}</Tag> : '—') },
      { id: 'subs', header: 'Subtopics', accessorFn: (r) => r.values.subtopics?.length ?? 0, meta: { align: 'right', className: 'tnum' } },
      {
        id: 'date',
        header: 'Planned',
        accessorFn: (r) => r.values.planned_date ?? '',
        cell: ({ row: { original: r } }) => (
          <div className="whitespace-nowrap">
            <div>{r.values.planned_date ? fmt.date(r.values.planned_date) : r.raw.planned_date ? <span className={excluded(r) ? 'text-fg-muted' : 'text-danger'}>{r.raw.planned_date}</span> : '—'}</div>
            {r.values.planned_start_time && <div className="meta">{fmt.timeRange(r.values.planned_start_time, r.values.planned_end_time)}</div>}
          </div>
        ),
      },
      {
        id: 'professor',
        header: 'Professor · Room',
        accessorFn: (r) => r.values.professor_name ?? r.raw.professor_employee_id ?? '',
        cell: ({ row: { original: r } }) => {
          if (excluded(r)) return <span className="text-fg-muted">—</span>
          const unmatched = !!r.values.professor_employee_id && !r.values.professor_id
          return (
            <div className="min-w-[150px] whitespace-nowrap">
              {unmatched ? (
                <>
                  <div className="font-medium text-danger">Professor not found</div>
                  <div className="meta font-mono">{r.values.professor_employee_id}</div>
                  <Button size="sm" className="mt-1" onClick={() => setEditing(r)}>Map Professor</Button>
                </>
              ) : (
                <>
                  <div className="text-fg-soft">{r.values.professor_id && <span className="text-primary" aria-hidden>✓ </span>}{r.values.professor_name ?? plan.professor.full_name}</div>
                  <div className="meta">{r.values.professor_id ? r.values.professor_employee_id : 'Plan professor'}{r.values.room ? ` · Room ${r.values.room}` : ''}</div>
                </>
              )}
            </div>
          )
        },
      },
      {
        id: 'status',
        header: 'Validation',
        accessorFn: (r) => r.status,
        cell: ({ row: { original: r } }) => (
          <div className="min-w-[200px]">
            <div className="flex items-center gap-1.5">
              <StatusBadge value={r.status} map={ROW_STATUS} />
              {r.edited && <Tag>Edited</Tag>}
            </div>
            {r.issues.slice(0, 3).map((i, n) => (
              <p key={n} className={cn('mt-1 text-[12px] leading-snug', i.level === 'ERROR' ? 'text-danger' : 'text-warning')}>
                {i.message}
              </p>
            ))}
            {r.issues.length > 3 && <p className="meta">+{r.issues.length - 3} more</p>}
          </div>
        ),
      },
      {
        id: 'actions',
        header: '',
        enableSorting: false,
        cell: ({ row: { original: r } }) => (
          <Menu
            label="Row actions"
            trigger={(p) => (
              <Button size="icon" variant="ghost" aria-label={`Actions for row ${r.row_number}`} {...p}>
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            )}
            items={
              r.status === 'REMOVED'
                ? [{ label: 'Restore row', icon: <Undo2 className="h-3.5 w-3.5" />, onSelect: () => void setRemoved(r, false) }]
                : [
                    { label: 'Edit row', icon: <Pencil className="h-3.5 w-3.5" />, onSelect: () => setEditing(r) },
                    { label: 'Remove row', icon: <Trash2 className="h-3.5 w-3.5" />, danger: true, onSelect: () => void setRemoved(r, true) },
                  ]
            }
          />
        ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [session.id],
  )

  const counts = {
    ALL: preview.rows.length,
    ERROR: s.errors,
    WARNING: s.warnings,
    VALID: s.valid,
    EXCLUDED: s.empty + s.removed,
  }

  return (
    <div className="space-y-4">
      <div className="panel">
        <div className="panel-header">
          <span className="panel-title">Teaching Plan Import Preview</span>
          <span className="meta">{session.source_name ?? (session.import_mode === 'COLUMN_WISE' ? 'Column-by-column paste' : 'Clipboard paste')}</span>
        </div>
        <div className="grid gap-4 p-4 lg:grid-cols-[1fr_auto]">
          <DefinitionList
            columns={4}
            items={[
              { label: 'Subject', value: `${plan.subject.code} · ${plan.subject.name}` },
              { label: 'Semester · Section', value: `${plan.semester.name} · Section ${plan.section.name}` },
              { label: 'Professor', value: plan.professor.full_name },
              { label: 'Academic Year', value: plan.academic_year.name },
            ]}
          />
          <div className="flex flex-wrap gap-x-5 gap-y-1 text-[13px] text-fg-secondary lg:justify-end">
            <span className="tnum"><b className="text-fg">{s.lectures}</b> lectures</span>
            <span className="tnum"><b className="text-fg">{s.units}</b> units</span>
            <span className="tnum"><b className="text-fg">{s.columns}</b> columns</span>
            <span className="tnum"><b className="text-primary">{s.valid}</b> valid</span>
            <span className="tnum"><b className="text-warning">{s.warnings}</b> warnings</span>
            <span className="tnum"><b className={s.errors ? 'text-danger' : 'text-fg'}>{s.errors}</b> errors</span>
          </div>
        </div>
      </div>

      {error && <InlineAlert tone="danger">{error}</InlineAlert>}
      {preview.session_issues.filter((i) => i.level === 'ERROR').map((i, n) => (
        <InlineAlert key={n} tone="danger">{i.message}</InlineAlert>
      ))}

      <div className="panel">
        <DataTable
          columns={columns}
          data={rows}
          pageSize={50}
          searchPlaceholder="Search topic, subtopic, row…"
          maxHeight="max-h-[640px]"
          rowClassName={(r) => cn(r.original.status === 'ERROR' && 'bg-danger/5', (r.original.status === 'REMOVED' || r.original.status === 'EMPTY') && 'opacity-55')}
          toolbar={
            <Segmented<Filter>
              size="sm"
              ariaLabel="Filter rows"
              value={filter}
              onChange={setFilter}
              options={[
                { value: 'ALL', label: 'All', count: counts.ALL },
                { value: 'ERROR', label: 'Errors', count: counts.ERROR },
                { value: 'WARNING', label: 'Warnings', count: counts.WARNING },
                { value: 'VALID', label: 'Valid', count: counts.VALID },
                { value: 'EXCLUDED', label: 'Excluded', count: counts.EXCLUDED },
              ]}
            />
          }
        />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button onClick={onBack}>Back</Button>
        <div className="flex items-center gap-2">
          <Button onClick={() => navigate(`/admin/imports?saved=${encodeURIComponent(plan.name)}`)}>Save draft &amp; exit</Button>
          <Button variant="primary" disabled={!preview.can_commit} onClick={onContinue}>
            Confirm &amp; publish
          </Button>
        </div>
      </div>

      {editing && <EditRowDialog session={session} row={editing} onClose={() => setEditing(null)} onSaved={(se, p) => { onPreview(se, p); setEditing(null) }} />}
    </div>
  )
}

const EDIT_FIELDS: { key: string; label: string; placeholder?: string }[] = [
  { key: 'lecture_no', label: 'Lecture number' },
  { key: 'unit_no', label: 'Unit' },
  { key: 'content_topic', label: 'Content topic' },
  { key: 'blooms_taxonomy', label: "Bloom's level", placeholder: 'K1–K6' },
  { key: 'planned_date', label: 'Planned date', placeholder: 'DD/MM/YYYY' },
  { key: 'planned_start_time', label: 'Start time', placeholder: '10:00' },
  { key: 'planned_end_time', label: 'End time', placeholder: '11:00' },
  { key: 'room', label: 'Room', placeholder: 'Plan default' },
]

function EditRowDialog({ session, row, onClose, onSaved }: { session: ImportSessionView; row: PreviewRow; onClose: () => void; onSaved: (s: ImportSessionView, p: PreviewData) => void }) {
  const [values, setValues] = useState<Record<string, string>>(() => {
    const v: Record<string, string> = {}
    for (const f of EDIT_FIELDS) v[f.key] = row.raw[f.key] ?? ''
    v.lecture_type = row.values.lecture_type ?? 'THEORY'
    v.subtopics = (row.values.subtopics ?? []).join('\n')
    v.professor_employee_id = row.values.professor_employee_id ?? ''
    return v
  })
  // "Map Professor": the row is pointed at an existing professor account by employee ID. No account is ever created here.
  const professors = useApi<Paged<ManagedUser>>(PROFESSOR_OPTIONS, professorParams(session.teaching_plan.subject.id)).data?.items.filter((p) => p.employee_id) ?? []
  const unknown = !!values.professor_employee_id && !professors.some((p) => p.employee_id?.toLowerCase() === values.professor_employee_id.toLowerCase())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const issueFor = (k: string) => row.issues.find((i) => i.field === k)

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      const body: Record<string, unknown> = { ...values, subtopics: values.subtopics.split('\n').map((x) => x.trim()).filter(Boolean) }
      const { data } = await api.put<{ session: ImportSessionView; preview: PreviewData }>(`/imports/${session.id}/rows/${row.index}`, { values: body })
      onSaved(data.session, data.preview)
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
      title={`Edit row ${row.row_number}`}
      description="Changes apply to this import only. The values are validated again when you save."
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={save}>
            Save row
          </Button>
        </>
      }
    >
      {error && <InlineAlert tone="danger" className="mb-4">{error}</InlineAlert>}
      <div className="grid gap-4 sm:grid-cols-2">
        {EDIT_FIELDS.map((f) => (
          <FormField key={f.key} label={f.label} error={issueFor(f.key)?.level === 'ERROR' ? issueFor(f.key)!.message : undefined} hint={issueFor(f.key)?.level === 'WARNING' ? issueFor(f.key)!.message : undefined} className={f.key === 'content_topic' ? 'sm:col-span-2' : ''}>
            <Input value={values[f.key]} placeholder={f.placeholder} invalid={issueFor(f.key)?.level === 'ERROR'} onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))} />
          </FormField>
        ))}
        <FormField label="Lecture type">
          <Select value={values.lecture_type} onChange={(e) => setValues((v) => ({ ...v, lecture_type: e.target.value }))}>
            {Object.entries(LECTURE_TYPE_LABEL).map(([k, l]) => (
              <option key={k} value={k}>{l}</option>
            ))}
          </Select>
        </FormField>
        <FormField label="Professor" className="sm:col-span-2"
          error={issueFor('professor_employee_id')?.level === 'ERROR' && unknown ? `No professor account has employee ID “${values.professor_employee_id}”. Choose the professor for this lecture.` : issueFor('professor_employee_id')?.level === 'ERROR' ? issueFor('professor_employee_id')!.message : undefined}
          hint="Only active professor accounts from User Management can be chosen.">
          <Select value={unknown ? '__unknown' : values.professor_employee_id} invalid={unknown} onChange={(e) => setValues((v) => ({ ...v, professor_employee_id: e.target.value }))}>
            {unknown && <option value="__unknown" disabled>Not found: {values.professor_employee_id}</option>}
            <option value="">{session.teaching_plan.professor.full_name} · plan professor</option>
            {professors.map((p) => <option key={p.id} value={p.employee_id!}>{professorLabel(p)}</option>)}
          </Select>
        </FormField>
        <FormField label="Subtopics" hint="One subtopic per line, in teaching order." className="sm:col-span-2">
          <Textarea rows={4} value={values.subtopics} onChange={(e) => setValues((v) => ({ ...v, subtopics: e.target.value }))} />
        </FormField>
      </div>
    </Dialog>
  )
}
