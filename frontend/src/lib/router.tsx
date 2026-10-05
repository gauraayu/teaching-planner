'use client'

/**
 * Thin navigation layer over Next.js (next/link + next/navigation).
 *
 * Feature code imports Link / NavLink / useNavigate / useParams /
 * useSearchParams from here, so pages stay framework-agnostic and the App
 * Router only lives in src/app/.
 */
import NextLink from 'next/link'
import { useParams as useNextParams, usePathname, useRouter, useSearchParams as useNextSearchParams } from 'next/navigation'
import { useCallback, useEffect, type AnchorHTMLAttributes } from 'react'

export type LinkProps = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> & { to: string; replace?: boolean }

export function Link({ to, replace, children, ...rest }: LinkProps) {
  return (
    <NextLink href={to} replace={replace} {...rest}>
      {children}
    </NextLink>
  )
}

type NavLinkProps = Omit<LinkProps, 'className'> & {
  end?: boolean
  className?: string | ((s: { isActive: boolean }) => string)
}

/** Link that knows whether it points at the current section. */
export function NavLink({ to, end, className, ...rest }: NavLinkProps) {
  const pathname = usePathname() ?? ''
  const isActive = end ? pathname === to : pathname === to || pathname.startsWith(`${to}/`)
  return (
    <Link to={to} aria-current={isActive ? 'page' : undefined} className={typeof className === 'function' ? className({ isActive }) : className} {...rest} />
  )
}

type NavigateOptions = { replace?: boolean }

export function useNavigate() {
  const router = useRouter()
  return useCallback(
    (to: string, opts?: NavigateOptions) => (opts?.replace ? router.replace(to) : router.push(to)),
    [router],
  )
}

/** Client-side redirect element. */
export function Navigate({ to, replace }: { to: string; replace?: boolean }) {
  const navigate = useNavigate()
  useEffect(() => {
    navigate(to, { replace })
  }, [navigate, to, replace])
  return null
}

export function useParams<T extends Record<string, string> = Record<string, string>>(): Partial<T> {
  return (useNextParams() ?? {}) as Partial<T>
}

export function useLocation() {
  return { pathname: usePathname() ?? '/' }
}

/** Returns [params, setParams] like the familiar tuple API, backed by the URL. */
export function useSearchParams(): [URLSearchParams, (next: Record<string, string>, opts?: NavigateOptions) => void] {
  const params = useNextSearchParams()
  const pathname = usePathname()
  const router = useRouter()
  const current = new URLSearchParams(params?.toString() ?? '')
  const set = useCallback(
    (next: Record<string, string>, opts?: NavigateOptions) => {
      const url = `${pathname}?${new URLSearchParams(next).toString()}`
      if (opts?.replace) router.replace(url, { scroll: false })
      else router.push(url, { scroll: false })
    },
    [pathname, router],
  )
  return [current, set]
}

