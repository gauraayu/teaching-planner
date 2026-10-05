import { Archive, CalendarClock, Copy, MoreHorizontal, Pencil, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { EmptyState, ErrorState, LoadingRows, useToast } from '@/components/feedback/States'
import { PageHeader, useBreadcrumbs } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button, ButtonLink } from '@/components/ui/Button'
import { ConfirmDialog } from '@/components/ui/Dialog'
import { Menu } from '@/components/ui/Menu'
import { useApi } from '@/hooks/useApi'
import { SPRINT_STATUS, sprintPlansApi, type SprintPlanBrief } from '@/lib/api/sprintPlans'
import { Link, useNavigate } from '@/lib/router'
import { fmt } from '@/lib/status'
import { ApiError, errorMessage, type Paged } from '@/services/api'
import { SprintPlanDialog } from './SprintPlanForm'

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

/** What the ⋮ menu offers for one sprint plan, and the two confirmations behind Archive and Delete. */
export function useSprintPlanActions(onChanged: () => void) {
  const toast = useToast()
  const navigate = useNavigate()
  const [edit, setEdit] = useState<SprintPlanBrief | null>(null)
  const [del, setDel] = useState<SprintPlanBrief | null>(null)
  const [arch, setArch] = useState<SprintPlanBrief | null>(null)
  const duplicate = async (p: SprintPlanBrief) => {
    try {
      const copy = await sprintPlansApi.duplicate(p.id)
      toast('success', copy.duplicate?.skipped.length ? `Copy created. ${copy.duplicate.skipped.join(', ')} still run in the original, so they were not copied.` : `Copy created with ${copy.duplicate?.copied ?? 0} subject(s).`)
      navigate(`/admin/sprint-plans/${copy.id}`)
    } catch (e) {
      toast('danger', errorMessage(e))
    }
  }
  const menu = (p: SprintPlanBrief) => (
    <Menu label="Sprint plan actions" trigger={(t) => <Button size="icon" variant="ghost" aria-label={`Actions for ${p.name}`} {...t}><MoreHorizontal className="h-4 w-4" /></Button>}
      items={[
        ...(p.status !== 'ARCHIVED' ? [{ label: 'Edit sprint plan', icon: <Pencil className="h-3.5 w-3.5" />, onSelect: () => setEdit(p) }] : []),
        { label: 'Duplicate sprint plan', icon: <Copy className="h-3.5 w-3.5" />, onSelect: () => void duplicate(p) },
        ...(p.status !== 'ARCHIVED' ? [{ label: 'Archive sprint plan', icon: <Archive className="h-3.5 w-3.5" />, onSelect: () => setArch(p) }] : []),
        { label: 'Delete sprint plan', icon: <Trash2 className="h-3.5 w-3.5" />, onSelect: () => (p.in_use ? setArch(p) : setDel(p)) },
      ]} />
  )
  const dialogs = (
    <>
      <SprintPlanDialog open={!!edit} plan={edit} onClose={() => setEdit(null)} onSaved={(p) => { setEdit(null); toast('success', p.needs_regeneration ? 'Saved. Generate the semester sprint again to apply the new dates.' : 'Sprint plan saved.'); onChanged() }} />
      <ConfirmDialog open={!!del} onClose={() => setDel(null)} tone="danger" title="Delete sprint plan?" confirmLabel="Delete"
        onConfirm={async () => {
          try {
            await sprintPlansApi.remove(del!.id)
            toast('success', 'Sprint plan deleted.')
            setDel(null)
            onChanged()
            navigate('/admin/sprint-plans')
          } catch (e) {
            // Someone published or recorded something in the meantime: offer the safe action instead.
            if (e instanceof ApiError && e.code === 'SPRINT_PLAN_IN_USE') { setArch(del); setDel(null) }
            toast('danger', errorMessage(e))
          }
        }}>
        <span className="block font-medium text-fg">{del?.name}</span>
        <span className="mt-0.5 block text-fg-secondary">{del ? `${fmt.date(del.start_date)} – ${fmt.date(del.end_date)}` : ''}</span>
        <span className="mt-2 block">This removes the sprint plan, its {del?.subject_count ?? 0} subject allocation{del?.subject_count === 1 ? '' : 's'} with their imported topics, and its unpublished weekly plans. Nothing has been published or recorded in it.</span>
      </ConfirmDialog>
      <ConfirmDialog open={!!arch} onClose={() => setArch(null)} title="Archive sprint plan?" confirmLabel="Archive"
        onConfirm={async () => {
          try {
            await sprintPlansApi.archive(arch!.id)
            toast('success', 'Sprint plan archived. Its academic records are kept.')
            setArch(null)
            onChanged()
          } catch (e) {
            toast('danger', errorMessage(e))
          }
        }}>
        <span className="block font-medium text-fg">{arch?.name}</span>
        {arch?.in_use && <span className="mt-2 block">This plan has published weeks or recorded classes, so it cannot be deleted. Archiving keeps every professor submission, CL/CH and OM verification.</span>}
        <span className="mt-2 block">Its classes leave everyone&apos;s schedule and nothing more is planned from it.</span>
      </ConfirmDialog>
    </>
  )
  return { menu, dialogs }
}

