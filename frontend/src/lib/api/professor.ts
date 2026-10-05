import { api } from '@/services/api'
import type { AuditEntry, LectureDetail, SprintRow, SubjectProgressRow, SubmissionStatus, UnitRow, VerificationLevel, VerificationStatus } from '@/types/domain'

export type ActionItem = {
  kind: 'CORRECTION' | 'PENDING_LOG' | 'MISSING_ASSET' | 'NOT_SUBMITTED'
  lecture_id: string
  title: string
  subject: string
  detail: string
  by: string | null
  at: string | null
  action: string
}

export type ProfessorDashboardData = {
  today: string
  counts: {
    today: number
    today_completed: number
    pending: number
    overdue: number
    completed: number
    partial: number
    total: number
    corrections: number
    awaiting_verification: number
    verified: number
    pending_updates: number
    course_progress_pct: number
  }
  courses: SubjectProgressRow[]
  schedule_today: SprintRow[]
  action_items: ActionItem[]
  pipeline: null | {
    lecture_id: string
    lecture_no: number
    topic: string
    subject: string
    submission_status: SubmissionStatus
    submitted_at: string | null
    round: number
    chain: VerificationLevel[]
    steps: { verification_level: VerificationLevel; status: VerificationStatus; round: number; verified_at: string | null }[]
  }
  recent: AuditEntry[]
  syllabus: (SubjectProgressRow & { units: UnitRow[] })[]
}

const data = <T,>(p: Promise<{ data: T }>) => p.then((r) => r.data)

/** The professor's live-class actions. The server stamps the time of each one. */
export const professorApi = {
  startClass: (lectureId: string, checkin: 'TIME' | 'IMAGE' | 'SKIPPED') => data(api.post<LectureDetail>(`/lectures/${lectureId}/start`, { checkin })),
  endClass: (lectureId: string) => data(api.post<LectureDetail>(`/lectures/${lectureId}/end`)),
}
