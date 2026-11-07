import { useEffect, useState } from 'react'
import { useAgentConfig, useCandidateScreenings, useCreateScreening, useScreeningAction } from '../../api/hooks'
import { Alert, Badge, Button, Card, Empty, ErrorAlert, Field, Input, Loading, Modal, Table, Td } from '../../components/ui'
import { formatDate, humanize } from '../../lib/format'
import type { Candidate, Screening } from '../../lib/types'
import { ManualResultForm } from './ManualResultForm'
import { ScreeningResult } from './ScreeningResult'
import { ScreeningReviewForm } from './ScreeningReviewForm'

const ACTIVE = ['PENDING_CALL', 'CALL_IN_PROGRESS', 'ANALYZING', 'ANALYSIS_FAILED', 'AWAITING_MANUAL_RESULT', 'AWAITING_HR_REVIEW']

function AttemptsTable({ screening }: { screening: Screening }) {
  if (!screening.call_attempts.length) return null
  return (
    <Table head={['#', 'Status', 'Outcome', 'To', 'Telephony', 'Duration', 'Started']}>
      {screening.call_attempts.map((a) => (
        <tr key={a.public_id}>
          <Td>{a.attempt_number}</Td>
          <Td><Badge value={a.status} /></Td>
          <Td>{a.outcome ? <Badge value={a.outcome} /> : '—'}{a.error_message && <div className="mt-1 text-xs text-rose-700">{a.error_message}</div>}</Td>
          <Td className="font-mono text-xs">{a.destination_masked}</Td>
          <Td className="text-xs">{a.telephony_status || a.provider_status || '—'}</Td>
          <Td>{a.duration_seconds != null ? `${a.duration_seconds}s` : '—'}</Td>
          <Td>{formatDate(a.started_at)}</Td>
        </tr>
      ))}
    </Table>
  )
}

export function ActiveScreening({ screening, canEdit }: { screening: Screening; canEdit: boolean }) {
  const action = useScreeningAction()
  const [cancelReason, setCancelReason] = useState('')
  const [cancelOpen, setCancelOpen] = useState(false)
  const run = (name: 'call' | 'sync' | 'retry-analysis') => action.mutate({ id: screening.public_id, action: name })
  const waitUntil = screening.next_attempt_not_before && new Date(screening.next_attempt_not_before) > new Date() ? screening.next_attempt_not_before : null
  const { mutate } = action

  // While a call is live, poll the provider through the backend (webhook remains the primary signal).
  useEffect(() => {
    if (!canEdit || !['CALL_IN_PROGRESS', 'ANALYZING'].includes(screening.status)) return
    const timer = window.setInterval(() => mutate({ id: screening.public_id, action: 'sync' }), 20_000)
    return () => window.clearInterval(timer)
  }, [canEdit, screening.status, screening.public_id, mutate])

  return (
    <Card
      title={<span className="flex items-center gap-2">{screening.channel === 'AI_VOICE' ? 'AI screening call' : 'Human-led screening'} <Badge value={screening.status} /></span>}
      actions={canEdit && (
        <>
          {screening.status === 'PENDING_CALL' && <Button size="sm" loading={action.isPending && action.variables?.action === 'call'} disabled={Boolean(waitUntil)} onClick={() => run('call')}>Place call now</Button>}
          {screening.status === 'CALL_IN_PROGRESS' && <Button size="sm" variant="secondary" loading={action.isPending} onClick={() => run('sync')}>Refresh call status</Button>}
          {screening.status === 'ANALYSIS_FAILED' && <Button size="sm" loading={action.isPending} onClick={() => run('retry-analysis')}>Retry analysis</Button>}
          {['PENDING_CALL', 'AWAITING_MANUAL_RESULT', 'ANALYSIS_FAILED'].includes(screening.status) && <Button size="sm" variant="ghost" onClick={() => setCancelOpen(true)}>Cancel screening</Button>}
        </>
      )}
    >
      <div className="space-y-4">
        <ErrorAlert error={action.error} />
        {screening.call_error && <Alert>{screening.call_error}</Alert>}
        {screening.error_message && <Alert>{screening.error_message}</Alert>}
        {screening.channel === 'AI_VOICE' && (
          <p className="text-sm text-slate-600">
            Attempts {screening.attempt_count} / {screening.max_attempts} · script {screening.script_version}
            {waitUntil && <> · next attempt allowed after {formatDate(waitUntil)}</>}
            {screening.status === 'PENDING_CALL' && screening.call_status !== 'NOT_STARTED' && <> · last result <Badge value={screening.call_status} /></>}
          </p>
        )}
        {screening.status === 'CALL_IN_PROGRESS' && <Alert tone="info">The call is in progress. Results arrive by webhook; this page refreshes automatically, or use “Refresh call status”.</Alert>}
        {screening.status === 'ANALYZING' && <Alert tone="info">The call ended. Summarising the transcript…</Alert>}
        <AttemptsTable screening={screening} />
        {screening.status === 'AWAITING_MANUAL_RESULT' && canEdit && <ManualResultForm screening={screening} />}
        {screening.status === 'AWAITING_HR_REVIEW' && (
          <>
            <ScreeningResult screening={screening} />
            {canEdit && <ScreeningReviewForm screening={screening} />}
          </>
        )}
      </div>
      <Modal open={cancelOpen} title="Cancel screening" onClose={() => setCancelOpen(false)}>
        <div className="space-y-3">
          <Field label="Reason"><Input value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} /></Field>
          <Button variant="danger" disabled={!cancelReason.trim()} loading={action.isPending}
            onClick={async () => { await action.mutateAsync({ id: screening.public_id, action: 'cancel', body: { reason: cancelReason } }); setCancelOpen(false) }}>
            Cancel screening
          </Button>
          <p className="text-xs text-slate-500">The candidate returns to “Approved for Screening”.</p>
        </div>
      </Modal>
    </Card>
  )
}

