import { api } from '@/services/api'

export type SlotType = 'LECTURE' | 'LUNCH' | 'BREAK'
export type TimingSlot = { id: string; slot_type: SlotType; lecture_number: number | null; start: string; end: string; is_teaching_slot: boolean }
/** One year group's day: its own lecture periods and its own lunch. Lecture numbers mean nothing outside it. */
export type TimingTemplate = {
  id: string
  code: string
  name: string
  short_name: string
  description: string | null
  semester_numbers: number[]
  is_active: boolean
  slots: TimingSlot[]
}

export type ClassType = 'THEORY' | 'LAB' | 'TUTORIAL' | 'REMEDIAL'
export const CLASS_TYPE_LABEL: Record<ClassType, string> = { THEORY: 'Theory', LAB: 'Lab', TUTORIAL: 'Tutorial', REMEDIAL: 'Remedial' }

export type TimetableEntry = {
  id: string
  plan_id: string
  weekday: number
  day: string
  start: string
  end: string
  room: string | null
  class_type: ClassType
  professor: { id: string; full_name: string }
  is_substitute: boolean
  subject: { id: string; code: string; name: string; short_name: string | null }
  semester: string
  semester_number: number
  semester_id: string
  section: string
  section_id: string
  year: string
  academic_year: string
  branch_code: string
  plan_status: string
  template: string | null
  lecture_numbers: number[]
}

export type TimetableConflict = {
  kind: 'PROFESSOR' | 'SECTION' | 'ROOM' | 'LUNCH' | 'OUTSIDE_HOURS' | 'NO_TEMPLATE'
  level: 'ERROR' | 'WARNING'
  weekday: number
  keys: string[]
  message: string
}
export const CONFLICT_TITLE: Record<string, string> = {
  PROFESSOR: 'Professor conflict',
  SECTION: 'Section conflict',
  ROOM: 'Room conflict',
  LUNCH: 'Lunch conflict',
  OUTSIDE_HOURS: 'Outside teaching hours',
  NO_TEMPLATE: 'No timing template',
}

export type TimetableVersion = {
  id: string
  status: 'DRAFT' | 'PUBLISHED' | 'ARCHIVED'
  version_number: number | null
  note: string | null
  entry_count: number
  published_at: string | null
  published_by: { id: string; full_name: string } | null
  updated_at: string | null
}

export type TimetableView = {
  showing: 'DRAFT' | 'PUBLISHED' | null
  published: TimetableVersion | null
  draft: TimetableVersion | null
  templates: TimingTemplate[]
  entries: TimetableEntry[]
  conflicts: TimetableConflict[]
  can_publish: boolean
  scope: { summary?: string; label?: string } | null
  today_weekday: number
  generation?: { placed: number; plans: number; unplaced: { plan_id: string; label: string; missing: number; reason: string }[] }
}

export type Room = { id: string; name: string; room_type: 'CLASSROOM' | 'LAB'; capacity: number | null; is_active: boolean }
export type Holiday = { id: string; date: string; name: string }

export type EntryBody = {
  teaching_plan_id: string
  weekday: number
  start_time: string
  end_time: string
  room: string | null
  class_type: ClassType
  professor_id?: string | null
}

const data = <T,>(p: Promise<{ data: T }>) => p.then((r) => r.data)

/** Admin actions on the master timetable. Everything works on a draft; only Publish changes what people see. */
export const timetableApi = {
  startDraft: () => data(api.post<TimetableView>('/timetable/draft')),
  discardDraft: () => data(api.delete<TimetableView>('/timetable/draft')),
  generate: (days: number[], replace: boolean) => data(api.post<TimetableView>('/timetable/generate', { days, replace })),
  addEntry: (body: EntryBody) => data(api.post<TimetableView>('/timetable/entries', body)),
  updateEntry: (id: string, body: EntryBody) => data(api.put<TimetableView>(`/timetable/entries/${id}`, body)),
  deleteEntry: (id: string) => data(api.delete<TimetableView>(`/timetable/entries/${id}`)),
  publish: (note: string | null) => data(api.post<TimetableView>('/timetable/publish', { note })),
  saveTemplate: (id: string, body: { name: string; short_name: string; description: string | null; semester_numbers: number[]; slots: { slot_type: SlotType; start_time: string; end_time: string }[] }) =>
    data(api.put<TimingTemplate>(`/timing-templates/${id}`, body)),
  setAllocation: (planId: string, body: { classes_per_week: number; labs_per_week: number; room: string | null; lab_room: string | null }) =>
    data(api.patch(`/teaching-plans/${planId}/allocation`, body)),
}

export const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
export const hm = (t: string) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5))

/** semester number -> template code, from the configured mapping (never hard-coded in the UI). */
export function templateOf(templates: TimingTemplate[], semesterNumber: number | null | undefined): string | null {
  if (!semesterNumber) return null
  return templates.find((t) => t.semester_numbers.includes(semesterNumber))?.code ?? null
}
