import { ArrowLeft, CheckCircle2, FileWarning } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from '@/lib/router'
import { ExecutionSummary, MasterPlanPanel, Section, VerificationHistory } from '@/components/domain/LectureRecord'
import { ClassTimingPanel, VerificationTimeline } from '@/components/domain/VerificationTimeline'
import { ErrorState, InlineAlert, PageLoading, useToast } from '@/components/feedback/States'
import { FormField, Textarea } from '@/components/forms/Fields'
import { useBreadcrumbs } from '@/components/layout/PageHeader'
import { StatusBadge, Tag } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { ConfirmDialog, Dialog } from '@/components/ui/Dialog'
import { DefinitionList } from '@/components/ui/Display'
import { useApi } from '@/hooks/useApi'
import { fmt, SUBMISSION_STATUS, VERIFICATION_STATUS } from '@/lib/status'
import { api, errorMessage } from '@/services/api'
import { levelName, VERIFICATION_CHAIN, type LectureDetail, type QueueRow, type VerificationEntry } from '@/types/domain'

type Review = { verification: QueueRow; lecture: LectureDetail; history: VerificationEntry[]; can_act: boolean; acting_level: string | null; waiting_for: string | null }

/** Shared by CL/CH and OM. `queuePath` is where the verifier returns after acting. */
export function ReviewPage({ queuePath = '/verification/pending', queueLabel = 'Pending verification' }: { queuePath?: string; queueLabel?: string }) {
  const { verificationId } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const review = useApi<Review>(`/verifications/${verificationId}`)
  const r = review.data
  useBreadcrumbs([{ label: queueLabel, to: queuePath }, { label: r ? `${r.verification.subject.short_name ?? r.verification.subject.code} · Lecture ${r.verification.lecture_no}` : 'Review' }])
  const [remarks, setRemarks] = useState('')
  const [correctionOpen, setCorrectionOpen] = useState(false)
  const [correction, setCorrection] = useState('')
  const [verifyOpen, setVerifyOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (review.loading && !r) return <PageLoading />
  if (review.error || !r) return <ErrorState message={review.error?.message ?? 'Record not found'} onRetry={review.reload} />
  const v = r.verification
  const d = r.lecture
  const chain = d.verification_chain ?? VERIFICATION_CHAIN
  const finalStep = v.level === chain[chain.length - 1]
  const next = levelName(chain[chain.indexOf(v.level) + 1])

  const act = async (kind: 'verify' | 'correct') => {
    setBusy(true)
    setError(null)
    try {
      if (kind === 'verify') await api.post(`/verifications/${v.id}/verify`, { remarks: remarks.trim() || null })
      else await api.post(`/verifications/${v.id}/request-correction`, { remarks: correction.trim() })
      toast('success', kind === 'verify' ? (finalStep ? `Lecture ${v.lecture_no} final verified.` : `Lecture ${v.lecture_no} verified. It is now with ${next} for final verification.`) : `Correction requested. ${v.professor.full_name} has been notified.`)
      navigate(queuePath)
    } catch (e) {
      setError(errorMessage(e))
      setCorrectionOpen(false)
      setVerifyOpen(false)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-6xl pb-24 lg:pb-0">
      <Link to={queuePath} className="mb-3 inline-flex items-center gap-1 text-[13px] text-fg-label hover:text-fg">
        <ArrowLeft className="h-3.5 w-3.5" /> {queueLabel}
      </Link>
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[12px] font-semibold tracking-wide text-primary uppercase">
            {v.subject.name} · Section {v.section} · Lecture {v.lecture_no}
          </div>
          <h1 className="mt-0.5 text-[21px] leading-tight font-semibold tracking-tight text-fg sm:text-2xl">{v.topic}</h1>
          <p className="meta mt-1">
            {v.professor.full_name} · submitted {fmt.dateTime(v.submitted_at)}
            {v.is_resubmission && ` · resubmission (round ${v.round})`}
          </p>
        </div>
        <div className="flex gap-2">
          <Tag>{levelName(v.level)} step</Tag>
          <StatusBadge value={v.status} map={VERIFICATION_STATUS} />
        </div>
      </div>

      {v.is_resubmission && (() => {
        const last = r.history.filter((h) => h.status === 'CORRECTION_REQUIRED').at(-1)
        return last ? (
          <InlineAlert tone="info" className="mb-4" title="This is a corrected resubmission">
            Earlier {levelName(last.verification_level)} remark: “{last.remarks}”
          </InlineAlert>
        ) : null
      })()}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1.4fr)_minmax(320px,1fr)]">
        <div className="space-y-5">
          <Section title="Verification progress">
            <VerificationTimeline submitted={!!d.execution?.submitted_at} submissionStatus={d.submission_status} steps={d.verifications} chain={chain} round={v.round} />
          </Section>
          <MasterPlanPanel d={d} label="A" />
          <ExecutionSummary d={d} label="B" />
          <ClassTimingPanel session={d.class_session} label="C" emphasise={v.level === 'OM'} />
        </div>
        <div className="space-y-5 lg:sticky lg:top-20 lg:self-start">
          <Section title="Verification" label="D">
            <DefinitionList
              columns={2}
              items={[
                { label: 'You act as', value: levelName(r.acting_level) || 'Viewer' },
                { label: 'Step', value: `${levelName(v.level)} · round ${v.round}` },
                { label: 'Record status', value: <StatusBadge value={d.submission_status} map={SUBMISSION_STATUS} /> },
                { label: 'Next', value: finalStep ? 'Final verified' : `${next} final verification` },
              ]}
            />
            {r.can_act ? (
              <div className="mt-4 space-y-3">
                <FormField label="Remarks" hint={finalStep ? 'Optional when verifying. Visible to the professor.' : 'Optional when verifying. Visible to the professor and to OM.'} htmlFor="vr">
                  <Textarea id="vr" rows={3} value={remarks} onChange={(e) => setRemarks(e.target.value)} />
                </FormField>
                {error && <InlineAlert tone="danger">{error}</InlineAlert>}
                <div className="fixed inset-x-0 bottom-0 z-30 flex gap-2 border-t border-line bg-bg/95 px-4 py-3 backdrop-blur lg:static lg:border-0 lg:bg-transparent lg:p-0">
                  <Button variant="danger" className="flex-1 justify-center" icon={<FileWarning className="h-4 w-4" />} onClick={() => { setCorrection(remarks); setCorrectionOpen(true) }}>
                    Request correction
                  </Button>
                  <Button variant="success" className="flex-1 justify-center" icon={<CheckCircle2 className="h-4 w-4" />} onClick={() => (finalStep ? setVerifyOpen(true) : act('verify'))} loading={busy && !verifyOpen && !correctionOpen}>
                    {finalStep ? 'Final verify' : 'Verify'}
                  </Button>
                </div>
              </div>
            ) : (
              <InlineAlert tone="info" className="mt-4">
                {v.status !== 'PENDING' ? `This step is ${VERIFICATION_STATUS[v.status].label.toLowerCase()}${v.verifier ? ` by ${v.verifier.full_name}` : ''}.` : r.waiting_for ?? (r.acting_level ? `This step is for ${levelName(v.level)}.` : `Waiting for ${levelName(v.level)}. Administrators monitor the workflow; verification is done by CL/CH and OM.`)}
              </InlineAlert>
            )}
          </Section>
          <Section title="History">
            <VerificationHistory items={r.history} />
          </Section>
        </div>
      </div>

      <Dialog
        open={correctionOpen}
        onClose={() => setCorrectionOpen(false)}
        title="Request correction"
        description={`${v.professor.full_name} will be notified and the record reopens for editing.`}
        footer={<><Button onClick={() => setCorrectionOpen(false)}>Cancel</Button><Button variant="danger" loading={busy} disabled={correction.trim().length < 5} onClick={() => act('correct')}>Send correction request</Button></>}
      >
        <FormField label="Correction remarks" required hint="Say exactly what needs to change." htmlFor="cr">
          <Textarea id="cr" rows={4} value={correction} onChange={(e) => setCorrection(e.target.value)} data-autofocus />
        </FormField>
      </Dialog>
      <ConfirmDialog open={verifyOpen} onClose={() => setVerifyOpen(false)} onConfirm={() => act('verify')} loading={busy} tone="success" title={`Final verify Lecture ${v.lecture_no}?`} confirmLabel="Final verify">
        This completes the Professor → CL/CH → OM chain. The record becomes final, its class timing is locked, and it counts toward verified completion.
      </ConfirmDialog>
    </div>
  )
}
