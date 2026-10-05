import type { ColumnDef } from '@tanstack/react-table'
import { KeyRound, MoreHorizontal, Pencil, Plus, UserCheck, UserX, Users } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { EmptyState, InlineAlert, useToast } from '@/components/feedback/States'
import { FormField, Input, Segmented, Select } from '@/components/forms/Fields'
import { PageHeader, useBreadcrumbs } from '@/components/layout/PageHeader'
import { DataTable } from '@/components/tables/DataTable'
import { FilterBar, FilterSelect } from '@/components/tables/FilterBar'
import { Badge, Tag } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { ConfirmDialog, Dialog } from '@/components/ui/Dialog'
import { Metric, MetricStrip } from '@/components/ui/Display'
import { Menu } from '@/components/ui/Menu'
import { PASSWORD_MIN } from '@/features/auth/ChangePasswordDialog'
import { useAuth } from '@/features/auth/AuthContext'
import { useApi } from '@/hooks/useApi'
import { usersApi, type ScopeInput, type UserInput } from '@/lib/api/users'
import { fmt } from '@/lib/status'
import { ApiError, errorMessage, type Paged } from '@/services/api'
import { ROLE_NAME, type ManagedUser, type Role } from '@/types/domain'
import { cn } from '@/utils/cn'

