import { useMemo, useState } from 'react'
import { Segmented } from '@/components/forms/Fields'
import { PageHeader, useBreadcrumbs } from '@/components/layout/PageHeader'
import { useSearchParams } from '@/lib/router'
import { fmt } from '@/lib/status'
import { ClassOperations } from '../components/ClassOperations'
import { useOmDay } from '../hooks/useOmDay'
import type { ClassState } from '../types/om.types'

type Filter = 'ALL' | 'OPEN' | 'RUNNING' | 'DONE'
const MATCH: Record<Filter, ClassState[] | null> = {
  ALL: null,
  OPEN: ['YET_TO_START', 'ENTRY_DUE', 'NOT_RECORDED', 'EXIT_MISSING'],
  RUNNING: ['IN_CLASS'],
  DONE: ['COMPLETED'],
}

export function TodayClasses() {
  useBreadcrumbs([{ label: 'Live Operations' }, { label: "Today's Classes" }])
  const day = useOmDay()
  const [params, setParams] = useSearchParams()
  const [filter, setFilter] = useState<Filter>('ALL')
  const all = day.data?.classes
  const count = (f: Filter) => (all ?? []).filter((c) => !MATCH[f] || MATCH[f]!.includes(c.state)).length
  const rows = useMemo(() => all?.filter((c) => !MATCH[filter] || MATCH[filter]!.includes(c.state)), [all, filter])
  return (
    <div>
      <PageHeader title="Today's Classes" description={day.data ? `${fmt.weekday(day.data.date)}, ${fmt.date(day.data.date)} · every published class scheduled today${day.data.scope ? ` · scope: ${day.data.scope.label}` : ''}` : 'Every published class scheduled today'} />
      <ClassOperations
        rows={rows}
        loading={day.loading}
        error={day.error?.message}
        onRetry={day.reload}
        onChanged={day.applyRow}
        openId={params.get('class')}
        onOpened={() => setParams({}, { replace: true })}
        emptyTitle={filter === 'ALL' ? 'No classes scheduled today' : 'No classes in this state'}
        emptyDescription={filter === 'ALL' ? 'Open Class Schedule to work on another day.' : 'Choose another filter to see the rest of today.'}
        toolbar={
          <Segmented
            ariaLabel="Class state"
            size="sm"
            value={filter}
            onChange={setFilter}
            options={[
              { value: 'ALL', label: 'All', count: count('ALL') },
              { value: 'OPEN', label: 'Entry pending', count: count('OPEN') },
              { value: 'RUNNING', label: 'In class', count: count('RUNNING') },
              { value: 'DONE', label: 'Completed', count: count('DONE') },
            ]}
          />
        }
        pageSize={50}
      />
    </div>
  )
}
