import { Download } from 'lucide-react'
import { useState } from 'react'
import { PageHeader, useBreadcrumbs } from '@/components/layout/PageHeader'
import { FilterBar, FilterDate, FilterSelect, useAcademicOptions } from '@/components/tables/FilterBar'
import { Button } from '@/components/ui/Button'
import { useApi } from '@/hooks/useApi'
import { fmt, isoLocal, todayISO } from '@/lib/status'
import type { Paged } from '@/services/api'
import type { UserBrief } from '@/types/domain'
import { downloadCsv } from '@/utils/cn'
import { ClassOperations } from '../components/ClassOperations'
import type { ClassRow } from '../types/om.types'

export function daysAgo(n: number) {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return isoLocal(d)
}

/** Every class with a recorded entry, newest first. */
export function OperationsRecords() {
  useBreadcrumbs([{ label: 'Records' }, { label: 'Operations Records' }])
  const opts = useAcademicOptions()
  const professors = useApi<Paged<UserBrief>>('/users', { role: 'PROFESSOR' })
  const initial = { date_from: daysAgo(30), date_to: todayISO(), professor_id: '', subject_id: '', timing: '' }
  const [f, setF] = useState(initial)
  const set = (k: keyof typeof f) => (v: string) => setF((x) => ({ ...x, [k]: v }))
  const records = useApi<Paged<ClassRow>>('/om/records', f)
  const rows = records.data?.items
  const patch = (row: ClassRow) => records.setData((prev) => (prev ? { ...prev, items: prev.items.map((r) => (r.lecture_id === row.lecture_id ? row : r)) } : (prev as unknown as Paged<ClassRow>)))

  const exportCsv = () =>
    downloadCsv(
      `operations-records-${f.date_from}-to-${f.date_to}.csv`,
      ['Date', 'Scheduled start', 'Scheduled end', 'Professor', 'Subject', 'Section', 'Room', 'Lecture', 'Entry', 'Exit', 'Delay (min)', 'Timing', 'Delay reason', 'Remarks', 'CL/CH', 'OM'],
      (rows ?? []).map((r) => [r.date, r.scheduled_start, r.scheduled_end, r.professor.full_name, r.subject.name, `Sem ${r.semester.replace('Semester ', '')}-${r.section}`, r.room, r.lecture_no, r.entry_time, r.exit_time, r.delay_minutes, r.timing_status === 'DELAYED' ? 'Delayed' : 'On time', r.delay_reason_label, r.delay_remarks, r.verification.levels.CL_CH, r.verification.levels.OM]),
    )

  return (
    <div>
      <PageHeader
        title="Operations Records"
        description={`Recorded class timings${records.data ? ` · ${records.data.total} between ${fmt.dateShort(f.date_from)} and ${fmt.dateShort(f.date_to)}` : ''}`}
        actions={<Button icon={<Download className="h-4 w-4" />} onClick={exportCsv} disabled={!rows?.length}>Export CSV</Button>}
      />
      <div className="mb-4">
        <FilterBar onReset={() => setF(initial)} active={JSON.stringify(f) !== JSON.stringify(initial)}>
          <FilterDate label="From" value={f.date_from} onChange={set('date_from')} />
          <FilterDate label="To" value={f.date_to} onChange={set('date_to')} />
          <FilterSelect label="Professor" value={f.professor_id} onChange={set('professor_id')} options={professors.data?.items.map((p) => ({ value: p.id, label: p.full_name })) ?? []} />
          <FilterSelect label="Subject" value={f.subject_id} onChange={set('subject_id')} options={opts.subjects} width="w-52" />
          <FilterSelect label="Timing" value={f.timing} onChange={set('timing')} options={[{ value: 'ON_TIME', label: 'On time' }, { value: 'DELAYED', label: 'Delayed' }]} width="w-32" />
        </FilterBar>
      </div>
      <ClassOperations
        showDate
        rows={rows}
        loading={records.loading}
        error={records.error?.message}
        onRetry={records.reload}
        onChanged={patch}
        emptyTitle="No records in this range"
        emptyDescription="Widen the dates or clear the filters."
      />
    </div>
  )
}