const CREATABLE: Role[] = ['ADMIN', 'PROFESSOR', 'CL_CH', 'OM']
const ROLE_TONE: Record<Role, 'neutral' | 'info' | 'brand' | 'warning'> = { ADMIN: 'neutral', PROFESSOR: 'info', CL_CH: 'brand', OM: 'warning' }
const ROMAN = ['', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII']

function lastLogin(iso: string | null) {
  if (!iso) return 'Never'
  const d = new Date(iso)
  return d.toDateString() === new Date().toDateString() ? `Today, ${fmt.time(iso)}` : fmt.dateTime(iso)
}

export function UserManagementPage() {
  useBreadcrumbs([{ label: 'System' }, { label: 'User Management' }])
  const toast = useToast()
  const { user: me } = useAuth()
  const [role, setRole] = useState('')
  const [status, setStatus] = useState('')
  const users = useApi<Paged<ManagedUser>>('/admin/users', { role, status })
  const all = useApi<Paged<ManagedUser>>('/admin/users')
  const [editing, setEditing] = useState<ManagedUser | 'new' | null>(null)
  const [resetting, setResetting] = useState<ManagedUser | null>(null)
  const [creds, setCreds] = useState<{ user: ManagedUser; password: string } | null>(null)
  const [toggling, setToggling] = useState<ManagedUser | null>(null)

  const reload = () => { void users.reload(true); void all.reload(true) }
  const counts = useMemo(() => {
    const items = all.data?.items ?? []
    return { total: items.length, active: items.filter((u) => u.is_active).length, PROFESSOR: items.filter((u) => u.role === 'PROFESSOR').length, CL_CH: items.filter((u) => u.role === 'CL_CH').length, OM: items.filter((u) => u.role === 'OM').length }
  }, [all.data])

  const columns = useMemo<ColumnDef<ManagedUser, unknown>[]>(() => [
    { id: 'name', header: 'Name', accessorFn: (u) => `${u.full_name} ${u.designation ?? ''}`, cell: ({ row: { original: u } }) => (
      <div className="min-w-[160px]"><div className="font-medium text-fg">{u.full_name}</div>{u.designation && <div className="meta">{u.designation}</div>}</div>
    ) },
    { id: 'employee_id', header: 'Employee ID', accessorFn: (u) => u.employee_id ?? '', cell: ({ getValue }) => <span className="tnum whitespace-nowrap">{getValue<string>() || '—'}</span> },
    { id: 'login', header: 'Email / Username', accessorFn: (u) => `${u.email} ${u.username ?? ''}`, cell: ({ row: { original: u } }) => (
      <div className="min-w-[180px]"><div className="text-fg-soft">{u.email}</div>{u.username && <div className="meta font-mono">{u.username}</div>}</div>
    ) },
    { id: 'role', header: 'Role', accessorFn: (u) => ROLE_NAME[u.role], cell: ({ row: { original: u } }) => <Badge tone={ROLE_TONE[u.role]} icon={false}>{ROLE_NAME[u.role]}</Badge> },
    { id: 'department', header: 'Department', accessorFn: (u) => u.department?.code ?? '—' },
    { id: 'scope', header: 'Assigned scope', accessorFn: (u) => u.scope_label, cell: ({ row: { original: u } }) => (
      <span className="whitespace-nowrap" title={u.role === 'PROFESSOR' && u.workload ? `${u.workload.plans} plan(s), ${u.workload.upcoming_lectures} upcoming lecture(s)` : undefined}>{u.scope_label}</span>
    ) },
    { id: 'status', header: 'Status', accessorFn: (u) => u.status, cell: ({ row: { original: u } }) => (
      <div className="flex flex-col items-start gap-1">{u.is_active ? <Badge tone="success">Active</Badge> : <Badge>Inactive</Badge>}{u.must_change_password && u.is_active && <Tag className="whitespace-nowrap" title="Has not replaced the temporary password yet">Temp password</Tag>}</div>
    ) },
    { id: 'last_login', header: 'Last login', accessorFn: (u) => u.last_login_at ?? '', cell: ({ row: { original: u } }) => <span className="meta whitespace-nowrap">{lastLogin(u.last_login_at)}</span> },
    { id: 'action', header: '', enableSorting: false, cell: ({ row: { original: u } }) => (
      <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
        <Button size="sm" onClick={() => setEditing(u)}>Edit</Button>
        <Menu label={`More actions for ${u.full_name}`} trigger={(p) => <Button size="icon" variant="ghost" aria-label={`More actions for ${u.full_name}`} {...p}><MoreHorizontal className="h-4 w-4" /></Button>} items={[
          { label: 'Edit details', icon: <Pencil className="h-3.5 w-3.5" />, onSelect: () => setEditing(u) },
          { label: 'Set new password', icon: <KeyRound className="h-3.5 w-3.5" />, onSelect: () => setResetting(u) },
          'separator',
          u.is_active
            ? { label: 'Deactivate', icon: <UserX className="h-3.5 w-3.5" />, danger: true, disabled: u.id === me?.id, onSelect: () => setToggling(u) }
            : { label: 'Activate', icon: <UserCheck className="h-3.5 w-3.5" />, onSelect: () => setToggling(u) },
        ]} />
      </div>
    ) },
  ], [me?.id])

  return (
    <div>
      <PageHeader
        title="User Management"
        description="Manage faculty and academic operations accounts"
        actions={<Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setEditing('new')}>Add User</Button>}
      />
      <MetricStrip className="mb-5">
        <Metric label="Accounts" value={all.data ? counts.total : '–'} sub={all.data ? `${counts.active} active` : undefined} />
        <Metric label="Professors" value={all.data ? counts.PROFESSOR : '–'} />
        <Metric label="CL/CH" value={all.data ? counts.CL_CH : '–'} />
        <Metric label="OM" value={all.data ? counts.OM : '–'} />
      </MetricStrip>
      <div className="mb-4">
        <FilterBar onReset={() => { setRole(''); setStatus('') }} active={!!(role || status)}>
          <FilterSelect label="Role" value={role} onChange={setRole} allLabel="All roles" options={CREATABLE.map((r) => ({ value: r, label: ROLE_NAME[r] }))} />
          <FilterSelect label="Status" value={status} onChange={setStatus} allLabel="All statuses" options={[{ value: 'ACTIVE', label: 'Active' }, { value: 'INACTIVE', label: 'Inactive' }]} width="w-36" />
        </FilterBar>
      </div>
      <div className="panel">
        <DataTable
          columns={columns}
          data={users.data?.items}
          loading={users.loading}
          error={users.error?.message}
          onRetry={users.reload}
          searchPlaceholder="Search name, employee ID, email…"
          onRowClick={(u) => setEditing(u)}
          empty={<EmptyState icon={<Users className="h-5 w-5" />} title="No accounts match" description="Change the filters, or add a user." action={<Button variant="primary" size="sm" onClick={() => setEditing('new')}>Add User</Button>} />}
        />
      </div>

      {editing && <UserDialog user={editing === 'new' ? null : editing} onClose={() => setEditing(null)} onSaved={(u, created, password) => { setEditing(null); reload(); if (created && password) setCreds({ user: u, password }); else toast('success', `${u.full_name}'s account updated.`) }} />}
      {creds && <CredentialsDialog user={creds.user} password={creds.password} onClose={() => setCreds(null)} />}
      {resetting && <PasswordDialog user={resetting} onClose={() => setResetting(null)} onDone={() => { setResetting(null); reload(); toast('success', 'New temporary password set.') }} />}
      <ConfirmDialog
        open={!!toggling}
        onClose={() => setToggling(null)}
        tone={toggling?.is_active ? 'danger' : 'primary'}
        title={toggling?.is_active ? `Deactivate ${toggling.full_name}?` : `Activate ${toggling?.full_name}?`}
        confirmLabel={toggling?.is_active ? 'Deactivate' : 'Activate'}
        onConfirm={async () => {
          if (!toggling) return
          try {
            await usersApi.setActive(toggling.id, !toggling.is_active)
            toast('success', toggling.is_active ? `${toggling.full_name} can no longer sign in.` : `${toggling.full_name} can sign in again.`)
            reload()
          } catch (e) {
            toast('danger', errorMessage(e))
          }
          setToggling(null)
        }}
      >
        {toggling?.is_active ? (
          <>
            They are signed out immediately and cannot sign in again. Nothing is deleted: their lectures, verifications and audit history keep showing their name.
            {toggling.role === 'PROFESSOR' && !!toggling.workload?.upcoming_lectures && (
              <span className="mt-2 block text-warning">{toggling.workload.upcoming_lectures} upcoming lecture(s) are still allocated to this professor. Reassign them in the Weekly Sprint Plan.</span>
            )}
          </>
        ) : 'They will be able to sign in again with their existing password.'}
      </ConfirmDialog>
    </div>
  )
}

