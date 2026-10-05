import type { ColumnDef } from '@tanstack/react-table'
import { MoreHorizontal, Pencil, Plus, Trash2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { InlineAlert, useToast } from '@/components/feedback/States'
import { Checkbox, FormField, Input, Select } from '@/components/forms/Fields'
import { DataTable } from '@/components/tables/DataTable'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { Menu } from '@/components/ui/Menu'
import { useApi } from '@/hooks/useApi'
import { api, errorMessage, type Paged } from '@/services/api'

export type FieldSpec = {
  name: string
  label: string
  type?: 'text' | 'date' | 'number' | 'select' | 'checkbox'
  required?: boolean
  options?: { value: string; label: string }[]
  hint?: string
  placeholder?: string
  span?: boolean
}

/** Table + create/edit dialog for one academic master-data entity. */
export function EntityManager<T extends { id: string }>({
  title,
  endpoint,
  columns,
  fields,
  toForm,
  canManage,
  addLabel,
  params,
  blank,
  deletable,
}: {
  title: string
  endpoint: string
  columns: ColumnDef<T, unknown>[]
  fields: FieldSpec[]
  toForm: (row: T) => Record<string, unknown>
  canManage: boolean
  addLabel: string
  params?: Record<string, unknown>
  blank?: Record<string, unknown>
  deletable?: boolean
}) {
  const data = useApi<Paged<T>>(endpoint, params)
  const [editing, setEditing] = useState<T | 'new' | null>(null)
  const cols = useMemo<ColumnDef<T, unknown>[]>(
    () =>
      canManage
        ? [
            ...columns,
            {
              id: 'actions',
              header: '',
              enableSorting: false,
              cell: ({ row: { original } }) => (
                <Menu label="Actions" trigger={(p) => <Button size="icon" variant="ghost" aria-label="Actions" {...p}><MoreHorizontal className="h-4 w-4" /></Button>} items={[{ label: 'Edit', icon: <Pencil className="h-3.5 w-3.5" />, onSelect: () => setEditing(original) }, ...(deletable ? [{ label: 'Delete', icon: <Trash2 className="h-3.5 w-3.5" />, onSelect: () => { void api.delete(`${endpoint}/${original.id}`).then(() => data.reload(true)) } }] : [])]} />
              ),
            },
          ]
        : columns,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [columns, canManage, deletable, endpoint],
  )
  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">{title}</span>
        {canManage && (
          <Button size="sm" variant="primary" icon={<Plus className="h-3.5 w-3.5" />} onClick={() => setEditing('new')}>
            {addLabel}
          </Button>
        )}
      </div>
      <DataTable columns={cols} data={data.data?.items} loading={data.loading} error={data.error?.message} onRetry={data.reload} searchPlaceholder={`Search ${title.toLowerCase()}…`} />
      {editing && (
        <EntityDialog
          title={editing === 'new' ? addLabel : `Edit ${title.replace(/s$/, '').toLowerCase()}`}
          fields={fields}
          initial={editing === 'new' ? blank ?? {} : toForm(editing)}
          onClose={() => setEditing(null)}
          onSubmit={async (values) => {
            if (editing === 'new') await api.post(endpoint, values)
            else await api.put(`${endpoint}/${editing.id}`, values)
            setEditing(null)
            void data.reload(true)
          }}
        />
      )}
    </div>
  )
}

function EntityDialog({ title, fields, initial, onClose, onSubmit }: { title: string; fields: FieldSpec[]; initial: Record<string, unknown>; onClose: () => void; onSubmit: (v: Record<string, unknown>) => Promise<void> }) {
  const toast = useToast()
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<Record<string, unknown>>({ defaultValues: initial })
  const [error, setError] = useState<string | null>(null)
  const submit = handleSubmit(async (raw) => {
    setError(null)
    const values: Record<string, unknown> = {}
    for (const f of fields) {
      const v = raw[f.name]
      if (f.type === 'number') values[f.name] = v === '' || v === undefined || v === null ? null : Number(v)
      else if (f.type === 'checkbox') values[f.name] = !!v
      else values[f.name] = v === '' ? null : v
    }
    try {
      await onSubmit(values)
      toast('success', 'Saved.')
    } catch (e) {
      setError(errorMessage(e))
    }
  })
  return (
    <Dialog open onClose={onClose} title={title} footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={isSubmitting} onClick={submit}>Save</Button></>}>
      <form onSubmit={submit} noValidate className="grid gap-4 sm:grid-cols-2">
        {error && <InlineAlert tone="danger" className="sm:col-span-2">{error}</InlineAlert>}
        {fields.map((f) =>
          f.type === 'checkbox' ? (
            <Checkbox key={f.name} className="sm:col-span-2" label={f.label} description={f.hint} {...register(f.name)} />
          ) : (
            <FormField key={f.name} label={f.label} required={f.required} hint={f.hint} error={errors[f.name] ? `${f.label} is required.` : undefined} className={f.span ? 'sm:col-span-2' : ''} htmlFor={f.name}>
              {f.type === 'select' ? (
                <Select id={f.name} invalid={!!errors[f.name]} {...register(f.name, { required: f.required })}>
                  <option value="">Select…</option>
                  {f.options?.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </Select>
              ) : (
                <Input id={f.name} type={f.type ?? 'text'} placeholder={f.placeholder} invalid={!!errors[f.name]} {...register(f.name, { required: f.required })} />
              )}
            </FormField>
          ),
        )}
        <button type="submit" className="hidden" />
      </form>
    </Dialog>
  )
}
