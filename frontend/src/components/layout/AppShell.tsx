import { Bell, CalendarRange, ChevronDown, KeyRound, LogOut, Menu as MenuIcon, X } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { NavLink, useLocation, useNavigate } from '@/lib/router'
import { Button } from '@/components/ui/Button'
import { Menu } from '@/components/ui/Menu'
import { useAuth } from '@/features/auth/AuthContext'
import { ChangePasswordDialog } from '@/features/auth/ChangePasswordDialog'
import { useApi } from '@/hooks/useApi'
import { fmt, todayISO } from '@/lib/status'
import { api } from '@/services/api'
import type { NotificationItem } from '@/types/domain'
import { cn, initials } from '@/utils/cn'
import { AREA_BY_ROLE, NAVIGATION, ROLE_LABEL, type NavGroup } from './navigation'
import { InstitutionClock } from '@/components/shared/InstitutionClock'
import { ScheduleNotificationProvider } from '@/providers/ScheduleNotificationProvider'
import { BreadcrumbProvider, Breadcrumbs } from './PageHeader'

export function BrandMark({ className }: { className?: string }) {
  return (
    <div className={cn('flex items-center justify-center rounded-md border border-primary-border bg-primary-soft text-primary', className)} aria-hidden>
      <svg viewBox="0 0 32 32" className="h-[62%] w-[62%]">
        <path d="M6 11.5 16 6l10 5.5-10 5.5-10-5.5Z" fill="currentColor" />
        <path d="M10 15v6c0 1.8 2.7 3.6 6 3.6s6-1.8 6-3.6v-6l-6 3.3-6-3.3Z" fill="currentColor" opacity="0.45" />
      </svg>
    </div>
  )
}

function Brand() {
  return (
    <div className="flex items-center gap-2.5">
      <BrandMark className="h-8 w-8" />
      <div className="leading-tight">
        <div className="text-[13px] font-semibold text-fg">Teaching Plan Portal</div>
        <div className="text-[11px] text-fg-label">Academic Delivery Office</div>
      </div>
    </div>
  )
}

function SidebarNav({ groups, badges, onNavigate }: { groups: NavGroup[]; badges: Record<string, number>; onNavigate?: () => void }) {
  const { can } = useAuth()
  return (
    <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-4 scroll-thin" aria-label="Main">
      {groups.map((g, gi) => {
        const items = g.items.filter((i) => !i.permission || can(i.permission))
        if (!items.length) return null
        return (
          <div key={gi}>
            {g.label && <div className="mb-1.5 px-2.5 text-[10.5px] font-semibold tracking-[0.08em] text-fg-muted uppercase">{g.label}</div>}
            <ul className="space-y-0.5">
              {items.map((item) => {
                const badge = item.badgeKey ? badges[item.badgeKey] : 0
                return (
                  <li key={item.to}>
                    <NavLink
                      to={item.to}
                      end={item.end}
                      onClick={onNavigate}
                      className={({ isActive }) =>
                        cn(
                          'relative flex h-8 items-center gap-2.5 rounded-md px-2.5 text-[13px] font-medium transition-colors',
                          isActive
                            ? 'bg-primary-soft text-primary before:absolute before:top-1.5 before:bottom-1.5 before:-left-3 before:w-[3px] before:rounded-r before:bg-primary'
                            : 'text-fg-secondary hover:bg-primary/5 hover:text-fg',
                        )
                      }
                    >
                      <item.icon className="h-4 w-4 shrink-0" strokeWidth={1.9} aria-hidden />
                      <span className="flex-1 truncate">{item.label}</span>
                      {badge > 0 && (
                        <span className={cn('tnum rounded-sm px-1.5 text-[11px] font-semibold', item.badgeKey === 'running' ? 'bg-primary/15 text-primary' : 'bg-warning/15 text-warning')}>{badge}</span>
                      )}
                    </NavLink>
                  </li>
                )
              })}
            </ul>
          </div>
        )
      })}
    </nav>
  )
}

