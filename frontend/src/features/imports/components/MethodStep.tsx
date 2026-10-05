import { Check, Columns3, FileSpreadsheet, Table2 } from 'lucide-react'
import { useState } from 'react'
import { InlineAlert } from '@/components/feedback/States'
import { Checkbox } from '@/components/forms/Fields'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/forms/Fields'
import { api, errorMessage } from '@/services/api'
import type { ImportMode } from '@/types/domain'
import { cn } from '@/utils/cn'
import { columnLetter, parseTable, type ParsedGrid } from '../parsers/tsv'
import type { ImportSessionView } from '../types'
import { ImportDropzone, PasteArea } from './PasteArea'

type Method = 'FULL_TABLE' | 'COLUMN_WISE' | 'FILE'

const METHODS: { value: Method; title: string; text: string; icon: typeof Table2 }[] = [
  { value: 'FULL_TABLE', title: 'Full table copy-paste', text: 'Copy the whole range (with headers) from Google Sheets or Excel and paste it once.', icon: Table2 },
  { value: 'COLUMN_WISE', title: 'Column-by-column paste', text: 'Choose a portal field, paste that column, repeat. Rows are aligned strictly by position.', icon: Columns3 },
  { value: 'FILE', title: 'Excel / CSV upload', text: 'Upload an .xlsx workbook or a .csv export of the plan.', icon: FileSpreadsheet },
]

const methodOf = (m: ImportMode | null): Method | null => (m === 'EXCEL' || m === 'CSV' ? 'FILE' : m)

export function MethodStep({ session, onSession, onContinue }: { session: ImportSessionView; onSession: (s: ImportSessionView) => void; onContinue: (mode: ImportMode) => void }) {
  const [method, setMethod] = useState<Method | null>(methodOf(session.import_mode))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const choose = async (m: Method) => {
    setMethod(m)
    setError(null)
    if (m === 'COLUMN_WISE') {
      try {
        const { data } = await api.put<ImportSessionView>(`/imports/${session.id}/mode`, { import_mode: 'COLUMN_WISE' })
        onSession(data)
      } catch (e) {
        setError(errorMessage(e))
      }
    }
  }

  const hasTableData = (session.import_mode === 'FULL_TABLE' || session.import_mode === 'EXCEL' || session.import_mode === 'CSV') && (session.columns?.length ?? 0) > 0

  return (
    <div className="space-y-5">
      <fieldset>
        <legend className="mb-2 text-[13px] font-semibold text-fg">Choose how to bring the plan in</legend>
        <div className="grid gap-2 lg:grid-cols-3">
          {METHODS.map((m) => {
            const active = method === m.value
            return (
              <label
                key={m.value}
                className={cn(
                  'flex cursor-pointer gap-3 rounded-md border bg-surface px-3.5 py-3 transition-colors',
                  active ? 'border-primary ring-1 ring-primary' : 'border-line hover:border-line-strong',
                )}
              >
                <input type="radio" name="method" className="sr-only" checked={active} onChange={() => void choose(m.value)} />
                <m.icon className={cn('mt-0.5 h-4 w-4 shrink-0', active ? 'text-primary' : 'text-fg-muted')} aria-hidden />
                <span>
                  <span className="block text-[13.5px] font-semibold text-fg">{m.title}</span>
                  <span className="meta mt-0.5 block leading-snug">{m.text}</span>
                </span>
              </label>
            )
          })}
        </div>
      </fieldset>

      {error && <InlineAlert tone="danger">{error}</InlineAlert>}

      {method === 'FULL_TABLE' && <FullTablePaste session={session} onSession={onSession} onContinue={() => onContinue('FULL_TABLE')} existing={hasTableData && session.import_mode === 'FULL_TABLE'} busy={busy} setBusy={setBusy} />}
      {method === 'FILE' && <FileUpload session={session} onSession={onSession} onContinue={() => onContinue(session.import_mode ?? 'EXCEL')} existing={hasTableData && session.import_mode !== 'FULL_TABLE'} />}
      {method === 'COLUMN_WISE' && (
        <div className="flex justify-end">
          <Button variant="primary" onClick={() => onContinue('COLUMN_WISE')}>
            Continue to field selection
          </Button>
        </div>
      )}
    </div>
  )
}

