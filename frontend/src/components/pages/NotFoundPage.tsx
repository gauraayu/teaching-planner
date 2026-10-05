import { ButtonLink } from '@/components/ui/Button'

export function NotFoundPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-bg px-6 text-center">
      <p className="text-[12px] font-semibold tracking-widest text-fg-muted uppercase">Error 404</p>
      <h1 className="mt-2 text-xl font-semibold text-fg">This page does not exist</h1>
      <p className="meta mt-1">The link may be outdated, or you may not have access to it.</p>
      <ButtonLink to="/" variant="primary" className="mt-5">
        Go to my dashboard
      </ButtonLink>
    </div>
  )
}
