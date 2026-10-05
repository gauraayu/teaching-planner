import { cloneElement, forwardRef, isValidElement, useId, type InputHTMLAttributes, type ReactElement, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react'
import { cn } from '@/utils/cn'

/** Label is always visible; placeholder is never the only label. */
export function FormField({
  label,
  hint,
  error,
  required,
  children,
  className,
  htmlFor,
}: {
  label: ReactNode
  hint?: ReactNode
  error?: string
  required?: boolean
  children: ReactNode
  className?: string
  htmlFor?: string
}) {
  // Always associate the label with its control, even when the caller forgot an id.
  const auto = useId()
  const child = isValidElement(children) ? (children as ReactElement<{ id?: string; 'aria-describedby'?: string }>) : null
  const id = htmlFor ?? child?.props.id ?? auto
  // An explicit htmlFor means the caller already put that id on the real control (which may be nested).
  const control = child && !child.props.id && !htmlFor ? cloneElement(child, { id }) : children
  return (
    <div className={className}>
      <label className="label" htmlFor={id}>
        {label}
        {required && <span className="ml-0.5 text-danger" aria-hidden>*</span>}
      </label>
      {control}
      {error ? (
        <p className="mt-1 text-[12.5px] text-danger" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p className="meta mt-1">{hint}</p>
      ) : null}
    </div>
  )
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }>(function Input(
  { className, invalid, ...rest },
  ref,
) {
  return <input ref={ref} aria-invalid={invalid || undefined} className={cn('field', invalid && 'field-error', className)} {...rest} />
})

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement> & { invalid?: boolean }>(function Select(
  { className, invalid, children, ...rest },
  ref,
) {
  return (
    <select ref={ref} aria-invalid={invalid || undefined} className={cn('field pr-8', invalid && 'field-error', className)} {...rest}>
      {children}
    </select>
  )
})

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement> & { invalid?: boolean }>(function Textarea(
  { className, invalid, rows = 3, ...rest },
  ref,
) {
  return (
    <textarea
      ref={ref}
      rows={rows}
      aria-invalid={invalid || undefined}
      className={cn('field h-auto py-2 leading-relaxed', invalid && 'field-error', className)}
      {...rest}
    />
  )
})

export const Checkbox = forwardRef<HTMLInputElement, Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> & { label: ReactNode; description?: ReactNode }>(
  function Checkbox({ label, description, className, id, ...rest }, ref) {
    const auto = useId()
    const cid = id ?? auto
    return (
      <label htmlFor={cid} className={cn('flex cursor-pointer items-start gap-2.5 text-sm text-fg', rest.disabled && 'cursor-not-allowed opacity-70', className)}>
        <input
          ref={ref}
          id={cid}
          type="checkbox"
          className="mt-0.5 h-4 w-4 shrink-0 cursor-pointer rounded-sm border-line-hover accent-primary disabled:cursor-not-allowed"
          {...rest}
        />
        <span>
          {label}
          {description && <span className="meta block">{description}</span>}
        </span>
      </label>
    )
  },
)

/** Segmented single-choice control (radio group semantics). */
export function Segmented<T extends string>({
  value,
  onChange,
  options,
  name,
  size = 'md',
  disabled,
  ariaLabel,
}: {
  value: T | null | undefined
  onChange: (v: T) => void
  options: { value: T; label: ReactNode; count?: number }[]
  name?: string
  size?: 'sm' | 'md'
  disabled?: boolean
  ariaLabel?: string
}) {
  const auto = useId()
  return (
    <div role="radiogroup" aria-label={ariaLabel} className="inline-flex max-w-full overflow-x-auto rounded-md border border-line-strong bg-surface p-0.5 scroll-thin">
      {options.map((o) => {
        const active = o.value === value
        return (
          <label
            key={o.value}
            className={cn(
              'relative inline-flex cursor-pointer items-center gap-1.5 rounded-[4px] font-medium whitespace-nowrap transition-colors',
              size === 'sm' ? 'h-7 px-2.5 text-[12.5px]' : 'h-8 px-3 text-[13px]',
              active ? 'bg-primary-soft text-primary ring-1 ring-primary-border ring-inset' : 'text-fg-secondary hover:bg-surface-3 hover:text-fg',
              disabled && 'cursor-not-allowed opacity-60',
            )}
          >
            <input
              type="radio"
              className="sr-only"
              name={name ?? auto}
              value={o.value}
              checked={active}
              disabled={disabled}
              onChange={() => onChange(o.value)}
            />
            {o.label}
            {o.count !== undefined && (
              <span className={cn('tnum rounded-sm px-1 text-[11px]', active ? 'bg-primary/15 text-primary' : 'bg-surface-3 text-fg-secondary')}>{o.count}</span>
            )}
          </label>
        )
      })}
    </div>
  )
}
