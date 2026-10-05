import { ArrowRight, RefreshCw } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { InlineAlert, LoadingRows } from '@/components/feedback/States'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Metric, MetricStrip } from '@/components/ui/Display'
import { api, errorMessage } from '@/services/api'
import type { FieldDef, ImportSessionView, PreviewData } from '../types'

export function ValidateStep({
  session,
  preview,
  fields,
  onValidated,
  onBack,
  onContinue,
  onFilter,
}: {
  session: ImportSessionView
  preview: PreviewData | null
  fields: FieldDef[]
  onValidated: (s: ImportSessionView, p: PreviewData) => void
  onBack: () => void
  onContinue: () => void
  onFilter: (status: string) => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = async () => {
    setBusy(true)
    setError(null)
    try {
      const { data } = await api.post<{ session: ImportSessionView; preview: PreviewData }>(`/imports/${session.id}/validate`, {})
      onValidated(data.session, data.preview)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    if (!preview || session.is_validation_stale) void run()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const groups = useMemo(() => {
    const map = new Map<string, { level: string; field: string; message: string; example: string; rows: number[] }>()
    for (const r of preview?.rows ?? []) {
      for (const i of r.issues) {
        // Group identical problems ("'K9' is not valid" and "'K7' is not valid") under one line.
        const generic = i.message.replace(/'[^']*'\s*/g, '').replace(/\d{1,2} \w{3} \d{4}/g, 'the date').replace(/rows? [\d, ]+/g, 'other rows').replace(/Lecture \d+/g, 'an earlier lecture')
        const key = `${i.level}|${i.field}|${generic}`
        const g = map.get(key) ?? { level: i.level, field: i.field ?? '', message: generic, example: i.message, rows: [] as number[] }
        g.rows.push(r.row_number)
        map.set(key, g)
      }
    }
    return [...map.values()].sort((a, b) => (a.level === b.level ? b.rows.length - a.rows.length : a.level === 'ERROR' ? -1 : 1))
  }, [preview])

  if (busy && !preview) {
    return (
      <div className="panel">
        <div className="panel-header"><span className="panel-title">Validating…</span></div>
        <LoadingRows rows={5} />
      </div>
    )
  }
  if (!preview) return error ? <InlineAlert tone="danger" title="Validation could not run" action={<Button size="sm" onClick={run}>Retry</Button>}>{error}</InlineAlert> : null

  const s = preview.summary
  const sessionErrors = preview.session_issues.filter((i) => i.level === 'ERROR')
  const sessionWarnings = preview.session_issues.filter((i) => i.level === 'WARNING')
  const label = (k: string) => fields.find((f) => f.key === k)?.label ?? k.replace(/_/g, ' ')

  return (
    <div className="space-y-4">
      {preview.can_commit ? (
        <InlineAlert tone="success" title={`${s.lectures} lectures are ready to import`}>
          {s.warnings > 0 ? `${s.warnings} row(s) have warnings you may want to review. Warnings do not block publishing.` : 'Every row passed validation.'}
        </InlineAlert>
      ) : (
        <InlineAlert tone="danger" title={`${s.errors + sessionErrors.length} issue(s) require attention`}>
          Fix the source data, edit the rows in the preview, or remove rows that should not be imported.
        </InlineAlert>
      )}
      {preview.stale && <InlineAlert tone="warning">The data changed after the last validation. Run validation again.</InlineAlert>}
      {error && <InlineAlert tone="danger">{error}</InlineAlert>}

      <MetricStrip>
        <Metric label="Rows" value={s.rows} />
        <Metric label="Lectures" value={s.lectures} />
        <Metric label="Units" value={s.units} />
        <Metric label="Subtopics" value={s.subtopics} />
        <Metric label="Valid" value={s.valid} tone="success" />
        <Metric label="Warnings" value={s.warnings} tone={s.warnings ? 'warning' : undefined} />
        <Metric label="Errors" value={s.errors} tone={s.errors ? 'danger' : undefined} />
      </MetricStrip>

      {(sessionErrors.length > 0 || sessionWarnings.length > 0) && (
        <div className="panel">
          <div className="panel-header"><span className="panel-title">Import-level checks</span></div>
          <ul className="divide-y divide-line-subtle">
            {[...sessionErrors, ...sessionWarnings].map((i, n) => (
              <li key={n} className="flex items-start gap-3 px-4 py-2.5 text-[13px]">
                <Badge tone={i.level === 'ERROR' ? 'danger' : 'warning'}>{i.level === 'ERROR' ? 'Error' : 'Warning'}</Badge>
                <span className="text-fg-soft">{i.message}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="panel">
        <div className="panel-header">
          <span className="panel-title">Row checks</span>
          <span className="meta">{s.empty > 0 && `${s.empty} empty row(s) skipped · `}{s.removed > 0 && `${s.removed} removed · `}{s.scheduled} of {s.lectures} lectures scheduled</span>
        </div>
        {groups.length === 0 ? (
          <p className="px-4 py-6 text-[13px] text-fg-secondary">No row-level issues were found.</p>
        ) : (
          <ul className="divide-y divide-line-subtle">
            {groups.map((g, n) => (
              <li key={n} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 text-[13px]">
                <Badge tone={g.level === 'ERROR' ? 'danger' : 'warning'}>{g.level === 'ERROR' ? 'Error' : 'Warning'}</Badge>
                <span className="font-medium text-fg">{label(g.field)}</span>
                <span className="text-fg-secondary">{g.rows.length === 1 ? g.example : g.message.charAt(0).toUpperCase() + g.message.slice(1)}</span>
                <span className="meta tnum ml-auto">
                  {g.rows.length} row{g.rows.length > 1 ? 's' : ''}: {g.rows.slice(0, 8).join(', ')}
                  {g.rows.length > 8 ? '…' : ''}
                </span>
                <Button size="sm" variant="link" onClick={() => onFilter(g.level === 'ERROR' ? 'ERROR' : 'WARNING')}>
                  View rows
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button onClick={onBack}>Back</Button>
        <div className="flex gap-2">
          <Button icon={<RefreshCw className="h-3.5 w-3.5" />} loading={busy} onClick={run}>
            Run validation again
          </Button>
          <Button variant="primary" onClick={onContinue}>
            Continue to preview <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
