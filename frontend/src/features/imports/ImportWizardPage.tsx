import { useCallback, useEffect, useState } from 'react'
import { useParams } from '@/lib/router'
import { ErrorState, InlineAlert, PageLoading } from '@/components/feedback/States'
import { PageHeader, useBreadcrumbs } from '@/components/layout/PageHeader'
import { StatusBadge } from '@/components/ui/Badge'
import { ButtonLink, Button } from '@/components/ui/Button'
import { DefinitionList } from '@/components/ui/Display'
import { useApi } from '@/hooks/useApi'
import { IMPORT_MODE_LABEL, IMPORT_STATUS, PLAN_STATUS } from '@/lib/status'
import { api } from '@/services/api'
import { ColumnWorkspace } from './components/ColumnWorkspace'
import { MappingStep } from './components/MappingStep'
import { MethodStep } from './components/MethodStep'
import { PreviewStep } from './components/PreviewStep'
import { ImportDone, PublishStep } from './components/PublishStep'
import { Stepper } from './components/Stepper'
import { ValidateStep } from './components/ValidateStep'
import { COLUMN_STEPS, TABLE_STEPS, type FieldDef, type ImportSessionView, type PreviewData, type StepKey } from './types'

function initialStep(s: ImportSessionView): StepKey {
  switch (s.current_step) {
    case 'MAP': return 'map'
    case 'COLUMNS': return (s.columns?.length ?? 0) > 0 ? 'columns' : 'field'
    case 'PASTE': return 'method'
    case 'PREVIEW': return 'preview'
    case 'DONE': return 'publish'
    default: return 'details'
  }
}

