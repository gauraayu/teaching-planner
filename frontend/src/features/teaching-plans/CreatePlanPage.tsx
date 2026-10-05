import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useNavigate, useSearchParams } from '@/lib/router'
import { z } from 'zod'
import { InlineAlert } from '@/components/feedback/States'
import { FormField, Input, Select } from '@/components/forms/Fields'
import { PageHeader, useBreadcrumbs } from '@/components/layout/PageHeader'
import { Button, ButtonLink } from '@/components/ui/Button'
import { useApi } from '@/hooks/useApi'
import { ApiError, api, errorMessage, type Paged } from '@/services/api'
import type { ManagedUser, PlanBrief } from '@/types/domain'
import { PROFESSOR_OPTIONS, professorLabel, professorParams } from '@/lib/api/users'
import { startImport } from '@/features/imports/ImportsPage'

const schema = z.object({
  academic_year_id: z.string().min(1, 'Select the academic year'),
  semester_id: z.string().min(1, 'Select the semester'),
  department_id: z.string().min(1, 'Select the department'),
  branch_id: z.string().min(1, 'Select the branch'),
  section_id: z.string().min(1, 'Select the section'),
  subject_id: z.string().min(1, 'Select the subject'),
  professor_id: z.string().min(1, 'Assign a professor'),
  name: z.string().max(200).optional(),
  room: z.string().max(40).optional(),
  classes_per_week: z.number().int().min(0).max(12),
  labs_per_week: z.number().int().min(0).max(6),
  lab_room: z.string().max(40).optional(),
})
type Form = z.infer<typeof schema>

type Opt = { id: string; name: string }

