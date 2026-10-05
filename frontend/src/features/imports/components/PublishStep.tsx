import { CheckCircle2 } from 'lucide-react'
import { useState } from 'react'
import { InlineAlert } from '@/components/feedback/States'
import { Checkbox } from '@/components/forms/Fields'
import { Button, ButtonLink } from '@/components/ui/Button'
import { fmt, plural } from '@/lib/status'
import { api, errorMessage } from '@/services/api'
import type { ImportSessionView, PreviewData } from '../types'

export function PublishStep({ session, preview, onBack, onDone }: { session: ImportSessionView; preview: PreviewData | null; onBack: () => void; onDone: (result: { lectures: number; subtopics: number; status: string }) => void }) {
  const [publishNow, setPublishNow] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const plan = session.teaching_plan
  const s = preview?.summary

  const commit = async () => {
    setBusy(true)
    setError(null)
    try {
      const { data } = await api.post<{ lectures: number; subtopics: number; status: string }>(`/imports/${session.id}/commit`, { confirm: true, publish: publishNow })
      onDone(data)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  if (!s) return <InlineAlert tone="warning">Validate the import first.</InlineAlert>
  return (
    <div className="mx-auto max-w-xl">
      <div className="panel">
        <div className="border-b border-line px-5 py-4">
          <h2 className="text-[15px] font-semibold text-fg">Confirm import</h2>
          <p className="meta mt-0.5">Lectures are written in one transaction. If anything fails, nothing is saved.</p>
        </div>
        <div className="space-y-5 px-5 py-5 text-[13.5px]">
          <div>
            <div className="text-[12px] font-medium text-fg-label">You are about to create</div>
            <ul className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
              {[
                ['1', 'Teaching plan'],
                [s.lectures, 'Lectures'],
                [s.units, 'Units'],
                [s.subtopics, 'Subtopics'],
              ].map(([n, l]) => (
                <li key={l as string} className="rounded-md border border-line px-3 py-2">
                  <div className="tnum text-[20px] font-semibold text-fg">{n}</div>
                  <div className="meta">{l}</div>
                </li>
              ))}
            </ul>
          </div>
          <dl className="grid grid-cols-[120px_1fr] gap-y-2">
            <dt className="text-fg-label">Assigned to</dt>
            <dd className="font-medium text-fg">{plan.professor.full_name}</dd>
            <dt className="text-fg-label">Subject</dt>
            <dd className="font-medium text-fg">{plan.subject.name}</dd>
            <dt className="text-fg-label">Class</dt>
            <dd className="font-medium text-fg">
              {plan.semester.name} – Section {plan.section.name} · {plan.branch.code}
            </dd>
            <dt className="text-fg-label">Schedule</dt>
            <dd className="text-fg">{s.first_date ? `${fmt.date(s.first_date)} to ${fmt.date(s.last_date)} · ${plural(s.scheduled, 'lecture')} dated` : 'No planned dates'}</dd>
            {s.warnings > 0 && (
              <>
                <dt className="text-fg-label">Warnings</dt>
                <dd className="text-warning">{plural(s.warnings, 'row')} imported with warnings</dd>
              </>
            )}
          </dl>
          <Checkbox
            checked={publishNow}
            onChange={(e) => setPublishNow(e.target.checked)}
            label="Publish immediately"
            description={publishNow ? 'The professor sees these lectures in their task list right away.' : 'The plan is saved as Ready. Publish it later from the plan page.'}
          />
          {error && <InlineAlert tone="danger" title="Unable to import plan">{error}</InlineAlert>}
        </div>
        <div className="flex justify-end gap-2 border-t border-line bg-surface-2 px-5 py-3">
          <Button onClick={onBack} disabled={busy}>
            Cancel
          </Button>
          <Button variant="primary" loading={busy} onClick={commit}>
            {busy ? 'Importing…' : publishNow ? 'Publish teaching plan' : 'Save as ready'}
          </Button>
        </div>
      </div>
    </div>
  )
}

export function ImportDone({ session, result }: { session: ImportSessionView; result: { lectures: number; subtopics?: number; status?: string } }) {
  const plan = session.teaching_plan
  return (
    <div className="mx-auto max-w-xl">
      <div className="panel px-6 py-8 text-center">
        <CheckCircle2 className="mx-auto h-9 w-9 text-primary" aria-hidden />
        <h2 className="mt-3 text-[17px] font-semibold text-fg">{plural(result.lectures, 'lecture')} imported successfully</h2>
        <p className="meta mt-1">
          {plan.name} is {result.status === 'READY' ? 'saved as Ready to publish' : `published to ${plan.professor.full_name}`}.
        </p>
        <div className="mt-5 flex justify-center gap-2">
          <ButtonLink variant="primary" to={`/admin/plans/${plan.id}`}>
            Open teaching plan
          </ButtonLink>
          <ButtonLink to="/admin/imports">Import another plan</ButtonLink>
        </div>
      </div>
    </div>
  )
}
