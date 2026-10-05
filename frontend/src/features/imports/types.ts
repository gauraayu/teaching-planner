import type { ImportMode, ImportStatus, MappingStatus, PlanBrief, RowStatus } from '@/types/domain'

export type FieldDef = { key: string; label: string; required: boolean; multi: boolean; description: string }

export type ColumnMapping = {
  field: string | null
  status: MappingStatus
  method: string
  confidence: number
  order: number | null
  suggestion: string | null
  note: string | null
  fill_down: boolean
}

export type ImportColumn = {
  key: string
  header: string
  letter: string | null
  value_count: number
  non_empty_count: number
  samples: string[]
  values: string[] | null
  mapping: ColumnMapping | null
}

export type ImportSummary = {
  rows: number
  lectures: number
  units: number
  subtopics: number
  columns: number
  scheduled: number
  valid: number
  warnings: number
  errors: number
  empty: number
  removed: number
  session_errors: number
  session_warnings: number
  first_date: string | null
  last_date: string | null
}

export type ImportSessionView = {
  id: string
  status: ImportStatus
  import_mode: ImportMode | null
  current_step: string | null
  source_name: string | null
  row_count: number
  revision: number
  validated_revision: number | null
  is_validation_stale: boolean
  failure_reason: string | null
  committed_at: string | null
  created_at: string
  updated_at: string
  teaching_plan: PlanBrief
  summary: ImportSummary | null
  columns?: ImportColumn[]
  has_header?: boolean
  source?: { kind: string; file_name?: string; sheet?: string; sheets?: string[]; trailing_empty_rows_dropped?: number; notes?: string[] } | null
  padded?: Record<string, { expected: number; received: number }>
  last_added_key?: string | null
  can_undo?: boolean
  overrides?: Record<string, Record<string, unknown>>
  removed?: number[]
  grid_preview?: string[][]
}

export type Issue = { field?: string; level: 'ERROR' | 'WARNING'; message: string; code?: string }

export type PreviewRow = {
  index: number
  row_number: number
  status: RowStatus
  raw: Record<string, string>
  values: {
    serial_no?: number | null
    lecture_no?: number | null
    lecture_type?: string
    unit_no?: number | null
    content_topic?: string | null
    blooms_taxonomy?: string | null
    subtopics?: string[]
    planned_date?: string | null
    planned_start_time?: string | null
    planned_end_time?: string | null
    room?: string | null
    /** As written in the sheet. `professor_id` is set only when it matched a real professor account. */
    professor_employee_id?: string | null
    professor_id?: string | null
    professor_name?: string | null
  }
  issues: Issue[]
  edited: boolean
}

export type PreviewData = {
  summary: ImportSummary
  session_issues: Issue[]
  rows: PreviewRow[]
  can_commit: boolean
  stale: boolean
}

export type MismatchResult = {
  status: 'MISMATCH'
  field: string
  field_label: string
  expected: number
  received: number
  difference: number
  reference_column: string
  can_pad: boolean
  can_extend: boolean
  alignment: { row: number; reference: string | null; incoming: string | null }[]
  notes: string[]
}

export type StepKey = 'details' | 'method' | 'map' | 'field' | 'paste' | 'columns' | 'validate' | 'preview' | 'publish'

export const TABLE_STEPS: { key: StepKey; label: string }[] = [
  { key: 'details', label: 'Academic Details' },
  { key: 'method', label: 'Import Method' },
  { key: 'map', label: 'Map Columns' },
  { key: 'validate', label: 'Validate' },
  { key: 'preview', label: 'Preview' },
  { key: 'publish', label: 'Publish' },
]

export const COLUMN_STEPS: { key: StepKey; label: string }[] = [
  { key: 'details', label: 'Academic Details' },
  { key: 'field', label: 'Select Field' },
  { key: 'paste', label: 'Paste Data' },
  { key: 'columns', label: 'Add More Columns' },
  { key: 'validate', label: 'Validate' },
  { key: 'preview', label: 'Preview' },
  { key: 'publish', label: 'Publish' },
]
