import { X } from 'lucide-react'
import type { ReactNode } from 'react'
import { Button } from '@/components/ui/Button'
import { useApi } from '@/hooks/useApi'
import type { Paged } from '@/services/api'

/** One filter layout used on every screen: compact labelled selects in a wrapping row. */
export function FilterBar({ children, onReset, active }: { children: ReactNode; onReset?: () => void; active?: boolean }) {
  return (
    <div className="flex flex-wrap items-end gap-x-3 gap-y-2">
      {children}
      {onReset && active && (
        <Button size="sm" variant="ghost" icon={<X className="h-3.5 w-3.5" />} onClick={onReset}>
          Clear filters
        </Button>
      )}
    </div>
  )
}

export function FilterSelect({
  label,
  value,
  onChange,
  options,
  allLabel = 'All',
  width = 'w-44',
}: {
  label: string
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string }[]
  allLabel?: string
  width?: string
}) {
  return (
    <label className={`flex flex-col ${width}`}>
      <span className="mb-1 text-[11.5px] font-medium text-fg-label">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} className="field h-8 text-[13px]">
        <option value="">{allLabel}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  )
}

export function FilterDate({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="flex w-40 flex-col">
      <span className="mb-1 text-[11.5px] font-medium text-fg-label">{label}</span>
      <input type="date" value={value} onChange={(e) => onChange(e.target.value)} className="field h-8 text-[13px]" />
    </label>
  )
}

type Opt = { id: string; name: string }

/** Loads the shared academic filter options once per screen. */
export function useAcademicOptions() {
  const years = useApi<Paged<Opt>>('/academic-years')
  const semesters = useApi<Paged<Opt & { academic_year_id: string; number: number }>>('/semesters')
  const branches = useApi<Paged<Opt & { code: string }>>('/branches')
  const sections = useApi<Paged<Opt & { branch_code: string; semester: string; semester_id: string; branch_id: string }>>('/sections')
  const subjects = useApi<Paged<Opt & { code: string; branch_id: string; semester_number: number }>>('/subjects')
  return {
    years: years.data?.items.map((y) => ({ value: y.id, label: y.name })) ?? [],
    semesters: semesters.data?.items.map((s) => ({ value: s.id, label: s.name })) ?? [],
    branches: branches.data?.items.map((b) => ({ value: b.id, label: b.code })) ?? [],
    sections: sections.data?.items.map((s) => ({ value: s.id, label: `${s.branch_code} · ${s.semester.replace('Semester ', 'Sem ')} · ${s.name}` })) ?? [],
    subjects: subjects.data?.items.map((s) => ({ value: s.id, label: `${s.code} ${s.name}` })) ?? [],
  }
}