export function CreatePlanPage() {
  useBreadcrumbs([{ label: 'Teaching Plans', to: '/admin/plans' }, { label: 'Create plan' }])
  const navigate = useNavigate()
  const sprintId = useSearchParams()[0].get('sprint') // set when the subject is added from a sprint plan
  const years = useApi<Paged<Opt & { is_current: boolean }>>('/academic-years')
  const depts = useApi<Paged<Opt & { code: string }>>('/departments')
  const { register, handleSubmit, watch, setValue, formState: { errors, isSubmitting } } = useForm<Form>({ resolver: zodResolver(schema), defaultValues: { name: '', classes_per_week: 3, labs_per_week: 0 } })
  const [serverError, setServerError] = useState<string | null>(null)
  const [duplicate, setDuplicate] = useState<PlanBrief | null>(null)
  const [created, setCreated] = useState<PlanBrief | null>(null)

  const [year, sem, dept, branch, section, subject] = watch(['academic_year_id', 'semester_id', 'department_id', 'branch_id', 'section_id', 'subject_id'])
  const semesters = useApi<Paged<Opt & { number: number }>>(year ? '/semesters' : null, { academic_year_id: year })
  const branches = useApi<Paged<Opt & { code: string }>>(dept ? '/branches' : null, { department_id: dept })
  const sections = useApi<Paged<Opt>>(sem && branch ? '/sections' : null, { semester_id: sem, branch_id: branch })
  const semNumber = semesters.data?.items.find((s) => s.id === sem)?.number
  const subjects = useApi<Paged<Opt & { code: string }>>(branch && semNumber ? '/subjects' : null, { branch_id: branch, semester_number: semNumber })
  // Real, active professor accounts from User Management - narrowed to those eligible for the chosen subject.
  const professors = useApi<Paged<ManagedUser>>(PROFESSOR_OPTIONS, professorParams(subject))

  // Sensible defaults: current academic year, the only department.
  useEffect(() => {
    const cur = years.data?.items.find((y) => y.is_current)
    if (cur && !year) setValue('academic_year_id', cur.id)
  }, [years.data, year, setValue])
  useEffect(() => {
    if (depts.data?.items.length === 1 && !dept) setValue('department_id', depts.data.items[0].id)
  }, [depts.data, dept, setValue])

  // Live duplicate check as soon as subject + section + semester are known.
  useEffect(() => {
    setDuplicate(null)
    if (!subject || !section || !sem) return
    api.get<{ duplicate: PlanBrief | null }>('/teaching-plans/check-duplicate', { params: { subject_id: subject, section_id: section, semester_id: sem } })
      .then((r) => setDuplicate(r.data.duplicate)).catch(() => {})
  }, [subject, section, sem])

  const suggestedName = useMemo(() => {
    const s = subjects.data?.items.find((x) => x.id === subject)
    const se = semesters.data?.items.find((x) => x.id === sem)
    const sc = sections.data?.items.find((x) => x.id === section)
    return s && se && sc ? `${s.name} – ${se.name} – Section ${sc.name}` : ''
  }, [subjects.data, semesters.data, sections.data, subject, sem, section])

  const onSubmit = async (values: Form) => {
    setServerError(null)
    try {
      const { data } = await api.post<PlanBrief>('/teaching-plans', { ...values, name: values.name || undefined, room: values.room || undefined, lab_room: values.lab_room || undefined, sprint_plan_id: sprintId || undefined })
      setCreated(data)
    } catch (e) {
      if (e instanceof ApiError && e.code === 'DUPLICATE_PLAN') {
        const d = e.details as { plan_id: string; name: string; status: PlanBrief['status'] }
        setDuplicate({ id: d.plan_id, name: d.name, status: d.status } as PlanBrief)
      }
      setServerError(errorMessage(e))
    }
  }

  if (created) {
    return (
      <div className="mx-auto max-w-xl">
        <div className="panel px-6 py-7">
          <h1 className="text-[17px] font-semibold text-fg">Teaching plan created</h1>
          <p className="meta mt-1">{created.name} is a draft assigned to {created.professor.full_name}. Import the lectures next.</p>
          <div className="mt-5 flex gap-2">
            <Button variant="primary" onClick={async () => navigate(`/admin/imports/${await startImport(created.id)}`)}>
              Continue to import plan
            </Button>
            {sprintId ? <ButtonLink to={`/admin/sprint-plans/${sprintId}`}>Back to sprint plan</ButtonLink> : <ButtonLink to={`/admin/plans/${created.id}`}>Open plan</ButtonLink>}
          </div>
        </div>
      </div>
    )
  }

  const sel = (name: keyof Form, label: string, items: { id: string; label: string }[] | undefined, disabled: boolean, hint?: string) => (
    <FormField label={label} required error={errors[name]?.message} hint={hint} htmlFor={name}>
      <Select id={name} invalid={!!errors[name]} disabled={disabled} {...register(name)}>
        <option value="">{disabled ? '—' : `Select ${label.toLowerCase()}`}</option>
        {items?.map((i) => (
          <option key={i.id} value={i.id}>{i.label}</option>
        ))}
      </Select>
    </FormField>
  )

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title={sprintId ? 'Add subject to sprint plan' : 'Create subject plan'} description="Subject, section, professor and the sessions it needs every week. Its topics are imported in the next step." />
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="panel">
        <div className="space-y-6 p-5">
          <section>
            <h2 className="mb-3 text-[13px] font-semibold text-fg">Academic session</h2>
            <div className="grid gap-4 sm:grid-cols-2">
              {sel('academic_year_id', 'Academic year', years.data?.items.map((y) => ({ id: y.id, label: y.name })), false)}
              {sel('semester_id', 'Semester', semesters.data?.items.map((s) => ({ id: s.id, label: s.name })), !year)}
            </div>
          </section>
          <section>
            <h2 className="mb-3 text-[13px] font-semibold text-fg">Class</h2>
            <div className="grid gap-4 sm:grid-cols-3">
              {sel('department_id', 'Department', depts.data?.items.map((d) => ({ id: d.id, label: d.name })), false)}
              {sel('branch_id', 'Branch', branches.data?.items.map((b) => ({ id: b.id, label: `${b.code} · ${b.name}` })), !dept)}
              {sel('section_id', 'Section', sections.data?.items.map((s) => ({ id: s.id, label: `Section ${s.name}` })), !branch || !sem)}
            </div>
          </section>
          <section>
            <h2 className="mb-3 text-[13px] font-semibold text-fg">Subject &amp; faculty</h2>
            <div className="grid gap-4 sm:grid-cols-2">
              {sel('subject_id', 'Subject', subjects.data?.items.map((s) => ({ id: s.id, label: `${s.code} · ${s.name}` })), !branch || !semNumber, branch && semNumber ? `Subjects offered in ${semesters.data?.items.find((s) => s.id === sem)?.name}` : undefined)}
              {sel('professor_id', 'Assigned professor', professors.data?.items.map((p) => ({ id: p.id, label: professorLabel(p) })), false)}
            </div>
          </section>
          <FormField label="Plan name" hint={suggestedName ? `Leave blank to use “${suggestedName}”.` : 'Optional. Generated from the subject, semester and section if left blank.'} htmlFor="name">
            <Input id="name" placeholder={suggestedName || 'Optional'} {...register('name')} />
          </FormField>
          <section>
            <h2 className="mb-1 text-[13px] font-semibold text-fg">Weekly allocation</h2>
            <p className="meta mb-3">How many sessions this subject needs every week. The sprint plan schedules exactly these; you can change them there at any time.</p>
            <div className="grid gap-4 sm:grid-cols-4">
              <FormField label="Weekly sessions" error={errors.classes_per_week?.message} htmlFor="classes_per_week">
                <Input id="classes_per_week" type="number" min={0} max={12} className="tnum" {...register('classes_per_week', { valueAsNumber: true })} />
              </FormField>
              <FormField label="Labs per week" hint="Two periods each" error={errors.labs_per_week?.message} htmlFor="labs_per_week">
                <Input id="labs_per_week" type="number" min={0} max={6} className="tnum" {...register('labs_per_week', { valueAsNumber: true })} />
              </FormField>
              <FormField label="Classroom" hint="Optional preference" htmlFor="room">
                <Input id="room" placeholder="e.g. C-204" {...register('room')} />
              </FormField>
              <FormField label="Lab room" hint="Optional preference" htmlFor="lab_room">
                <Input id="lab_room" placeholder="e.g. Lab-301" {...register('lab_room')} />
              </FormField>
            </div>
          </section>
          {duplicate && (
            <InlineAlert tone="warning" title="A plan already exists for this class" action={<ButtonLink size="sm" to={`/admin/plans/${duplicate.id}`}>Open it</ButtonLink>}>
              {duplicate.name} ({duplicate.status.toLowerCase()}). Archive it before creating a new one.
            </InlineAlert>
          )}
          {serverError && !duplicate && <InlineAlert tone="danger">{serverError}</InlineAlert>}
        </div>
        <div className="flex justify-end gap-2 border-t border-line bg-surface-2 px-5 py-3">
          <ButtonLink to={sprintId ? `/admin/sprint-plans/${sprintId}` : '/admin/plans'}>Cancel</ButtonLink>
          <Button type="submit" variant="primary" loading={isSubmitting} disabled={!!duplicate}>
            {sprintId ? 'Add subject' : 'Create subject plan'}
          </Button>
        </div>
      </form>
    </div>
  )
}