function StartScreening({ candidate }: { candidate: Candidate }) {
  const create = useCreateScreening(candidate.public_id)
  const config = useAgentConfig()
  const [open, setOpen] = useState(false)
  const optOut = Boolean(candidate.consent_preferences?.automated_call_opt_out) || candidate.recording_consent_status === 'DECLINED' || candidate.contact_consent_status === 'DECLINED'
  const policy = config.data?.calling_policy
  const configured = config.data && config.data.integration.elevenlabs_api_key && config.data.integration.elevenlabs_agent_id && config.data.integration.elevenlabs_agent_phone_number_id

  return (
    <Card title="Start screening (Agent 2)">
      <div className="space-y-3">
        <ErrorAlert error={create.error} />
        <p className="text-sm text-slate-600">The candidate was approved for screening by a recruiter. Choose the screening route:</p>
        {optOut && <Alert tone="warning">This candidate opted out of automated calls or declined recording. Use a human-led screening.</Alert>}
        {config.data && !configured && <Alert tone="warning">Twilio/ElevenLabs is not configured on the server, so AI calls cannot be placed. Human-led screening is available.</Alert>}
        <div className="flex flex-wrap gap-2">
          <Button disabled={optOut} onClick={() => setOpen(true)}>AI voice screening call</Button>
          <Button variant="secondary" loading={create.isPending && create.variables?.channel === 'HUMAN_LED'} onClick={() => create.mutate({ channel: 'HUMAN_LED', start_call_now: false })}>Human-led screening</Button>
        </div>
      </div>
      <Modal open={open} title="Confirm AI screening call" onClose={() => setOpen(false)}>
        <div className="space-y-3 text-sm">
          <p>The AI agent will call <strong>{candidate.phone || 'no phone on file'}</strong> and will:</p>
          <ul className="list-disc space-y-1 pl-5 text-slate-700">
            <li>say it is an AI assistant calling for the recruiting team and explain the purpose</li>
            <li>ask consent to record and transcribe, and stop if it is declined</li>
            <li>ask only the requisition's approved job-related questions</li>
            <li>stop and route to a human on request</li>
          </ul>
          {policy && <p className="text-xs text-slate-500">Policy: max {String(policy.max_attempts)} attempts, {String(policy.retry_interval_minutes)} min apart, {String(policy.window_start_hour)}:00–{String(policy.window_end_hour)}:00 {String(policy.timezone)}. Pakistani (+92) numbers only.</p>}
          <div className="flex gap-2">
            <Button loading={create.isPending} onClick={async () => { await create.mutateAsync({ channel: 'AI_VOICE', start_call_now: true }); setOpen(false) }}>Create screening and call now</Button>
            <Button variant="secondary" loading={create.isPending} onClick={async () => { await create.mutateAsync({ channel: 'AI_VOICE', start_call_now: false }); setOpen(false) }}>Create, call later</Button>
          </div>
        </div>
      </Modal>
    </Card>
  )
}

export function ScreeningPanel({ candidate, canEdit }: { candidate: Candidate; canEdit: boolean }) {
  const screenings = useCandidateScreenings(candidate.public_id)
  const active = screenings.data?.find((s) => ACTIVE.includes(s.status))
  const past = screenings.data?.filter((s) => s !== active) ?? []

  if (screenings.isLoading) return <Loading />
  return (
    <div className="space-y-6">
      <ErrorAlert error={screenings.error} />
      {active ? <ActiveScreening screening={active} canEdit={canEdit} /> : canEdit && candidate.current_status === 'APPROVED_FOR_SCREENING' ? <StartScreening candidate={candidate} /> : null}
      {!active && candidate.current_status !== 'APPROVED_FOR_SCREENING' && !past.length && <Card><Empty>Screening becomes available once a recruiter approves the candidate for screening.</Empty></Card>}
      {past.map((s) => (
        <Card key={s.public_id} title={<span className="flex items-center gap-2">{s.channel === 'AI_VOICE' ? 'AI screening call' : 'Human-led screening'} · {formatDate(s.created_at)} <Badge value={s.status} /></span>}>
          {s.review && <Alert tone="info">HR decision: {humanize(s.review.decision)} by {s.review.decided_by_name} — {s.review.decision_reason}</Alert>}
          <div className="mt-3"><ScreeningResult screening={s} /></div>
          <div className="mt-3"><AttemptsTable screening={s} /></div>
        </Card>
      ))}
    </div>
  )
}
