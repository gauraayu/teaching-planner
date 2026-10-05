import { useEffect, useState } from 'react'
import { InlineAlert } from '@/components/feedback/States'
import { FormField, Input, Select, Textarea } from '@/components/forms/Fields'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { useApi } from '@/hooks/useApi'
import { addDays, adminSprintApi, type AdminSprintRow, type AdminWeek, type CarryForward } from '@/lib/api/sprint'
import { fmt, LECTURE_TYPE_LABEL } from '@/lib/status'
import { errorMessage, type Paged } from '@/services/api'
import type { ManagedUser, PlanBrief } from '@/types/domain'
import { PROFESSOR_OPTIONS, professorLabel, professorParams } from '@/lib/api/users'
import { describeSlot } from './ChangeDiff'

export type LectureDialogState =
  | { mode: 'edit'; row: AdminSprintRow }
  | { mode: 'add'; carry?: CarryForward; date?: string }
  | { mode: 'cancel'; row: AdminSprintRow }

type Form = { plan_id: string; professor_id: string; date: string; start: string; end: string; room: string; topic: string; subtopics: string; lecture_type: string; reason: string; remarks: string }

function plusMinutes(hm: string, minutes: number) {
  const total = Math.min(23 * 60 + 59, Number(hm.slice(0, 2)) * 60 + Number(hm.slice(3)) + minutes)
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`
}

/**
 * Edit / add / cancel one lecture inside the sprint meeting draft. Saving updates the DRAFT
 * only - the professor's published schedule changes when the weekly revision is published.
 */
export function LectureDialog({ state, week, onClose, onSaved }: { state: LectureDialogState | null; week: AdminWeek; onClose: () => void; onSaved: (w: AdminWeek, message: string) => void }) {
  const professors = useApi<Paged<ManagedUser>>(state && state.mode !== 'cancel' ? PROFESSOR_OPTIONS : null, professorParams())
  const plans = useApi<Paged<PlanBrief>>(state?.mode === 'add' ? '/teaching-plans' : null, { status: 'PUBLISHED' })
  const [f, setF] = useState<Form | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const revisionId = week.draft?.id
  const weekEnd = addDays(week.week.start, 6)
  const minDate = week.today > week.week.start ? week.today : week.week.start

  useEffect(() => {
    if (!state) return setF(null)
    setError(null)
    if (state.mode === 'add') {
      const c = state.carry
      const start = '10:00'
      setF({
        plan_id: c?.plan_id ?? '', professor_id: c?.professor.id ?? '', date: state.date && state.date >= minDate ? state.date : minDate, start,
        end: plusMinutes(start, c?.duration_minutes ?? 60), room: c?.room ?? '', topic: c ? (c.kind === 'PARTIAL' ? `${c.topic} (remaining)` : c.topic) : '',
        subtopics: c?.remaining.join('\n') ?? '', lecture_type: c?.lecture_type ?? 'THEORY', reason: c ? 'PREVIOUS_TOPIC_INCOMPLETE' : 'SPRINT_MEETING_DECISION', remarks: '',
      })
    } else {
      const r = state.row
      setF({
        plan_id: r.plan_id, professor_id: r.professor.id, date: r.date, start: r.start ?? '', end: r.end ?? '', room: r.room ?? '', topic: r.topic,
        subtopics: r.subtopics.join('\n'), lecture_type: r.lecture_type, reason: r.draft?.reason ?? (state.mode === 'cancel' ? 'SPRINT_MEETING_DECISION' : ''), remarks: r.draft?.remarks ?? '',
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state])

  if (!state || !f || !revisionId) return null
  const set = (k: keyof Form) => (e: { target: { value: string } }) => { setError(null); setF((x) => (x ? { ...x, [k]: e.target.value } : x)) }
  const row = state.mode !== 'add' ? state.row : null
  const plan = plans.data?.items.find((p) => p.id === f.plan_id)

  const save = async () => {
    if (!f.reason) return setError('Select the reason for this change.')
    if (f.reason === 'OTHER' && !f.remarks.trim()) return setError('Add a remark when the reason is Other.')
    setBusy(true)
    setError(null)
    const common = { reason: f.reason, remarks: f.remarks.trim() || null }
    const values = {
      planned_date: f.date, planned_start_time: f.start, planned_end_time: f.end || null, room: f.room.trim() || null, professor_id: f.professor_id || undefined,
      content_topic: f.topic.trim(), subtopics: f.subtopics.split('\n').map((s) => s.trim()).filter(Boolean), lecture_type: f.lecture_type,
    }
    try {
      if (state.mode === 'cancel') onSaved(await adminSprintApi.cancelLecture(revisionId, row!.lecture_id!, common), 'Lecture marked for cancellation in the draft.')
      else if (state.mode === 'edit') onSaved(await adminSprintApi.editLecture(revisionId, row!.lecture_id!, { ...values, ...common }), 'Draft updated. Professors see it after you publish.')
      else {
        if (!f.plan_id) throw new Error('Choose the teaching plan.')
        if (!f.topic.trim()) throw new Error('Enter the topic.')
        onSaved(await adminSprintApi.addLecture(revisionId, { ...values, ...common, teaching_plan_id: f.plan_id, carry_forward_lecture_id: state.carry?.lecture_id }),
          state.carry ? 'Carry-forward item added to the draft.' : 'Lecture added to the draft.')
      }
      onClose()
    } catch (e) {
      setError(e instanceof Error && !(e as { status?: number }).status ? e.message : errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const title = state.mode === 'cancel' ? 'Cancel lecture' : state.mode === 'edit' ? 'Edit lecture for this week' : state.carry ? 'Add carry-forward to this week' : 'Add lecture to this week'
  const subject = row ? `${row.subject.name} · Lecture ${row.lecture_no} · Sem ${row.semester.replace('Semester ', '')}-${row.section}` : state.mode === 'add' && state.carry ? `${state.carry.subject.name} · from Lecture ${state.carry.lecture_no}` : 'New lecture in the weekly draft'

  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={title}
      description={subject}
      footer={
        <>
          <Button onClick={onClose} disabled={busy}>Close</Button>
          <Button variant={state.mode === 'cancel' ? 'danger' : 'primary'} loading={busy} onClick={save}>
            {state.mode === 'cancel' ? 'Cancel this lecture' : state.mode === 'edit' ? 'Save to draft' : 'Add to draft'}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {row && (row.master || row.revised) && (
          <div className="grid grid-cols-1 gap-2 rounded-md border border-line bg-surface-2 p-3 text-[12.5px] sm:grid-cols-2">
            <div><div className="th text-[10.5px]">Original semester plan</div><div className="mt-0.5 text-fg-soft">{describeSlot(row.master ?? row.revised?.old)}</div>{row.master?.professor_name && <div className="text-fg-label">{row.master.professor_name}</div>}</div>
            <div><div className="th text-[10.5px]">Current weekly revision{row.revised?.revision_number ? ` · v${row.revised.revision_number}` : ''}</div><div className="mt-0.5 text-fg-soft">{describeSlot({ planned_date: row.draft?.old?.planned_date ?? row.date, planned_start_time: row.draft?.old?.planned_start_time ?? row.start, planned_end_time: row.draft?.old?.planned_end_time ?? row.end, room: row.draft?.old?.room ?? row.room })}</div></div>
          </div>
        )}

        {state.mode === 'cancel' ? (
          <p className="text-[13.5px] text-fg-soft">
            <span className="font-medium text-fg">{row!.topic}</span> on {fmt.weekday(row!.date)}, {fmt.date(row!.date)} at {fmt.clock(row!.start)} will be removed from {row!.professor.full_name}&apos;s schedule when this revision is published. The master plan keeps the record.
          </p>
        ) : (
          <>
            {state.mode === 'add' && (
              <FormField label="Teaching plan" required htmlFor="sp-plan" hint={state.carry ? 'A carry-forward item stays in its own subject.' : undefined}>
                <Select id="sp-plan" value={f.plan_id} disabled={!!state.carry} onChange={(e) => setF((x) => (x ? { ...x, plan_id: e.target.value, professor_id: plans.data?.items.find((p) => p.id === e.target.value)?.professor.id ?? x.professor_id, room: x.room || plans.data?.items.find((p) => p.id === e.target.value)?.room || '' } : x))}>
                  <option value="">{plans.loading ? 'Loading…' : 'Select subject and section'}</option>
                  {state.carry && !plan && <option value={state.carry.plan_id}>{state.carry.subject.name} · Section {state.carry.section}</option>}
                  {plans.data?.items.map((p) => <option key={p.id} value={p.id}>{p.subject.code} · {p.subject.name} · Section {p.section.name}</option>)}
                </Select>
              </FormField>
            )}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <FormField label="Date" required htmlFor="sp-date" hint={state.mode === 'add' ? 'Within this week' : undefined}>
                <Input id="sp-date" type="date" value={f.date} min={minDate} max={state.mode === 'add' ? weekEnd : undefined} onChange={set('date')} />
              </FormField>
              <FormField label="Start time" required htmlFor="sp-start"><Input id="sp-start" type="time" className="tnum" value={f.start} onChange={set('start')} /></FormField>
              <FormField label="End time" htmlFor="sp-end"><Input id="sp-end" type="time" className="tnum" value={f.end} onChange={set('end')} /></FormField>
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <FormField label="Professor" required htmlFor="sp-prof" className="sm:col-span-2">
                <Select id="sp-prof" value={f.professor_id} onChange={set('professor_id')}>
                  {!f.professor_id && <option value="">Plan&apos;s professor</option>}
                  {professors.data?.items.map((p) => <option key={p.id} value={p.id}>{professorLabel(p)}</option>)}
                  {row && professors.data && !professors.data.items.some((p) => p.id === row.professor.id) && <option value={row.professor.id}>{row.professor.full_name} (inactive)</option>}
                  {row && !professors.data && <option value={row.professor.id}>{row.professor.full_name}</option>}
                </Select>
              </FormField>
              <FormField label="Room" htmlFor="sp-room"><Input id="sp-room" value={f.room} onChange={set('room')} placeholder="e.g. A-305" /></FormField>
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <FormField label="Topic" required htmlFor="sp-topic" className="sm:col-span-2"><Input id="sp-topic" value={f.topic} onChange={set('topic')} /></FormField>
              <FormField label="Lecture type" htmlFor="sp-type">
                <Select id="sp-type" value={f.lecture_type} onChange={set('lecture_type')}>{Object.entries(LECTURE_TYPE_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select>
              </FormField>
            </div>
            <FormField label="Subtopics" hint="One per line. The professor ticks these off after the class." htmlFor="sp-subs">
              <Textarea id="sp-subs" rows={3} value={f.subtopics} onChange={set('subtopics')} />
            </FormField>
          </>
        )}

        <div className="grid grid-cols-1 gap-4 border-t border-line-subtle pt-4 sm:grid-cols-2">
          <FormField label="Reason for change" required htmlFor="sp-reason">
            <Select id="sp-reason" value={f.reason} onChange={set('reason')}>
              <option value="">Select reason</option>
              {week.reasons.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
            </Select>
          </FormField>
          <FormField label="Meeting remark" required={f.reason === 'OTHER'} hint={f.reason === 'OTHER' ? undefined : 'Optional'} htmlFor="sp-remarks">
            <Input id="sp-remarks" value={f.remarks} onChange={set('remarks')} maxLength={1000} />
          </FormField>
        </div>
        {error && <InlineAlert tone="danger">{error}</InlineAlert>}
      </div>
    </Dialog>
  )
}
