import { useEffect, useRef, useState, type ReactNode } from 'react'
import { cn } from '@/utils/cn'

export type MenuItem = { label: ReactNode; onSelect: () => void; icon?: ReactNode; danger?: boolean; disabled?: boolean } | 'separator'

/** Contextual action menu (View / Edit / Archive) instead of rows of buttons. */
export function Menu({ trigger, items, align = 'end', label }: { trigger: (props: { onClick: () => void; 'aria-expanded': boolean; 'aria-haspopup': 'menu' }) => ReactNode; items: MenuItem[]; align?: 'start' | 'end'; label?: string }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false)
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault()
        const buttons = Array.from(ref.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]:not([disabled])') ?? [])
        const idx = buttons.indexOf(document.activeElement as HTMLButtonElement)
        buttons[(idx + (e.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length]?.focus()
      }
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    requestAnimationFrame(() => ref.current?.querySelector<HTMLButtonElement>('[role="menuitem"]:not([disabled])')?.focus())
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])
  return (
    <div ref={ref} className="relative inline-block">
      {trigger({ onClick: () => setOpen((o) => !o), 'aria-expanded': open, 'aria-haspopup': 'menu' })}
      {open && (
        <div
          role="menu"
          aria-label={label}
          className={cn('absolute z-40 mt-1 min-w-44 rounded-md border border-line bg-surface py-1 shadow-pop', align === 'end' ? 'right-0' : 'left-0')}
        >
          {items.map((item, i) =>
            item === 'separator' ? (
              <div key={i} className="my-1 border-t border-line-subtle" />
            ) : (
              <button
                key={i}
                role="menuitem"
                type="button"
                disabled={item.disabled}
                onClick={() => {
                  setOpen(false)
                  item.onSelect()
                }}
                className={cn(
                  'flex w-full items-center gap-2 px-3 py-1.5 text-left text-[13px] hover:bg-surface-2 focus:bg-surface-2 focus:outline-none disabled:cursor-not-allowed disabled:text-fg-faint',
                  item.danger ? 'text-danger' : 'text-fg-soft',
                )}
              >
                {item.icon}
                {item.label}
              </button>
            ),
          )}
        </div>
      )}
    </div>
  )
}
