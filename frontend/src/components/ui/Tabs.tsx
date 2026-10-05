import type { ReactNode } from 'react'
import { cn } from '@/utils/cn'

export type TabItem<T extends string> = { value: T; label: ReactNode; count?: number }

/** Underline tabs with ARIA tab semantics and arrow-key navigation. */
export function Tabs<T extends string>({ value, onChange, items, className }: { value: T; onChange: (v: T) => void; items: TabItem<T>[]; className?: string }) {
  return (
    <div role="tablist" className={cn('flex gap-1 overflow-x-auto border-b border-line scroll-thin', className)}>
      {items.map((t, i) => {
        const active = t.value === value
        return (
          <button
            key={t.value}
            role="tab"
            type="button"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(t.value)}
            onKeyDown={(e) => {
              if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
                const next = items[(i + (e.key === 'ArrowRight' ? 1 : -1) + items.length) % items.length]
                onChange(next.value)
                ;(e.currentTarget.parentElement?.children[items.indexOf(next)] as HTMLElement | undefined)?.focus()
              }
            }}
            className={cn(
              '-mb-px flex h-10 items-center gap-1.5 border-b-2 px-3 text-[13px] font-medium whitespace-nowrap transition-colors',
              active ? 'border-primary text-primary' : 'border-transparent text-fg-label hover:border-line-strong hover:text-fg',
            )}
          >
            {t.label}
            {t.count !== undefined && <span className="tnum rounded-sm bg-surface-3 px-1.5 text-[11px] text-fg-secondary">{t.count}</span>}
          </button>
        )
      })}
    </div>
  )
}
