import { Check } from 'lucide-react'
import { cn } from '@/utils/cn'
import type { StepKey } from '../types'

export function Stepper({ steps, current, reachable, onSelect }: { steps: { key: StepKey; label: string }[]; current: StepKey; reachable: (k: StepKey) => boolean; onSelect: (k: StepKey) => void }) {
  const currentIndex = steps.findIndex((s) => s.key === current)
  return (
    <nav aria-label="Import progress" className="overflow-x-auto scroll-thin">
      <ol className="flex min-w-max items-center gap-0">
        {steps.map((s, i) => {
          const done = i < currentIndex
          const active = i === currentIndex
          const canGo = !active && reachable(s.key)
          return (
            <li key={s.key} className="flex items-center">
              <button
                type="button"
                disabled={!canGo}
                onClick={() => onSelect(s.key)}
                aria-current={active ? 'step' : undefined}
                className={cn('group flex items-center gap-2 rounded-md px-2 py-1.5 text-[13px]', canGo && 'hover:bg-surface-3')}
              >
                <span
                  className={cn(
                    'tnum flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[12px] font-semibold',
                    active ? 'bg-primary text-on-primary' : done ? 'bg-primary/15 text-primary' : 'border border-line-strong bg-surface text-fg-label',
                  )}
                >
                  {done ? <Check className="h-3.5 w-3.5" strokeWidth={3} aria-label="Completed" /> : i + 1}
                </span>
                <span className={cn('font-medium', active ? 'text-fg' : done ? 'text-fg-soft' : 'text-fg-muted')}>{s.label}</span>
              </button>
              {i < steps.length - 1 && <span className={cn('mx-1 h-px w-6 lg:w-10', i < currentIndex ? 'bg-primary-muted' : 'bg-track')} aria-hidden />}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
