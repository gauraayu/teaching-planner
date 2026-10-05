import { AlertTriangle, CheckCircle2, Circle, MoreHorizontal, RotateCcw, Undo2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { InlineAlert } from '@/components/feedback/States'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { Menu } from '@/components/ui/Menu'
import { api, errorMessage } from '@/services/api'
import { cn } from '@/utils/cn'
import { parseColumn } from '../parsers/tsv'
import type { FieldDef, ImportColumn, ImportSessionView, MismatchResult } from '../types'
import { PasteArea } from './PasteArea'

type Choice = { key: string; field: string; order?: number; label: string; disabled: boolean }

export function ColumnWorkspace({
  session,
  fields,
  onSession,
  onStage,
  onBack,
  onContinue,
}: {
  session: ImportSessionView
  fields: FieldDef[]
  onSession: (s: ImportSessionView) => void
  onStage: (stage: 'field' | 'paste' | 'columns') => void
  onBack: () => void
  onContinue: () => void
}) {
  const columns = session.columns ?? []
  const [choice, setChoice] = useState<string>('')
  const [replacing, setReplacing] = useState<ImportColumn | null>(null)
  const [raw, setRaw] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [mismatch, setMismatch] = useState<MismatchResult | null>(null)
  const [reviewOpen, setReviewOpen] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const fieldOfColumn = (c: ImportColumn) => c.mapping?.field ?? ''
  const subtopicCount = columns.filter((c) => fieldOfColumn(c) === 'subtopic').length

  const choices: Choice[] = useMemo(() => {
    const out: Choice[] = []
    for (const f of fields) {
      if (f.key === 'subtopic') {
        out.push({ key: `subtopic:${subtopicCount + 1}`, field: 'subtopic', order: subtopicCount + 1, label: `Subtopic ${subtopicCount + 1}`, disabled: false })
      } else {
        out.push({ key: f.key, field: f.key, label: f.label + (f.required ? ' *' : ''), disabled: columns.some((c) => fieldOfColumn(c) === f.key) })
      }
    }
    return out
  }, [fields, columns, subtopicCount])

  const selected = choices.find((c) => c.key === choice)
  const parsed = raw !== null ? parseColumn(raw) : null
  const expected = columns.length ? Math.max(...columns.filter((c) => c.key !== replacing?.key).map((c) => c.value_count), 0) : null

  const reset = () => {
    setRaw(null)
    setMismatch(null)
    setReviewOpen(false)
    setReplacing(null)
    setChoice('')
    onStage('field')
  }

  const submit = async (onMismatch?: 'PAD' | 'EXTEND') => {
    if (!raw || (!selected && !replacing)) return
    setBusy(true)
    setError(null)
    try {
      const body = replacing
        ? { field: fieldOfColumn(replacing), raw_text: raw, replace_key: replacing.key, on_mismatch: onMismatch }
        : { field: selected!.field, order: selected!.order, raw_text: raw, on_mismatch: onMismatch }
      const { data } = await api.post<{ result: { status: string; values_detected?: number; notes?: string[] } | MismatchResult; session: ImportSessionView }>(`/imports/${session.id}/column`, body)
      if (data.result.status === 'MISMATCH') {
        setMismatch(data.result as MismatchResult)
        return
      }
      onSession(data.session)
      const label = replacing ? replacing.header : selected!.label.replace(' *', '')
      setNotice(`${label}: ${(data.result as { values_detected: number }).values_detected} values imported.`)
      reset()
      onStage('columns')
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const act = async (fn: () => Promise<{ data: ImportSessionView }>) => {
    setBusy(true)
    setError(null)
    try {
      onSession((await fn()).data)
      setNotice(null)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const required = fields.filter((f) => f.required)
  const imported = new Set(columns.map(fieldOfColumn))
  const canContinue = required.every((f) => imported.has(f.key)) && columns.length > 0
  const previewRows = Math.min(session.row_count, 60)

  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-[360px_minmax(0,1fr)]">
      {/* Left: select field + paste */}
      <div className="space-y-4">
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">{replacing ? `Replace: ${replacing.header}` : 'Add a column'}</span>
            {(raw || replacing) && (
              <Button size="sm" variant="ghost" onClick={reset}>
                Cancel
              </Button>
            )}
          </div>
          <div className="space-y-4 p-4">
            {!replacing && (
              <div>
                <label htmlFor="field-to-import" className="label">
                  Field to import
                </label>
                <select
                  id="field-to-import"
                  className="field"
                  value={choice}
                  onChange={(e) => {
                    setChoice(e.target.value)
                    setMismatch(null)
                    onStage(e.target.value ? 'paste' : 'field')
                  }}
                >
                  <option value="">— Select a portal field —</option>
                  {choices.map((c) => (
                    <option key={c.key} value={c.key} disabled={c.disabled}>
                      {c.label}
                      {c.disabled ? ' (imported)' : ''}
                    </option>
                  ))}
                </select>
                <p className="meta mt-1">Copy only the data cells of that column (no header).</p>
              </div>
            )}

            {(selected || replacing) && !parsed && (
              <PasteArea compact onText={(t) => { setRaw(t); setMismatch(null) }} title={`Paste the ${replacing ? replacing.header : selected!.label.replace(' *', '')} column`} />
            )}

            {parsed && (
              <div className="space-y-3">
                <div className="flex items-baseline justify-between">
                  <span className="text-[13px] font-semibold text-fg tnum">{parsed.values.length} values detected</span>
                  {expected !== null && expected > 0 && (
                    <span className={cn('text-[12.5px] tnum', parsed.values.length === expected ? 'text-primary' : 'text-warning')}>
                      {parsed.values.length === expected ? `Matches ${expected} rows` : `Table has ${expected} rows`}
                    </span>
                  )}
                </div>
                {parsed.multipleColumns && <InlineAlert tone="warning">The paste had more than one column. Only the first will be used.</InlineAlert>}
                <ol className="max-h-40 overflow-y-auto rounded-md border border-line text-[12.5px] scroll-thin">
                  {parsed.values.slice(0, 50).map((v, i) => (
                    <li key={i} className="flex gap-3 border-b border-line-subtle px-2.5 py-1 last:border-0">
                      <span className="tnum w-6 shrink-0 text-right text-fg-muted">{i + 1}</span>
                      <span className={cn('truncate', !v && 'text-fg-faint italic')}>{v || 'blank'}</span>
                    </li>
                  ))}
                </ol>
                {!mismatch && (
                  <div className="flex gap-2">
                    <Button variant="primary" loading={busy} onClick={() => void submit()}>
                      {replacing ? 'Replace column' : 'Add column'}
                    </Button>
                    <Button variant="ghost" onClick={() => setRaw(null)}>
                      Paste again
                    </Button>
                  </div>
                )}
              </div>
            )}

            {mismatch && (
              <div className="rounded-md border border-warning-border bg-warning-soft p-3.5" role="alert">
                <div className="flex items-center gap-2 text-[13px] font-semibold tracking-wide text-warning uppercase">
                  <AlertTriangle className="h-4 w-4" /> Row count mismatch
                </div>
                <dl className="mt-2.5 grid grid-cols-3 gap-2 text-center">
                  {[['Expected', mismatch.expected], ['Received', mismatch.received], ['Difference', mismatch.difference]].map(([l, v]) => (
                    <div key={l as string} className="rounded bg-surface px-2 py-1.5 ring-1 ring-warning-border">
                      <dt className="text-[11px] text-warning">{l}</dt>
                      <dd className="tnum text-[17px] font-semibold text-fg">{v}</dd>
                    </div>
                  ))}
                </dl>
                <p className="mt-2.5 text-[12.5px] leading-snug text-warning">
                  “{mismatch.field_label}” does not line up with “{mismatch.reference_column}”. Nothing has been imported. Rows are never shifted automatically.
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button size="sm" onClick={() => setReviewOpen(true)}>
                    Review rows
                  </Button>
                  {mismatch.can_pad && (
                    <Button size="sm" loading={busy} onClick={() => void submit('PAD')}>
                      Continue with empty values
                    </Button>
                  )}
                  {mismatch.can_extend && (
                    <Button size="sm" loading={busy} onClick={() => void submit('EXTEND')}>
                      Extend table to {mismatch.received} rows
                    </Button>
                  )}
                  <Button size="sm" variant="ghost" onClick={() => { setRaw(null); setMismatch(null) }}>
                    Replace column
                  </Button>
                </div>
                {mismatch.can_pad && <p className="meta mt-2">Empty values are added at the end, after row {mismatch.received}.</p>}
              </div>
            )}
            {error && <InlineAlert tone="danger">{error}</InlineAlert>}
          </div>
        </div>

        <div className="panel px-4 py-3">
          <div className="mb-2 text-[12px] font-semibold text-fg-label uppercase">Required</div>
          <ul className="space-y-1 text-[13px]">
            {required.map((f) => (
              <li key={f.key} className="flex items-center gap-2">
                {imported.has(f.key) ? <CheckCircle2 className="h-4 w-4 text-primary" aria-label="Imported" /> : <Circle className="h-4 w-4 text-fg-faint" aria-label="Not imported" />}
                {f.label}
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Right: live preview */}
      <div className="min-w-0 space-y-4">
        {notice && <InlineAlert tone="success">{notice}</InlineAlert>}
        <div className="panel min-w-0">
          <div className="panel-header">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px]">
              <span className="panel-title">Live import preview</span>
              <span className="tnum text-fg-secondary">Imported columns: <b className="text-fg">{columns.length}</b></span>
              <span className="tnum text-fg-secondary">Rows: <b className="text-fg">{session.row_count}</b></span>
            </div>
            <Button size="sm" variant="ghost" icon={<Undo2 className="h-3.5 w-3.5" />} disabled={!session.can_undo || busy} onClick={() => void act(() => api.post(`/imports/${session.id}/undo`))}>
              Undo last import
            </Button>
          </div>
          {columns.length === 0 ? (
            <div className="px-6 py-14 text-center">
              <p className="text-sm font-semibold text-fg">No columns yet</p>
              <p className="meta mt-1">Start with Content Topic, then add Lecture Number, Unit, Bloom's level, subtopics and dates.</p>
            </div>
          ) : (
            <div className="max-h-[560px] overflow-auto scroll-thin">
              <table className="w-full min-w-max text-[12.5px]">
                <thead className="sticky top-0 z-10 bg-surface-2">
                  <tr className="border-b border-line">
                    <th className="w-12 px-3 py-2 text-right text-[11px] font-semibold text-fg-muted uppercase">Row</th>
                    {columns.map((c) => {
                      const recent = c.key === session.last_added_key
                      const padded = session.padded?.[c.key]
                      return (
                        <th key={c.key} className={cn('px-3 py-1.5 text-left', recent && 'bg-primary-soft')}>
                          <div className="flex items-center gap-1">
                            <span className="text-[12px] font-semibold text-fg-soft">{c.header}</span>
                            <Menu
                              label={`${c.header} actions`}
                              trigger={(p) => (
                                <button type="button" {...p} className="rounded p-0.5 text-fg-muted hover:bg-track hover:text-fg-soft" aria-label={`${c.header} actions`}>
                                  <MoreHorizontal className="h-3.5 w-3.5" />
                                </button>
                              )}
                              items={[
                                { label: 'Replace column', icon: <RotateCcw className="h-3.5 w-3.5" />, onSelect: () => { setReplacing(c); setRaw(null); setMismatch(null); onStage('paste') } },
                                { label: 'Clear column', danger: true, onSelect: () => void act(() => api.delete(`/imports/${session.id}/columns/${c.key}`)) },
                              ]}
                            />
                          </div>
                          <div className="text-[11px] font-normal text-fg-muted tnum">
                            {c.value_count} values{padded ? ` · ${padded.expected - padded.received} padded` : ''}
                          </div>
                        </th>
                      )
                    })}
                  </tr>
                </thead>
                <tbody>
                  {Array.from({ length: previewRows }).map((_, r) => (
                    <tr key={r} className="border-b border-line-subtle">
                      <td className="tnum px-3 py-1.5 text-right text-fg-muted">{r + 1}</td>
                      {columns.map((c) => {
                        const v = c.values?.[r] ?? ''
                        const pad = session.padded?.[c.key] && r >= session.padded[c.key].received
                        return (
                          <td key={c.key} className={cn('max-w-[260px] truncate px-3 py-1.5', c.key === session.last_added_key && 'bg-primary/5', pad && 'bg-warning-soft')} title={v}>
                            {v || <span className="text-fg-faint">—</span>}
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
              {session.row_count > previewRows && <p className="meta px-3 py-2">Showing the first {previewRows} of {session.row_count} rows.</p>}
            </div>
          )}
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Button onClick={onBack}>Back</Button>
          <div className="flex items-center gap-3">
            {!canContinue && <span className="meta">Import Lecture Number and Content Topic to continue.</span>}
            <Button variant="primary" disabled={!canContinue} onClick={onContinue}>
              Continue to validation
            </Button>
          </div>
        </div>
      </div>

      <Dialog open={reviewOpen && !!mismatch} onClose={() => setReviewOpen(false)} size="lg" title="Review row alignment" description={mismatch ? `Compare “${mismatch.reference_column}” with the pasted “${mismatch.field_label}” row by row.` : undefined}>
        {mismatch && (
          <div className="max-h-[60vh] overflow-y-auto rounded-md border border-line scroll-thin">
            <table className="w-full text-[12.5px]">
              <thead className="sticky top-0 bg-surface-2 text-left text-[11px] font-semibold text-fg-label uppercase">
                <tr>
                  <th className="w-14 px-3 py-2 text-right">Row</th>
                  <th className="px-3 py-2">{mismatch.reference_column}</th>
                  <th className="px-3 py-2">Pasted {mismatch.field_label}</th>
                </tr>
              </thead>
              <tbody>
                {mismatch.alignment.map((a) => (
                  <tr key={a.row} className={cn('border-t border-line-subtle', (a.incoming === null || a.reference === null) && 'bg-danger-soft')}>
                    <td className="tnum px-3 py-1.5 text-right text-fg-muted">{a.row}</td>
                    <td className="px-3 py-1.5">{a.reference ?? <em className="text-danger">no row</em>}</td>
                    <td className="px-3 py-1.5">{a.incoming === null ? <em className="text-danger">missing</em> : a.incoming || <span className="text-fg-faint">blank</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Dialog>
    </div>
  )
}
