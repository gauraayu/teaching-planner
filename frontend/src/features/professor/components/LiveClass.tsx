import { Camera, CircleStop, Clock, ImagePlus, Play, Trash2 } from 'lucide-react'
import { useRef, useState } from 'react'
import { Section } from '@/components/domain/LectureRecord'
import { InlineAlert, useToast } from '@/components/feedback/States'
import { InstitutionClock } from '@/components/shared/InstitutionClock'
import { Button } from '@/components/ui/Button'
import { ConfirmDialog, Dialog } from '@/components/ui/Dialog'
import { professorApi } from '@/lib/api/professor'
import { fileSrc, IMAGE_ACCEPT, IMAGE_MAX_MB, imageProblem, uploadsApi } from '@/lib/api/uploads'
import { classPhase, countdownLabel, useInstNow } from '@/lib/date-time/institution'
import { fmt } from '@/lib/status'
import { useTodayFeed } from '@/providers/ScheduleNotificationProvider'
import { errorMessage } from '@/services/api'
import type { LectureDetail } from '@/types/domain'

type Saved = (d: LectureDetail, message: string) => void

/** Start Class / End Class. The server records the time of each click; the OM's entry and exit stay separate. */
export function LiveClassPanel({ d, onSaved }: { d: LectureDetail; onSaved: Saved }) {
  const now = useInstNow(15_000)
  const { leadMinutes, reload } = useTodayFeed()
  const [checkin, setCheckin] = useState(false)
  const [confirmEnd, setConfirmEnd] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const e = d.execution
  const started = e?.professor_started_at
  const ended = e?.professor_ended_at
  const { phase, minutesToStart } = classPhase(d.class_date, d.master.planned_start_time, d.master.planned_end_time, now, leadMinutes)

  const start = async (mode: 'TIME' | 'IMAGE' | 'SKIPPED', image?: File) => {
    setBusy(mode)
    setError(null)
    try {
      let next = await professorApi.startClass(d.id, mode)
      if (image) next = await uploadsApi.addClassImage(d.id, image, { kind: 'CHECKIN_IMAGE', caption: 'Check-in' })
      setCheckin(false)
      reload()
      onSaved(next, `Class started at ${fmt.time(next.execution?.professor_started_at)}.`)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(null)
    }
  }
  const end = async () => {
    setBusy('end')
    try {
      const next = await professorApi.endClass(d.id)
      setConfirmEnd(false)
      onSaved(next, 'Class ended. Record what was covered below and submit.')
    } catch (err) {
      setError(errorMessage(err))
      setConfirmEnd(false)
    } finally {
      setBusy(null)
    }
  }
  const pickImage = (file: File | undefined) => {
    if (!file) return
    const problem = imageProblem(file)
    if (problem) return setError(problem)
    void start('IMAGE', file)
  }

  if (!started && !d.can_start) {
    if (!d.can_edit || !d.class_date || d.class_date <= now.date) return null
    return <p className="meta mb-4 rounded-md border border-line bg-surface px-4 py-2.5">Start Class becomes available on {fmt.weekday(d.class_date)}, {fmt.date(d.class_date)}.</p>
  }

  return (
    <section className={`panel mb-5 ${started && !ended ? 'border-primary-border' : ''}`} aria-label="Class session">
      <div className="flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          {started && !ended ? (
            <div className="inline-flex items-center gap-1.5 text-[11.5px] font-semibold tracking-[0.08em] text-primary uppercase"><span className="live-dot" aria-hidden />Live class</div>
          ) : (
            <div className="th">{ended ? 'Class session' : phase === 'NOW' ? 'Starting now' : phase === 'OVER' ? 'Scheduled slot is over' : countdownLabel(minutesToStart, phase) || 'Class today'}</div>
          )}
          <dl className="tnum mt-2 flex flex-wrap gap-x-6 gap-y-1 text-[13px]">
            <div><dt className="inline text-fg-label">Scheduled </dt><dd className="inline font-medium text-fg">{fmt.timeRange(d.master.planned_start_time, d.master.planned_end_time) || '—'}</dd></div>
            {started && <div><dt className="inline text-fg-label">Started </dt><dd className="inline font-medium text-fg">{fmt.time(started)}</dd></div>}
            {ended && <div><dt className="inline text-fg-label">Ended </dt><dd className="inline font-medium text-fg">{fmt.time(ended)}</dd></div>}
            <div><dt className="inline text-fg-label">Room </dt><dd className="inline font-medium text-fg">{d.room ?? '—'}</dd></div>
          </dl>
          {started && <p className="meta mt-1.5">Your start and end times are your own record. The Operations Manager records the official entry and exit separately.</p>}
        </div>
        {d.can_start && <Button variant="primary" size="lg" className="shrink-0 justify-center" icon={<Play className="h-4 w-4" />} onClick={() => { setError(null); setCheckin(true) }}>Start class</Button>}
        {d.can_end && <Button size="lg" className="shrink-0 justify-center" icon={<CircleStop className="h-4 w-4" />} onClick={() => setConfirmEnd(true)}>End class</Button>}
      </div>
      {error && !checkin && <div className="px-4 pb-4"><InlineAlert tone="danger">{error}</InlineAlert></div>}

      <Dialog open={checkin} onClose={() => setCheckin(false)} size="sm" title="Start class" description="Entry / check-in evidence is optional.">
        <div className="space-y-3">
          <div className="flex items-center justify-between rounded-md border border-line bg-surface-2 px-3 py-2.5">
            <span className="text-[12.5px] text-fg-label">Current time</span>
            <InstitutionClock showDate={false} />
          </div>
          <Button variant="primary" className="h-11 w-full justify-center" loading={busy === 'TIME'} disabled={!!busy} icon={<Clock className="h-4 w-4" />} onClick={() => start('TIME')}>Use current time</Button>
          <Button className="h-11 w-full justify-center" loading={busy === 'IMAGE'} disabled={!!busy} icon={<Camera className="h-4 w-4" />} onClick={() => fileRef.current?.click()}>Upload classroom image</Button>
          <Button variant="ghost" className="h-10 w-full justify-center" loading={busy === 'SKIPPED'} disabled={!!busy} onClick={() => start('SKIPPED')}>Skip</Button>
          <input ref={fileRef} type="file" accept={IMAGE_ACCEPT} capture="environment" className="sr-only" aria-label="Classroom image" onChange={(ev) => { pickImage(ev.target.files?.[0]); ev.target.value = '' }} />
          {error && <InlineAlert tone="danger">{error}</InlineAlert>}
          <p className="meta">The start time is taken from the server when you choose an option, whichever one you pick.</p>
        </div>
      </Dialog>
      <ConfirmDialog open={confirmEnd} onClose={() => setConfirmEnd(false)} onConfirm={end} loading={busy === 'end'} title="End this class?" confirmLabel="End class">
        The end time is recorded now. You can then mark the topics covered, add notes and submit the lecture record.
      </ConfirmDialog>
    </section>
  )
}

