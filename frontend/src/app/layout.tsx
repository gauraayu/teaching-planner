import '@fontsource-variable/inter'
import './globals.css'
import type { Metadata, Viewport } from 'next'
import type { ReactNode } from 'react'
import { Providers } from './providers'

export const metadata: Metadata = {
  title: { default: 'Academic Teaching Plan Portal', template: '%s · Teaching Plan Portal' },
  description: 'Plan, execute, track and verify academic delivery from one centralized system.',
  icons: { icon: '/favicon.svg' },
}

export const viewport: Viewport = { themeColor: '#020805', width: 'device-width', initialScale: 1 }

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}
