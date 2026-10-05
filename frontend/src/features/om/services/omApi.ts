import { instNow } from '@/lib/date-time/institution'
import { api } from '@/services/api'
import type { ClassRow, EntryPayload } from '../types/om.types'

/** Every write the OM portal makes. Reads go through `useApi` so they share loading/error handling. */
export const omApi = {
  recordEntry: (lectureId: string, body: EntryPayload) => api.post<ClassRow>(`/om/classes/${lectureId}/entry`, body).then((r) => r.data),
  recordExit: (lectureId: string, time: string | null, earlyExitReason?: string) =>
    api.post<ClassRow>(`/om/classes/${lectureId}/exit`, { ...(time ? { time } : {}), ...(earlyExitReason ? { early_exit_reason: earlyExitReason } : {}) }).then((r) => r.data),
}

/** "HH:MM" for right now on the institution's clock. The backend still validates the time that is sent. */
export function nowHM(): string {
  return instNow().hm
}
