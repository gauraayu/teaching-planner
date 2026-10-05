import type { ReactNode } from 'react'
import { Navigate } from '@/lib/router'
import { PageLoading } from '@/components/feedback/States'
import type { Role } from '@/types/domain'
import { HOME_BY_ROLE, useAuth } from './AuthContext'
import { ChangePasswordDialog } from './ChangePasswordDialog'

/** Route guard. Roles here only decide navigation; every API call is authorised server-side. */
export function RequireRole({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { session, status } = useAuth()
  if (status === 'loading') return <PageLoading />
  if (!session) return <Navigate to="/login" replace />
  if (!roles.includes(session.role)) return <Navigate to={HOME_BY_ROLE[session.role]} replace />
  // First sign-in with the temporary password the administrator set: nothing else loads (the API refuses it too)
  // until the person has chosen their own password.
  if (session.must_change_password) {
    return (
      <div className="min-h-screen bg-deep">
        <ChangePasswordDialog open forced onClose={() => {}} />
      </div>
    )
  }
  return <>{children}</>
}
