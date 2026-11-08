import { useEffect, useRef, useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react'
import { errorMessage } from '../lib/api'
import { displayToIsoDate, humanize, isoToDisplayDate, maskDateInput, toneFor } from '../lib/format'

const cx = (...classes: (string | false | null | undefined)[]) => classes.filter(Boolean).join(' ')

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost' | 'success'

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-indigo-600 text-white hover:bg-indigo-700 disabled:bg-indigo-300',
  secondary: 'bg-white text-slate-700 ring-1 ring-slate-300 hover:bg-slate-50 disabled:text-slate-400',
  danger: 'bg-rose-600 text-white hover:bg-rose-700 disabled:bg-rose-300',
  success: 'bg-emerald-600 text-white hover:bg-emerald-700 disabled:bg-emerald-300',
  ghost: 'text-indigo-700 hover:bg-indigo-50 disabled:text-slate-400',
}

export function Button({
  variant = 'primary',
  loading,
  className,
  children,
  size = 'md',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; loading?: boolean; size?: 'sm' | 'md' }) {
  return (
    <button
      type="button"
      {...props}
      disabled={props.disabled || loading}
      className={cx(
        'inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors disabled:cursor-not-allowed',
        size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-3.5 py-2 text-sm',
        VARIANTS[variant],
        className,
      )}
    >
      {loading && <Spinner small />}
      {children}
    </button>
  )
}

export function Spinner({ small }: { small?: boolean }) {
  return (
    <span
      aria-label="Loading"
      className={cx('inline-block animate-spin rounded-full border-2 border-current border-r-transparent', small ? 'h-3.5 w-3.5' : 'h-6 w-6 text-indigo-600')}
    />
  )
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 p-6 text-sm text-slate-500">
      <Spinner /> {label}
    </div>
  )
}

export function Card({ title, actions, children, className }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx('rounded-lg bg-white shadow-sm ring-1 ring-slate-200', className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
          <div className="flex flex-wrap gap-2">{actions}</div>
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  )
}

const BADGE_TONES = {
  gray: 'bg-slate-100 text-slate-700 ring-slate-200',
  blue: 'bg-sky-50 text-sky-700 ring-sky-200',
  green: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  amber: 'bg-amber-50 text-amber-800 ring-amber-200',
  red: 'bg-rose-50 text-rose-700 ring-rose-200',
  purple: 'bg-violet-50 text-violet-700 ring-violet-200',
}

export function Badge({ value, label, tone }: { value?: string | null; label?: string; tone?: keyof typeof BADGE_TONES }) {
  return (
    <span className={cx('inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset', BADGE_TONES[tone ?? toneFor(value)])}>
      {label ?? humanize(value)}
    </span>
  )
}

export function Alert({ tone = 'error', children }: { tone?: 'error' | 'info' | 'warning' | 'success'; children: ReactNode }) {
  const styles = {
    error: 'bg-rose-50 text-rose-800 ring-rose-200',
    info: 'bg-sky-50 text-sky-800 ring-sky-200',
    warning: 'bg-amber-50 text-amber-900 ring-amber-200',
    success: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  }
  return <div className={cx('rounded-md px-3 py-2 text-sm ring-1', styles[tone])}>{children}</div>
}

export function ErrorAlert({ error }: { error: unknown }) {
  if (!error) return null
  return <Alert>{errorMessage(error)}</Alert>
}

export function Field({ label, hint, children, className }: { label: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <label className={cx('block text-sm', className)}>
      <span className="mb-1 block font-medium text-slate-700">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  )
}

const inputClass = 'block w-full rounded-md border-0 px-2.5 py-1.5 text-sm ring-1 ring-slate-300 ring-inset focus:ring-2 focus:ring-indigo-500 disabled:bg-slate-100'

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cx(inputClass, props.className)} />
}

/**
 * Date entry in DD/MM/YYYY (a native date input always follows the browser's locale). `value` and `onChange` use ISO
 * `YYYY-MM-DD` ('' while the text is incomplete or not a real date); the calendar button opens the native picker.
 */
