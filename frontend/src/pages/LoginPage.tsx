import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { Button, ErrorAlert, Field, Input } from '../components/ui'

export function LoginPage() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to="/" replace />

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(username, password)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 p-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-lg bg-white p-6 shadow ring-1 ring-slate-200">
        <div>
          <h1 className="text-lg font-semibold text-slate-900">HR Assistant</h1>
          <p className="text-sm text-slate-500">Sign in with your HR account.</p>
        </div>
        <ErrorAlert error={error} />
        <Field label="Username">
          <Input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required autoFocus />
        </Field>
        <Field label="Password">
          <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
        </Field>
        <Button type="submit" loading={busy} className="w-full">
          Sign in
        </Button>
        <div className="text-center text-sm">
          <Link to="/forgot-password" className="text-indigo-700 hover:underline">Forgot your password?</Link>
        </div>
        <Link
          to="/docs"
          className="group flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3.5 py-3 text-left transition-colors hover:border-indigo-300 hover:bg-indigo-50"
        >
          <span>
            <span className="block text-sm font-medium text-slate-900">Documentation</span>
            <span className="block text-xs text-slate-500">How the assistant works: architecture, agents and controls</span>
          </span>
          <span aria-hidden className="text-indigo-600 transition-transform group-hover:translate-x-0.5">→</span>
        </Link>
      </form>
    </div>
  )
}
