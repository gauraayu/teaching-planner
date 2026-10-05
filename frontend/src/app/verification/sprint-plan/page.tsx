'use client'

import { Suspense } from 'react'
import { SprintSheetPage } from '@/features/sprint/SprintSheetPage'

export default function Page() {
  return (
    <Suspense>
      <SprintSheetPage variant="verification" />
    </Suspense>
  )
}
