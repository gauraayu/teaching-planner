import { instNow } from '@/lib/date-time/institution'
import type { Bucket, ExecutionStatus, ImportStatus, MappingStatus, PlanStatus, RowStatus, SubmissionStatus, VerificationStatus } from '@/types/domain'

export type Tone = 'neutral' | 'brand' | 'success' | 'warning' | 'danger' | 'info'

type StatusMeta = { label: string; tone: Tone }

export const PLAN_STATUS: Record<PlanStatus, StatusMeta> = {
  DRAFT: { label: 'Draft', tone: 'neutral' },
  READY: { label: 'Ready', tone: 'info' },
  PUBLISHED: { label: 'Published', tone: 'success' },
  ARCHIVED: { label: 'Archived', tone: 'neutral' },
}

export const EXECUTION_STATUS: Record<ExecutionStatus, StatusMeta> = {
  SCHEDULED: { label: 'Scheduled', tone: 'neutral' },
  IN_PROGRESS: { label: 'In progress', tone: 'info' },
  PARTIALLY_COMPLETED: { label: 'Partially completed', tone: 'warning' },
  COMPLETED: { label: 'Completed', tone: 'success' },
  RESCHEDULED: { label: 'Rescheduled', tone: 'info' },
  NOT_CONDUCTED: { label: 'Not conducted', tone: 'danger' },
}

export const SUBMISSION_STATUS: Record<SubmissionStatus, StatusMeta> = {
  DRAFT: { label: 'Draft saved', tone: 'neutral' },
  SUBMITTED: { label: 'Submitted', tone: 'info' },
  RESUBMITTED: { label: 'Resubmitted', tone: 'info' },
  CORRECTION_REQUIRED: { label: 'Correction required', tone: 'danger' },
  FINAL_VERIFIED: { label: 'Final verified', tone: 'success' },
}

export const VERIFICATION_STATUS: Record<VerificationStatus, StatusMeta> = {
  PENDING: { label: 'Pending', tone: 'warning' },
  VERIFIED: { label: 'Verified', tone: 'success' },
  CORRECTION_REQUIRED: { label: 'Correction required', tone: 'danger' },
  SUPERSEDED: { label: 'Superseded', tone: 'neutral' },
}

export const IMPORT_STATUS: Record<ImportStatus, StatusMeta> = {
  DRAFT: { label: 'Draft', tone: 'neutral' },
  VALIDATING: { label: 'Validating', tone: 'info' },
  READY: { label: 'Ready to publish', tone: 'success' },
  IMPORTED: { label: 'Imported', tone: 'brand' },
  FAILED: { label: 'Failed', tone: 'danger' },
}

export const MAPPING_STATUS: Record<MappingStatus, StatusMeta> = {
  MAPPED: { label: 'Mapped', tone: 'success' },
  SUGGESTED: { label: 'Suggested', tone: 'warning' },
  NEEDS_REVIEW: { label: 'Needs review', tone: 'warning' },
  IGNORED: { label: 'Ignored', tone: 'neutral' },
}

export const ROW_STATUS: Record<RowStatus, StatusMeta> = {
  VALID: { label: 'Valid', tone: 'success' },
  WARNING: { label: 'Warning', tone: 'warning' },
  ERROR: { label: 'Error', tone: 'danger' },
  EMPTY: { label: 'Empty row', tone: 'neutral' },
  REMOVED: { label: 'Removed', tone: 'neutral' },
}

export const BUCKET: Record<Bucket, StatusMeta> = {
  completed: { label: 'Completed', tone: 'success' },
  partial: { label: 'Partial', tone: 'warning' },
  delayed: { label: 'Delayed', tone: 'danger' },
  pending: { label: 'Pending', tone: 'neutral' },
}

export const IMPORT_MODE_LABEL = {
  FULL_TABLE: 'Full table paste',
  COLUMN_WISE: 'Column-by-column',
  EXCEL: 'Excel upload',
  CSV: 'CSV upload',
} as const

export const LECTURE_TYPE_LABEL: Record<string, string> = {
  THEORY: 'Theory',
  PRACTICAL: 'Practical',
  TUTORIAL: 'Tutorial',
  REVISION: 'Revision',
  ASSESSMENT: 'Assessment',
  OTHER: 'Other',
}

export const BLOOM_LABEL: Record<string, string> = {
  K1: 'Remember',
  K2: 'Understand',
  K3: 'Apply',
  K4: 'Analyse',
  K5: 'Evaluate',
  K6: 'Create',
}

const DATE_FMT = new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
const DATE_SHORT = new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short' })
const WEEKDAY = new Intl.DateTimeFormat('en-IN', { weekday: 'short' })
const DATE_TIME = new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', hour: 'numeric', minute: '2-digit' })
const TIME = new Intl.DateTimeFormat('en-IN', { hour: 'numeric', minute: '2-digit' })

/** "2026-10-01" is a calendar date - parse it as local midnight, never as UTC. */
export function parseDate(iso: string): Date {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  return new Date(y, m - 1, d)
}

export const fmt = {
  date: (iso?: string | null) => (iso ? DATE_FMT.format(parseDate(iso)) : '—'),
  dateShort: (iso?: string | null) => (iso ? DATE_SHORT.format(parseDate(iso)) : '—'),
  weekday: (iso?: string | null) => (iso ? WEEKDAY.format(parseDate(iso)) : ''),
  dateTime: (iso?: string | null) => (iso ? DATE_TIME.format(new Date(iso)) : '—'),
  time: (iso?: string | null) => (iso ? TIME.format(new Date(iso)) : '—'),
  /** "10:00" -> "10:00 am" */
  clock: (hm?: string | null) => {
    if (!hm) return ''
    const [h, m] = hm.split(':').map(Number)
    return TIME.format(new Date(2000, 0, 1, h, m))
  },
  timeRange: (start?: string | null, end?: string | null) =>
    start ? `${fmt.clock(start)}${end ? ` – ${fmt.clock(end)}` : ''}` : '',
  relative(iso: string) {
    const diff = (Date.now() - new Date(iso).getTime()) / 1000
    if (diff < 60) return 'just now'
    if (diff < 3600) return `${Math.floor(diff / 60)} min ago`
    if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`
    if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} d ago`
    return DATE_FMT.format(new Date(iso))
  },
  pct: (n?: number | null) => `${n ?? 0}%`,
}

export function isoLocal(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** Today on the institution's calendar (not the laptop's timezone). */
export function todayISO(): string {
  return instNow().date
}

export function plural(n: number, one: string, many = `${one}s`) {
  return `${n.toLocaleString('en-IN')} ${n === 1 ? one : many}`
}
