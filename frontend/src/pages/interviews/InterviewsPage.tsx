import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAddAvailability, useAvailability, useDeleteAvailability, useInterviews, useUsers } from '../../api/hooks'
import { useAuth } from '../../auth/AuthContext'
import { Alert, Badge, Button, Card, Empty, ErrorAlert, Field, Input, Loading, PageHeader, Select, Table, Td } from '../../components/ui'
import { BROWSER_TZ, COMMON_TIMEZONES, formatInZone, humanize } from '../../lib/format'

function AvailabilityManager() {
  const { user, isRecruiter } = useAuth()
  const users = useUsers(undefined, isRecruiter)
  const [interviewer, setInterviewer] = useState<number | undefined>(isRecruiter ? undefined : user?.id)
  const slots = useAvailability(interviewer)
  const add = useAddAvailability()
  const remove = useDeleteAvailability()
  const [form, setForm] = useState({ date: new Date().toISOString().slice(0, 10), start_time: '09:00', end_time: '13:00', timezone: 'Asia/Karachi' })

  return (
    <Card title="Interviewer availability (internal calendar)">
      <div className="space-y-4">
        <Alert tone="info">No Google/Microsoft calendar is connected. This internal availability calendar is the scheduling source; booked interviews are excluded automatically.</Alert>
        <ErrorAlert error={add.error ?? remove.error} />
        <div className="flex flex-wrap items-end gap-2">
          {isRecruiter && (
            <Field label="Interviewer">
              <Select value={interviewer ? String(interviewer) : ''} onChange={(e) => setInterviewer(e.target.value ? Number(e.target.value) : undefined)}
                options={[{ value: '', label: 'All interviewers (view)' }, ...(users.data ?? []).map((u) => ({ value: String(u.id), label: u.full_name || u.username }))]} />
            </Field>
          )}
          <Field label="Date"><Input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} /></Field>
          <Field label="From"><Input type="time" value={form.start_time} onChange={(e) => setForm({ ...form, start_time: e.target.value })} /></Field>
          <Field label="To"><Input type="time" value={form.end_time} onChange={(e) => setForm({ ...form, end_time: e.target.value })} /></Field>
          <Field label="Time zone"><Select value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value })} options={COMMON_TIMEZONES.map((z) => ({ value: z, label: z }))} /></Field>
          <Button loading={add.isPending} disabled={isRecruiter && !interviewer} title={isRecruiter && !interviewer ? 'Choose an interviewer' : ''}
            onClick={() => add.mutate({ ...form, interviewer: interviewer ?? user?.id })}>Add window</Button>
        </div>
        {slots.isLoading ? <Loading /> : !slots.data?.length ? <Empty>No upcoming availability.</Empty> : (
          <Table head={['Interviewer', 'From', 'To', 'Entered in', '']}>
            {slots.data.map((s) => (
              <tr key={s.public_id}>
                <Td>{s.interviewer_name}</Td>
                <Td>{formatInZone(s.start, s.timezone, false)}</Td>
                <Td>{formatInZone(s.end, s.timezone, false)}</Td>
                <Td className="text-xs">{s.timezone}</Td>
                <Td><Button size="sm" variant="ghost" onClick={() => remove.mutate(s.public_id)}>Remove</Button></Td>
              </tr>
            ))}
          </Table>
        )}
      </div>
    </Card>
  )
}

export function InterviewsPage() {
  const { isRecruiter } = useAuth()
  const [status, setStatus] = useState('ACTIVE')
  const interviews = useInterviews({ status: status || undefined, mine: isRecruiter ? undefined : '1' })
  return (
    <>
      <PageHeader title="Interviews" subtitle="Scheduling coordination, confirmed interviews and interviewer availability (FR-09–FR-11)." />
      <div className="space-y-6">
        <Card>
          <div className="mb-4 max-w-xs">
            <Select value={status} onChange={(e) => setStatus(e.target.value)} options={[
              { value: 'ACTIVE', label: 'Active' }, { value: 'NEEDS_HR_COORDINATION', label: 'Needs HR coordination' },
              { value: 'PROPOSED', label: 'Slots proposed' }, { value: 'SLOT_CONFIRMED', label: 'Slot confirmed' },
              { value: 'SCHEDULED', label: 'Scheduled' }, { value: 'CANCELLED', label: 'Cancelled' }, { value: '', label: 'All' }]} />
          </div>
          <ErrorAlert error={interviews.error} />
          {interviews.isLoading ? <Loading /> : !interviews.data?.length ? <Empty>No interviews.</Empty> : (
            <Table head={['Candidate', 'Role', 'Interviewer', 'Status', 'When (candidate time)', 'Your time']}>
              {interviews.data.map((i) => (
                <tr key={i.public_id} className="hover:bg-slate-50">
                  <Td><Link to={`/candidates/${i.candidate_reference}?tab=interview`} className="font-medium text-indigo-700 hover:underline">{i.candidate_name || 'Candidate'}</Link></Td>
                  <Td>{i.requisition_title}</Td>
                  <Td>{i.interviewer_name}</Td>
                  <Td><Badge value={i.status} label={humanize(i.status)} /></Td>
                  <Td>{i.confirmed_start ? formatInZone(i.confirmed_start, i.timezone) : `${i.proposed_slots.length} proposed`}</Td>
                  <Td>{i.confirmed_start ? formatInZone(i.confirmed_start, BROWSER_TZ, false) : '—'}</Td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
        <AvailabilityManager />
      </div>
    </>
  )
}
