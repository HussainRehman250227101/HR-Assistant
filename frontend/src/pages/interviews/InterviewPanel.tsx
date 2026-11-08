import { useState } from 'react'
import { useAutoSchedule, useCandidateEvents, useCandidateInterviews, useCandidateScreenings, useInterviewAction, usePlanInterview } from '../../api/hooks'
import { Alert, Badge, Button, Card, Empty, ErrorAlert, Field, Input, KeyValue, Loading, Modal } from '../../components/ui'
import { BROWSER_TZ, formatDate, formatInZone, humanize } from '../../lib/format'
import type { Candidate, Interview } from '../../lib/types'
import { CommunicationsCard, InvitationSection } from './Communications'
import { InterviewPlanForm } from './InterviewPlanForm'

const ACTIVE = ['PROPOSED', 'NEEDS_HR_COORDINATION', 'SLOT_CONFIRMED', 'SCHEDULED']

function SlotPicker({ interview }: { interview: Interview }) {
  const action = useInterviewAction()
  const [slot, setSlot] = useState('')
  const [candidateOk, setCandidateOk] = useState(false)
  const [interviewerOk, setInterviewerOk] = useState(false)
  return (
    <div className="space-y-3">
      <ErrorAlert error={action.error} />
      <div className="text-sm font-medium">Mutually available slots</div>
      <div className="grid gap-2 sm:grid-cols-2">
        {interview.proposed_slots.map((s) => (
          <label key={s.start} className={`flex cursor-pointer items-start gap-2 rounded-md p-2 text-sm ring-1 ${slot === s.start ? 'bg-indigo-50 ring-indigo-400' : 'ring-slate-200'}`}>
            <input type="radio" name={`slot-${interview.public_id}`} checked={slot === s.start} onChange={() => setSlot(s.start)} className="mt-1" />
            <span>
              <span className="font-medium">{formatInZone(s.start, interview.timezone)}</span>
              {interview.timezone !== BROWSER_TZ && <span className="block text-xs text-slate-500">Your time: {formatInZone(s.start, BROWSER_TZ)}</span>}
            </span>
          </label>
        ))}
      </div>
      <div className="space-y-1 text-sm">
        <label className="flex items-center gap-2"><input type="checkbox" checked={candidateOk} onChange={(e) => setCandidateOk(e.target.checked)} /> The candidate confirmed this slot</label>
        <label className="flex items-center gap-2"><input type="checkbox" checked={interviewerOk} onChange={(e) => setInterviewerOk(e.target.checked)} /> The interviewer confirmed this slot</label>
      </div>
      <Button disabled={!slot || !candidateOk || !interviewerOk} loading={action.isPending}
        onClick={() => action.mutate({ id: interview.public_id, action: 'confirm-slot', body: { slot_start: slot, candidate_confirmed: candidateOk, interviewer_confirmed: interviewerOk } })}>
        Confirm slot
      </Button>
    </div>
  )
}

export function InterviewDetails({ interview }: { interview: Interview }) {
  return (
    <KeyValue items={[
      ['Interviewer', `${interview.interviewer_name} · ${interview.interviewer_email}`],
      ['Duration', `${interview.duration_minutes} minutes`],
      ['Candidate time zone', interview.timezone],
      ['Format', humanize(interview.mode)],
      ['Where / how', interview.meeting_link || (interview.contact_whatsapp ? `WhatsApp video call on ${interview.contact_whatsapp}` : interview.location)],
      ['Scheduled by', interview.auto_scheduled ? 'Scheduling agent (automatic)' : interview.created_by_name],
      ['Confirmed slot', interview.confirmed_start ? formatInZone(interview.confirmed_start, interview.timezone) : ''],
      ['Calendar source', interview.calendar_source_label],
      ['Candidate availability (stated)', interview.candidate_availability_note],
    ]} />
  )
}