/** Optional class photos: classroom, board, activity. Files go to storage; only their URL and metadata are saved with the lecture. */
export function EvidencePanel({ d, onSaved }: { d: LectureDetail; onSaved: Saved }) {
  const toast = useToast()
  const inputRef = useRef<HTMLInputElement>(null)
  const [caption, setCaption] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const items = d.execution?.evidence ?? []

  const upload = async (list: FileList | null) => {
    const files = Array.from(list ?? []) // copy now: the input is cleared right after, which empties the live FileList
    if (!files.length) return
    setError(null)
    setBusy(true)
    let latest: LectureDetail | null = null
    try {
      for (const file of files) {
        const problem = imageProblem(file)
        if (problem) throw new Error(`${file.name}: ${problem}`)
        latest = await uploadsApi.addClassImage(d.id, file, { caption: caption.trim() || undefined })
      }
      setCaption('')
      if (latest) onSaved(latest, `${files.length} image${files.length === 1 ? '' : 's'} uploaded.`)
    } catch (err) {
      if (latest) onSaved(latest, 'Some images were uploaded.')
      setError(err instanceof Error && !(err as { status?: number }).status ? err.message : errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  const remove = async (id: string) => {
    try {
      onSaved(await uploadsApi.removeClassImage(id), 'Image removed.')
    } catch (err) {
      toast('danger', errorMessage(err))
    }
  }

  return (
    <Section title="Class records" aside={<span className="meta">Optional · JPG, PNG or WebP up to {IMAGE_MAX_MB} MB</span>}>
      {items.length === 0 ? (
        <p className="meta">No images yet. Classroom, board or activity photos can be added as supporting records.</p>
      ) : (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {items.map((m) => (
            <li key={m.id} className="overflow-hidden rounded-md border border-line bg-surface-2">
              <a href={fileSrc(m.file_url)} target="_blank" rel="noreferrer">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={fileSrc(m.file_url)} alt={m.caption ?? m.file_name ?? 'Class photo'} className="h-28 w-full object-cover" />
              </a>
              <div className="flex items-start justify-between gap-2 px-2.5 py-2">
                <div className="min-w-0 text-[12px]">
                  <div className="truncate font-medium text-fg-soft">{m.caption || m.file_name || 'Class photo'}{m.material_type === 'CHECKIN_IMAGE' && !m.caption ? ' (check-in)' : ''}</div>
                  <div className="text-fg-muted">{fmt.dateTime(m.uploaded_at)}</div>
                </div>
                <button type="button" onClick={() => remove(m.id)} aria-label="Remove image" className="shrink-0 rounded p-1 text-fg-muted hover:bg-danger-soft hover:text-danger"><Trash2 className="h-3.5 w-3.5" /></button>
              </div>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <input type="text" value={caption} onChange={(e) => setCaption(e.target.value)} maxLength={300} placeholder="Caption for the next upload (optional)" aria-label="Image caption" className="field sm:max-w-xs" />
        <Button loading={busy} icon={<ImagePlus className="h-4 w-4" />} onClick={() => inputRef.current?.click()}>Upload image</Button>
        <input ref={inputRef} type="file" accept={IMAGE_ACCEPT} multiple className="sr-only" aria-label="Class images" onChange={(e) => { void upload(e.target.files); e.target.value = '' }} />
      </div>
      {error && <InlineAlert tone="danger" className="mt-3">{error}</InlineAlert>}
    </Section>
  )
}
