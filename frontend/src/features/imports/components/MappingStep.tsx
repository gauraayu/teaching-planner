import { ArrowRight, CheckCircle2, Circle } from 'lucide-react'
import { useState } from 'react'
import { InlineAlert } from '@/components/feedback/States'
import { Checkbox } from '@/components/forms/Fields'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { api, errorMessage } from '@/services/api'
import { cn } from '@/utils/cn'
import type { ColumnMapping, FieldDef, ImportColumn, ImportSessionView } from '../types'

const FILLABLE = new Set(['unit_no', 'lecture_type', 'planned_date', 'blooms_taxonomy', 'planned_start_time', 'planned_end_time'])

function MappingBadge({ m }: { m: ColumnMapping | null }) {
  if (!m) return <Badge tone="warning">Needs review</Badge>
  if (m.status === 'MAPPED') return <Badge tone="success">{m.method === 'MANUAL' ? 'Mapped manually' : 'Mapped'}</Badge>
  if (m.status === 'SUGGESTED') return <Badge tone="warning">Suggested · {m.confidence}%</Badge>
  if (m.status === 'IGNORED') return <Badge tone="neutral">Ignored</Badge>
  return <Badge tone="warning">Needs review</Badge>
}

export function MappingStep({ session, fields, onSession, onBack, onContinue }: { session: ImportSessionView; fields: FieldDef[]; onSession: (s: ImportSessionView) => void; onBack: () => void; onContinue: () => void }) {
  const [busyKey, setBusyKey] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const columns = session.columns ?? []
  const label = (key: string | null) => fields.find((f) => f.key === key)?.label ?? key

  const update = async (key: string, body: Record<string, unknown>) => {
    setBusyKey(key)
    setError(null)
    try {
      const { data } = await api.put<ImportSessionView>(`/imports/${session.id}/mapping`, { columns: { [key]: body } })
      onSession(data)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusyKey(null)
    }
  }

  const run = async (fn: () => Promise<{ data: ImportSessionView }>, key: string) => {
    setBusyKey(key)
    setError(null)
    try {
      onSession((await fn()).data)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusyKey(null)
    }
  }

  const counts = {
    mapped: columns.filter((c) => c.mapping?.status === 'MAPPED').length,
    review: columns.filter((c) => c.mapping?.status === 'NEEDS_REVIEW' || c.mapping?.status === 'SUGGESTED' || !c.mapping).length,
    ignored: columns.filter((c) => c.mapping?.status === 'IGNORED').length,
    suggested: columns.filter((c) => c.mapping?.status === 'SUGGESTED').length,
  }
  const mappedFields = new Set(columns.filter((c) => c.mapping?.status === 'MAPPED').map((c) => c.mapping!.field))
  const required = fields.filter((f) => f.required)
  const blocked = counts.review > 0 || required.some((f) => !mappedFields.has(f.key))

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-fg-secondary">
          <span className="tnum"><b className="text-fg">{columns.length}</b> columns</span>
          <span className="tnum"><b className="text-primary">{counts.mapped}</b> mapped</span>
          <span className="tnum"><b className={counts.review ? 'text-warning' : 'text-fg'}>{counts.review}</b> need review</span>
          <span className="tnum"><b className="text-fg">{counts.ignored}</b> ignored</span>
          <span className="tnum"><b className="text-fg">{session.row_count}</b> data rows</span>
        </div>
        <div className="flex items-center gap-3">
          <Checkbox
            label="First row contains column headers"
            checked={!!session.has_header}
            disabled={busyKey !== null}
            onChange={(e) => void run(() => api.put(`/imports/${session.id}/header`, { has_header: e.target.checked }), '__header')}
          />
          {counts.suggested > 0 && (
            <Button size="sm" loading={busyKey === '__confirm'} onClick={() => void run(() => api.post(`/imports/${session.id}/mapping/confirm-suggestions`), '__confirm')}>
              Confirm {counts.suggested} suggestion{counts.suggested > 1 ? 's' : ''}
            </Button>
          )}
        </div>
      </div>

      {error && <InlineAlert tone="danger">{error}</InlineAlert>}

      <div className="panel overflow-hidden">
        <div className="overflow-x-auto scroll-thin">
          <table className="w-full min-w-[860px] text-[13px]">
            <thead>
              <tr className="border-b border-line bg-surface-2 text-left text-[11.5px] font-semibold tracking-wide text-fg-label uppercase">
                <th className="w-[26%] px-4 py-2">Spreadsheet column</th>
                <th className="w-[28%] px-3 py-2">Sample values</th>
                <th className="w-8" />
                <th className="w-[26%] px-3 py-2">Portal field</th>
                <th className="px-3 py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {columns.map((c) => (
                <MappingRow key={c.key} column={c} fields={fields} label={label} busy={busyKey === c.key} onChange={(body) => void update(c.key, body)} />
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel flex flex-wrap items-center gap-x-5 gap-y-2 px-4 py-3 text-[13px]">
        <span className="font-medium text-fg-soft">Required fields</span>
        {required.map((f) => (
          <span key={f.key} className="inline-flex items-center gap-1.5">
            {mappedFields.has(f.key) ? <CheckCircle2 className="h-4 w-4 text-primary" aria-label="Mapped" /> : <Circle className="h-4 w-4 text-fg-faint" aria-label="Not mapped" />}
            {f.label}
          </span>
        ))}
        <span className="meta">Recommended: Unit Number, Bloom's Taxonomy, Planned Date, Subtopics.</span>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button onClick={onBack}>Back</Button>
        <div className="flex items-center gap-3">
          {blocked && <span className="meta">Resolve every column and map the required fields to continue.</span>}
          <Button variant="primary" disabled={blocked} onClick={onContinue}>
            Continue to validation <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}

