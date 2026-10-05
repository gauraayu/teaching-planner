import type { TimingStatus, UserBrief, VerificationLevel, VerificationStatus, SubmissionStatus, ExecutionStatus } from '@/types/domain'

/** Derived on the server from schedule + clock + recorded times. Never stored. */
export type ClassState = 'YET_TO_START' | 'ENTRY_DUE' | 'IN_CLASS' | 'EXIT_MISSING' | 'COMPLETED' | 'NOT_RECORDED'

export type ChainStep = { level: VerificationLevel; status: VerificationStatus; verifier: UserBrief | null; remarks: string | null; verified_at: string | null }

export type ClassRow = {
  lecture_id: string
  plan_id: string
  date: string
  scheduled_start: string | null
  scheduled_end: string | null
  room: string | null
  professor: UserBrief
  subject: { code: string; name: string; short_name: string | null }
  section: string
  semester: string
  semester_number: number
  branch_code: string
  lecture_no: number
  topic: string
  lecture_type: string
  state: ClassState
  is_rescheduled: boolean
  entry_time: string | null
  exit_time: string | null
  delay_minutes: number | null
  timing_status: TimingStatus | null
  delay_reason: string | null
  delay_reason_label: string | null
  delay_remarks: string | null
  duration_minutes: number | null
  early_exit_minutes: number | null
  early_exit_reason: string | null
  /** The professor's own Start / End Class clicks - shown beside, never merged with, entry / exit. */
  professor_started_at: string | null
  professor_ended_at: string | null
  execution_status: ExecutionStatus
  verification: {
    submission_status: SubmissionStatus | null
    submitted_at: string | null
    round: number
    levels: Record<VerificationLevel, VerificationStatus | null>
    om_verification_id: string | null
    steps: ChainStep[]
    /** True once CL/CH has verified and the OM step is open. Until then `waiting_for` says what is missing. */
    final_ready?: boolean
    waiting_for?: string | null
  }
}

export type ClassDetail = ClassRow & {
  subtopics: string[]
  professor_update: null | { execution_status: ExecutionStatus; actual_completion_date: string | null; remarks: string | null; notes_count: number; has_assignment: boolean }
  tolerance_minutes: number
}

export type OMDay = {
  date: string
  is_today: boolean
  now: string
  tolerance_minutes: number
  metrics: {
    total: number
    running: number
    entry_due: number
    yet_to_start: number
    completed: number
    not_recorded: number
    exit_missing: number
    delayed_entry: number
    awaiting_final_verification: number
  }
  /** The signed-in OM's operational scope (null for an administrator). */
  scope?: { label: string; mode: 'ALL' | 'SELECTED' } | null
  classes: ClassRow[]
}

export type DelayReasonOption = { value: string; label: string }

export type TimingAggregate = {
  recorded: number
  on_time: number
  delayed: number
  on_time_pct: number
  average_delay_minutes: number
  total_delay_minutes: number
  average_duration_minutes: number | null
  exit_missing: number
}

export type FacultyRecord = TimingAggregate & { professor: UserBrief; subjects: string[]; top_delay_reason: string | null; last_recorded: string }

export type OMReport = {
  date_from: string
  date_to: string
  tolerance_minutes: number
  summary: TimingAggregate & { scheduled: number; coverage_pct: number; awaiting_final_verification: number }
  reasons: { reason: string; label: string; count: number }[]
  daily: { date: string; recorded: number; delayed: number; on_time: number }[]
  faculty: FacultyRecord[]
  definitions: Record<string, string>
}

/** No `time` = Clock In: the server's clock is the record. A typed time is a correction. */
export type EntryPayload = { time?: string; delay_reason?: string; delay_remarks?: string }