export function DateInput({ value, onChange, required, className, disabled }: {
  value: string
  onChange: (iso: string) => void
  required?: boolean
  className?: string
  disabled?: boolean
}) {
  const [draft, setDraft] = useState<string | null>(null)
  const pickerRef = useRef<HTMLInputElement>(null)
  const shown = draft !== null && displayToIsoDate(draft) === value ? draft : isoToDisplayDate(value)
  const invalid = shown !== '' && displayToIsoDate(shown) === ''

  return (
    <div className={cx('relative', className)}>
      <input
        type="text" inputMode="numeric" autoComplete="off" placeholder="DD/MM/YYYY" maxLength={10}
        required={required} disabled={disabled} value={shown} title="Date as DD/MM/YYYY"
        ref={(el) => el?.setCustomValidity(invalid ? 'Enter a valid date as DD/MM/YYYY' : '')}
        onChange={(e) => { const text = maskDateInput(e.target.value); setDraft(text); onChange(displayToIsoDate(text)) }}
        className={cx(inputClass, 'pr-9')}
      />
      <button type="button" aria-label="Pick a date" tabIndex={-1} disabled={disabled}
        className="absolute inset-y-0 right-0 px-2 text-slate-500 hover:text-slate-800"
        onClick={() => { try { pickerRef.current?.showPicker() } catch { /* picker not supported: type the date */ } }}>
        <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4" aria-hidden="true">
          <path d="M6 2a1 1 0 0 1 1 1v1h6V3a1 1 0 1 1 2 0v1h1a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h1V3a1 1 0 0 1 1-1Zm-2 7v7h12V9H4Z" />
        </svg>
      </button>
      <input ref={pickerRef} type="date" tabIndex={-1} aria-hidden="true" value={value}
        onChange={(e) => { setDraft(null); onChange(e.target.value) }}
        className="pointer-events-none absolute right-0 bottom-0 h-0 w-0 opacity-0" />
    </div>
  )
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea rows={3} {...props} className={cx(inputClass, props.className)} />
}

export function Select({ options, ...props }: SelectHTMLAttributes<HTMLSelectElement> & { options: { value: string; label: string }[] }) {
  return (
    <select {...props} className={cx(inputClass, 'pr-8', props.className)}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  )
}

export function Modal({ open, title, onClose, children, wide }: { open: boolean; title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-4 pt-16" onMouseDown={onClose}>
      <div className={cx('w-full rounded-lg bg-white shadow-xl', wide ? 'max-w-3xl' : 'max-w-lg')} onMouseDown={(e) => e.stopPropagation()}>
        <header className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
          <h3 className="font-semibold text-slate-900">{title}</h3>
          <button className="text-slate-400 hover:text-slate-600" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>
        <div className="p-5">{children}</div>
      </div>
    </div>
  )
}

export function PageHeader({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{title}</h1>
        {subtitle && <div className="mt-1 text-sm text-slate-500">{subtitle}</div>}
      </div>
      <div className="flex flex-wrap gap-2">{actions}</div>
    </div>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-sm text-slate-500">{children}</p>
}

export function Table({ head, children }: { head: ReactNode[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead>
          <tr>
            {head.map((h, i) => (
              <th key={i} className="px-3 py-2 text-left text-xs font-semibold tracking-wide text-slate-500 uppercase">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">{children}</tbody>
      </table>
    </div>
  )
}

export function Td({ children, className }: { children?: ReactNode; className?: string }) {
  return <td className={cx('px-3 py-2 align-top', className)}>{children}</td>
}

export function KeyValue({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
      {items.map(([k, v]) => (
        <div key={k}>
          <dt className="text-xs font-medium text-slate-500 uppercase">{k}</dt>
          <dd className="mt-0.5 break-words text-slate-800">{v || '—'}</dd>
        </div>
      ))}
    </dl>
  )
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { value: T; label: ReactNode }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="mb-4 flex flex-wrap gap-1 border-b border-slate-200">
      {tabs.map((t) => (
        <button
          key={t.value}
          type="button"
          onClick={() => onChange(t.value)}
          className={cx(
            '-mb-px border-b-2 px-3 py-2 text-sm font-medium',
            value === t.value ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-500 hover:text-slate-700',
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}