export function SprintPlansPage() {
  useBreadcrumbs([{ label: 'Teaching Management' }, { label: 'Sprint Plans' }])
  const navigate = useNavigate()
  const list = useApi<Paged<SprintPlanBrief>>('/sprint-plans')
  const [creating, setCreating] = useState(false)
  const { menu, dialogs } = useSprintPlanActions(() => void list.reload(true))
  return (
    <div>
      <PageHeader title="Sprint Plans" description="One plan per semester: its dates, subjects, professors and weekly sessions. The weekly sprint plans, every professor's schedule and all verification are read from it."
        actions={<Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setCreating(true)}>Create sprint plan</Button>} />
      {list.error ? <div className="panel"><ErrorState message={list.error.message} onRetry={list.reload} /></div> : !list.data ? <div className="panel"><LoadingRows rows={4} /></div> : list.data.items.length === 0 ? (
        <div className="panel"><EmptyState icon={<CalendarClock className="h-5 w-5" />} title="No sprint plan yet" description="Create the semester's sprint plan: set the start and end date, add subjects with their professors and weekly sessions, import the topics, then generate." action={<Button variant="primary" onClick={() => setCreating(true)}>Create sprint plan</Button>} /></div>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {list.data.items.map((p) => (
            <section key={p.id} className="panel p-4" aria-label={p.name}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <Link to={`/admin/sprint-plans/${p.id}`} className="text-[15px] font-semibold text-fg hover:text-primary">{p.name}</Link>
                  <div className="mt-1 flex flex-wrap items-center gap-2">
                    <Badge tone={SPRINT_STATUS[p.status].tone}>{SPRINT_STATUS[p.status].label}</Badge>
                    {p.is_current && <Badge tone="info" icon={false}>Running now</Badge>}
                    <span className="meta">{p.academic_year.name}</span>
                  </div>
                </div>
                {menu(p)}
              </div>
              <div className="tnum mt-3 text-[13.5px] font-medium text-fg-soft">{fmt.date(p.start_date)} → {fmt.date(p.end_date)}</div>
              <div className="meta mt-1">{p.total_weeks} weeks · {p.working_days.map((d) => DAYS[d]).join(', ')} · {p.subject_count} subject{p.subject_count === 1 ? '' : 's'} · {p.topics ?? 0} topics</div>
              <div className="mt-3"><ButtonLink size="sm" to={`/admin/sprint-plans/${p.id}`}>Open sprint plan</ButtonLink></div>
            </section>
          ))}
        </div>
      )}
      <SprintPlanDialog open={creating} onClose={() => setCreating(false)} onSaved={(p) => { setCreating(false); navigate(`/admin/sprint-plans/${p.id}`) }} />
      {dialogs}
    </div>
  )
}