export function ImportWizardPage() {
  const { sessionId } = useParams()
  const { data: session, error, loading, setData: setSession, reload } = useApi<ImportSessionView>(`/imports/${sessionId}`)
  const fields = useApi<{ items: FieldDef[] }>('/imports/fields').data?.items ?? []
  const [step, setStep] = useState<StepKey | null>(null)
  const [preview, setPreview] = useState<PreviewData | null>(null)
  const [previewFilter, setPreviewFilter] = useState<string | undefined>()
  const [done, setDone] = useState<{ lectures: number; subtopics?: number; status?: string } | null>(null)

  useBreadcrumbs([{ label: 'Import Plan', to: '/admin/imports' }, { label: session?.teaching_plan.subject.short_name ?? session?.teaching_plan.subject.code ?? 'Import' }, { label: session ? `${session.teaching_plan.semester.name} · ${session.teaching_plan.section.name}` : '…' }])

  const loadPreview = useCallback(async () => {
    try {
      const { data } = await api.get<PreviewData>(`/imports/${sessionId}/preview`)
      setPreview(data)
    } catch {
      setPreview(null)
    }
  }, [sessionId])

  const wantsPreview = !!session && (step ?? initialStep(session)) === 'preview' && !!session.summary
  useEffect(() => {
    if (wantsPreview && !preview) void loadPreview()
  }, [wantsPreview, preview, loadPreview])

  if (loading && !session) return <PageLoading />
  if (error || !session) return <ErrorState message={error?.message ?? 'Import session not found.'} onRetry={reload} />

  const isColumn = session.import_mode === 'COLUMN_WISE'
  const steps = isColumn ? COLUMN_STEPS : TABLE_STEPS
  let current: StepKey = step ?? initialStep(session)
  if (!steps.some((s) => s.key === current)) current = isColumn ? 'field' : 'method'
  const imported = session.status === 'IMPORTED'
  const hasData = (session.columns?.length ?? 0) > 0

  const reachable = (k: StepKey): boolean => {
    if (imported) return false
    const order = steps.map((s) => s.key)
    if (order.indexOf(k) <= order.indexOf(current)) return true
    if (k === 'map' || k === 'validate' || k === 'columns') return hasData
    if (k === 'preview') return hasData && !!preview
    if (k === 'publish') return !!preview?.can_commit && !session.is_validation_stale
    return true
  }
  const go = (k: StepKey) => setStep(k)
  const plan = session.teaching_plan

  return (
    <div>
      <PageHeader
        title="Import Teaching Plan"
        description="Bring an existing spreadsheet plan into the portal once. Professors then work from the published schedule."
        meta={
          <>
            <StatusBadge value={session.status} map={IMPORT_STATUS} />
            {session.import_mode && <span className="meta">{IMPORT_MODE_LABEL[session.import_mode]}</span>}
            <span className="meta">· Draft saved automatically</span>
          </>
        }
        actions={<ButtonLink to="/admin/imports">Exit</ButtonLink>}
      />

      <div className="panel mb-5 px-3 py-2">
        <Stepper steps={steps} current={imported || done ? 'publish' : current} reachable={reachable} onSelect={go} />
      </div>

      {session.status === 'FAILED' && session.failure_reason && !done && (
        <InlineAlert tone="danger" title="The last publish attempt failed" className="mb-4">
          {session.failure_reason} Your draft is intact - review the data and try again.
        </InlineAlert>
      )}

      {done || imported ? (
        <ImportDone session={session} result={done ?? { lectures: session.summary?.lectures ?? 0, status: plan.status }} />
      ) : current === 'details' ? (
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">Academic details</span>
            <StatusBadge value={plan.status} map={PLAN_STATUS} />
          </div>
          <div className="p-5">
            <DefinitionList
              columns={3}
              items={[
                { label: 'Teaching plan', value: plan.name },
                { label: 'Academic year', value: plan.academic_year.name },
                { label: 'Semester', value: plan.semester.name },
                { label: 'Department', value: plan.department.name },
                { label: 'Branch', value: plan.branch.name },
                { label: 'Section', value: `Section ${plan.section.name}` },
                { label: 'Subject', value: `${plan.subject.code} · ${plan.subject.name}` },
                { label: 'Assigned professor', value: plan.professor.full_name },
              ]}
            />
            <p className="meta mt-5">These details come from the teaching plan. To change them, create the plan again from Teaching Plans.</p>
          </div>
          <div className="flex justify-end border-t border-line px-5 py-3">
            <Button variant="primary" onClick={() => go(isColumn ? 'field' : 'method')}>
              Continue
            </Button>
          </div>
        </div>
      ) : current === 'method' ? (
        <MethodStep session={session} onSession={setSession} onContinue={(mode) => go(mode === 'COLUMN_WISE' ? 'field' : 'map')} />
      ) : current === 'map' ? (
        <MappingStep session={session} fields={fields} onSession={setSession} onBack={() => go('method')} onContinue={() => go('validate')} />
      ) : current === 'field' || current === 'paste' || current === 'columns' ? (
        <>
          {!hasData && (
            <div className="mb-4 flex justify-end">
              <Button size="sm" variant="ghost" onClick={() => go('method')}>
                Change import method
              </Button>
            </div>
          )}
          <ColumnWorkspace
            session={session}
            fields={fields}
            onSession={setSession}
            onStage={(s) => setStep(hasData || s === 'columns' ? 'columns' : s)}
            onBack={() => go('details')}
            onContinue={() => go('validate')}
          />
        </>
      ) : current === 'validate' ? (
        <ValidateStep
          session={session}
          preview={session.is_validation_stale ? null : preview}
          fields={fields}
          onValidated={(s, p) => { setSession(s); setPreview(p) }}
          onBack={() => go(isColumn ? 'columns' : 'map')}
          onContinue={() => { setPreviewFilter(undefined); go('preview') }}
          onFilter={(f) => { setPreviewFilter(f); go('preview') }}
        />
      ) : current === 'preview' ? (
        preview ? (
          <PreviewStep key={previewFilter ?? 'all'} session={session} preview={preview} initialFilter={previewFilter} onPreview={(s, p) => { setSession(s); setPreview(p) }} onBack={() => go('validate')} onContinue={() => go('publish')} />
        ) : (
          <PageLoading />
        )
      ) : (
        <PublishStep session={session} preview={preview} onBack={() => go('preview')} onDone={(r) => { setDone(r); void reload(true) }} />
      )}
    </div>
  )
}
