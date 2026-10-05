'use client'

import { Suspense, type ReactNode } from 'react'
import { PageLoading, ToastProvider } from '@/components/feedback/States'
import { AuthProvider } from '@/features/auth/AuthContext'

export function Providers({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <ToastProvider>
        <Suspense fallback={<PageLoading />}>{children}</Suspense>
      </ToastProvider>
    </AuthProvider>
  )
}
