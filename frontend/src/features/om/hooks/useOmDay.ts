import { useCallback, useEffect } from 'react'
import { useApi } from '@/hooks/useApi'
import type { ClassRow, OMDay } from '../types/om.types'

/**
 * One day of class operations. Refreshes every minute so "yet to start" turns into
 * "entry due" on its own, and patches a single row in place right after the OM saves,
 * so the screen never needs a reload.
 */
export function useOmDay(on?: string) {
  const day = useApi<OMDay>('/om/dashboard', on ? { on } : undefined)
  const { reload, setData } = day

  useEffect(() => {
    const t = setInterval(() => void reload(true), 60_000)
    return () => clearInterval(t)
  }, [reload])

  const applyRow = useCallback(
    (row: ClassRow) => {
      setData((prev) => (prev ? { ...prev, classes: prev.classes.map((c) => (c.lecture_id === row.lecture_id ? row : c)) } : (prev as unknown as OMDay)))
      void reload(true) // metrics follow
    },
    [reload, setData],
  )

  return { ...day, applyRow }
}
