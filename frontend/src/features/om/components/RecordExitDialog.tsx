import { Clock } from 'lucide-react'
import { useEffect, useState } from 'react'
import { InlineAlert, useToast } from '@/components/feedback/States'
import { FormField, Input, Textarea } from '@/components/forms/Fields'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { fmt, todayISO } from '@/lib/status'
import { ApiError, errorMessage } from '@/services/api'
import { nowHM, omApi } from '../services/omApi'
import type { ClassRow } from '../types/om.types'
import { ClassFacts } from './RecordEntryDialog'

export function RecordExitDialog({ row, onClose, onSaved }: { row: ClassRow | null; onClose: () => void; onSaved: (row: ClassRow) => void }) {
  const toast = useToast()
  const [time, setTime] = useState('')
  const [manual, setManual] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [early, setEarly] = useState<{ minutes: number; tolerance: number } | null>(null)
  const [reason, setReason] = useState('')
  const isToday = row?.date === todayISO()

  useEffect(() => {
    if (!row) return
    setTime(row.exit_time ?? (row.date === todayISO() ? nowHM() : row.scheduled_end ?? ''))
    setError(null)
    setEarly(null)
    setReason(row.early_exit_reason ?? '')
    setManual(false)
  }, [row])

  if (!row) return null
  // Clock Out (today, nothing recorded yet) sends no time: the server's clock decides.
  const clockOut = row.date === todayISO() && !row.exit_time && !manual

  const save = async () => {
    if (!clockOut && !time) return setError('Enter the exit time.')
    setBusy(true)
    setError(null)
    try {
      const saved = await omApi.recordExit(row.lecture_id, clockOut ? null : time, early ? reason.trim() : undefined)
      toast('success', `Exit saved: ${fmt.clock(saved.exit_time)} · ${saved.duration_minutes} min in class.`)
      onSaved(saved)
      onClose()
    } catch (e) {
      // The backend decides what counts as leaving early, then this dialog asks for the reason.
      if (e instanceof ApiError && e.code === 'EARLY_EXIT_REASON_REQUIRED') {
        const d = e.details as { early_minutes: number; tolerance_minutes: number }
        setEarly({ minutes: d.early_minutes, tolerance: d.tolerance_minutes })
      } else setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog
      open
      onClose={onClose}
      title={row.exit_time ? 'Correct exit time' : clockOut ? 'Clock out' : 'Record exit'}
      description={`${fmt.weekday(row.date)}, ${fmt.date(row.date)}`}
      footer={
        <>
          <Button onClick={onClose} disabled={busy}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={save} disabled={!!early && !reason.trim()}>{clockOut ? 'Clock out now' : 'Save exit'}</Button>
        </>
      }
    >
      <div className="space-y-4">
        <ClassFacts
          row={row}
          extra={[
            { label: 'Entry time', value: <span className="tnum">{fmt.clock(row.entry_time)}{row.timing_status === 'DELAYED' ? ` · ${row.delay_minutes} min late` : ''}</span> },
            { label: 'Scheduled end', value: <span className="tnum">{fmt.clock(row.scheduled_end) || '—'}</span> },
          ]}
        />
        {clockOut ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-line bg-surface-2 px-3.5 py-3">
            <div className="flex items-center gap-2.5 text-[13px] text-fg-soft"><Clock className="h-4 w-4 text-primary" aria-hidden />The exit time is taken from the server clock when you clock out.</div>
            <Button size="sm" variant="link" onClick={() => { setManual(true); setEarly(null) }}>Enter a time instead</Button>
          </div>
        ) : (
          <FormField label="Actual exit time" required htmlFor="exit-time">
            <div className="flex gap-2">
              <Input id="exit-time" type="time" className="tnum max-w-[9.5rem]" value={time} onChange={(e) => { setTime(e.target.value); setError(null); setEarly(null) }} data-autofocus />
              {isToday && <Button icon={<Clock className="h-4 w-4" />} onClick={() => setTime(nowHM())}>Use current time</Button>}
            </div>
          </FormField>
        )}
        {early && (
          <div className="rounded-md border border-warning-border bg-warning-soft p-3.5">
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-[13px] font-semibold text-warning">Early exit: {early.minutes} minutes before the scheduled end</span>
              <span className="text-[12px] text-fg-label">Tolerance {early.tolerance} min</span>
            </div>
            <FormField label="Reason for early exit" required htmlFor="early-reason" className="mt-3">
              <Textarea id="early-reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} />
            </FormField>
          </div>
        )}
        {error && <InlineAlert tone="danger">{error}</InlineAlert>}
      </div>
    </Dialog>
  )
}
