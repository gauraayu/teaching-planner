import { ChevronRight } from 'lucide-react'
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { Link } from '@/lib/router'

export type Crumb = { label: string; to?: string }

const Ctx = createContext<{ crumbs: Crumb[]; setCrumbs: (c: Crumb[]) => void }>({ crumbs: [], setCrumbs: () => {} })

export function BreadcrumbProvider({ children }: { children: ReactNode }) {
  const [crumbs, setCrumbs] = useState<Crumb[]>([])
  return <Ctx.Provider value={{ crumbs, setCrumbs }}>{children}</Ctx.Provider>
}

/** Pages declare their trail; the top bar renders it. */
export function useBreadcrumbs(crumbs: Crumb[]) {
  const { setCrumbs } = useContext(Ctx)
  const key = JSON.stringify(crumbs)
  useEffect(() => {
    setCrumbs(crumbs)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, setCrumbs])
}

export function Breadcrumbs() {
  const { crumbs } = useContext(Ctx)
  if (!crumbs.length) return null
  return (
    <nav aria-label="Breadcrumb" className="min-w-0">
      <ol className="flex min-w-0 items-center gap-1 text-[13px] text-fg-label">
        {crumbs.map((c, i) => {
          const last = i === crumbs.length - 1
          return (
            <li key={`${c.label}-${i}`} className={last ? 'min-w-0 truncate' : 'max-sm:hidden shrink-0 items-center gap-1 sm:flex'}>
              {c.to && !last ? (
                <Link to={c.to} className="hover:text-fg">
                  {c.label}
                </Link>
              ) : (
                <span className={last ? 'font-medium text-fg' : ''} aria-current={last ? 'page' : undefined}>
                  {c.label}
                </span>
              )}
              {!last && <ChevronRight className="h-3.5 w-3.5 text-fg-faint" aria-hidden />}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

export function PageHeader({ title, description, actions, meta }: { title: ReactNode; description?: ReactNode; actions?: ReactNode; meta?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <h1 className="text-[22px] leading-8 font-semibold tracking-tight text-fg sm:text-2xl">{title}</h1>
        {description && <p className="mt-0.5 text-[13.5px] text-fg-label">{description}</p>}
        {meta && <div className="mt-2 flex flex-wrap items-center gap-2">{meta}</div>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}
