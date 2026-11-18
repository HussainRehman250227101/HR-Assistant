import { useState, type FormEvent } from 'react'
import { useUpdateRecruiter } from '../api/hooks'
import { Button, ErrorAlert, Field, Input, Modal } from '../components/ui'
import type { User } from '../lib/types'

function EditForm({ recruiter, onClose }: { recruiter: User; onClose: () => void }) {
  const update = useUpdateRecruiter()
  const [form, setForm] = useState({
    first_name: recruiter.first_name, last_name: recruiter.last_name, email: recruiter.email,
    job_title: recruiter.job_title, department: recruiter.department,
  })
  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [key]: e.target.value }))
  const submit = (e: FormEvent) => {
    e.preventDefault()
    update.mutate({ id: recruiter.id, data: form }, { onSuccess: onClose })
  }
  return (
    <form onSubmit={submit} className="grid gap-4 md:grid-cols-2">
      <Field label="First name"><Input required value={form.first_name} onChange={set('first_name')} /></Field>
      <Field label="Last name"><Input value={form.last_name} onChange={set('last_name')} /></Field>
      <Field label="Email" hint="Interview notices and password reset links are sent here."><Input required type="email" value={form.email} onChange={set('email')} /></Field>
      <Field label="Username" hint="The username cannot be changed."><Input disabled value={recruiter.username} /></Field>
      <Field label="Job title"><Input value={form.job_title} onChange={set('job_title')} /></Field>
      <Field label="Department"><Input value={form.department} onChange={set('department')} /></Field>
      <div className="space-y-3 md:col-span-2">
        <ErrorAlert error={update.error} />
        <div className="flex gap-2">
          <Button type="submit" loading={update.isPending}>Save changes</Button>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </form>
  )
}

/** Edit a recruiter's details (HR Administrator or Hiring Manager). The form is keyed so it always starts from the saved values. */
export function EditRecruiterModal({ recruiter, onClose }: { recruiter: User | null; onClose: () => void }) {
  return (
    <Modal open={recruiter !== null} title={recruiter ? `Edit ${recruiter.full_name || recruiter.username}` : ''} onClose={onClose} wide>
      {recruiter && <EditForm recruiter={recruiter} onClose={onClose} />}
    </Modal>
  )
}