function MappingRow({ column: c, fields, label, busy, onChange }: { column: ImportColumn; fields: FieldDef[]; label: (k: string | null) => string | null; busy: boolean; onChange: (body: Record<string, unknown>) => void }) {
  const m = c.mapping
  const value = m?.status === 'IGNORED' ? '__ignore' : m?.field ?? ''
  const needsAttention = !m || m.status === 'NEEDS_REVIEW' || m.status === 'SUGGESTED'
  return (
    <tr className={cn('border-b border-line-subtle align-top last:border-0', needsAttention && 'bg-warning/5')}>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          {c.letter && <span className="flex h-5 min-w-5 items-center justify-center rounded-sm bg-surface-3 px-1 text-[11px] font-semibold text-fg-label">{c.letter}</span>}
          <span className="font-medium text-fg">{c.header || <em className="text-fg-muted">No header</em>}</span>
        </div>
        <div className="meta mt-0.5 tnum">
          {c.non_empty_count} of {c.value_count} cells filled
        </div>
      </td>
      <td className="px-3 py-3">
        <div className="flex flex-wrap gap-1">
          {c.samples.length === 0 && <span className="meta">All blank</span>}
          {c.samples.slice(0, 3).map((s, i) => (
            <span key={i} className="max-w-[180px] truncate rounded-sm bg-surface-3 px-1.5 py-0.5 text-[12px] text-fg-soft" title={s}>
              {s}
            </span>
          ))}
        </div>
      </td>
      <td className="pt-3.5 text-fg-faint">
        <ArrowRight className="h-4 w-4" aria-hidden />
      </td>
      <td className="px-3 py-3">
        <select
          aria-label={`Portal field for ${c.header || c.letter}`}
          className={cn('field h-8 text-[13px]', needsAttention && 'border-warning')}
          value={value}
          disabled={busy}
          onChange={(e) => {
            const v = e.target.value
            onChange(v === '__ignore' ? { ignore: true } : { field: v || null })
          }}
        >
          <option value="">— Select field —</option>
          {fields.map((f) => (
            <option key={f.key} value={f.key}>
              {f.label}
              {f.required ? ' *' : ''}
            </option>
          ))}
          <option value="__ignore">Ignore this column</option>
        </select>
        {m?.field === 'subtopic' && <div className="meta mt-1">Subtopic order {m.order}</div>}
        {m?.status === 'MAPPED' && m.field && FILLABLE.has(m.field) && c.non_empty_count < c.value_count && (
          <label className="mt-1.5 flex items-center gap-1.5 text-[12px] text-fg-secondary">
            <input type="checkbox" className="accent-primary" checked={!!m.fill_down} disabled={busy} onChange={(e) => onChange({ fill_down: e.target.checked })} />
            Fill blank cells from the row above
          </label>
        )}
      </td>
      <td className="px-3 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <MappingBadge m={m} />
          {m?.status === 'SUGGESTED' && (
            <Button size="sm" variant="link" onClick={() => onChange({ confirm: true })} disabled={busy}>
              Confirm
            </Button>
          )}
          {m?.status === 'NEEDS_REVIEW' && m.suggestion && (
            <Button size="sm" variant="link" onClick={() => onChange({ field: m.suggestion })} disabled={busy}>
              Use {label(m.suggestion)}
            </Button>
          )}
        </div>
        {m?.note && <p className="meta mt-1 leading-snug">{m.note}</p>}
      </td>
    </tr>
  )
}
