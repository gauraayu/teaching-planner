/**
 * The institution's clock - the single place the frontend decides "what time is it".
 *
 * Classes run on the institution's wall clock (Asia/Kolkata by default), not on whatever
 * timezone the laptop is set to. The timezone comes from the API session, and the clock is
 * corrected by the difference between the server's time and the browser's, so a wrong
 * laptop clock cannot shift a countdown.
 *
 * This is for DISPLAY (countdowns, "today", default values in a time field). Every
 * timestamp that is stored is taken from the server when the action is submitted.
 */
import { useEffect, useState } from 'react'

let timezone = process.env.NEXT_PUBLIC_INSTITUTION_TIMEZONE || 'Asia/Kolkata'
let offsetMs = 0
let formatter: Intl.DateTimeFormat | null = null

function fmt() {
  if (!formatter) {
    formatter = new Intl.DateTimeFormat('en-CA', {
      timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
    })
  }
  return formatter
}

export function configureInstitutionTime(opts: { timezone?: string | null; serverNow?: string | null }) {
  if (opts.timezone && opts.timezone !== timezone) {
    try {
      new Intl.DateTimeFormat('en-CA', { timeZone: opts.timezone })
      timezone = opts.timezone
      formatter = null
    } catch {
      /* unknown zone name: keep the current one */
    }
  }
  if (opts.serverNow) {
    const server = new Date(opts.serverNow).getTime()
    if (!Number.isNaN(server)) offsetMs = server - Date.now()
  }
}

export const institutionTimezone = () => timezone

export type InstNow = { date: string; hm: string; h: number; m: number; s: number; minutes: number; seconds: number }

export function instNow(at: Date = new Date(Date.now() + offsetMs)): InstNow {
  const p = Object.fromEntries(fmt().formatToParts(at).map((x) => [x.type, x.value]))
  const h = Number(p.hour) % 24
  const m = Number(p.minute)
  const s = Number(p.second)
  return { date: `${p.year}-${p.month}-${p.day}`, hm: `${p.hour.padStart(2, '0').replace('24', '00')}:${p.minute}`, h, m, s, minutes: h * 60 + m, seconds: h * 3600 + m * 60 + s }
}

export const hmToMinutes = (hm: string) => Number(hm.slice(0, 2)) * 60 + Number(hm.slice(3, 5))

/** Re-renders the caller on a fixed tick and returns the institution's current time. */
export function useInstNow(intervalMs = 1000): InstNow {
  const [now, setNow] = useState<InstNow>(() => instNow())
  useEffect(() => {
    setNow(instNow())
    const t = setInterval(() => setNow(instNow()), intervalMs)
    return () => clearInterval(t)
  }, [intervalMs])
  return now
}

export type ClassPhase = 'UPCOMING' | 'SOON' | 'NOW' | 'OVER' | 'OTHER_DAY_PAST' | 'OTHER_DAY_FUTURE'

/** Where a scheduled slot stands against the clock. `soon` = within `leadMinutes` of the start. */
export function classPhase(date: string | null, start: string | null, end: string | null, now: InstNow, leadMinutes = 5): { phase: ClassPhase; minutesToStart: number | null } {
  if (!date || !start) return { phase: 'UPCOMING', minutesToStart: null }
  if (date < now.date) return { phase: 'OTHER_DAY_PAST', minutesToStart: null }
  if (date > now.date) return { phase: 'OTHER_DAY_FUTURE', minutesToStart: null }
  const startMin = hmToMinutes(start)
  const endMin = end ? hmToMinutes(end) : startMin + 60
  if (now.minutes >= endMin) return { phase: 'OVER', minutesToStart: null }
  if (now.minutes >= startMin) return { phase: 'NOW', minutesToStart: 0 }
  const left = Math.max(1, Math.ceil((startMin * 60 - now.seconds) / 60)) // never negative, never "0 min"
  return { phase: left <= leadMinutes ? 'SOON' : 'UPCOMING', minutesToStart: left }
}

/** "Starts in 18 min" / "Starts in 1 h 5 min" / "Starting now". */
export function countdownLabel(minutes: number | null, phase: ClassPhase): string {
  if (phase === 'NOW') return 'Starting now'
  if (minutes == null) return ''
  if (minutes >= 60) return `Starts in ${Math.floor(minutes / 60)} h${minutes % 60 ? ` ${minutes % 60} min` : ''}`
  return `Starts in ${minutes} min`
}
