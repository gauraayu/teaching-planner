import { FormField, Select, Textarea } from '@/components/forms/Fields'
import { useApi } from '@/hooks/useApi'
import type { DelayReasonOption } from '../types/om.types'

export type DelayState = { minutes: number; tolerance: number }

/**
 * The delay step of the entry dialog. It appears only after the backend has judged the
 * entry to be past the tolerance (422 DELAY_REASON_REQUIRED) - the UI never decides
 * what counts as late.
 */
export function DelayReasonFields({
  delay,
  reason,
  remarks,
  onReason,
  onRemarks,
  error,
}: {
  delay: DelayState
  reason: string
  remarks: string
  onReason: (v: string) => void
  onRemarks: (v: string) => void
  error?: string | null
}) {
  const reasons = useApi<{ items: DelayReasonOption[] }>('/om/delay-reasons')
  return (
    <div className="rounded-md border border-warning-border bg-warning-soft p-3.5">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[13px] font-semibold text-warning">Delay: {delay.minutes} minutes</span>
        <span className="text-[12px] text-fg-label">Tolerance {delay.tolerance} min</span>
      </div>
      <div className="mt-3 space-y-3">
        <FormField label="Delay reason" required htmlFor="delay-reason" error={error && !reason ? error : undefined}>
          <Select id="delay-reason" value={reason} onChange={(e) => onReason(e.target.value)} invalid={!!error && !reason}>
            <option value="">Select reason</option>
            {(reasons.data?.items ?? []).map((r) => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </Select>
        </FormField>
        {reason === 'OTHER' && (
          <FormField label="Additional remarks" required htmlFor="delay-remarks" error={error && reason === 'OTHER' && !remarks.trim() ? error : undefined}>
            <Textarea id="delay-remarks" rows={2} value={remarks} onChange={(e) => onRemarks(e.target.value)} maxLength={500} />
          </FormField>
        )}
        {reason && reason !== 'OTHER' && (
          <FormField label="Additional remarks" hint="Optional" htmlFor="delay-remarks">
            <Textarea id="delay-remarks" rows={2} value={remarks} onChange={(e) => onRemarks(e.target.value)} maxLength={500} />
          </FormField>
        )}
      </div>
    </div>
  )
}
