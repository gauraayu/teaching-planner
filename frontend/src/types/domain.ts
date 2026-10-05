/** Mirrors app/core/enums.py - the only place status strings live on the frontend. */

export const ROLES = ['ADMIN', 'PROFESSOR', 'CL_CH', 'OM'] as const
export type Role = (typeof ROLES)[number]
/** Code / database identifiers on the left, what people read on the right. CL and CH are one role: CL/CH. */
export const ROLE_NAME: Record<Role, string> = { ADMIN: 'Admin', PROFESSOR: 'Professor', CL_CH: 'CL/CH', OM: 'OM' }
/** Ordered verification chain: Professor submits -> CL/CH -> OM (final). 'CH' only appears on records from before the merge. */
export type VerificationLevel = 'CL_CH' | 'OM' | 'CH'
export const VERIFICATION_CHAIN: VerificationLevel[] = ['CL_CH', 'OM']
export const LEVEL_NAME: Record<string, string> = { CL_CH: 'CL/CH', OM: 'OM', CH: 'CH (legacy)', CL: 'CL (legacy)' }
export const levelName = (level: string | null | undefined) => (level ? LEVEL_NAME[level] ?? level : '')
export type ScopeMode = 'ALL' | 'SELECTED'
export type UserScope = { mode: ScopeMode; department_id: string | null; semester_numbers: number[]; section_names: string[]; subject_ids: string[]; label: string }

/** An account as the administrator sees it in User Management. */
export type ManagedUser = {
  id: string
  full_name: string
  employee_id: string | null
  email: string
  username: string | null
  role: Role
  role_label: string
  designation: string | null
  phone: string | null
  department: { id: string; code: string; name: string } | null
  is_active: boolean
  status: 'ACTIVE' | 'INACTIVE'
  last_login_at: string | null
  must_change_password: boolean
  can_sign_in: boolean
  created_at: string
  scope: UserScope
  scope_label: string
  workload: { subjects: number; plans: number; upcoming_lectures: number } | null
  has_history?: boolean
}
export type TimingStatus = 'ON_TIME' | 'DELAYED'

/** The Operations Manager's timing record for one class, as shown beside a lecture update. */
export type ClassSessionBrief = {
  date: string
  scheduled_start: string | null
  scheduled_end: string | null
  room: string | null
  entry_time: string | null
  exit_time: string | null
  delay_minutes: number
  timing_status: TimingStatus
  delay_reason: string | null
  delay_reason_label: string | null
  delay_remarks: string | null
  duration_minutes: number | null
  early_exit_minutes?: number
  early_exit_reason?: string | null
}

export type PlanStatus = 'DRAFT' | 'READY' | 'PUBLISHED' | 'ARCHIVED'
export type ExecutionStatus = 'SCHEDULED' | 'IN_PROGRESS' | 'PARTIALLY_COMPLETED' | 'COMPLETED' | 'RESCHEDULED' | 'NOT_CONDUCTED'
export type SubmissionStatus = 'DRAFT' | 'SUBMITTED' | 'CORRECTION_REQUIRED' | 'RESUBMITTED' | 'FINAL_VERIFIED'
export type VerificationStatus = 'PENDING' | 'VERIFIED' | 'CORRECTION_REQUIRED' | 'SUPERSEDED'
export type ImportMode = 'FULL_TABLE' | 'COLUMN_WISE' | 'EXCEL' | 'CSV'
export type ImportStatus = 'DRAFT' | 'VALIDATING' | 'READY' | 'IMPORTED' | 'FAILED'
export type MappingStatus = 'MAPPED' | 'SUGGESTED' | 'NEEDS_REVIEW' | 'IGNORED'
export type RowStatus = 'VALID' | 'WARNING' | 'ERROR' | 'EMPTY' | 'REMOVED'
export type Bucket = 'completed' | 'partial' | 'delayed' | 'pending'

export const EXECUTION_STATUSES: ExecutionStatus[] = ['SCHEDULED', 'IN_PROGRESS', 'PARTIALLY_COMPLETED', 'COMPLETED', 'RESCHEDULED', 'NOT_CONDUCTED']

export type UserBrief = { id: string; full_name: string; designation: string | null; role: Role }

export type SessionInfo = {
  user: UserBrief & { email: string; employee_code: string | null; username?: string | null; department: { name: string } | null }
  role: Role
  role_label?: string
  must_change_password?: boolean
  scope?: UserScope
  timezone?: string
  permissions: string[]
  academic_session: {
    academic_year: { id: string; name: string } | null
    semester: { id: string; name: string; number: number } | null
  }
}

