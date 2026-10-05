import { Plus, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { ErrorState, InlineAlert, LoadingRows, useToast } from '@/components/feedback/States'
import { FormField, Input, Select } from '@/components/forms/Fields'
import { Badge, Tag } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { useApi } from '@/hooks/useApi'
import { timetableApi, type SlotType, type TimingTemplate } from '@/lib/api/timetable'
import { errorMessage, type Paged } from '@/services/api'
import { cn } from '@/utils/cn'

const ROMAN = ['', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII']
type Row = { slot_type: SlotType; start_time: string; end_time: string }

function TemplateDialog({ tpl, others, onClose, onSaved }: { tpl: TimingTemplate | null; others: TimingTemplate[]; onClose: () => void; onSaved: () => void }) {
  const toast = useToast()
  const [name, setName] = useState('')
  const [shortName, setShortName] = useState('')
  const [sems, setSems] = useState<number[]>([])
  const [rows, setRows] = useState<Row[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (!tpl) return
    setName(tpl.name)
    setShortName(tpl.short_name)
    setSems(tpl.semester_numbers)
    setRows(tpl.slots.map((s) => ({ slot_type: s.slot_type, start_time: s.start, end_time: s.end })))
    setError(null)
  }, [tpl])
  if (!tpl) return null
  const taken = new Map(others.flatMap((o) => o.semester_numbers.map((n) => [n, o.short_name] as const)))
  const set = (i: number, patch: Partial<Row>) => setRows((r) => r.map((x, n) => (n === i ? { ...x, ...patch } : x)))
  let lecture = 0
  const save = async () => {
    if (rows.some((r) => !r.start_time || !r.end_time || r.end_time <= r.start_time)) return setError('Every period needs a start time and a later end time.')
    setBusy(true)
    setError(null)
    try {
      await timetableApi.saveTemplate(tpl.id, { name: name.trim(), short_name: shortName.trim(), description: tpl.description, semester_numbers: sems, slots: rows })
      toast('success', `${name} timings saved.`)
      onSaved()
      onClose()
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <Dialog open onClose={onClose} size="lg" title={`Edit ${tpl.name} timings`} description="Lecture numbers are counted from this list. A lunch or break here stops only this year group's classes."
      footer={<><Button onClick={onClose} disabled={busy}>Cancel</Button><Button variant="primary" loading={busy} onClick={save}>Save timings</Button></>}>
      <div className="space-y-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField label="Name" required htmlFor="tpl-name"><Input id="tpl-name" value={name} onChange={(e) => setName(e.target.value)} /></FormField>
          <FormField label="Short name" required htmlFor="tpl-short" hint="Shown on the timetable"><Input id="tpl-short" value={shortName} onChange={(e) => setShortName(e.target.value)} maxLength={24} /></FormField>
        </div>
        <div>
          <div className="label">Semesters that follow these timings</div>
          <div className="flex flex-wrap gap-1.5">
            {ROMAN.slice(1, 9).map((r, i) => {
              const n = i + 1, on = sems.includes(n), other = taken.get(n)
              return (
                <button key={n} type="button" disabled={!!other} aria-pressed={on} title={other ? `Follows ${other}` : undefined} onClick={() => setSems((s) => (on ? s.filter((x) => x !== n) : [...s, n].sort((a, b) => a - b)))}
                  className={cn('h-8 min-w-[3rem] rounded-md border px-2 text-[12.5px] font-medium', on ? 'border-primary-border bg-primary-soft text-primary' : 'border-line-strong text-fg-secondary hover:bg-surface-3', other && 'cursor-not-allowed opacity-45')}>
                  Sem {r}
                </button>
              )
            })}
          </div>
        </div>
        <div>
          <div className="label">Day structure</div>
          <ul className="space-y-1.5">
            {rows.map((r, i) => {
              const teaching = r.slot_type === 'LECTURE'
              if (teaching) lecture += 1
              return (
                <li key={i} className="grid grid-cols-[72px_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_36px] items-center gap-2">
                  <span className={cn('text-[12.5px] font-semibold', teaching ? 'text-fg' : 'text-fg-muted')}>{teaching ? `Lecture ${lecture}` : '—'}</span>
                  <Select aria-label="Type" value={r.slot_type} onChange={(e) => set(i, { slot_type: e.target.value as SlotType })}>
                    <option value="LECTURE">Lecture</option><option value="LUNCH">Lunch</option><option value="BREAK">Break</option>
                  </Select>
                  <Input aria-label="Start" type="time" className="tnum" value={r.start_time} onChange={(e) => set(i, { start_time: e.target.value })} />
                  <Input aria-label="End" type="time" className="tnum" value={r.end_time} onChange={(e) => set(i, { end_time: e.target.value })} />
                  <Button size="icon" variant="ghost" aria-label="Remove period" disabled={rows.length <= 1} onClick={() => setRows((x) => x.filter((_, n) => n !== i))}><Trash2 className="h-4 w-4" /></Button>
                </li>
              )
            })}
          </ul>
          <Button size="sm" className="mt-2" icon={<Plus className="h-3.5 w-3.5" />} onClick={() => setRows((x) => [...x, { slot_type: 'LECTURE', start_time: x[x.length - 1]?.end_time ?? '', end_time: '' }])}>Add period</Button>
        </div>
        <p className="meta">Changing timings does not move classes that are already scheduled. Regenerate the semester sprint afterwards.</p>
        {error && <InlineAlert tone="danger">{error}</InlineAlert>}
      </div>
    </Dialog>
  )
}

/** Each year group's own day: lecture periods and its own lunch. Two templates never share a "global" break. */
export function TimingTemplatesPanel({ canManage }: { canManage: boolean }) {
  const data = useApi<Paged<TimingTemplate>>('/timing-templates')
  const [edit, setEdit] = useState<TimingTemplate | null>(null)
  if (data.error) return <div className="panel"><ErrorState message={data.error.message} onRetry={data.reload} /></div>
  if (!data.data) return <div className="panel"><LoadingRows rows={4} /></div>
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      {data.data.items.map((t) => (
        <section key={t.id} className="panel" aria-label={t.name}>
          <div className="panel-header">
            <div className="min-w-0">
              <div className="panel-title">{t.name}</div>
              <div className="meta mt-0.5">{t.semester_numbers.length ? `Semesters ${t.semester_numbers.map((n) => ROMAN[n] ?? n).join(', ')}` : 'No semester follows these timings yet'}</div>
            </div>
            {canManage && <Button size="sm" onClick={() => setEdit(t)}>Edit timings</Button>}
          </div>
          <ul>
            {t.slots.map((s) => (
              <li key={s.id} className={cn('flex items-center justify-between gap-3 border-b border-line-subtle px-4 py-2 text-[13px] last:border-0', !s.is_teaching_slot && 'bg-track/50')}>
                <span className={cn('font-medium', s.is_teaching_slot ? 'text-fg' : 'text-fg-muted')}>{s.is_teaching_slot ? `Lecture ${s.lecture_number}` : s.slot_type === 'LUNCH' ? 'Lunch' : 'Break'}</span>
                <span className="flex items-center gap-2"><span className="tnum text-fg-secondary">{s.start} – {s.end}</span>{!s.is_teaching_slot && <Badge tone="neutral" icon={false}>{t.short_name} only</Badge>}</span>
              </li>
            ))}
          </ul>
        </section>
      ))}
      <p className="meta xl:col-span-2">A lecture number is local to its year group: <Tag>Lecture 3</Tag> is a different clock time in each template. Clash checks always compare real start and end times.</p>
      <TemplateDialog tpl={edit} others={data.data.items.filter((t) => t.id !== edit?.id)} onClose={() => setEdit(null)} onSaved={() => void data.reload(true)} />
    </div>
  )
}
