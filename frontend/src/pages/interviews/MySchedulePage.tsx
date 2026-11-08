import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAddAvailability, useAvailability, useDeleteAvailability, useInterviews } from '../../api/hooks'
import { useAuth } from '../../auth/AuthContext'
import { Alert, Badge, Button, Card, DateInput, Empty, ErrorAlert, Field, Input, KeyValue, Loading, PageHeader, Select, Table, Td } from '../../components/ui'
import { BROWSER_TZ, COMMON_TIMEZONES, formatDate, formatInZone, humanize } from '../../lib/format'
import type { AvailabilitySlot, Interview } from '../../lib/types'

const todayIso = () => new Date().toISOString().slice(0, 10)

/** Interviews that occupy the interviewer's calendar. */
const isBooked = (i: Interview) => (i.status === 'SLOT_CONFIRMED' || i.status === 'SCHEDULED') && Boolean(i.confirmed_start)

function bookedInterview(slot: AvailabilitySlot, interviews: Interview[]) {
  return interviews.find((i) => {
    if (!isBooked(i) || !i.confirmed_start) return false
    const start = new Date(i.confirmed_start).getTime()
    return start >= new Date(slot.start).getTime() && start < new Date(slot.end).getTime()
  })
}

/** Where / how the interview takes place, in words the interviewer can act on. */
function whereText(i: Interview) {
  if (i.mode === 'ONSITE') return i.location ? `On-site: ${i.location}` : 'On-site'
  if (i.mode === 'VIDEO') {
    if (i.meeting_link) return `Video call: ${i.meeting_link}`
    if (i.contact_whatsapp) return `WhatsApp video call on ${i.contact_whatsapp}`
    return 'Video call'
  }
  return humanize(i.mode)
}

const STATUS_NOTE: Record<Interview['status'], string> = {
  PROPOSED: 'Slots are proposed; waiting for a time to be confirmed.',
  NEEDS_HR_COORDINATION: 'No shared time was found; HR is coordinating with the candidate.',
  SLOT_CONFIRMED: 'The time is confirmed; the invitation email has not been sent yet.',
  SCHEDULED: 'The invitation was sent to the candidate. This interview is scheduled.',
  CANCELLED: 'This interview was cancelled.',
}

function MyAvailability({ userId }: { userId: number }) {
  const slots = useAvailability(userId)
  const active = useInterviews({ status: 'ACTIVE', mine: '1' })
  const add = useAddAvailability()
  const remove = useDeleteAvailability()
  const [form, setForm] = useState({ date: todayIso(), start_time: '09:00', end_time: '13:00', timezone: BROWSER_TZ })
  const badRange = form.end_time <= form.start_time
  const interviews = active.data ?? []

  return (
    <Card title="When I am available to interview">
      <div className="space-y-4">
        <Alert tone="info">
          Add the dates and times you can interview. The scheduling agent only books candidates inside these windows, and a booked time is removed from your availability automatically.
        </Alert>
        <ErrorAlert error={add.error ?? remove.error} />
        <div className="flex flex-wrap items-end gap-2">
          <Field label="Date"><DateInput required value={form.date} onChange={(iso) => setForm({ ...form, date: iso })} className="w-44" /></Field>
          <Field label="From"><Input type="time" required value={form.start_time} onChange={(e) => setForm({ ...form, start_time: e.target.value })} /></Field>
          <Field label="To"><Input type="time" required value={form.end_time} onChange={(e) => setForm({ ...form, end_time: e.target.value })} /></Field>
          <Field label="Time zone">
            <Select value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value })} options={COMMON_TIMEZONES.map((z) => ({ value: z, label: z }))} />
          </Field>
          <Button loading={add.isPending} disabled={!form.date || badRange} title={badRange ? 'The end time must be after the start time' : ''}
            onClick={() => add.mutate({ ...form, interviewer: userId })}>Add availability</Button>
        </div>
        {badRange && <p className="text-xs text-rose-600">The end time must be after the start time.</p>}
        {slots.isLoading ? <Loading /> : !slots.data?.length ? <Empty>You have not added any upcoming availability yet.</Empty> : (
          <Table head={['Day and start', 'Until', 'Entered in', 'Status', '']}>
            {slots.data.map((s) => {
              const booked = bookedInterview(s, interviews)
              return (
                <tr key={s.public_id}>
                  <Td>{formatInZone(s.start, s.timezone, false)}</Td>
                  <Td>{formatInZone(s.end, s.timezone, false)}</Td>
                  <Td className="text-xs">{s.timezone}</Td>
                  <Td>{booked ? <Badge tone="blue" label={`Booked: ${booked.candidate_name || 'candidate'}`} /> : <Badge tone="green" label="Free" />}</Td>
                  <Td>
                    <Button size="sm" variant="ghost"
                      onClick={() => { if (!booked || confirm('An interview is booked inside this window. Removing it does not cancel the interview. Remove anyway?')) remove.mutate(s.public_id) }}>
                      Remove
                    </Button>
                  </Td>
                </tr>
              )
            })}
          </Table>
        )}
      </div>
    </Card>
  )
}

