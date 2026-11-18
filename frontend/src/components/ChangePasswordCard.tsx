import { useState, type FormEvent } from 'react'
import { useChangePassword } from '../api/hooks'
import { Alert, Button, Card, ErrorAlert, Field, Input } from './ui'

const EMPTY = { current_password: '', new_password: '', new_password_confirm: '' }

/** Lets the signed-in user change their own password (recruiters get an initial one from HR). */
export function ChangePasswordCard() {
  const change = useChangePassword()
  const [form, setForm] = useState(EMPTY)
  const [done, setDone] = useState(false)
  const set = (key: keyof typeof EMPTY) => (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [key]: e.target.value }))

  function submit(e: FormEvent) {
    e.preventDefault()
    setDone(false)
    change.mutate(form, { onSuccess: () => { setDone(true); setForm(EMPTY) } })
  }

  return (
    <Card title="Change my password">
      <form onSubmit={submit} className="grid max-w-xl gap-4">
        <Field label="Current password"><Input required type="password" autoComplete="current-password" value={form.current_password} onChange={set('current_password')} /></Field>
        <Field label="New password"><Input required type="password" autoComplete="new-password" value={form.new_password} onChange={set('new_password')} /></Field>
        <Field label="Confirm new password"><Input required type="password" autoComplete="new-password" value={form.new_password_confirm} onChange={set('new_password_confirm')} /></Field>
        <ErrorAlert error={change.error} />
        {done && <Alert tone="success">Your password was changed.</Alert>}
        <div><Button type="submit" loading={change.isPending}>Change password</Button></div>
      </form>
    </Card>
  )
}
