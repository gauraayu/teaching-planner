import { ArrowRight, ClipboardCheck, Eye, EyeOff, GraduationCap, Radio, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { InlineAlert } from '@/components/feedback/States'
import { BrandMark } from '@/components/layout/AppShell'
import { Button } from '@/components/ui/Button'
import { useApi } from '@/hooks/useApi'
import { Navigate, useNavigate } from '@/lib/router'
import { errorMessage } from '@/services/api'
import { ROLE_NAME, type Role } from '@/types/domain'
import { cn } from '@/utils/cn'
import { HOME_BY_ROLE, useAuth } from './AuthContext'

/**
 * The four portals. The tabs only organise the screen: the account's role is read from the database
 * by the server, and the person lands in the portal that role belongs to.
 */
const PORTALS: { value: Role; icon: typeof ShieldCheck; title: string; text: string }[] = [
  { value: 'ADMIN', icon: ShieldCheck, title: 'Administrator Portal', text: 'Create accounts, build the semester sprint plan, allocate professors and publish weekly revisions.' },
  { value: 'PROFESSOR', icon: GraduationCap, title: 'Professor Portal', text: 'See the classes allocated to you, start and end them, record what was covered and submit for verification.' },
  { value: 'CL_CH', icon: ClipboardCheck, title: 'CL/CH Verification Portal', text: 'Review professor lecture records inside your assigned scope, verify them or request a correction.' },
  { value: 'OM', icon: Radio, title: 'OM Operations Portal', text: 'Record professor entry and exit for scheduled classes and give the final verification after CL/CH.' },
]

type DemoAccount = { role: Role; username: string; password: string }

export function LoginPage() {
  const { login, session } = useAuth()
  const navigate = useNavigate()
  const config = useApi<{ demo_accounts: DemoAccount[] }>('/auth/config')
  const [portal, setPortal] = useState<Role>('ADMIN')
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [touched, setTouched] = useState(false)

  if (session && !busy) return <Navigate to={HOME_BY_ROLE[session.role]} replace />

  const signIn = async (id: string, pw: string) => {
    setBusy(true)
    setError(null)
    try {
      const s = await login(id.trim(), pw)
      // The portal that opens is decided by the account's role on the server, whichever tab was selected.
      navigate(HOME_BY_ROLE[s.role], { replace: true })
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    setTouched(true)
    if (!identifier.trim() || !password) return
    void signIn(identifier, password)
  }

  const copy = PORTALS.find((p) => p.value === portal)!
  const demo = config.data?.demo_accounts.find((d) => d.role === portal)
  return (
    <div className="relative flex min-h-screen flex-col overflow-hidden bg-deep">
      {/* Atmosphere lives on this screen only; the working screens stay flat. */}
      <div className="login-atmosphere pointer-events-none absolute inset-0" aria-hidden />
      <main className="relative flex flex-1 items-center justify-center px-4 py-10">
        <div className="w-full max-w-[520px]">
          <div className="mb-8 flex items-center gap-3">
            <BrandMark className="h-10 w-10" />
            <div className="text-[11.5px] font-semibold tracking-[0.14em] text-fg-label uppercase">Academic Delivery Office</div>
          </div>
          <h1 className="text-[26px] leading-[1.15] font-semibold tracking-tight text-fg uppercase sm:text-[30px]">
            Academic Teaching Plan
            <br />
            <span className="text-primary">&amp;</span> Execution Management Portal
          </h1>
          <p className="mt-3 max-w-[440px] text-[14px] leading-relaxed text-fg-secondary">
            Plan, execute, monitor and verify academic delivery through one centralized institutional platform.
          </p>

          <div className="mt-8 rounded-lg border border-line bg-surface/90 p-5 sm:p-6">
            <div id="portal-label" className="th mb-2">Select portal</div>
            <div role="tablist" aria-labelledby="portal-label" className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {PORTALS.map((t) => {
                const active = t.value === portal
                return (
                  <button
                    key={t.value}
                    role="tab"
                    type="button"
                    aria-selected={active}
                    onClick={() => { setPortal(t.value); setError(null) }}
                    className={cn(
                      'flex h-11 items-center justify-center gap-1.5 rounded-md border text-[12.5px] font-semibold tracking-wide uppercase transition-colors',
                      active ? 'border-primary bg-primary-soft text-primary' : 'border-line-strong text-fg-secondary hover:border-line-hover hover:text-fg',
                    )}
                  >
                    <t.icon className="h-4 w-4" aria-hidden />
                    {ROLE_NAME[t.value]}
                  </button>
                )
              })}
            </div>

            <form role="tabpanel" className="mt-6" onSubmit={submit} noValidate>
              <h2 className="text-[16px] font-semibold text-fg">{copy.title}</h2>
              <p className="mt-1.5 text-[13.5px] leading-relaxed text-fg-secondary">{copy.text}</p>

              <div className="mt-5 space-y-4">
                <div>
                  <label htmlFor="identifier" className="label">Email, username or employee ID</label>
                  <input id="identifier" className={cn('field h-10', touched && !identifier.trim() && 'field-error')} autoComplete="username" autoCapitalize="none" spellCheck={false}
                    value={identifier} onChange={(e) => setIdentifier(e.target.value)} />
                  {touched && !identifier.trim() && <p className="mt-1 text-[12.5px] text-danger" role="alert">Enter your email, username or employee ID.</p>}
                </div>
                <div>
                  <label htmlFor="password" className="label">Password</label>
                  <div className="relative">
                    <input id="password" type={show ? 'text' : 'password'} className={cn('field h-10 pr-10', touched && !password && 'field-error')} autoComplete="current-password"
                      value={password} onChange={(e) => setPassword(e.target.value)} />
                    <button type="button" onClick={() => setShow((s) => !s)} aria-label={show ? 'Hide password' : 'Show password'} aria-pressed={show}
                      className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-fg-muted hover:text-fg">
                      {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                  {touched && !password && <p className="mt-1 text-[12.5px] text-danger" role="alert">Enter your password.</p>}
                </div>
              </div>

              {error && <InlineAlert tone="danger" className="mt-4">{error}</InlineAlert>}
              <Button type="submit" variant="primary" size="lg" className="mt-5 w-full justify-center" loading={busy}>
                Sign in to {ROLE_NAME[portal]} portal
                {!busy && <ArrowRight className="h-4 w-4" />}
              </Button>
              <p className="meta mt-3">Accounts are created by the administrator. Forgot your password? Ask the administrator to set a new one.</p>
            </form>
          </div>

          {demo && (
            // Shown only while DEMO_AUTH_ENABLED=true and the seeded demo accounts exist. It signs in with the real
            // password check - there is no role shortcut.
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-dashed border-line-strong px-4 py-3">
              <div className="min-w-0 text-[12.5px] text-fg-secondary">
                <span className="font-semibold text-fg-soft">Demo account</span> · <span className="font-mono text-fg-soft">{demo.username}</span> / <span className="font-mono text-fg-soft">{demo.password}</span>
              </div>
              <Button size="sm" disabled={busy} onClick={() => { setIdentifier(demo.username); setPassword(demo.password); void signIn(demo.username, demo.password) }}>
                Use demo account
              </Button>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
