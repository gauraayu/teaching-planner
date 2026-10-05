import { useEffect, useState } from 'react'
import { InlineAlert } from '@/components/feedback/States'
import { Checkbox, FormField, Input, Select } from '@/components/forms/Fields'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { useApi } from '@/hooks/useApi'
import { sprintPlansApi, type SprintPlanBrief, type SprintPlanDetail } from '@/lib/api/sprintPlans'
import { WEEKDAYS } from '@/lib/api/timetable'
import { errorMessage, type Paged } from '@/services/api'

/** Create / edit the frame of a sprint plan: its name, dates and working days. Subjects are added on its page. */
export function SprintPlanDialog({ open, plan, onClose, onSaved }: { open: boolean; plan?: SprintPlanBrief | null; onClose: () => void; onSaved: (p: SprintPlanDetail) => void }) {
  const years = useApi<Paged<{ id: string; name: string; is_current: boolean }>>(open ? '/academic-years' : null)
  const [f, setF] = useState({ name: '', academic_year_id: '', start_date: '', end_date: '', working_days: [0, 1, 2, 3, 4, 5] })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (!open) return
    setError(null)
    setF(plan ? { name: plan.name, academic_year_id: plan.academic_year.id, start_date: plan.start_date, end_date: plan.end_date, working_days: plan.working_days }
      : { name: '', academic_year_id: '', start_date: '', end_date: '', working_days: [0, 1, 2, 3, 4, 5] })
  }, [open, plan])
  useEffect(() => {
    const cur = years.data?.items.find((y) => y.is_current)
    if (open && !plan && cur) setF((x) => (x.academic_year_id ? x : { ...x, academic_year_id: cur.id }))
  }, [years.data, open, plan])
  if (!open) return null
  const save = async () => {
    if (f.name.trim().length < 3) return setError('Give the sprint plan a name.')
    if (!f.academic_year_id) return setError('Choose the academic year.')
    if (!f.start_date || !f.end_date) return setError('The start date and end date are required: the whole plan is calculated from them.')
    if (f.end_date <= f.start_date) return setError('The end date must be after the start date.')
    if (!f.working_days.length) return setError('Choose at least one working day.')
    setBusy(true)
    setError(null)
    try {
      onSaved(plan ? await sprintPlansApi.update(plan.id, { ...f, name: f.name.trim() }) : await sprintPlansApi.create({ ...f, name: f.name.trim() }))
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <Dialog open onClose={onClose} title={plan ? 'Edit sprint plan' : 'Create sprint plan'} description="The semester's dates and working days. Subjects, professors and weekly sessions are added next."
      footer={<><Button onClick={onClose} disabled={busy}>Cancel</Button><Button variant="primary" loading={busy} onClick={save}>{plan ? 'Save' : 'Create sprint plan'}</Button></>}>
      <div className="space-y-4">
        <FormField label="Sprint plan name" required htmlFor="sp-name"><Input id="sp-name" value={f.name} onChange={(e) => setF((x) => ({ ...x, name: e.target.value }))} placeholder="B.Tech Semester Sprint Plan – Jan 2027" data-autofocus /></FormField>
        <FormField label="Academic year" required htmlFor="sp-ay">
          <Select id="sp-ay" value={f.academic_year_id} onChange={(e) => setF((x) => ({ ...x, academic_year_id: e.target.value }))}>
            <option value="">Select academic year</option>
            {years.data?.items.map((y) => <option key={y.id} value={y.id}>{y.name}</option>)}
          </Select>
        </FormField>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField label="Start date" required htmlFor="sp-start"><Input id="sp-start" type="date" value={f.start_date} onChange={(e) => setF((x) => ({ ...x, start_date: e.target.value }))} /></FormField>
          <FormField label="End date" required htmlFor="sp-end" hint="Every topic is planned to finish by this date"><Input id="sp-end" type="date" value={f.end_date} min={f.start_date} onChange={(e) => setF((x) => ({ ...x, end_date: e.target.value }))} /></FormField>
        </div>
        <div>
          <div className="label">Working days</div>
          <div className="flex flex-wrap gap-x-5 gap-y-2">
            {WEEKDAYS.map((d, i) => <Checkbox key={d} label={d} checked={f.working_days.includes(i)} onChange={(e) => setF((x) => ({ ...x, working_days: e.target.checked ? [...x.working_days, i].sort() : x.working_days.filter((n) => n !== i) }))} />)}
          </div>
        </div>
        {plan?.status === 'ACTIVE' && <InlineAlert tone="info">After changing the dates or working days, choose Generate Semester Sprint again. Published weeks are not moved.</InlineAlert>}
        {error && <InlineAlert tone="danger">{error}</InlineAlert>}
      </div>
    </Dialog>
  )
}
