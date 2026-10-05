'use client'

import { PageLoading } from '@/components/feedback/States'
import { HOME_BY_ROLE, useAuth } from '@/features/auth/AuthContext'
import { Navigate } from '@/lib/router'

export default function Home() {
  const { session, status } = useAuth()
  if (status === 'loading') return <PageLoading />
  return <Navigate to={session ? HOME_BY_ROLE[session.role] : '/login'} replace />
}
