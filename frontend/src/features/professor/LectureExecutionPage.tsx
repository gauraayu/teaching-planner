import { zodResolver } from '@hookform/resolvers/zod'
import { ArrowLeft, Link2, Lock, Plus, Send, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Controller, useFieldArray, useForm, useWatch } from 'react-hook-form'
import { Link, useParams } from '@/lib/router'
import { z } from 'zod'
import { ExecutionSummary, MasterPlanPanel, Section, VerificationHistory } from '@/components/domain/LectureRecord'
import { ClassTimingPanel, VerificationTimeline } from '@/components/domain/VerificationTimeline'
import { ErrorState, InlineAlert, PageLoading, useToast } from '@/components/feedback/States'
import { Checkbox, FormField, Input, Textarea } from '@/components/forms/Fields'
import { useBreadcrumbs } from '@/components/layout/PageHeader'
import { StatusBadge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { ConfirmDialog } from '@/components/ui/Dialog'
import { useApi } from '@/hooks/useApi'
import { EXECUTION_STATUS, fmt, SUBMISSION_STATUS, todayISO } from '@/lib/status'
import { ApiError, api, errorMessage } from '@/services/api'
import { EXECUTION_STATUSES, type ExecutionStatus, type LectureDetail } from '@/types/domain'
import { cn } from '@/utils/cn'
import { EvidencePanel, LiveClassPanel } from './components/LiveClass'

const url = z.string().trim().url('Enter a full link starting with https://')

const schema = z
  .object({
    execution_status: z.enum(EXECUTION_STATUSES as [ExecutionStatus, ...ExecutionStatus[]]),
    actual_completion_date: z.string().optional(),
    rescheduled_to: z.string().optional(),
    covered_subtopic_ids: z.array(z.string()),
    remarks: z.string().max(4000).optional(),
    recording_url: z.union([z.literal(''), url]).optional(),
    additional_topics: z.string().max(1000).optional(),
    shared: z.enum(['', 'yes', 'no']),
    not_shared_reason: z.string().optional(),
    notes: z.array(z.object({ id: z.string().optional(), title: z.string().max(200).optional(), file_url: url })).max(10),
    has_assignment: z.boolean(),
    assignment: z.object({
      title: z.string().optional(),
      description: z.string().max(4000).optional(),
      link_url: z.string().optional(),
      due_date: z.string().optional(),
      shared: z.enum(['', 'yes', 'no']),
      not_shared_reason: z.string().optional(),
    }),
  })
  .superRefine((v, ctx) => {
    const today = todayISO()
    const done = v.execution_status === 'COMPLETED' || v.execution_status === 'PARTIALLY_COMPLETED'
    if (done && !v.actual_completion_date) ctx.addIssue({ code: 'custom', path: ['actual_completion_date'], message: 'Enter the date the lecture was delivered.' })
    if (v.actual_completion_date && v.actual_completion_date > today) ctx.addIssue({ code: 'custom', path: ['actual_completion_date'], message: 'The date cannot be in the future.' })
    if (v.execution_status === 'RESCHEDULED' && !v.rescheduled_to) ctx.addIssue({ code: 'custom', path: ['rescheduled_to'], message: 'Choose the new date.' })
    if (v.execution_status === 'RESCHEDULED' && v.rescheduled_to && v.rescheduled_to < today) ctx.addIssue({ code: 'custom', path: ['rescheduled_to'], message: 'The new date cannot be in the past.' })
    if (v.execution_status === 'NOT_CONDUCTED' && !v.remarks?.trim()) ctx.addIssue({ code: 'custom', path: ['remarks'], message: 'Say why the class was not conducted.' })
    if (v.shared === 'no' && !v.not_shared_reason?.trim()) ctx.addIssue({ code: 'custom', path: ['not_shared_reason'], message: 'Explain why the material was not shared.' })
    if (v.has_assignment) {
      if (!v.assignment.title?.trim() || v.assignment.title.trim().length < 2) ctx.addIssue({ code: 'custom', path: ['assignment', 'title'], message: 'Give the assignment a title.' })
      if (v.assignment.link_url && !url.safeParse(v.assignment.link_url).success) ctx.addIssue({ code: 'custom', path: ['assignment', 'link_url'], message: 'Enter a full link starting with https://' })
      if (v.assignment.shared === 'no' && !v.assignment.not_shared_reason?.trim()) ctx.addIssue({ code: 'custom', path: ['assignment', 'not_shared_reason'], message: 'Explain why the assignment was not shared.' })
    }
  })

type FormValues = z.infer<typeof schema>

const STATUS_HELP: Record<ExecutionStatus, string> = {
  SCHEDULED: 'Not taught yet',
  IN_PROGRESS: 'Underway right now',
  PARTIALLY_COMPLETED: 'Some subtopics covered',
  COMPLETED: 'All subtopics covered',
  RESCHEDULED: 'Moved to another date',
  NOT_CONDUCTED: 'Class did not happen',
}

function toForm(d: LectureDetail): FormValues {
  const e = d.execution
  const a = e?.assignment
  return {
    execution_status: e?.execution_status ?? 'SCHEDULED',
    actual_completion_date: e?.actual_completion_date ?? '',
    rescheduled_to: e?.rescheduled_to ?? '',
    covered_subtopic_ids: e?.covered_subtopic_ids ?? [],
    remarks: e?.remarks ?? '',
    recording_url: e?.recording_url ?? '',
    additional_topics: e?.additional_topics ?? '',
    shared: e?.shared_with_students === true ? 'yes' : e?.shared_with_students === false ? 'no' : '',
    not_shared_reason: e?.not_shared_reason ?? '',
    notes: e?.notes.map((n) => ({ id: n.id, title: n.title ?? '', file_url: n.file_url })) ?? [],
    has_assignment: !!a,
    assignment: {
      title: a?.title ?? '',
      description: a?.description ?? '',
      link_url: a?.link_url ?? '',
      due_date: a?.due_date ?? '',
      shared: a?.shared_with_students === true ? 'yes' : a?.shared_with_students === false ? 'no' : '',
      not_shared_reason: a?.not_shared_reason ?? '',
    },
  }
}

function toPayload(v: FormValues) {
  const done = v.execution_status === 'COMPLETED' || v.execution_status === 'PARTIALLY_COMPLETED'
  return {
    execution_status: v.execution_status,
    actual_completion_date: done && v.actual_completion_date ? v.actual_completion_date : null,
    rescheduled_to: v.execution_status === 'RESCHEDULED' ? v.rescheduled_to || null : null,
    covered_subtopic_ids: v.covered_subtopic_ids,
    remarks: v.remarks?.trim() || null,
    recording_url: v.recording_url?.trim() || null,
    additional_topics: v.additional_topics?.trim() || null,
    shared_with_students: v.shared === '' ? null : v.shared === 'yes',
    not_shared_reason: v.shared === 'no' ? v.not_shared_reason : null,
    notes: v.notes.map((n) => ({ ...(n.id ? { id: n.id } : {}), title: n.title || null, file_url: n.file_url.trim() })),
    assignment: v.has_assignment
      ? {
          title: v.assignment.title!.trim(),
          description: v.assignment.description || null,
          link_url: v.assignment.link_url?.trim() || null,
          due_date: v.assignment.due_date || null,
          shared_with_students: v.assignment.shared === '' ? null : v.assignment.shared === 'yes',
          not_shared_reason: v.assignment.shared === 'no' ? v.assignment.not_shared_reason : null,
        }
      : null,
  }
}

function YesNo({ value, onChange, name, label }: { value: '' | 'yes' | 'no'; onChange: (v: 'yes' | 'no') => void; name: string; label: string }) {
  return (
    <fieldset>
      <legend className="label">{label}</legend>
      <div className="flex gap-2">
        {(['yes', 'no'] as const).map((o) => (
          <label key={o} className={cn('flex h-9 flex-1 cursor-pointer items-center justify-center rounded-md border text-[13px] font-medium sm:flex-none sm:px-6', value === o ? 'border-primary bg-primary-soft text-primary' : 'border-line-strong text-fg-secondary hover:bg-surface-2')}>
            <input type="radio" name={name} className="sr-only" checked={value === o} onChange={() => onChange(o)} />
            {o === 'yes' ? 'Yes' : 'No'}
          </label>
        ))}
      </div>
    </fieldset>
  )
}

export function LectureExecutionPage() {
  const { lectureId } = useParams()
  const toast = useToast()
  const detail = useApi<LectureDetail>(`/lectures/${lectureId}`)
  const d = detail.data
  useBreadcrumbs([{ label: 'Course Progress', to: '/professor/courses' }, { label: d ? d.subject.short_name ?? d.subject.code : '…', to: d ? `/professor/courses/${d.plan.id}` : undefined }, { label: d ? `Lecture ${d.lecture_no}` : '…' }])

  if (detail.loading && !d) return <PageLoading />
  if (detail.error || !d) return <ErrorState message={detail.error?.message ?? 'Lecture not found'} onRetry={detail.reload} />

  return (
    <div className="mx-auto max-w-6xl pb-24 lg:pb-0">
      <Link to="/professor/sprint-plan" className="mb-3 inline-flex items-center gap-1 text-[13px] text-fg-label hover:text-fg">
        <ArrowLeft className="h-3.5 w-3.5" /> Sprint Plan
      </Link>
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[12px] font-semibold tracking-wide text-primary uppercase">
            {d.subject.name} · Lecture {d.lecture_no}
          </div>
          <h1 className="mt-0.5 text-[21px] leading-tight font-semibold tracking-tight text-fg sm:text-2xl">{d.content_topic}</h1>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusBadge value={d.execution_status} map={EXECUTION_STATUS} />
          {d.submission_status && <StatusBadge value={d.submission_status} map={SUBMISSION_STATUS} />}
        </div>
      </div>

      {d.open_correction && (
        <InlineAlert tone="danger" className="mb-4" title={`${d.open_correction.verification_level} requested a correction`}>
          “{d.open_correction.remarks}” — {d.open_correction.verifier?.full_name}, {fmt.dateTime(d.open_correction.verified_at)}
        </InlineAlert>
      )}

      {/* Start / End Class sits above everything so it is the first thing on a phone. */}
      <LiveClassPanel d={d} onSaved={(next, msg) => { detail.setData(next); toast('success', msg) }} />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]">
        <div className="space-y-5 lg:sticky lg:top-20 lg:self-start">
          <MasterPlanPanel d={d} />
          {(d.verifications.length > 0 || d.class_session) && (
            <Section title="Verification progress">
              <VerificationTimeline submitted={!!d.execution?.submitted_at} submissionStatus={d.submission_status} steps={d.verifications} chain={d.verification_chain} />
            </Section>
          )}
          {d.class_session && <ClassTimingPanel session={d.class_session} />}
          {d.verifications.length > 0 && (
            <Section title="Verification history">
              <VerificationHistory items={d.verifications} />
            </Section>
          )}
        </div>
        <div>
          {d.can_edit ? (
            <div className="space-y-5">
              <ExecutionForm d={d} onSaved={(next, msg) => { detail.setData(next); toast('success', msg) }} />
              <EvidencePanel d={d} onSaved={(next, msg) => { detail.setData(next); toast('success', msg) }} />
            </div>
          ) : (
            <div className="space-y-4">
              <InlineAlert tone="info" title="This record is locked">
                {d.submission_status === 'FINAL_VERIFIED'
                  ? 'It has been verified by CL/CH and final verified by OM.'
                  : `Submitted ${fmt.dateTime(d.execution?.submitted_at)}. It unlocks only if a verifier requests a correction.`}
              </InlineAlert>
              <ExecutionSummary d={d} />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function ExecutionForm({ d, onSaved }: { d: LectureDetail; onSaved: (d: LectureDetail, message: string) => void }) {
  const { register, control, handleSubmit, setValue, reset, trigger, getValues, formState: { errors, isDirty } } = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: toForm(d) })
  const notes = useFieldArray({ control, name: 'notes' })
  const [status, covered, shared, hasAssignment, assignmentShared] = useWatch({ control, name: ['execution_status', 'covered_subtopic_ids', 'shared', 'has_assignment', 'assignment.shared'] })
  const [saving, setSaving] = useState<'draft' | 'submit' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)

  useEffect(() => reset(toForm(d)), [d, reset])

  const subtopics = d.master.subtopics
  const allCovered = subtopics.length === 0 || subtopics.every((s) => covered.includes(s.id))
  const someCovered = covered.length > 0
  const done = status === 'COMPLETED' || status === 'PARTIALLY_COMPLETED'

  // Gentle automation: ticking everything suggests Completed; leaving gaps suggests Partial.
  const toggleSub = (id: string, on: boolean) => {
    const next = on ? [...covered, id] : covered.filter((x) => x !== id)
    setValue('covered_subtopic_ids', next, { shouldDirty: true })
    if (!getValues('actual_completion_date') && next.length) setValue('actual_completion_date', todayISO(), { shouldDirty: true })
    // Keep Completed / Partially completed in step with the ticks; never override Rescheduled.
    if (next.length && status !== 'RESCHEDULED') {
      setValue('execution_status', subtopics.every((s) => next.includes(s.id)) ? 'COMPLETED' : 'PARTIALLY_COMPLETED', { shouldDirty: true })
    }
  }

  const save = async (values: FormValues): Promise<LectureDetail | null> => {
    setError(null)
    try {
      const { data } = await api.put<LectureDetail>(`/lectures/${d.id}/progress`, toPayload(values))
      return data
    } catch (e) {
      setError(e instanceof ApiError && e.code === 'VALIDATION_ERROR' ? 'Some fields are invalid. Check the highlighted fields.' : errorMessage(e))
      return null
    }
  }

  const onDraft = handleSubmit(async (values) => {
    setSaving('draft')
    const next = await save(values)
    setSaving(null)
    if (next) onSaved(next, 'Draft saved.')
  })

  const onSubmitForVerification = async () => {
    setSaving('submit')
    const next = await save(getValues())
    if (next?.execution) {
      try {
        const { data } = await api.post<LectureDetail>(`/lecture-progress/${next.execution.id}/submit`)
        setConfirmOpen(false)
        onSaved(data, `Lecture ${d.lecture_no} submitted for verification.`)
      } catch (e) {
        setError(errorMessage(e))
      }
    }
    setSaving(null)
    setConfirmOpen(false)
  }

  const askSubmit = async () => {
    setError(null)
    if (!(await trigger())) return
    const v = getValues()
    if (!(v.execution_status === 'COMPLETED' || v.execution_status === 'PARTIALLY_COMPLETED')) {
      setError('Only completed or partially completed lectures can be submitted for verification.')
      return
    }
    if (v.shared === '') {
      setError('Say whether the lecture material was shared with students before submitting.')
      return
    }
    setConfirmOpen(true)
  }

  return (
    <form onSubmit={onDraft} noValidate>
      <Section title="Lecture execution" aside={<span className="meta">{isDirty ? 'Unsaved changes' : d.execution ? `Saved ${fmt.dateTime(d.execution.updated_at)}` : 'Not recorded yet'}</span>}>
        <div className="space-y-6">
          <fieldset>
            <legend className="label">Status</legend>
            <Controller
              control={control}
              name="execution_status"
              render={({ field }) => (
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {EXECUTION_STATUSES.map((s) => (
                    <label key={s} className={cn('cursor-pointer rounded-md border px-3 py-2', field.value === s ? 'border-primary bg-primary-soft ring-1 ring-primary' : 'border-line-strong hover:bg-surface-2')}>
                      <input type="radio" className="sr-only" checked={field.value === s} onChange={() => field.onChange(s)} name={field.name} />
                      <span className="block text-[13px] font-semibold text-fg">{EXECUTION_STATUS[s].label}</span>
                      <span className="meta block">{STATUS_HELP[s]}</span>
                    </label>
                  ))}
                </div>
              )}
            />
            {status === 'COMPLETED' && !allCovered && (
              <InlineAlert tone="warning" className="mt-3" action={<Button size="sm" onClick={() => setValue('execution_status', 'PARTIALLY_COMPLETED', { shouldDirty: true })}>Use Partially completed</Button>}>
                {subtopics.length - covered.length} subtopic(s) are not ticked. A lecture is Completed only when every subtopic is covered.
              </InlineAlert>
            )}
          </fieldset>

          {subtopics.length > 0 && (
            <fieldset>
              <legend className="label">Covered subtopics <span className="font-normal text-fg-muted">· {covered.length} of {subtopics.length}</span></legend>
              <div className="divide-y divide-line-subtle rounded-md border border-line">
                {subtopics.map((s) => (
                  <Checkbox key={s.id} className="px-3 py-2.5" label={s.title} checked={covered.includes(s.id)} onChange={(e) => toggleSub(s.id, e.target.checked)} />
                ))}
              </div>
              {status === 'PARTIALLY_COMPLETED' && !someCovered && <p className="mt-1 text-[12.5px] text-danger">Tick at least one covered subtopic.</p>}
            </fieldset>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            {(done || status === 'IN_PROGRESS') && (
              <FormField label="Actual completion date" required={done} error={errors.actual_completion_date?.message} hint={d.master.planned_date ? `Planned for ${fmt.date(d.master.planned_date)} - the planned date is never changed.` : undefined} htmlFor="actual">
                <Input id="actual" type="date" max={todayISO()} invalid={!!errors.actual_completion_date} {...register('actual_completion_date')} />
              </FormField>
            )}
            {status === 'RESCHEDULED' && (
              <FormField label="New date" required error={errors.rescheduled_to?.message} hint="The original planned date stays on record for delay reports." htmlFor="resched">
                <Input id="resched" type="date" min={todayISO()} invalid={!!errors.rescheduled_to} {...register('rescheduled_to')} />
              </FormField>
            )}
          </div>

          <div>
            <div className="label">Daily lecture notes</div>
            <div className="space-y-2">
              {notes.fields.map((f, i) => (
                <div key={f.id} className="flex flex-col gap-2 rounded-md border border-line p-2.5 sm:flex-row sm:items-start">
                  <Input aria-label="Notes title" placeholder="Title (optional)" className="sm:w-48" {...register(`notes.${i}.title`)} />
                  <div className="flex-1">
                    <Input aria-label="Notes link" placeholder="https://drive.google.com/…" invalid={!!errors.notes?.[i]?.file_url} {...register(`notes.${i}.file_url`)} />
                    {errors.notes?.[i]?.file_url && <p className="mt-1 text-[12.5px] text-danger">{errors.notes[i]!.file_url!.message}</p>}
                  </div>
                  <Button size="icon" variant="ghost" aria-label="Remove notes link" onClick={() => notes.remove(i)}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
              <div className="flex flex-wrap items-center gap-3">
                <Button size="sm" icon={<Link2 className="h-3.5 w-3.5" />} onClick={() => notes.append({ title: '', file_url: '' })} disabled={notes.fields.length >= 10}>
                  Add notes link
                </Button>
                <span className="meta">PDF upload is planned; add a Drive or LMS link for now.</span>
              </div>
            </div>
          </div>

          <Controller control={control} name="shared" render={({ field }) => <YesNo name="shared" label="Shared with students?" value={field.value} onChange={field.onChange} />} />
          {shared === 'no' && (
            <FormField label="Reason not shared" required error={errors.not_shared_reason?.message} htmlFor="nsr">
              <Textarea id="nsr" rows={2} invalid={!!errors.not_shared_reason} {...register('not_shared_reason')} />
            </FormField>
          )}

          <div className="rounded-md border border-line">
            <div className="flex items-center justify-between gap-3 px-3 py-2.5">
              <Checkbox label="Weekly assignment" description="Attach an assignment given with this lecture" {...register('has_assignment')} />
              {!hasAssignment && <Plus className="h-4 w-4 text-fg-faint" aria-hidden />}
            </div>
            {hasAssignment && (
              <div className="grid gap-4 border-t border-line p-3 sm:grid-cols-2">
                <FormField label="Assignment title" required error={errors.assignment?.title?.message} className="sm:col-span-2" htmlFor="at">
                  <Input id="at" invalid={!!errors.assignment?.title} {...register('assignment.title')} />
                </FormField>
                <FormField label="Description" className="sm:col-span-2" htmlFor="ad">
                  <Textarea id="ad" rows={2} {...register('assignment.description')} />
                </FormField>
                <FormField label="Assignment link" error={errors.assignment?.link_url?.message} htmlFor="al">
                  <Input id="al" placeholder="https://" invalid={!!errors.assignment?.link_url} {...register('assignment.link_url')} />
                </FormField>
                <FormField label="Due date" htmlFor="add">
                  <Input id="add" type="date" {...register('assignment.due_date')} />
                </FormField>
                <div className="sm:col-span-2">
                  <Controller control={control} name="assignment.shared" render={({ field }) => <YesNo name="ashared" label="Assignment shared in student groups?" value={field.value} onChange={field.onChange} />} />
                </div>
                {assignmentShared === 'no' && (
                  <FormField label="Reason not shared" required error={errors.assignment?.not_shared_reason?.message} className="sm:col-span-2" htmlFor="ansr">
                    <Textarea id="ansr" rows={2} {...register('assignment.not_shared_reason')} />
                  </FormField>
                )}
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormField label="Additional topics covered" hint="Optional. Anything taught beyond the planned subtopics." error={errors.additional_topics?.message} htmlFor="additional_topics">
              <Textarea id="additional_topics" rows={2} invalid={!!errors.additional_topics} {...register('additional_topics')} />
            </FormField>
            <FormField label="Class recording link" hint="Optional. Paste the link if the class was recorded." error={errors.recording_url?.message} htmlFor="recording_url">
              <Input id="recording_url" type="url" inputMode="url" placeholder="https://" invalid={!!errors.recording_url} {...register('recording_url')} />
            </FormField>
          </div>

          <FormField label="Remarks" required={status === 'NOT_CONDUCTED'} error={errors.remarks?.message} hint="Anything the verifiers should know - deviations, extra coverage, disruptions." htmlFor="remarks">
            <Textarea id="remarks" rows={3} invalid={!!errors.remarks} {...register('remarks')} />
          </FormField>

          {error && <InlineAlert tone="danger">{error}</InlineAlert>}
        </div>
      </Section>

      {/* Sticky on mobile so the primary actions are always reachable. */}
      <div className="fixed inset-x-0 bottom-0 z-30 flex gap-2 border-t border-line bg-bg/95 px-4 py-3 backdrop-blur lg:static lg:mt-4 lg:justify-end lg:border-0 lg:bg-transparent lg:p-0">
        <Button type="submit" className="flex-1 justify-center lg:flex-none" loading={saving === 'draft'} disabled={!!saving}>
          Save draft
        </Button>
        <Button variant="primary" className="flex-1 justify-center lg:flex-none" icon={<Send className="h-4 w-4" />} disabled={!!saving} onClick={askSubmit}>
          Submit for verification
        </Button>
      </div>

      <ConfirmDialog open={confirmOpen} onClose={() => setConfirmOpen(false)} onConfirm={onSubmitForVerification} loading={saving === 'submit'} title={`Submit Lecture ${d.lecture_no} for verification?`} confirmLabel="Submit">
        <p>The record goes to CL/CH for academic verification, then to OM for final verification. It is locked while under review and reopens only if a verifier requests a correction.</p>
        <p className="mt-2 inline-flex items-center gap-1.5 text-fg-label">
          <Lock className="h-3.5 w-3.5" /> {EXECUTION_STATUS[status].label}
          {getValues('actual_completion_date') ? ` on ${fmt.date(getValues('actual_completion_date'))}` : ''}
        </p>
      </ConfirmDialog>
    </form>
  )
}
