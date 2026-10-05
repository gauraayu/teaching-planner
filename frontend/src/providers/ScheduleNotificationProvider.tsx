'use client'

import { BellRing, X } from 'lucide-react'
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ButtonLink } from '@/components/ui/Button'
import { useAuth } from '@/features/auth/AuthContext'
import { classPhase, configureInstitutionTime, instNow } from '@/lib/date-time/institution'
import { fmt } from '@/lib/status'
import { api } from '@/services/api'

export type FeedClass = {
  lecture_id: string
  date: string
  start: string | null
  end: string | null
  subject: { code: string; name: string; short_name: string | null }
  section: string
  semester: string
  room: string | null
  professor: string
  lecture_no: number
  topic: string
  started: boolean
  entry_recorded: boolean
  link: string
}
type Feed = { now: string; timezone: string; today: string; lead_minutes: number; role: string; classes: FeedClass[] }

type Ctx = { classes: FeedClass[]; leadMinutes: number; reload: () => void; ready: boolean }
const ScheduleContext = createContext<Ctx>({ classes: [], leadMinutes: 5, reload: () => {}, ready: false })

/** Today's classes for the signed-in professor / OM, kept fresh for every page under the shell. */
export const useTodayFeed = () => useContext(ScheduleContext)

const FEED_REFRESH_MS = 60_000
const CHECK_MS = 15_000
const key = (userId: string, c: FeedClass) => `atp.class-alert.v1:${userId}:${c.lecture_id}:${c.date}`

function alreadyAlerted(k: string): boolean {
  try {
    return localStorage.getItem(k) === '1'
  } catch {
    return false
  }
}
function markAlerted(k: string) {
  try {
    localStorage.setItem(k, '1')
  } catch {
    /* storage unavailable: the in-memory set below still prevents repeats in this tab */
  }
}

/**
 * One schedule watcher for the whole portal (mounted in the app shell, so it keeps working
 * while the user moves between pages). It
 *   - loads today's classes from the API every minute and syncs the display clock to the server,
 *   - checks them against the institution clock every 15 seconds,
 *   - raises the "class starts in 5 minutes" alert exactly once per class per user per day
 *     (remembered in localStorage and recorded in the notification history on the server).
 *
 * The transport is deliberately isolated here: swapping the polling in `load` for a
 * WebSocket / SSE subscription later does not touch any page.
 */
export function ScheduleNotificationProvider({ children }: { children: ReactNode }) {
  const { session } = useAuth()
  const role = session?.role
  const userId = session?.user.id
  const active = role === 'PROFESSOR' || role === 'OM'
  const [feed, setFeed] = useState<Feed | null>(null)
  const [alerts, setAlerts] = useState<FeedClass[]>([])
  const shown = useRef(new Set<string>())

  useEffect(() => {
    configureInstitutionTime({ timezone: session?.timezone })
  }, [session?.timezone])

  const load = useCallback(async () => {
    if (!active) return
    try {
      const { data } = await api.get<Feed>('/schedule/today')
      configureInstitutionTime({ timezone: data.timezone, serverNow: data.now })
      setFeed(data)
    } catch {
      /* keep the last good feed; the next poll retries */
    }
  }, [active])

  useEffect(() => {
    if (!active) {
      setFeed(null)
      setAlerts([])
      return
    }
    void load()
    const t = setInterval(() => void load(), FEED_REFRESH_MS)
    return () => clearInterval(t)
  }, [active, load])

  useEffect(() => {
    if (!feed || !userId) return
    const check = () => {
      const now = instNow()
      for (const c of feed.classes) {
        const waiting = role === 'PROFESSOR' ? !c.started : !c.entry_recorded
        if (!waiting) continue
        const { phase } = classPhase(c.date, c.start, c.end, now, feed.lead_minutes)
        if (phase !== 'SOON') continue
        const k = key(userId, c)
        if (shown.current.has(k) || alreadyAlerted(k)) continue
        shown.current.add(k)
        markAlerted(k)
        setAlerts((a) => [...a.filter((x) => x.lecture_id !== c.lecture_id), c])
        api.post(`/schedule/alerts/${c.lecture_id}`).catch(() => {}) // notification history; the server dedupes too
      }
    }
    check()
    const t = setInterval(check, CHECK_MS)
    return () => clearInterval(t)
  }, [feed, role, userId])

  const dismiss = (id: string) => setAlerts((a) => a.filter((x) => x.lecture_id !== id))
  const value = useMemo<Ctx>(() => ({ classes: feed?.classes ?? [], leadMinutes: feed?.lead_minutes ?? 5, reload: () => void load(), ready: !!feed }), [feed, load])

  return (
    <ScheduleContext.Provider value={value}>
      {children}
      {alerts.length > 0 && (
        <div className="fixed right-4 bottom-4 z-[60] flex w-[min(92vw,360px)] flex-col gap-2" role="alert" aria-live="assertive">
          {alerts.map((c) => (
            <div key={c.lecture_id} className="rounded-md border border-primary-border bg-surface-3 p-4 shadow-pop">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-1.5 text-[11.5px] font-semibold tracking-[0.08em] text-primary uppercase">
                  <BellRing className="h-3.5 w-3.5" aria-hidden /> Class starting in {feed?.lead_minutes ?? 5} minutes
                </div>
                <button type="button" onClick={() => dismiss(c.lecture_id)} aria-label="Dismiss" className="-mt-1 -mr-1 rounded p-1 text-fg-muted hover:bg-surface-2 hover:text-fg">
                  <X className="h-4 w-4" />
                </button>
              </div>
              {role === 'OM' && <div className="mt-2 text-[13px] font-medium text-fg-soft">{c.professor}</div>}
              <div className="mt-1 text-[15px] leading-snug font-semibold text-fg">{c.subject.name}</div>
              <div className="mt-1 text-[13px] text-fg-secondary">
                Sem {c.semester.replace('Semester ', '')}-{c.section} · Room {c.room ?? 'not set'}
              </div>
              <div className="tnum mt-0.5 text-[13px] text-fg-secondary">
                {role === 'OM' ? 'Scheduled: ' : ''}{fmt.timeRange(c.start, c.end)}
              </div>
              <p className="mt-2 text-[13px] font-medium text-fg">{role === 'OM' ? 'Class' : 'Your class'} starts in {feed?.lead_minutes ?? 5} minutes.</p>
              <ButtonLink to={c.link} variant="primary" size="sm" className="mt-3 w-full justify-center" onClick={() => dismiss(c.lecture_id)}>
                {role === 'OM' ? 'Open class record' : 'Open class'}
              </ButtonLink>
            </div>
          ))}
        </div>
      )}
    </ScheduleContext.Provider>
  )
}
