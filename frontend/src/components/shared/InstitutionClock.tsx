'use client'

import { fmt } from '@/lib/status'
import { useInstNow } from '@/lib/date-time/institution'
import { cn } from '@/utils/cn'

/** Live institution time, ticking every second. Display only - stored timestamps always come from the server. */
export function InstitutionClock({ className, showDate = true, compact }: { className?: string; showDate?: boolean; compact?: boolean }) {
  const now = useInstNow(1000)
  const h12 = now.h % 12 || 12
  const time = `${String(h12).padStart(2, '0')}:${String(now.m).padStart(2, '0')}:${String(now.s).padStart(2, '0')} ${now.h < 12 ? 'AM' : 'PM'}`
  return (
    <span className={cn('tnum inline-flex items-baseline gap-2 whitespace-nowrap', className)} title="Institution time" suppressHydrationWarning>
      <span className={compact ? 'text-[12.5px] font-medium text-fg' : 'text-[15px] font-semibold text-fg'} suppressHydrationWarning>{time}</span>
      {showDate && <span className="text-[12px] text-fg-label" suppressHydrationWarning>{fmt.weekday(now.date)}, {fmt.date(now.date)}</span>}
    </span>
  )
}
