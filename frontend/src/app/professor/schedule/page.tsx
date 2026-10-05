'use client'

import { Suspense } from 'react'
import { MySchedulePage } from '@/features/professor/MySchedulePage'

export default function Page() {
  return (
    <Suspense>
      <MySchedulePage />
    </Suspense>
  )
}
