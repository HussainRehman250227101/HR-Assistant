import { useState, type FormEvent, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useForgotPassword, useResetPassword } from '../api/hooks'
import { Alert, Button, ErrorAlert, Field, Input } from '../components/ui'

function Shell({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 p-4">
      <div className="w-full max-w-sm space-y-4 rounded-lg bg-white p-6 shadow ring-1 ring-slate-200">
        <div>
          <h1 className="text-lg font-semibold text-slate-900">{title}</h1>
          <p className="text-sm text-slate-500">{subtitle}</p>
        </div>
        {children}
        <div className="text-center text-sm"><Link to="/login" className="text-indigo-700 hover:underline">Back to sign in</Link></div>
      </div>
    </div>
  )
}

/** For every role: administrators, hiring managers and recruiters. */
export function ForgotPasswordPage() {
  const forgot = useForgotPassword()
  const [email, setEmail] = useState('')
  const submit = (e: FormEvent) => { e.preventDefault(); forgot.mutate(email) }
  return (
    <Shell title="Forgot your password?" subtitle="Enter your account email and we will send you a reset link.">
      {forgot.isSuccess ? (
        <Alert tone="success">{forgot.data.detail} Check your inbox; the link is valid for one hour.</Alert>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <ErrorAlert error={forgot.error} />
          <Field label="Email"><Input type="email" required autoFocus autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
          <Button type="submit" loading={forgot.isPending} className="w-full">Send reset link</Button>
        </form>
      )}
    </Shell>
  )
}

export function ResetPasswordPage() {
  const [params] = useSearchParams()
  const uid = params.get('uid') ?? ''
  const token = params.get('token') ?? ''
  const reset = useResetPassword()
  const [form, setForm] = useState({ new_password: '', new_password_confirm: '' })
  const submit = (e: FormEvent) => { e.preventDefault(); reset.mutate({ uid, token, ...form }) }
  return (
    <Shell title="Choose a new password" subtitle="Pick a strong password you do not use anywhere else.">
      {!uid || !token ? (
        <Alert>This reset link is incomplete. Request a new one from the sign-in page.</Alert>
      ) : reset.isSuccess ? (
        <Alert tone="success">{reset.data.detail}</Alert>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <ErrorAlert error={reset.error} />
          <Field label="New password"><Input type="password" required autoFocus autoComplete="new-password" value={form.new_password} onChange={(e) => setForm({ ...form, new_password: e.target.value })} /></Field>
          <Field label="Confirm new password"><Input type="password" required autoComplete="new-password" value={form.new_password_confirm} onChange={(e) => setForm({ ...form, new_password_confirm: e.target.value })} /></Field>
          <Button type="submit" loading={reset.isPending} className="w-full">Reset password</Button>
        </form>
      )}
    </Shell>
  )
}
