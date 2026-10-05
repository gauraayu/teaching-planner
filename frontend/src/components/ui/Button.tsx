import { Loader2 } from 'lucide-react'
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { Link, type LinkProps } from '@/lib/router'
import { cn } from '@/utils/cn'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'success' | 'link'
type Size = 'sm' | 'md' | 'lg' | 'icon'

const VARIANTS: Record<Variant, string> = {
  // The one bright fill on a screen: dark text on emerald.
  primary: 'bg-primary text-on-primary font-semibold hover:bg-primary-hover active:bg-primary disabled:bg-primary-muted/40 disabled:text-on-primary/70',
  secondary: 'border border-line-strong bg-transparent text-fg-soft hover:border-primary hover:text-primary active:bg-primary-soft disabled:border-line disabled:text-fg-faint',
  ghost: 'text-fg-secondary hover:bg-surface-3 hover:text-fg disabled:text-fg-faint',
  // Destructive actions are never green.
  danger: 'border border-danger-border bg-transparent text-danger hover:border-danger hover:bg-danger-soft disabled:text-danger/40',
  success: 'bg-primary text-on-primary font-semibold hover:bg-primary-hover disabled:bg-primary-muted/40 disabled:text-on-primary/70',
  link: 'text-primary hover:text-primary-hover hover:underline underline-offset-2 px-0 h-auto',
}
const SIZES: Record<Size, string> = {
  sm: 'h-8 px-2.5 text-[13px] gap-1.5',
  md: 'h-9 px-3.5 text-sm gap-2',
  lg: 'h-11 px-5 text-[15px] gap-2',
  icon: 'h-8 w-8 justify-center',
}

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant
  size?: Size
  loading?: boolean
  icon?: ReactNode
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'md', loading, icon, className, children, disabled, type = 'button', ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        'inline-flex shrink-0 items-center rounded-md font-medium whitespace-nowrap transition-colors disabled:cursor-not-allowed',
        VARIANTS[variant],
        variant === 'link' ? 'text-sm' : SIZES[size],
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  )
})

export function buttonClass(variant: Variant = 'secondary', size: Size = 'md', className?: string) {
  return cn(
    'inline-flex shrink-0 items-center rounded-md font-medium whitespace-nowrap transition-colors',
    VARIANTS[variant],
    variant === 'link' ? 'text-sm' : SIZES[size],
    className,
  )
}

/** Navigation that looks like a button (avoids nesting <button> inside <a>). */
export function ButtonLink({ variant = 'secondary', size = 'md', icon, className, children, ...rest }: LinkProps & { variant?: Variant; size?: Size; icon?: ReactNode }) {
  return (
    <Link className={buttonClass(variant, size, className)} {...rest}>
      {icon}
      {children}
    </Link>
  )
}