/* ------------------------------------------------------------------ create / edit */

type Form = { full_name: string; employee_id: string; email: string; username: string; role: Role; department_id: string; designation: string; phone: string; password: string; is_active: boolean; scope: ScopeInput }

const emptyScope = (): ScopeInput => ({ mode: 'ALL', department_id: null, semester_numbers: [], section_names: [], subject_ids: [] })

function toForm(u: ManagedUser | null): Form {
  return {
    full_name: u?.full_name ?? '', employee_id: u?.employee_id ?? '', email: u?.email ?? '', username: u?.username ?? '', role: u?.role ?? 'PROFESSOR',
    department_id: u?.department?.id ?? '', designation: u?.designation ?? '', phone: u?.phone ?? '', password: '', is_active: u?.is_active ?? true,
    scope: u ? { mode: u.scope.mode, department_id: u.scope.department_id, semester_numbers: u.scope.semester_numbers, section_names: u.scope.section_names, subject_ids: u.scope.subject_ids } : emptyScope(),
  }
}

type Opt = { id: string; name: string }

function UserDialog({ user, onClose, onSaved }: { user: ManagedUser | null; onClose: () => void; onSaved: (u: ManagedUser, created: boolean, password?: string) => void }) {
  const departments = useApi<Paged<Opt & { code: string }>>('/departments').data?.items ?? []
  const semesters = useApi<Paged<{ number: number }>>('/semesters').data?.items ?? []
  const sections = useApi<Paged<{ name: string }>>('/sections').data?.items ?? []
  const subjects = useApi<Paged<Opt & { code: string; semester_number: number }>>('/subjects').data?.items ?? []
  const detail = useApi<ManagedUser>(user ? `/admin/users/${user.id}` : null)
  const [f, setF] = useState<Form>(() => toForm(user))
  const [errors, setErrors] = useState<Partial<Record<keyof Form | 'scope', string>>>({})
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const set = <K extends keyof Form>(k: K, v: Form[K]) => { setF((x) => ({ ...x, [k]: v })); setErrors((e) => ({ ...e, [k]: undefined })) }
  const setScope = (patch: Partial<ScopeInput>) => { setF((x) => ({ ...x, scope: { ...x.scope, ...patch } })); setErrors((e) => ({ ...e, scope: undefined })) }

  // The scope's department follows the account's department unless the admin picks another.
  useEffect(() => {
    if (!user && f.role !== 'PROFESSOR' && f.scope.mode === 'SELECTED' && !f.scope.department_id && f.department_id) setScope({ department_id: f.department_id })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [f.department_id, f.scope.mode])

  const isAdmin = f.role === 'ADMIN'
  const roleLocked = !!user && (isAdmin || !!detail.data?.has_history)
  const semesterNumbers = [...new Set(semesters.map((s) => s.number))].sort((a, b) => a - b)
  const sectionNames = [...new Set(sections.map((s) => s.name))].sort()
  const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v])

  const validate = () => {
    const e: typeof errors = {}
    if (f.full_name.trim().length < 2) e.full_name = 'Enter the full name.'
    if (!f.employee_id.trim()) e.employee_id = 'Enter the employee ID.'
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(f.email.trim())) e.email = 'Enter a valid email address.'
    if (f.username && !/^[A-Za-z0-9._-]{3,60}$/.test(f.username)) e.username = '3–60 letters, digits, dot, dash or underscore.'
    if (!isAdmin && !f.department_id) e.department_id = 'Choose the department.'
    if (!user && f.password.length < PASSWORD_MIN) e.password = `Use at least ${PASSWORD_MIN} characters.`
    const s = f.scope
    if (f.role !== 'PROFESSOR' && !isAdmin && s.mode === 'SELECTED' && !s.department_id && !s.semester_numbers.length && !s.section_names.length && !s.subject_ids.length)
      e.scope = 'Select at least a department, semester, section or subject - or choose All.'
    setErrors(e)
    return !Object.values(e).some(Boolean)
  }

  const submit = async (ev?: React.FormEvent) => {
    ev?.preventDefault()
    if (!validate()) return
    setBusy(true)
    setError(null)
    const body: UserInput = {
      full_name: f.full_name.trim(), employee_id: f.employee_id.trim(), email: f.email.trim(), username: f.username.trim() || null, role: f.role,
      department_id: f.department_id || null, designation: f.designation.trim() || null, phone: f.phone.trim() || null, is_active: f.is_active,
      scope: f.role === 'PROFESSOR' ? { ...emptyScope(), subject_ids: f.scope.subject_ids } : f.scope,
    }
    try {
      const saved = user ? await usersApi.update(user.id, body) : await usersApi.create({ ...body, password: f.password })
      onSaved(saved, !user, user ? undefined : f.password)
    } catch (e) {
      const fields = e instanceof ApiError ? (e.details as { fields?: Record<string, string> } | undefined)?.fields : undefined
      if (fields && !Array.isArray(fields)) setErrors((x) => ({ ...x, ...fields }))
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const scopeTitle = f.role === 'CL_CH' ? 'Verification scope' : f.role === 'OM' ? 'Operational scope' : 'Subject eligibility'
  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={user ? `Edit ${user.full_name}` : 'Add User'}
      description={user ? `${ROLE_NAME[user.role]} · last login ${lastLogin(user.last_login_at).toLowerCase()}` : 'The person signs in with the email, username or employee ID and the temporary password you set here.'}
      footer={<><Button onClick={onClose} disabled={busy}>Cancel</Button><Button variant="primary" loading={busy} onClick={() => void submit()}>{user ? 'Save changes' : 'Create User'}</Button></>}
    >
      <form onSubmit={submit} noValidate className="space-y-5">
        {error && <InlineAlert tone="danger">{error}</InlineAlert>}

        <FormField label="Role" required hint={roleLocked ? (isAdmin ? 'Administrator accounts keep their role.' : 'This account already has records, so its role can no longer be changed. Deactivate it and create a new account instead.') : undefined}>
          <Segmented<Role> ariaLabel="Role" value={f.role} disabled={roleLocked} onChange={(r) => { setF((x) => ({ ...x, role: r, scope: emptyScope() })); setErrors({}) }}
            options={(user && isAdmin ? (['ADMIN'] as Role[]) : CREATABLE).map((r) => ({ value: r, label: ROLE_NAME[r] }))} />
        </FormField>

        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label="Full name" required error={errors.full_name}><Input value={f.full_name} onChange={(e) => set('full_name', e.target.value)} invalid={!!errors.full_name} autoComplete="off" data-autofocus /></FormField>
          <FormField label="Employee ID" required error={errors.employee_id}><Input value={f.employee_id} onChange={(e) => set('employee_id', e.target.value)} invalid={!!errors.employee_id} autoComplete="off" /></FormField>
          <FormField label="Email" required error={errors.email}><Input type="email" value={f.email} onChange={(e) => set('email', e.target.value)} invalid={!!errors.email} autoComplete="off" /></FormField>
          <FormField label="Username" hint="Optional. Email and employee ID also work for sign-in." error={errors.username}><Input value={f.username} onChange={(e) => set('username', e.target.value)} invalid={!!errors.username} autoComplete="off" autoCapitalize="none" /></FormField>
          <FormField label="Department" required={!isAdmin} error={errors.department_id}>
            <Select value={f.department_id} onChange={(e) => set('department_id', e.target.value)} invalid={!!errors.department_id}>
              <option value="">Select…</option>
              {departments.map((d) => <option key={d.id} value={d.id}>{d.code} · {d.name}</option>)}
            </Select>
          </FormField>
          {(f.role === 'PROFESSOR' || isAdmin) && <FormField label="Designation"><Input value={f.designation} onChange={(e) => set('designation', e.target.value)} placeholder={f.role === 'PROFESSOR' ? 'Assistant Professor' : undefined} /></FormField>}
          <FormField label="Phone" hint="Optional"><Input type="tel" value={f.phone} onChange={(e) => set('phone', e.target.value)} autoComplete="off" /></FormField>
          {!user && (
            <FormField label="Temporary password" required hint="The user must change it at first sign-in." error={errors.password}>
              <Input type="text" value={f.password} onChange={(e) => set('password', e.target.value)} invalid={!!errors.password} autoComplete="new-password" className="font-mono" />
            </FormField>
          )}
          <FormField label="Status">
            <Segmented ariaLabel="Status" value={f.is_active ? 'ACTIVE' : 'INACTIVE'} onChange={(v) => set('is_active', v === 'ACTIVE')} options={[{ value: 'ACTIVE', label: 'Active' }, { value: 'INACTIVE', label: 'Inactive' }]} />
          </FormField>
        </div>

        {!isAdmin && (
          <fieldset className="rounded-md border border-line p-4">
            <legend className="px-1.5 text-[12px] font-semibold tracking-wide text-fg-label uppercase">{scopeTitle}</legend>
            {f.role === 'PROFESSOR' ? (
              <>
                <p className="meta mb-3">Subjects this professor can be allocated. Leave empty to allow any subject. Subjects are allocated in the Sprint Plan.</p>
                <ChipGroup label="Subjects" empty="Add subjects in Academic Setup first." options={subjects.map((s) => ({ value: s.id, label: s.code, title: s.name }))} selected={f.scope.subject_ids} onToggle={(v) => setScope({ subject_ids: toggle(f.scope.subject_ids, v) })} />
              </>
            ) : (
              <>
                <Segmented ariaLabel="Scope mode" value={f.scope.mode} onChange={(mode) => setScope({ mode })}
                  options={[{ value: 'ALL', label: f.role === 'CL_CH' ? 'All Professors' : 'All Classes' }, { value: 'SELECTED', label: 'Selected Scope' }]} />
                <p className="meta mt-2">
                  {f.scope.mode === 'ALL'
                    ? f.role === 'CL_CH' ? 'Sees and verifies submissions from every professor.' : 'Sees every scheduled class, records entry and exit, and gives the final verification.'
                    : f.role === 'CL_CH' ? 'Sees submissions from all professors teaching inside the selection below. Empty rows mean "any".' : 'Sees and records only the classes inside the selection below. Empty rows mean "any".'}
                </p>
                {f.scope.mode === 'SELECTED' && (
                  <div className="mt-4 space-y-4">
                    <FormField label="Department">
                      <Select value={f.scope.department_id ?? ''} onChange={(e) => setScope({ department_id: e.target.value || null })}>
                        <option value="">Any department</option>
                        {departments.map((d) => <option key={d.id} value={d.id}>{d.code} · {d.name}</option>)}
                      </Select>
                    </FormField>
                    <ChipGroup label="Semesters" empty="No semesters yet." options={semesterNumbers.map((n) => ({ value: n, label: `Sem ${ROMAN[n] ?? n}` }))} selected={f.scope.semester_numbers} onToggle={(v) => setScope({ semester_numbers: toggle(f.scope.semester_numbers, v) })} />
                    <ChipGroup label="Sections" empty="No sections yet." options={sectionNames.map((n) => ({ value: n, label: n }))} selected={f.scope.section_names} onToggle={(v) => setScope({ section_names: toggle(f.scope.section_names, v) })} />
                    <ChipGroup label="Subjects" empty="No subjects yet." options={subjects.map((s) => ({ value: s.id, label: s.code, title: s.name }))} selected={f.scope.subject_ids} onToggle={(v) => setScope({ subject_ids: toggle(f.scope.subject_ids, v) })} anyLabel="All subjects" />
                    {errors.scope && <p className="text-[12.5px] text-danger" role="alert">{errors.scope}</p>}
                  </div>
                )}
              </>
            )}
          </fieldset>
        )}
        <button type="submit" className="hidden" />
      </form>
    </Dialog>
  )
}