function GridPreview({ grid, hasHeader }: { grid: string[][]; hasHeader: boolean }) {
  const width = grid[0]?.length ?? 0
  return (
    <div className="overflow-x-auto rounded-md border border-line scroll-thin">
      <table className="min-w-full text-[12px]">
        <thead>
          <tr className="bg-surface-2">
            <th className="w-10 border-r border-b border-line px-2 py-1 text-fg-muted" />
            {Array.from({ length: width }).map((_, i) => (
              <th key={i} className="border-b border-line px-2 py-1 text-left font-medium text-fg-muted">
                {columnLetter(i)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {grid.slice(0, 6).map((row, r) => (
            <tr key={r} className={cn(r === 0 && hasHeader && 'bg-primary/5 font-semibold text-fg')}>
              <td className="tnum border-r border-line px-2 py-1 text-right text-fg-muted">{r + 1}</td>
              {row.map((c, i) => (
                <td key={i} className="max-w-56 truncate border-b border-line-subtle px-2 py-1 text-fg-soft" title={c}>
                  {c || <span className="text-fg-faint">·</span>}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function FullTablePaste({ session, onSession, onContinue, existing, busy, setBusy }: { session: ImportSessionView; onSession: (s: ImportSessionView) => void; onContinue: () => void; existing: boolean; busy: boolean; setBusy: (b: boolean) => void }) {
  const [raw, setRaw] = useState<string | null>(null)
  const [grid, setGrid] = useState<ParsedGrid | null>(null)
  const [hasHeader, setHasHeader] = useState<boolean | null>(null)
  const [error, setError] = useState<string | null>(null)

  const accept = (text: string) => {
    const g = parseTable(text)
    setRaw(text)
    setGrid(g)
    setError(g.rows.length === 0 ? 'Nothing was detected in the paste. Copy a range of cells and try again.' : null)
  }

  const submit = async () => {
    if (!raw) return
    setBusy(true)
    setError(null)
    try {
      const { data } = await api.post<{ session: ImportSessionView }>(`/imports/${session.id}/full-table`, { raw_text: raw, has_header: hasHeader })
      onSession(data.session)
      onContinue()
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const header = hasHeader ?? true
  const dataRows = grid ? grid.rows.length - (header ? 1 : 0) : 0
  return (
    <div className="space-y-4">
      {existing && !grid && (
        <InlineAlert tone="info" title="Pasted data is already saved for this import" action={<Button size="sm" variant="primary" onClick={onContinue}>Continue to mapping</Button>}>
          {session.row_count} rows · {session.columns?.length} columns. Paste again below to replace it.
        </InlineAlert>
      )}
      <PasteArea title="Paste the full teaching-plan range here" filled={!!grid && grid.rows.length > 0} onText={accept} hint="Include the header row. Blank cells are kept in place, so values never shift between rows." />
      {error && <InlineAlert tone="danger">{error}</InlineAlert>}
      {grid && grid.rows.length > 0 && (
        <div className="panel">
          <div className="panel-header">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px]">
              <span className="tnum inline-flex items-center gap-1.5 font-semibold text-fg"><Check className="h-3.5 w-3.5 text-primary" strokeWidth={3} aria-hidden />{dataRows} rows detected</span>
              <span className="tnum inline-flex items-center gap-1.5 font-semibold text-fg"><Check className="h-3.5 w-3.5 text-primary" strokeWidth={3} aria-hidden />{grid.width} columns detected</span>
              {grid.trailingEmptyRowsDropped > 0 && <span className="meta">{grid.trailingEmptyRowsDropped} empty trailing row(s) ignored</span>}
            </div>
            <Checkbox label="First row contains column headers" checked={header} onChange={(e) => setHasHeader(e.target.checked)} />
          </div>
          <div className="p-4">
            <GridPreview grid={grid.rows} hasHeader={header} />
            <p className="meta mt-2">Showing the first {Math.min(6, grid.rows.length)} of {grid.rows.length} pasted rows.</p>
          </div>
          <div className="flex justify-end border-t border-line px-4 py-3">
            <Button variant="primary" loading={busy} onClick={submit}>
              Continue to mapping
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

function FileUpload({ session, onSession, onContinue, existing }: { session: ImportSessionView; onSession: (s: ImportSessionView) => void; onContinue: () => void; existing: boolean }) {
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<{ rows_detected: number; columns_detected: number; sheet?: string; sheets?: string[]; notes?: string[] } | null>(null)

  const upload = async (f: File, sheet?: string) => {
    setFile(f)
    setBusy(true)
    setError(null)
    try {
      const form = new FormData()
      form.append('file', f)
      if (sheet) form.append('sheet', sheet)
      const { data } = await api.post<{ result: typeof result; session: ImportSessionView }>(`/imports/${session.id}/file`, form)
      setResult(data.result)
      onSession(data.session)
    } catch (e) {
      setError(errorMessage(e))
      setResult(null)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      {existing && !result && (
        <InlineAlert tone="info" title={`${session.source?.file_name ?? 'A file'} is already loaded`} action={<Button size="sm" variant="primary" onClick={onContinue}>Continue to mapping</Button>}>
          {session.row_count} rows · {session.columns?.length} columns. Upload another file to replace it.
        </InlineAlert>
      )}
      <ImportDropzone onFile={(f) => void upload(f)} busy={busy} />
      {error && <InlineAlert tone="danger" title="Unable to read the file">{error}</InlineAlert>}
      {result && file && (
        <div className="panel">
          <div className="panel-header">
            <div className="text-[13px]">
              <span className="font-semibold text-fg">{file.name}</span>
              <span className="meta ml-2 tnum">
                {result.rows_detected} rows · {result.columns_detected} columns
              </span>
            </div>
            {result.sheets && result.sheets.length > 1 && (
              <label className="flex items-center gap-2 text-[13px]">
                <span className="text-fg-label">Sheet</span>
                <Select className="h-8 w-48" value={result.sheet} onChange={(e) => void upload(file, e.target.value)}>
                  {result.sheets.map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </Select>
              </label>
            )}
          </div>
          <div className="space-y-3 p-4">
            {result.notes?.map((n) => <InlineAlert key={n} tone="info">{n}</InlineAlert>)}
            {session.grid_preview && <GridPreview grid={session.grid_preview} hasHeader={!!session.has_header} />}
          </div>
          <div className="flex justify-end border-t border-line px-4 py-3">
            <Button variant="primary" onClick={onContinue}>
              Continue to mapping
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
