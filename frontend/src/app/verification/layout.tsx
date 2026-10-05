'use client'

import type { ReactNode } from 'react'
import { AppShell } from '@/components/layout/AppShell'
import { RequireRole } from '@/features/auth/RequireRole'

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <RequireRole roles={['CL_CH']}>
      <AppShell>{children}</AppShell>
    </RequireRole>
  )
}