export type Ref = { id: string; name: string }

export type PlanBrief = {
  id: string
  name: string
  status: PlanStatus
  room: string | null
  classes_per_week?: number
  labs_per_week?: number
  lab_room?: string | null
  sprint_plan?: { id: string; name: string } | null
  academic_year: Ref
  semester: Ref & { number: number }
  department: Ref
  branch: Ref & { code: string }
  section: Ref
  subject: { id: string; code: string; name: string; short_name: string | null }
  professor: UserBrief
  published_at: string | null
  created_at: string
  updated_at: string
}

export type Metrics = {
  total: number
  completed: number
  partial: number
  delayed: number
  pending: number
  verified: number
  awaiting_verification: number
  correction_required: number
  execution_pct: number
  verified_pct: number
  on_time_pct: number
}

export type SubjectProgressRow = Metrics & {
  plan_id: string
  plan_name: string
  subject_code: string
  subject_name: string
  subject_short: string | null
  section: string
  semester: string
  professor: { id: string; full_name: string }
}

export type UnitRow = Metrics & { unit_no: number | null; first_topic: string }

export type Subtopic = { id: string; position: number; title: string }

export type Lecture = {
  id: string
  teaching_plan_id: string
  sequence: number
  serial_no: number | null
  lecture_no: number
  lecture_type: string
  unit_no: number | null
  content_topic: string
  blooms_taxonomy: string | null
  subtopics: Subtopic[]
  planned_date: string | null
  planned_start_time: string | null
  planned_end_time: string | null
  room?: string | null
  /** The professor account this lecture is allocated to (the plan's professor unless a substitute is set). */
  professor?: UserBrief | null
  is_substitute?: boolean
  is_cancelled?: boolean
  progress: null | {
    id: string
    execution_status: ExecutionStatus
    submission_status: SubmissionStatus
    actual_completion_date: string | null
    rescheduled_to: string | null
    submitted_at: string | null
    final_verified_at: string | null
  }
}

export type TaskCard = Lecture & {
  plan: { id: string; name: string; section: string; semester: string }
  room: string | null
  origin: 'MASTER' | 'SPRINT_ADDED' | 'CARRY_FORWARD'
  is_cancelled: boolean
  subject: { id: string; code: string; name: string; short_name: string | null }
  execution_status: ExecutionStatus
  submission_status: SubmissionStatus | null
  effective_date: string | null
  is_overdue: boolean
  subtopics_covered: number
}

export type VerificationEntry = {
  id: string
  round: number
  verification_level: VerificationLevel
  status: VerificationStatus
  verifier: UserBrief | null
  verifier_role: Role | null
  remarks: string | null
  verified_at: string | null
  created_at: string
}

export type Material = { id: string; title: string | null; caption?: string | null; material_type?: string; content_type?: string | null; file_name: string | null; file_url: string; uploaded_at: string }

export type AssignmentData = {
  id: string
  title: string
  description: string | null
  link_url: string | null
  due_date: string | null
  shared_with_students: boolean | null
  shared_at: string | null
  not_shared_reason: string | null
  created_at: string
}

export type LectureDetail = TaskCard & {
  professor?: UserBrief | null
  master: {
    subject: string
    lecture_no: number
    lecture_type: string
    unit_no: number | null
    content_topic: string
    blooms_taxonomy: string | null
    planned_date: string | null
    planned_start_time: string | null
    planned_end_time: string | null
    subtopics: Subtopic[]
  }
  execution: null | {
    id: string
    execution_status: ExecutionStatus
    submission_status: SubmissionStatus
    actual_completion_date: string | null
    rescheduled_to: string | null
    remarks: string | null
    recording_url?: string | null
    additional_topics?: string | null
    shared_with_students: boolean | null
    shared_at: string | null
    not_shared_reason: string | null
    submitted_at: string | null
    submission_count: number
    covered_subtopic_ids: string[]
    notes: Material[]
    evidence: Material[]
    /** The professor's own Start / End Class clicks (server time). Not the OM's official entry / exit. */
    professor_started_at: string | null
    professor_ended_at: string | null
    checkin_mode: 'TIME' | 'IMAGE' | 'SKIPPED' | null
    assignment: AssignmentData | null
    updated_at: string
  }
  verifications: VerificationEntry[]
  verification_chain: VerificationLevel[]
  class_session: ClassSessionBrief | null
  open_correction: VerificationEntry | null
  class_date: string | null
  can_start: boolean
  can_end: boolean
  sprint_change: SprintChange | null
  can_edit: boolean
  can_submit: boolean
}