function Notifications() {
  const navigate = useNavigate()
  const { data, reload } = useApi<{ items: NotificationItem[]; unread: number }>('/notifications')
  const [open, setOpen] = useState(false)
  useEffect(() => {
    const t = setInterval(() => void reload(true), 60_000)
    return () => clearInterval(t)
  }, [reload])
  const unread = data?.unread ?? 0
  return (
    <div className="relative">
      <Button variant="ghost" size="icon" aria-label={`Notifications${unread ? `, ${unread} unread` : ''}`} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <Bell className="h-4 w-4" />
        {unread > 0 && <span className="absolute top-1 right-1 h-2 w-2 rounded-full bg-primary ring-2 ring-bg" aria-hidden />}
      </Button>
      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} aria-hidden />
          <div className="absolute right-0 z-40 mt-1 w-[min(92vw,380px)] rounded-md border border-line bg-surface-2 shadow-pop">
            <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
              <span className="text-[13px] font-semibold">Notifications</span>
              {unread > 0 && (
                <Button variant="link" className="text-[12.5px]" onClick={async () => { await api.post('/notifications/read'); void reload(true) }}>
                  Mark all as read
                </Button>
              )}
            </div>
            <ul className="max-h-96 overflow-y-auto scroll-thin">
              {(data?.items ?? []).length === 0 && <li className="meta px-4 py-8 text-center">You're all caught up.</li>}
              {data?.items.map((n) => (
                <li key={n.id}>
                  <button
                    type="button"
                    className={cn('flex w-full gap-3 border-b border-line-subtle px-4 py-3 text-left hover:bg-surface-3', !n.is_read && 'bg-primary/5')}
                    onClick={async () => {
                      setOpen(false)
                      if (!n.is_read) await api.post(`/notifications/${n.id}/read`).catch(() => {})
                      void reload(true)
                      if (n.link) navigate(n.link)
                    }}
                  >
                    <span className={cn('mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full', n.is_read ? 'bg-transparent' : 'bg-primary')} aria-hidden />
                    <span className="min-w-0">
                      <span className="block text-[13px] font-medium text-fg">{n.title}</span>
                      {n.body && <span className="meta line-clamp-2 block">{n.body}</span>}
                      <span className="mt-0.5 block text-[11.5px] text-fg-muted">{fmt.relative(n.created_at)}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </div>
  )
}

function ProfileMenu() {
  const { session, logout } = useAuth()
  const navigate = useNavigate()
  const [changing, setChanging] = useState(false)
  if (!session) return null
  const u = session.user
  return (
    <>
    <Menu
      label="Account"
      trigger={(p) => (
        <button type="button" {...p} className="flex items-center gap-2 rounded-md py-1 pr-1.5 pl-1 hover:bg-surface-3">
          <span className="flex h-7 w-7 items-center justify-center rounded-full border border-primary-border bg-primary-soft text-[11px] font-semibold text-primary">{initials(u.full_name)}</span>
          <span className="max-md:hidden text-left leading-tight md:block">
            <span className="block text-[12.5px] font-medium text-fg">{u.full_name}</span>
            <span className="block text-[11px] text-fg-label">{ROLE_LABEL[session.role]}</span>
          </span>
          <ChevronDown className="max-md:hidden h-3.5 w-3.5 text-fg-muted md:block" />
        </button>
      )}
      items={[
        { label: <span className="text-fg-label">{u.email}</span>, onSelect: () => {}, disabled: true },
        ...(session.scope && (session.role === 'CL_CH' || session.role === 'OM')
          ? [{ label: <span className="text-fg-label">Scope: {session.scope.label}</span>, onSelect: () => {}, disabled: true }] : []),
        'separator' as const,
        { label: 'Change password', icon: <KeyRound className="h-3.5 w-3.5" />, onSelect: () => setChanging(true) },
        { label: 'Sign out', icon: <LogOut className="h-3.5 w-3.5" />, onSelect: () => { logout(); navigate('/login') } },
      ]}
    />
    <ChangePasswordDialog open={changing} onClose={() => setChanging(false)} />
    </>
  )
}

export function AppShell({ children }: { children: ReactNode }) {
  const { session } = useAuth()
  const location = useLocation()
  const [drawer, setDrawer] = useState(false)
  const [collapsed, setCollapsed] = useState(false)
  useEffect(() => setDrawer(false), [location.pathname])
  const area = session ? AREA_BY_ROLE[session.role] : 'admin'
  const groups = NAVIGATION[area]

  // Live counters for sidebar badges.
  const verificationMetrics = useApi<{ pending: number }>(area === 'verification' || area === 'om' ? '/verifications/metrics' : null)
  const professorDash = useApi<{ counts: { corrections: number } }>(area === 'professor' ? '/professor/dashboard' : null)
  const omDay = useApi<{ metrics: { running: number } }>(area === 'om' ? '/om/dashboard' : null)
  const badges = {
    pending: verificationMetrics.data?.pending ?? 0,
    corrections: professorDash.data?.counts.corrections ?? 0,
    running: omDay.data?.metrics.running ?? 0,
  }
  const sem = session?.academic_session

  return (
    <ScheduleNotificationProvider>
    <BreadcrumbProvider>
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[70] focus:rounded focus:bg-surface-3 focus:px-3 focus:py-2 focus:shadow-pop">
        Skip to content
      </a>
      <div className="flex min-h-screen">
        {/* Desktop / tablet sidebar */}
        <div className="max-md:hidden shrink-0 border-r border-line bg-deep md:block">
        <aside className={cn('sticky top-0 flex h-screen flex-col', collapsed ? 'w-[64px]' : 'w-60')}>
          <div className="flex h-14 items-center border-b border-line px-4">{collapsed ? <div className="mx-auto"><Brand /></div> : <Brand />}</div>
          {!collapsed && <SidebarNav groups={groups} badges={badges} />}
          {collapsed && (
            <nav className="flex-1 space-y-1 px-2 py-4" aria-label="Main">
              {groups.flatMap((g) => g.items).map((i) => (
                <NavLink key={i.to} to={i.to} title={i.label} aria-label={i.label} className={({ isActive }) => cn('flex h-9 items-center justify-center rounded-md', isActive ? 'bg-primary-soft text-primary' : 'text-fg-label hover:bg-primary/5 hover:text-fg')}>
                  <i.icon className="h-4 w-4" />
                </NavLink>
              ))}
            </nav>
          )}
          <button
            type="button"
            onClick={() => setCollapsed((c) => !c)}
            className="max-md:hidden border-t border-line px-4 py-2.5 text-left text-[12px] text-fg-muted hover:bg-primary/5 hover:text-fg-secondary md:block"
          >
            {collapsed ? '»' : '« Collapse sidebar'}
          </button>
        </aside>
        </div>

        {/* Mobile drawer */}
        {drawer && (
          <div className="fixed inset-0 z-50 md:hidden">
            <div className="absolute inset-0 bg-black/70" onClick={() => setDrawer(false)} aria-hidden />
            <aside className="absolute inset-y-0 left-0 flex w-72 flex-col border-r border-line bg-deep shadow-pop" aria-label="Navigation">
              <div className="flex h-14 items-center justify-between border-b border-line px-4">
                <Brand />
                <Button variant="ghost" size="icon" aria-label="Close navigation" onClick={() => setDrawer(false)}>
                  <X className="h-4 w-4" />
                </Button>
              </div>
              <SidebarNav groups={groups} badges={badges} onNavigate={() => setDrawer(false)} />
            </aside>
          </div>
        )}

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-line bg-bg px-4 sm:px-6">
            <Button variant="ghost" size="icon" className="md:hidden" aria-label="Open navigation" onClick={() => setDrawer(true)}>
              <MenuIcon className="h-4 w-4" />
            </Button>
            <div className="min-w-0 flex-1">
              <Breadcrumbs />
            </div>
            {sem?.academic_year && (
              <div className="max-lg:hidden items-center gap-1.5 rounded-md border border-line px-2.5 py-1 text-[12px] text-fg-secondary lg:flex" title="Current academic session">
                <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-hidden />
                <CalendarRange className="h-3.5 w-3.5 text-fg-muted" />
                {sem.academic_year.name}
                {sem.semester && <span className="text-fg-muted">·</span>}
                {sem.semester?.name}
              </div>
            )}
            {session?.role === 'PROFESSOR' || session?.role === 'OM' ? (
              // Live clock for the two roles that work against the timetable minute by minute.
              <InstitutionClock compact className="max-lg:hidden lg:inline-flex" />
            ) : (
              <div className="max-xl:hidden text-[12px] whitespace-nowrap text-fg-label xl:block" title="Today">{fmt.weekday(todayISO())}, {fmt.date(todayISO())}</div>
            )}
            <Notifications />
            <ProfileMenu />
          </header>
          <main id="main" className="mx-auto w-full max-w-[1440px] flex-1 px-4 py-5 sm:px-6 sm:py-6">
            {children}
          </main>
        </div>
      </div>
    </BreadcrumbProvider>
    </ScheduleNotificationProvider>
  )
}
