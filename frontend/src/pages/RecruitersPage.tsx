import { useState, type FormEvent } from 'react'
import { useCreateRecruiter, useDeleteRecruiter, useUpdateRecruiter, useUsers } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { DeactivateRecruiterModal } from './RemoveRecruiterModal'
import { EditRecruiterModal } from './EditRecruiterModal'
import type { User } from '../lib/types'
import { Alert, Badge, Button, Card, Empty, ErrorAlert, Field, Input, Loading, PageHeader, Table, Td } from '../components/ui'

const EMPTY = { first_name: '', last_name: '', username: '', email: '', job_title: 'HR Recruiter', department: '', password: '', password_confirm: '' }

/** HR Administrators and Hiring Managers add HR Recruiters (interviewers) here. The role is fixed by the backend. */
export function RecruitersPage() {
  const { isAdmin } = useAuth()
  const [removing, setRemoving] = useState<User | null>(null)
  const [editing, setEditing] = useState<User | null>(null)
  const recruiters = useUsers('RECRUITER', true, true)
  const update = useUpdateRecruiter()
  const del = useDeleteRecruiter()
  const create = useCreateRecruiter()
  const [form, setForm] = useState(EMPTY)
  const [added, setAdded] = useState<string | null>(null)
  const set = (key: keyof typeof EMPTY) => (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [key]: e.target.value }))

  function submit(e: FormEvent) {
    e.preventDefault()
    setAdded(null)
    create.mutate(form, {
      onSuccess: (user) => {
        setAdded(user.full_name || user.username)
        setForm(EMPTY)
      },
    })
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Recruiters" subtitle="Add HR Recruiters. They see only the candidates assigned to them and manage their own availability." />
      <Card title="Add a recruiter">
        <form onSubmit={submit} className="grid gap-4 md:grid-cols-2">
          <Field label="First name"><Input required value={form.first_name} onChange={set('first_name')} /></Field>
          <Field label="Last name"><Input value={form.last_name} onChange={set('last_name')} /></Field>
          <Field label="Email" hint="Interview assignment notices are sent here."><Input required type="email" value={form.email} onChange={set('email')} /></Field>
          <Field label="Username"><Input required autoComplete="off" value={form.username} onChange={set('username')} /></Field>
          <Field label="Job title"><Input value={form.job_title} onChange={set('job_title')} /></Field>
          <Field label="Department"><Input value={form.department} onChange={set('department')} /></Field>
          <Field label="Initial password" hint="Share it with the recruiter securely. It is never shown again. They can change it from My Schedule.">
            <Input required type="password" autoComplete="new-password" value={form.password} onChange={set('password')} />
          </Field>
          <Field label="Confirm initial password">
            <Input required type="password" autoComplete="new-password" value={form.password_confirm} onChange={set('password_confirm')} />
          </Field>
          <div className="md:col-span-2 space-y-3">
            <ErrorAlert error={create.error} />
            {added && <Alert tone="success">{added} was added as an HR Recruiter.</Alert>}
            <Button type="submit" loading={create.isPending}>Add recruiter</Button>
          </div>
        </form>
      </Card>
      <Card title="Current recruiters">
        <ErrorAlert error={recruiters.error ?? update.error ?? del.error} />
        {recruiters.isLoading ? <Loading /> : !recruiters.data?.length ? <Empty>No recruiters yet.</Empty> : (
          <Table head={['Name', 'Email', 'Username', 'Job title', 'Department', 'Status', '']}>
            {recruiters.data.map((u) => (
              <tr key={u.id}>
                <Td className="font-medium">{u.full_name || u.username}</Td>
                <Td>{u.email}</Td>
                <Td>{u.username}</Td>
                <Td>{u.job_title || '-'}</Td>
                <Td>{u.department || '-'}</Td>
                <Td><Badge tone={u.is_active ? 'green' : 'gray'} label={u.is_active ? 'Active' : 'Inactive'} /></Td>
                <Td className="space-x-1 whitespace-nowrap">
                  <Button size="sm" variant="ghost" onClick={() => setEditing(u)}>Edit</Button>
                  {isAdmin && (u.is_active
                    ? <Button size="sm" variant="ghost" onClick={() => setRemoving(u)}>Deactivate</Button>
                    : <Button size="sm" variant="ghost" loading={update.isPending} onClick={() => update.mutate({ id: u.id, data: { is_active: true } })}>Activate</Button>)}
                  {isAdmin && (
                    <Button size="sm" variant="ghost" className="text-rose-700" loading={del.isPending}
                      onClick={() => { if (confirm(`Delete ${u.full_name || u.username} permanently? This cannot be undone. Accounts with interview history cannot be deleted; deactivate them instead.`)) del.mutate(u.id) }}>
                      Delete
                    </Button>
                  )}
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <DeactivateRecruiterModal key={`d${removing?.id ?? 'none'}`} recruiter={removing} onClose={() => setRemoving(null)} />
      <EditRecruiterModal key={`e${editing?.id ?? 'none'}`} recruiter={editing} onClose={() => setEditing(null)} />
    </div>
  )
}
