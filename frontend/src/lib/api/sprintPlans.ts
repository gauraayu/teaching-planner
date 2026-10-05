import { api } from '@/services/api'

export type SprintPlanStatus = 'DRAFT' | 'ACTIVE' | 'ARCHIVED'
export type SprintPlanBrief = {
  id: string
  name: string
  status: SprintPlanStatus
  academic_year: { id: string; name: string }
  start_date: string
  end_date: string
  working_days: number[]
  generated_at: string | null
  subject_count: number
  in_use: boolean
  is_current: boolean
  topics?: number
  total_weeks?: number
}
export type SprintSubject = {
  plan_id: string
  status: string
  subject: { id: string; code: string; name: string; short_name: string | null }
  semester: string
  semester_number: number
  section: string
  year_group: string | null
  professor: { id: string; full_name: string }
  room: string | null
  lab_room: string | null
  classes_per_week: number
  labs_per_week: number
  weekly_sessions: number
  topics: number
  subtopics: number
  completed: number
  partially_completed: number
  remaining: number
  scheduled: number
  unscheduled: number
  weeks_left: number
  required_pace: number
  projected_completion: string | null
  at_risk: boolean
  extra_sessions_needed: number
  risk_message: string | null
  completion_pct: number
}
export type SprintWeekRow = {
  number: number
  start: string
  end: string
  week_start: string
  classes: number
  published: number
  delivered: number
  status: 'EMPTY' | 'DRAFT' | 'PUBLISHED'
  has_draft: boolean
  is_current: boolean
  is_past: boolean
}
export type SprintPlanDetail = SprintPlanBrief & {
  calendar: { calendar_days: number; total_weeks: number; working_weeks: number; working_days: number; teaching_days: number; holidays: { date: string; name: string }[] }
  totals: { topics: number; subtopics: number; planned_lectures: number; weekly_sessions: number; required_pace: number; remaining: number; weeks_left: number; completion_pct: number; projected_completion: string | null; at_risk: number }
  subjects: SprintSubject[]
  weeks: SprintWeekRow[]
  ready: { has_subjects: boolean; without_curriculum: string[]; without_sessions: string[] }
  generation?: { scheduled: number; unscheduled: number; subjects: number; notes: string[] }
  duplicate?: { copied: number; skipped: string[] }
  needs_regeneration?: boolean
}
export type SprintPlanBody = { name: string; academic_year_id: string; start_date: string; end_date: string; working_days: number[] }

const data = <T,>(p: Promise<{ data: T }>) => p.then((r) => r.data)

/** Semester sprint plan: the one schedule everything else is read from. */
export const sprintPlansApi = {
  create: (body: SprintPlanBody) => data(api.post<SprintPlanDetail>('/sprint-plans', body)),
  update: (id: string, body: SprintPlanBody) => data(api.put<SprintPlanDetail>(`/sprint-plans/${id}`, body)),
  generate: (id: string) => data(api.post<SprintPlanDetail>(`/sprint-plans/${id}/generate`)),
  duplicate: (id: string) => data(api.post<SprintPlanDetail>(`/sprint-plans/${id}/duplicate`)),
  archive: (id: string) => data(api.post<SprintPlanDetail>(`/sprint-plans/${id}/archive`)),
  remove: (id: string) => api.delete(`/sprint-plans/${id}`),
  attach: (id: string, planId: string) => data(api.post<SprintPlanDetail>(`/sprint-plans/${id}/subjects`, { teaching_plan_id: planId })),
}

export const SPRINT_STATUS: Record<SprintPlanStatus, { label: string; tone: 'neutral' | 'success' | 'warning' }> = {
  DRAFT: { label: 'Draft', tone: 'warning' },
  ACTIVE: { label: 'Active', tone: 'success' },
  ARCHIVED: { label: 'Archived', tone: 'neutral' },
}