function ActiveInterview({ interview, canEdit, children }: { interview: Interview; canEdit: boolean; children?: React.ReactNode }) {
  const action = useInterviewAction()
  const [replan, setReplan] = useState(false)
  const [cancelOpen, setCancelOpen] = useState(false)
  const [reason, setReason] = useState('')
  const canReplan = ['PROPOSED', 'NEEDS_HR_COORDINATION', 'SLOT_CONFIRMED', 'SCHEDULED'].includes(interview.status)

  return (
    <Card
      title={<span className="flex items-center gap-2">Interview <Badge value={interview.status} /></span>}
      actions={canEdit && (
        <>
          {canReplan && <Button size="sm" variant="secondary" onClick={() => setReplan(true)}>{interview.status === 'SCHEDULED' ? 'Reschedule' : 'Update availability & re-propose'}</Button>}
          <Button size="sm" variant="ghost" onClick={() => setCancelOpen(true)}>Cancel interview</Button>
        </>
      )}
    >
      <div className="space-y-4">
        <InterviewDetails interview={interview} />
        {interview.status === 'NEEDS_HR_COORDINATION' && (
          <Alert tone="warning">No shared availability between the candidate's windows and the interviewer's calendar. Coordinate manually: add interviewer availability or new candidate windows, then re-propose.</Alert>
        )}
        {interview.status === 'PROPOSED' && canEdit && <SlotPicker interview={interview} />}
        {interview.sequence > 0 && interview.status !== 'SCHEDULED' && (
          <Alert tone="info">Rescheduling: the previously sent time no longer applies. Confirm a new slot, then approve the updated invitation.</Alert>
        )}
        {canEdit && <InvitationSection interview={interview} />}
        {interview.status === 'SCHEDULED' && (
          <Alert tone="success">
            {interview.auto_scheduled
              ? 'The scheduling agent matched the candidate and interviewer availability and sent the invitation automatically. The interview is scheduled.'
              : 'Invitation approved and sent. The interview is scheduled.'}
          </Alert>
        )}
        {interview.status === 'SLOT_CONFIRMED' && interview.auto_scheduled && (
          <Alert tone="warning">The agent booked this slot but the invitation email was not sent. Review the draft below and retry sending.</Alert>
        )}
        {children}
      </div>
      <Modal open={replan} title="Update availability and re-propose slots" onClose={() => setReplan(false)} wide>
        <InterviewPlanForm initial={interview} submitLabel="Re-check calendar" busy={action.isPending} error={action.error}
          onSubmit={async (data) => { await action.mutateAsync({ id: interview.public_id, action: 'propose', body: data }); setReplan(false) }} />
      </Modal>
      <Modal open={cancelOpen} title="Cancel interview" onClose={() => setCancelOpen(false)}>
        <div className="space-y-3">
          <ErrorAlert error={action.error} />
          <Field label="Reason"><Input value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
          <Button variant="danger" disabled={!reason.trim()} loading={action.isPending}
            onClick={async () => { await action.mutateAsync({ id: interview.public_id, action: 'cancel', body: { reason } }); setCancelOpen(false) }}>Cancel interview</Button>
        </div>
      </Modal>
    </Card>
  )
}

export function InterviewPanel({ candidate, canEdit }: { candidate: Candidate; canEdit: boolean }) {
  const interviews = useCandidateInterviews(candidate.public_id)
  const screenings = useCandidateScreenings(candidate.public_id)
  const plan = usePlanInterview(candidate.public_id)
  const active = interviews.data?.find((i) => ACTIVE.includes(i.status))
  const past = interviews.data?.filter((i) => i !== active) ?? []
  const hint = screenings.data?.find((s) => s.candidate_stated_availability)?.candidate_stated_availability
  const auto = useAutoSchedule(candidate.public_id)
  const events = useCandidateEvents(candidate.public_id)
  const lastFailure = events.data?.find((e) => e.event_type === 'INTERVIEW_AUTO_SCHEDULE_FAILED')
  const failureReason = typeof lastFailure?.details?.reason === 'string' ? lastFailure.details.reason : ''

  if (interviews.isLoading) return <Loading />
  return (
    <div className="space-y-6">
      <ErrorAlert error={interviews.error} />
      {active ? <ActiveInterview interview={active} canEdit={canEdit} /> : canEdit && candidate.current_status === 'APPROVED_FOR_INTERVIEW' ? (
        <Card
          title="Schedule interview (Agent 3)"
          actions={<Button size="sm" loading={auto.isPending} onClick={() => auto.mutate()}>Run scheduling agent now</Button>}
        >
          <div className="mb-4 space-y-3">
            <ErrorAlert error={auto.error} />
            <p className="text-sm text-slate-600">
              Once HR approves a screening, the agent automatically matches the candidate's stated availability with an interviewer's calendar and emails the invitation.
              If it cannot (no shared time, missing availability or email), the reason is shown here and you can plan the interview manually below.
            </p>
            {failureReason && <Alert tone="warning">The agent could not schedule this interview automatically: {failureReason}</Alert>}
            {auto.data && auto.data.outcome !== 'SCHEDULED' && <Alert tone="info">{auto.data.detail}</Alert>}
          </div>
          <h4 className="mb-2 text-sm font-semibold text-slate-700">Plan manually</h4>
          <InterviewPlanForm availabilityHint={hint} submitLabel="Check calendar and propose slots" busy={plan.isPending} error={plan.error} onSubmit={(data) => plan.mutateAsync(data)} />
        </Card>
      ) : !past.length && <Card><Empty>Interview scheduling becomes available once HR approves the candidate for interview.</Empty></Card>}
      {past.map((i) => (
        <Card key={i.public_id} title={<span className="flex items-center gap-2">Interview · {formatDate(i.created_at)} <Badge value={i.status} /></span>}>
          <InterviewDetails interview={i} />
          {i.cancellation_reason && <p className="mt-3 text-sm text-slate-600">Cancelled: {i.cancellation_reason}</p>}
        </Card>
      ))}
      {canEdit && <CommunicationsCard candidateId={candidate.public_id} />}
    </div>
  )
}