function ChipGroup<T extends string | number>({ label, options, selected, onToggle, empty, anyLabel = 'Any' }: { label: string; options: { value: T; label: string; title?: string }[]; selected: T[]; onToggle: (v: T) => void; empty: string; anyLabel?: string }) {
  return (
    <div role="group" aria-label={label}>
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-[13px] font-medium text-fg-soft">{label}</span>
        <span className="meta">{selected.length ? `${selected.length} selected` : anyLabel}</span>
      </div>
      {options.length === 0 ? <p className="meta">{empty}</p> : (
        <div className="flex flex-wrap gap-1.5">
          {options.map((o) => {
            const on = selected.includes(o.value)
            return (
              <button key={String(o.value)} type="button" title={o.title} aria-pressed={on} onClick={() => onToggle(o.value)}
                className={cn('h-7 rounded-md border px-2.5 text-[12.5px] font-medium transition-colors', on ? 'border-primary bg-primary-soft text-primary' : 'border-line-strong text-fg-secondary hover:border-line-hover hover:text-fg')}>
                {o.label}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

function PasswordDialog({ user, onClose, onDone }: { user: ManagedUser; onClose: () => void; onDone: () => void }) {
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const short = password.length < PASSWORD_MIN
  const submit = async (e?: React.FormEvent) => {
    e?.preventDefault()
    if (short) return
    setBusy(true)
    setError(null)
    try {
      await usersApi.resetPassword(user.id, password)
      onDone()
    } catch (err) {
      setError(errorMessage(err))
      setBusy(false)
    }
  }
  return (
    <Dialog open onClose={onClose} size="sm" title={`Set new password for ${user.full_name}`} description="Give it to them directly. They will be asked to change it at their next sign-in."
      footer={<><Button onClick={onClose} disabled={busy}>Cancel</Button><Button variant="primary" loading={busy} disabled={short} onClick={() => void submit()}>Set password</Button></>}>
      <form onSubmit={submit} noValidate>
        {error && <InlineAlert tone="danger" className="mb-3">{error}</InlineAlert>}
        <FormField label="Temporary password" required hint={`At least ${PASSWORD_MIN} characters.`}>
          <Input type="text" className="font-mono" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} data-autofocus />
        </FormField>
        <button type="submit" className="hidden" />
      </form>
    </Dialog>
  )
}

/** Shown once, right after an account is created: what to hand to the person. The password itself is stored hashed. */
function CredentialsDialog({ user, password, onClose }: { user: ManagedUser; password: string; onClose: () => void }) {
  const toast = useToast()
  const login = user.username || user.employee_id || user.email
  const text = `${user.full_name}\nUsername: ${login}\nTemporary password: ${password}`
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      toast('success', 'Credentials copied.')
    } catch {
      toast('danger', 'Could not copy. Select the text and copy it yourself.')
    }
  }
  return (
    <Dialog open onClose={onClose} size="sm" title="Account created" description={`${ROLE_NAME[user.role]} · the person is asked to choose a new password at first sign-in.`}
      footer={<><Button onClick={onClose}>Done</Button><Button variant="primary" onClick={() => void copy()}>Copy credentials</Button></>}>
      <dl className="space-y-2.5 rounded-md border border-line bg-surface-2 p-3.5 text-[13.5px]">
        <div><dt className="th text-[10.5px]">{ROLE_NAME[user.role]}</dt><dd className="font-medium text-fg">{user.full_name}</dd></div>
        <div><dt className="th text-[10.5px]">Username</dt><dd className="font-mono text-fg">{login}</dd></div>
        <div><dt className="th text-[10.5px]">Temporary password</dt><dd className="font-mono text-fg">{password}</dd></div>
      </dl>
      <p className="meta mt-3">This is the only time the password is shown. It is stored hashed and cannot be read back later; use “Set new password” if it is lost.</p>
    </Dialog>
  )
}