export type QueueRow = {
  id: string
  level: VerificationLevel
  class_session: ClassSessionBrief | null
  status: VerificationStatus
  round: number
  professor: UserBrief
  subject: { code: string; name: string; short_name: string | null }
  plan_id: string
  section: string
  semester: string
  lecture_id: string
  lecture_no: number
  topic: string
  unit_no: number | null
  planned_date: string | null
  actual_date: string | null
  execution_status: ExecutionStatus
  submission_status: SubmissionStatus
  submitted_at: string | null
  is_resubmission: boolean
  prior_verifications: VerificationEntry[]
  verifier: UserBrief | null
  remarks: string | null
  verified_at: string | null
  created_at: string
}

export type AuditEntry = {
  id: string
  action: string
  entity_type: string
  entity_id: string | null
  summary: string
  actor: UserBrief | null
  actor_role: Role | null
  old_values: Record<string, unknown> | null
  new_values: Record<string, unknown> | null
  created_at: string
}

export type NotificationItem = {
  id: string
  kind: string
  title: string
  body: string | null
  link: string | null
  is_read: boolean
  created_at: string
}

export type FactRow = {
  lecture_id: string
  plan_id: string
  subject_code: string
  subject_name: string
  subject_short: string | null
  section: string
  professor: string
  unit_no: number | null
  lecture_no: number
  topic: string
  planned_date: string | null
  planned_start_time: string | null
  actual_date: string | null
  execution_status: ExecutionStatus
  submission_status: SubmissionStatus | null
  bucket: Bucket
  delay_days: number | null
  on_time: boolean
}

// ---------------------------------------------------------------- weekly sprint plan

export type SprintValues = {
  planned_date?: string | null
  planned_start_time?: string | null
  planned_end_time?: string | null
  room?: string | null
  professor_id?: string
  professor_name?: string | null
  content_topic?: string
  subtopics?: string[]
  lecture_type?: string
  is_cancelled?: boolean
  lecture_no?: number
}

/** One changed lecture in a weekly revision, as a before / after diff. */
export type SprintChange = {
  id: string
  change_type: 'UPDATE' | 'CANCEL' | 'ADD'
  lecture_id: string | null
  plan_id: string
  subject: { code: string; name: string; short_name: string | null }
  section: string
  semester: string
  lecture_no: number | null
  topic: string | null
  old: SprintValues | null
  new: SprintValues | null
  changed_fields: string[]
  reason: string
  reason_label: string
  remarks: string | null
  is_carry_forward: boolean
  revision_id: string
  revision_number: number | null
  published_at: string | null
}

export type SprintWeekInfo = { start: string; end: string; number: number | null; is_current: boolean; is_past: boolean; sprint_plan?: { id: string; name: string; end_date: string } | null }

export type SprintRevisionBrief = {
  id: string
  week_start: string
  week_end: string
  status: 'DRAFT' | 'PUBLISHED' | 'DISCARDED'
  revision_number: number | null
  meeting_date: string | null
  meeting_notes: string | null
  change_count: number
  created_by: UserBrief | null
  created_at: string
  published_by: UserBrief | null
  published_at: string | null
}

/** A class in a week view (admin and professor share the shape; admin rows add draft info). */
export type SprintRow = {
  lecture_id: string | null
  plan_id: string
  subject: { code: string; name: string; short_name: string | null }
  section: string
  semester: string
  branch_code: string
  section_id?: string
  semester_number?: number
  released?: boolean
  lecture_no: number | null
  unit_no: number | null
  lecture_type: string
  origin: 'MASTER' | 'SPRINT_ADDED' | 'CARRY_FORWARD'
  topic: string
  subtopics: string[]
  subtopics_covered: number
  date: string
  start: string | null
  end: string | null
  room: string | null
  professor: { id: string; full_name: string }
  is_cancelled: boolean
  execution_status: ExecutionStatus
  submission_status: SubmissionStatus | null
  started_at: string | null
  ended_at: string | null
  verification: Record<VerificationLevel, VerificationStatus | null>
  revised: SprintChange | null
  needs_update?: boolean
  needs_submission?: boolean
}