function InterviewCard({ interview: i }: { interview: Interview }) {
  const when = i.confirmed_start ? formatInZone(i.confirmed_start, BROWSER_TZ) : ''
  return (
    <div className="rounded-md p-4 ring-1 ring-slate-200">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-slate-900">
            <Link to={`/candidates/${i.candidate_reference}?tab=interview`} className="text-indigo-700 hover:underline">{i.candidate_name || 'Candidate'}</Link>
            {' · '}{i.requisition_title}
          </div>
          <div className="text-xs text-slate-500">{STATUS_NOTE[i.status]}</div>
        </div>
        <Badge value={i.status} label={humanize(i.status)} />
      </div>
      <KeyValue items={[
        ['When (your time)', when || (i.proposed_slots.length ? `${i.proposed_slots.length} slots proposed` : '')],
        ['Candidate time zone', i.confirmed_start && i.timezone !== BROWSER_TZ ? formatInZone(i.confirmed_start, i.timezone) : i.timezone],
        ['Duration', `${i.duration_minutes} minutes`],
        ['Format', humanize(i.mode)],
        ['Where / how', whereText(i)],
        ['Scheduled by', i.auto_scheduled ? 'Scheduling agent (automatic)' : i.created_by_name],
        ['Assigned', formatDate(i.created_at)],
        ['Cancellation reason', i.cancellation_reason],
      ]} />
      {i.status === 'PROPOSED' && i.proposed_slots.length > 0 && (
        <p className="mt-3 text-xs text-slate-500">Proposed: {i.proposed_slots.map((s) => formatInZone(s.start, BROWSER_TZ, false)).join(' · ')}</p>
      )}
    </div>
  )
}

function MyInterviews() {
  const [status, setStatus] = useState('ACTIVE')
  const interviews = useInterviews({ status: status || undefined, mine: '1' })
  return (
    <Card
      title={`Interviews assigned to me${interviews.data ? ` (${interviews.data.length})` : ''}`}
      actions={
        <Select value={status} onChange={(e) => setStatus(e.target.value)} options={[
          { value: 'ACTIVE', label: 'Active' }, { value: 'SCHEDULED', label: 'Scheduled' },
          { value: 'CANCELLED', label: 'Cancelled' }, { value: '', label: 'All' }]} />
      }
    >
      <div className="space-y-3">
        <ErrorAlert error={interviews.error} />
        {interviews.isLoading ? <Loading /> : !interviews.data?.length ? <Empty>No interviews are assigned to you in this view.</Empty> : (
          interviews.data.map((i) => <InterviewCard key={i.public_id} interview={i} />)
        )}
      </div>
    </Card>
  )
}

/** Personal page for anyone who interviews: set my availability and see my assigned interviews (route /my-schedule). */
export function MySchedulePage() {
  const { user } = useAuth()
  if (!user) return <Loading />
  return (
    <>
      <PageHeader title="My schedule" subtitle="Add the dates and times you are free to conduct interviews, and see the interviews assigned to you." />
      <div className="space-y-6">
        <MyAvailability userId={user.id} />
        <MyInterviews />
      </div>
    </>
  )
}
