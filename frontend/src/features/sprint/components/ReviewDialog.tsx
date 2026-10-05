import { useEffect, useState } from 'react'
import { ErrorState, InlineAlert, LoadingRows } from '@/components/feedback/States'
import { FormField, Textarea } from '@/components/forms/Fields'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { adminSprintApi, type AdminWeek, type RevisionChanges } from '@/lib/api/sprint'
import { fmt } from '@/lib/status'
import { errorMessage } from '@/services/api'
import { ChangeDiff } from './ChangeDiff'
import { weekLabel } from './WeekNav'

/** "Review Sprint Changes": everything in the draft, then one explicit publish. */
export function ReviewDialog({ open, week, onClose, onPublished, onRemoved }: { open: boolean; week: AdminWeek; onClose: () => void; onPublished: (r: RevisionChanges) => void; onRemoved: (w: AdminWeek) => void }) {
  const [data, setData] = useState<RevisionChanges | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const revisionId = week.draft?.id

  useEffect(() => {
    if (!open || !revisionId) return
    setData(null)
    setError(null)
    setNotes(week.draft?.meeting_notes ?? '')
    adminSprintApi.changes(revisionId).then(setData).catch((e) => setError(errorMessage(e)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, revisionId, week.draft?.change_count])

  if (!open || !revisionId) return null
  const count = data?.changes.length ?? week.draft?.change_count ?? 0
  // A professor in two classes at once cannot be published; a shared room is only a warning.
  const blocked = !!data?.conflicts?.some((c) => c.level === 'ERROR')

  const publish = async () => {
    setBusy(true)
    setError(null)
    try {
      onPublished(await adminSprintApi.publish(revisionId, notes.trim() || null))
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }
  const remove = async (itemId: string) => {
    try {
      onRemoved(await adminSprintApi.removeChange(revisionId, itemId))
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title="Review sprint changes"
      description={`${week.week.number ? `Week ${week.week.number} · ` : ''}${weekLabel(week.week)} · ${count} change${count === 1 ? '' : 's'} · will be published as v${week.version + 1}`}
      footer={
        <>
          <Button onClick={onClose} disabled={busy}>Continue editing</Button>
          <Button variant="primary" loading={busy} onClick={publish} disabled={!data || blocked} title={blocked ? 'Resolve the schedule conflict first' : undefined}>Publish weekly revision</Button>
        </>
      }
    >
      <div className="space-y-4">
        {!data && !error && <LoadingRows rows={3} />}
        {error && !data && <ErrorState message={error} />}
        {data && (
          <>
            {data.conflicts?.map((c, i) => (
              <InlineAlert key={i} tone={c.level === 'ERROR' ? 'danger' : 'warning'} title={`${c.kind === 'ROOM' ? 'Room conflict' : 'Schedule conflict'} · ${fmt.weekday(c.date)} ${fmt.dateShort(c.date)}`}>
                {c.message}{c.level === 'ERROR' && ' Change the professor or the time before publishing.'}
              </InlineAlert>
            ))}
            {data.changes.length === 0 ? (
              <InlineAlert tone="info" title="No schedule changes in this draft">Publishing records that the week was reviewed in the sprint meeting and keeps the schedule as it is. Professors are not notified.</InlineAlert>
            ) : (
              <div className="space-y-3">
                {data.changes.map((c, i) => (
                  <div key={c.id}>
                    <ChangeDiff c={c} index={i} />
                    <div className="mt-1 text-right"><Button variant="link" className="text-[12.5px]" onClick={() => remove(c.id)}>Undo this change</Button></div>
                  </div>
                ))}
              </div>
            )}
            <FormField label="Meeting notes" hint="Optional. Saved with the revision in Sprint Meeting History." htmlFor="sp-notes">
              <Textarea id="sp-notes" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={4000} />
            </FormField>
            {error && <InlineAlert tone="danger">{error}</InlineAlert>}
            <p className="meta">Publishing updates the affected professors&apos; schedules immediately and sends each of them one notification. The previous version stays in the history.</p>
          </>
        )}
      </div>
    </Dialog>
  )
}
