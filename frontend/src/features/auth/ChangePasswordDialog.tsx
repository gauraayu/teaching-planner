import { useState } from 'react'
import { InlineAlert, useToast } from '@/components/feedback/States'
import { FormField, Input } from '@/components/forms/Fields'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { errorMessage } from '@/services/api'
import { useAuth } from './AuthContext'

export const PASSWORD_MIN = 8

/**
 * Change the signed-in user's password. With `forced` (first sign-in with the temporary password
 * the administrator set) the dialog cannot be dismissed - the only other way out is to sign out.
 */
export function ChangePasswordDialog({ open, onClose, forced }: { open: boolean; onClose: () => void; forced?: boolean }) {
  const { changePassword, logout } = useAuth()
  const toast = useToast()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [again, setAgain] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [touched, setTouched] = useState(false)

  const tooShort = next.length > 0 && next.length < PASSWORD_MIN
  const mismatch = again.length > 0 && next !== again
  const ready = current && next.length >= PASSWORD_MIN && next === again

  const close = () => {
    setCurrent(''); setNext(''); setAgain(''); setError(null); setTouched(false)
    onClose()
  }
  const submit = async (e?: React.FormEvent) => {
    e?.preventDefault()
    setTouched(true)
    if (!ready) return
    setBusy(true)
    setError(null)
    try {
      await changePassword(current, next)
      toast('success', 'Password changed.')
      close()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog
      open={open}
      onClose={forced ? () => {} : close}
      size="sm"
      title={forced ? 'Set your own password' : 'Change password'}
      description={forced ? 'You signed in with a temporary password. Choose a new one to continue.' : undefined}
      footer={
        <>
          {forced ? <Button onClick={logout}>Sign out</Button> : <Button onClick={close} disabled={busy}>Cancel</Button>}
          <Button variant="primary" loading={busy} onClick={() => void submit()}>Save password</Button>
        </>
      }
    >
      <form onSubmit={submit} noValidate className="space-y-4">
        {error && <InlineAlert tone="danger">{error}</InlineAlert>}
        <FormField label={forced ? 'Temporary password' : 'Current password'} required error={touched && !current ? 'Enter your current password.' : undefined}>
          <Input type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} data-autofocus />
        </FormField>
        <FormField label="New password" required hint={`At least ${PASSWORD_MIN} characters.`} error={tooShort || (touched && !next) ? `Use at least ${PASSWORD_MIN} characters.` : undefined}>
          <Input type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} invalid={tooShort} />
        </FormField>
        <FormField label="Confirm new password" required error={mismatch ? 'The two passwords do not match.' : undefined}>
          <Input type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} invalid={mismatch} />
        </FormField>
        <button type="submit" className="hidden" />
      </form>
    </Dialog>
  )
}
