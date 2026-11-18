import { useState } from 'react'
import { useInterviews, useReassignInterview, useUpdateRecruiter, useUsers } from '../api/hooks'
import { Alert, Badge, Button, DateInput, ErrorAlert, Field, Input, Loading, Modal, Select } from '../components/ui'
import { BROWSER_TZ, COMMON_TIMEZONES, formatInZone } from '../lib/format'
import type { Interview, User } from '../lib/types'

const EMAIL_LABELS: Record<string, string> = {
  candidate: 'Candidate', new_interviewer: 'New interviewer', old_interviewer: 'Previous interviewer', interviewer: 'Interviewer',
}

/** One upcoming interview: pick the new interviewer and/or a new date and time, then reassign (emails go out automatically). */
function ReassignRow({ interview, leaving, others }: { interview: Interview; leaving: User; others: User[] }) {
  const reassign = useReassignInterview()
  const [interviewer, setInterviewer] = useState('')
  const [date, setDate] = useState('')
  const [time, setTime] = useState('')
  const [zone, setZone] = useState(interview.timezone || BROWSER_TZ)
  const result = reassign.data
  const changingTime = Boolean(date && time)
  const canSubmit = Boolean(interviewer) || changingTime

  function submit() {
    reassign.mutate({
      id: interview.public_id,
      data: { ...(interviewer ? { interviewer: Number(interviewer) } : {}), ...(changingTime ? { date, start_time: time, timezone: zone } : {}) },
    })
  }

  if (result) {
    return (
      <div className="rounded-md bg-emerald-50 p-4 text-sm ring-1 ring-emerald-200">
        <div className="font-medium text-slate-900">{interview.candidate_name || 'Candidate'} · {interview.requisition_title}: reassigned</div>
        <div className="mt-1 text-slate-700">Now with {result.interview.interviewer_name} · {formatInZone(result.interview.confirmed_start, result.interview.timezone)}</div>
        <div className="mt-2 flex flex-wrap gap-2">
          {Object.entries(result.emails).map(([who, state]) => (
            <Badge key={who} tone={state === 'SENT' ? 'green' : 'amber'} label={`${EMAIL_LABELS[who] ?? who}: ${state === 'SENT' ? 'emailed' : 'not emailed'}`} />
          ))}
        </div>
        {Object.values(result.emails).includes('NOT_SENT') && (
          <p className="mt-2 text-xs text-amber-800">An email was not sent (no address on file or the email provider refused it). Tell that person yourself.</p>
        )}
        {result.outside_declared_availability && <p className="mt-1 text-xs text-slate-600">This time is outside the new interviewer&apos;s declared availability.</p>}
      </div>
    )
  }

  return (
    <div className="space-y-3 border-t border-slate-100 pt-4 first:border-t-0 first:pt-0">
      <div>
        <div className="text-sm font-semibold text-slate-900">{interview.candidate_name || 'Candidate'} · {interview.requisition_title}</div>
        <div className="text-xs text-slate-500">
          {interview.confirmed_start ? formatInZone(interview.confirmed_start, interview.timezone) : 'Time not set yet'} · with {leaving.full_name || leaving.username}
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <Field label="New interviewer">
          <Select value={interviewer} onChange={(e) => setInterviewer(e.target.value)}
            options={[{ value: '', label: '— keep the same —' }, ...others.map((u) => ({ value: String(u.id), label: `${u.full_name || u.username} (${u.email})` }))]} />
        </Field>
        <Field label="Time zone">
          <Select value={zone} onChange={(e) => setZone(e.target.value)} options={Array.from(new Set([interview.timezone, ...COMMON_TIMEZONES])).map((z) => ({ value: z, label: z }))} />
        </Field>
        <Field label="New date (optional)"><DateInput value={date} onChange={setDate} /></Field>
        <Field label="New time (optional)"><Input type="time" value={time} onChange={(e) => setTime(e.target.value)} /></Field>
      </div>
      <p className="text-xs text-slate-500">
        On reassigning, the candidate and both interviewers are emailed automatically. Leave the date and time empty to keep the current ones.
        {!interview.confirmed_start && ' This interview has no time yet, so a date and time are required.'}
      </p>
      <ErrorAlert error={reassign.error} />
      <Button size="sm" disabled={!canSubmit} loading={reassign.isPending} onClick={submit}>Reassign and send emails</Button>
    </div>
  )
}

/** Deactivate a recruiter. While they still have upcoming interviews, each must be reassigned first. */
export function DeactivateRecruiterModal({ recruiter, onClose }: { recruiter: User | null; onClose: () => void }) {
  const open = recruiter !== null
  const interviews = useInterviews({ interviewer: recruiter ? String(recruiter.id) : undefined, status: 'ACTIVE', upcoming: '1' })
  const users = useUsers(undefined, open)
  const remove = useUpdateRecruiter()
  const [done, setDone] = useState(false)
  const others = (users.data ?? []).filter((u) => u.id !== recruiter?.id)
  const pending = (interviews.data ?? []).filter((i) => i.interviewer === recruiter?.id)

  function close() {
    setDone(false)
    remove.reset()
    onClose()
  }

  return (
    <Modal open={open} title={recruiter ? `Deactivate ${recruiter.full_name || recruiter.username}` : ''} onClose={close} wide>
      {!recruiter ? null : done ? (
        <div className="space-y-4">
          <Alert tone="success">{recruiter.full_name || recruiter.username} was deactivated. They can no longer sign in and are no longer offered as an interviewer. You can activate them again at any time.</Alert>
          <Button onClick={close}>Close</Button>
        </div>
      ) : interviews.isLoading || users.isLoading ? <Loading /> : (
        <div className="space-y-4">
          {pending.length > 0 ? (
            <>
              <Alert tone="warning">
                This recruiter has {pending.length} upcoming interview(s). Reassign each one to another interviewer (and change the date and time if needed) before deactivating them.
              </Alert>
              <div className="space-y-3">{pending.map((i) => <ReassignRow key={i.public_id} interview={i} leaving={recruiter} others={others} />)}</div>
            </>
          ) : (
            <p className="text-sm text-slate-700">
              This recruiter has no upcoming interviews. Deactivating keeps the account and its history for the audit trail, deletes their future availability and stops them signing in.
            </p>
          )}
          <ErrorAlert error={remove.error ?? interviews.error} />
          <div className="flex gap-2">
            <Button variant="danger" disabled={pending.length > 0} loading={remove.isPending}
              onClick={() => remove.mutate({ id: recruiter.id, data: { is_active: false } }, { onSuccess: () => setDone(true) })}>Deactivate recruiter</Button>
            <Button variant="secondary" onClick={close}>Cancel</Button>
          </div>
        </div>
      )}
    </Modal>
  )
}
