import { api } from '@/services/api'
import type { ExecutionStatus, SprintChange, SprintRevisionBrief, SprintRow, SprintValues, SprintWeekInfo } from '@/types/domain'

export type AdminSprintRow = SprintRow & {
  key: string
  locked: string | null
  draft: (SprintChange & { moved_out: boolean; moved_in?: boolean }) | null
  master: SprintValues | null
}

export type ExecutionSummary = {
  lectures_planned: number
  completed: number
  partially_completed: number
  not_conducted: number
  upcoming: number
  subtopics_planned: number
  subtopics_covered: number
  subtopics_remaining: number
  cancelled: number
}

export type CarryForward = {
  lecture_id: string
  plan_id: string
  subject: { code: string; name: string; short_name: string | null }
  section: string
  semester: string
  professor: { id: string; full_name: string }
  lecture_no: number
  unit_no: number | null
  topic: string
  lecture_type: string
  date: string
  kind: 'PARTIAL' | 'NOT_CONDUCTED'
  why: string
  remaining: string[]
  covered: number
  total: number
  status: 'OPEN' | 'DEFERRED'
  note: string | null
  draft_item_id: string | null
  room: string | null
  duration_minutes: number | null
}

export type AdminWeek = {
  week: SprintWeekInfo
  version: number
  published: SprintRevisionBrief | null
  draft: SprintRevisionBrief | null
  unpublished: number
  days: { date: string; lectures: AdminSprintRow[] }[]
  summary: ExecutionSummary
  previous_week: ExecutionSummary & { start: string; end: string }
  carry_forward: CarryForward[]
  reasons: { value: string; label: string }[]
  today: string
  conflicts?: SprintConflict[]
}

/** Level ERROR blocks publishing: one professor, section or room in two classes at once, or a class in its own year group's lunch. */
export type SprintConflict = { date: string; kind: 'PROFESSOR' | 'ROOM' | 'SECTION' | 'LUNCH'; level: 'ERROR' | 'WARNING'; message: string; keys?: string[] }

export type Generation = {
  slots: number
  carry_forward: number
  topics: number
  unchanged: number
  holiday_slots: number
  outside_semester: number
  empty_slots: number
  left_over: number
  notes: string[]
  pace?: { plan_id: string; subject: { code: string; name: string; short_name: string | null }; semester: string; section: string; remaining: number; weeks_left: number; required_pace: number; weekly_sessions: number; at_risk: boolean; extra_sessions_needed: number; risk_message: string | null }[]
}

export type RevisionChanges = {
  revision: SprintRevisionBrief
  week: SprintWeekInfo
  changes: SprintChange[]
  conflicts?: SprintConflict[]
}

export type LectureEdit = {
  planned_date?: string
  planned_start_time?: string
  planned_end_time?: string | null
  room?: string | null
  professor_id?: string
  content_topic?: string
  subtopics?: string[]
  lecture_type?: string
  reason: string
  remarks?: string | null
}

export type LectureAdd = LectureEdit & {
  teaching_plan_id: string
  content_topic: string
  planned_date: string
  planned_start_time: string
  carry_forward_lecture_id?: string
}

const base = '/admin/sprint-plan'
const data = <T,>(p: Promise<{ data: T }>) => p.then((r) => r.data)

/** Admin: weekly sprint meeting. Every call persists through FastAPI; nothing is kept only in the browser. */
export const adminSprintApi = {
  generate: (weekStart: string, replace: boolean) => data(api.post<AdminWeek & { generation: Generation }>(`${base}/generate`, { week_start: weekStart, replace })),
  publishWeek: (weekStart: string) => data(api.post<AdminWeek>(`${base}/weeks/publish`, { week_start: weekStart })),
  startMeeting: (weekStart: string) => data(api.post<AdminWeek>(`${base}/revisions`, { week_start: weekStart })),
  editLecture: (revisionId: string, lectureId: string, body: LectureEdit) => data(api.patch<AdminWeek>(`${base}/revisions/${revisionId}/lectures/${lectureId}`, body)),
  cancelLecture: (revisionId: string, lectureId: string, body: { reason: string; remarks?: string | null }) =>
    data(api.post<AdminWeek>(`${base}/revisions/${revisionId}/lectures/${lectureId}/cancel`, body)),
  addLecture: (revisionId: string, body: LectureAdd) => data(api.post<AdminWeek>(`${base}/revisions/${revisionId}/lectures`, body)),
  removeChange: (revisionId: string, itemId: string) => data(api.delete<AdminWeek>(`${base}/revisions/${revisionId}/items/${itemId}`)),
  discard: (revisionId: string) => data(api.delete<AdminWeek>(`${base}/revisions/${revisionId}`)),
  changes: (revisionId: string) => data(api.get<RevisionChanges>(`${base}/revisions/${revisionId}/changes`)),
  publish: (revisionId: string, meetingNotes: string | null) => data(api.post<RevisionChanges>(`${base}/revisions/${revisionId}/publish`, { meeting_notes: meetingNotes })),
  decideCarryForward: (lectureId: string, status: 'DEFERRED' | 'RESOLVED' | 'OPEN', note?: string) =>
    data(api.post(`${base}/carry-forward/${lectureId}`, { status, note: note || null })),
}

// ---------------------------------------------------------------- week arithmetic (calendar dates only)

function parts(iso: string) {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d))
}
export function addDays(iso: string, days: number): string {
  const d = parts(iso)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}
export function mondayOf(iso: string): string {
  const d = parts(iso)
  return addDays(iso, -((d.getUTCDay() + 6) % 7))
}

export type ProfessorWeek = {
  week: SprintWeekInfo
  today: string
  version: number
  revision: SprintRevisionBrief | null
  changed_for_me: number
  metrics: { total: number; completed: number; delivered: number; today_open: number; upcoming: number; pending_action: number; pace_pct: number; verified?: number }
  days: { date: string; lectures: SprintRow[] }[]
  courses: {
    plan_id: string
    subject: { code: string; name: string; short_name: string | null }
    section: string
    scheduled: number
    delivered: number
    sprint_pct: number
    semester_pct: number
    semester_completed: number
    semester_total: number
  }[]
}

export type ProfessorWeekHistory = { week: SprintWeekInfo; lectures: number; delivered: number; version: number }

export const DELIVERED: ExecutionStatus[] = ['COMPLETED', 'PARTIALLY_COMPLETED']
