import { ClipboardPaste, FileUp, Keyboard } from 'lucide-react'
import { useRef, useState, type ReactNode } from 'react'
import { Button } from '@/components/ui/Button'
import { cn } from '@/utils/cn'

/**
 * Focusable paste target. Spreadsheet clipboard data arrives as text/plain TSV;
 * we hand the raw string to the caller untouched (no trimming - a leading tab is
 * an empty first cell).
 */
export function PasteArea({ onText, title, hint, compact, disabled, filled }: { filled?: boolean; onText: (text: string) => void; title: string; hint?: ReactNode; compact?: boolean; disabled?: boolean }) {
  const [manual, setManual] = useState(false)
  const [draft, setDraft] = useState('')
  const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)

  if (manual) {
    return (
      <div>
        <label className="label" htmlFor="manual-paste">
          Paste or type values (one row per line, tab between columns)
        </label>
        <textarea id="manual-paste" value={draft} onChange={(e) => setDraft(e.target.value)} rows={compact ? 6 : 10} className="field h-auto py-2 font-mono text-[12px]" />
        <div className="mt-2 flex gap-2">
          <Button size="sm" variant="primary" disabled={!draft} onClick={() => onText(draft)}>
            Use this data
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setManual(false)}>
            Back to paste area
          </Button>
        </div>
      </div>
    )
  }
  return (
    <div>
      <div
        role="textbox"
        aria-label={`${title}. Focus and paste with Control V.`}
        aria-disabled={disabled}
        tabIndex={disabled ? -1 : 0}
        onPaste={(e) => {
          if (disabled) return
          e.preventDefault()
          const text = e.clipboardData.getData('text/plain')
          if (text) onText(text)
        }}
        className={cn(
          'group flex cursor-text flex-col items-center justify-center rounded-md border border-dashed bg-surface-2/60 text-center transition-colors',
          filled ? 'border-primary' : 'border-line-strong',
          'focus:border-primary focus:bg-primary/5 focus:ring-2 focus:ring-primary/15 focus:outline-none hover:border-line-hover',
          compact ? 'px-4 py-6' : 'px-6 py-10',
          disabled && 'pointer-events-none opacity-60',
        )}
      >
        <ClipboardPaste className="mb-2 h-5 w-5 text-fg-muted group-focus:text-primary" aria-hidden />
        <p className="text-[13.5px] font-medium text-fg">{title}</p>
        <p className="meta mt-1">
          Click here, then press <span className="kbd">{isMac ? '⌘' : 'Ctrl'}</span> + <span className="kbd">V</span>
        </p>
        {hint && <p className="meta mt-2 max-w-md">{hint}</p>}
      </div>
      <button type="button" onClick={() => setManual(true)} className="mt-2 inline-flex items-center gap-1.5 text-[12.5px] text-fg-label hover:text-fg">
        <Keyboard className="h-3.5 w-3.5" /> Enter data manually instead
      </button>
    </div>
  )
}

export function ImportDropzone({ onFile, busy }: { onFile: (f: File) => void; busy?: boolean }) {
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setOver(false)
        const f = e.dataTransfer.files?.[0]
        if (f) onFile(f)
      }}
      className={cn(
        'flex flex-col items-center justify-center rounded-md border border-dashed px-6 py-10 text-center transition-colors',
        over ? 'border-primary bg-primary/5' : 'border-line-strong bg-surface-2/60',
      )}
    >
      <FileUp className="mb-2 h-5 w-5 text-fg-muted" aria-hidden />
      <p className="text-[13.5px] font-medium text-fg">Drop an .xlsx or .csv file here</p>
      <p className="meta mt-1">The first sheet is used unless you choose another. Merged cells are expanded.</p>
      <Button className="mt-4" size="sm" loading={busy} onClick={() => input.current?.click()}>
        Browse files
      </Button>
      <input
        ref={input}
        type="file"
        accept=".xlsx,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv"
        className="sr-only"
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) onFile(f)
          e.target.value = ''
        }}
      />
    </div>
  )
}
