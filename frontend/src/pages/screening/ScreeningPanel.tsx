import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAgentConfig, useCandidateScreenings, useCreateScreening, useScreeningAction } from '../../api/hooks'
import { Alert, Badge, Button, Card, Empty, ErrorAlert, Field, Input, Loading, Modal, Table, Td } from '../../components/ui'
import { formatDate, humanize } from '../../lib/format'
import type { Candidate, Screening } from '../../lib/types'
import { ManualResultForm } from './ManualResultForm'
import { ScreeningJobPanel } from './ScreeningJobPanel'
import { ScreeningResult } from './ScreeningResult'
import { ScreeningReviewForm } from './ScreeningReviewForm'

const ACTIVE = ['PENDING_CALL', 'CALL_IN_PROGRESS', 'ANALYZING', 'ANALYSIS_FAILED', 'AWAITING_MANUAL_RESULT', 'AWAITING_HR_REVIEW']

const TITLES: Record<string, string> = {
  AI_VOICE: 'AI screening call',
  BROWSER_VOICE: 'Browser voice screening (demo · no phone call)',
  HUMAN_LED: 'Human-led screening',
}

function AttemptsTable({ screening }: { screening: Screening }) {
  if (!screening.call_attempts.length) return null
  const browser = screening.channel === 'BROWSER_VOICE'
  return (
    <Table head={['#', 'Status', 'Outcome', browser ? 'Where' : 'To', browser ? 'Provider status' : 'Telephony', 'Duration', 'Started']}>
      {screening.call_attempts.map((a) => (
        <tr key={a.public_id}>
          <Td>{a.attempt_number}</Td>
          <Td><Badge value={a.status} /></Td>
          <Td>{a.outcome ? <Badge value={a.outcome} /> : '—'}{a.error_message && <div className="mt-1 text-xs text-rose-700">{a.error_message}</div>}</Td>
          <Td className={browser ? 'text-xs' : 'font-mono text-xs'}>{a.destination_masked}</Td>
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
  const phone = screening.channel === 'AI_VOICE'
  const browser = screening.channel === 'BROWSER_VOICE'

  // While a phone call is live, poll the provider through the backend (webhook remains the primary signal).
  // Browser sessions are concluded by the session page itself, so they are not polled here.
  useEffect(() => {
    if (!canEdit || !phone || !['CALL_IN_PROGRESS', 'ANALYZING'].includes(screening.status)) return
    const timer = window.setInterval(() => mutate({ id: screening.public_id, action: 'sync' }), 20_000)
    return () => window.clearInterval(timer)
  }, [canEdit, phone, screening.status, screening.public_id, mutate])

  return (
    <Card
      title={<span className="flex items-center gap-2">{TITLES[screening.channel] ?? humanize(screening.channel)} <Badge value={screening.status} /></span>}
      actions={canEdit && (
        <>
          {phone && screening.status === 'PENDING_CALL' && <Button size="sm" loading={action.isPending && action.variables?.action === 'call'} disabled={Boolean(waitUntil)} onClick={() => run('call')}>Place call now</Button>}
          {phone && screening.status === 'CALL_IN_PROGRESS' && <Button size="sm" variant="secondary" loading={action.isPending} onClick={() => run('sync')}>Refresh call status</Button>}
          {browser && ['PENDING_CALL', 'CALL_IN_PROGRESS'].includes(screening.status) && (
            <Link to={`/screening/${screening.public_id}/browser`} className="inline-flex items-center rounded-md bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-indigo-700">
              Open browser session
            </Link>
          )}
          {browser && screening.status === 'CALL_IN_PROGRESS' && <Button size="sm" variant="secondary" loading={action.isPending} onClick={() => run('sync')}>Check session result</Button>}
          {screening.status === 'ANALYSIS_FAILED' && <Button size="sm" loading={action.isPending} onClick={() => run('retry-analysis')}>Retry analysis</Button>}
          {['PENDING_CALL', 'AWAITING_MANUAL_RESULT', 'ANALYSIS_FAILED'].includes(screening.status) && <Button size="sm" variant="ghost" onClick={() => setCancelOpen(true)}>Cancel screening</Button>}
        </>
      )}
    >
      <div className="space-y-4">
        <ErrorAlert error={action.error} />
        {screening.call_error && <Alert>{screening.call_error}</Alert>}
        {screening.error_message && <Alert>{screening.error_message}</Alert>}
        {phone && (
          <p className="text-sm text-slate-600">
            Attempts {screening.attempt_count} / {screening.max_attempts} · script {screening.script_version}
            {waitUntil && <> · next attempt allowed after {formatDate(waitUntil)}</>}
            {screening.status === 'PENDING_CALL' && screening.call_status !== 'NOT_STARTED' && <> · last result <Badge value={screening.call_status} /></>}
          </p>
        )}
        {browser && (
          <p className="text-sm text-slate-600">
            Sessions {screening.attempt_count} / {screening.max_attempts} · script {screening.script_version} · the ElevenLabs agent talks to the person at the computer; no phone call is placed
            {screening.status === 'PENDING_CALL' && screening.call_status !== 'NOT_STARTED' && <> · last result <Badge value={screening.call_status} /></>}
          </p>
        )}
        {phone && screening.status === 'CALL_IN_PROGRESS' && <Alert tone="info">The call is in progress. Results arrive by webhook; this page refreshes automatically, or use “Refresh call status”.</Alert>}
        {browser && screening.status === 'CALL_IN_PROGRESS' && <Alert tone="info">A browser voice session is open. Its transcript is fetched from ElevenLabs when the session ends. If the session page was closed, use “Check session result”.</Alert>}
        {screening.status === 'ANALYZING' && <Alert tone="info">{browser ? 'The session ended.' : 'The call ended.'} Summarising the transcript…</Alert>}
        <AttemptsTable screening={screening} />
        {screening.status === 'AWAITING_MANUAL_RESULT' && canEdit && <ManualResultForm screening={screening} />}
        {screening.status === 'AWAITING_HR_REVIEW' && (
          <div className="grid gap-6 lg:grid-cols-2">
            <ScreeningResult screening={screening} />
            <div className="space-y-6">
              <ScreeningJobPanel screening={screening} />
              {canEdit && <ScreeningReviewForm screening={screening} />}
            </div>
          </div>
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
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const optOut = Boolean(candidate.consent_preferences?.automated_call_opt_out) || candidate.recording_consent_status === 'DECLINED' || candidate.contact_consent_status === 'DECLINED'
  const policy = config.data?.calling_policy
  const integration = config.data?.integration
  const telephony = config.data?.voice_mode === 'telephony'
  const phoneConfigured = integration && integration.elevenlabs_api_key && integration.elevenlabs_agent_id && integration.elevenlabs_agent_phone_number_id
  const browserReady = Boolean(integration?.browser_voice_ready)

  async function startBrowserScreening() {
    try {
      const screening = await create.mutateAsync({ channel: 'BROWSER_VOICE', start_call_now: false })
      navigate(`/screening/${screening.public_id}/browser`)
    } catch {
      // The error is shown through create.error.
    }
  }

  return (
    <Card title="Start screening (Agent 2)">
      <div className="space-y-3">
        <ErrorAlert error={create.error} />
        <p className="text-sm text-slate-600">The candidate was approved for screening by a recruiter. Choose the screening route:</p>
        {optOut && <Alert tone="warning">This candidate opted out of automated screening or declined recording. Use a human-led screening.</Alert>}
        {config.data && !browserReady && <Alert tone="warning">ElevenLabs is not configured on the server (ELEVENLABS_API_KEY and ELEVENLABS_AGENT_ID), so browser voice sessions cannot start. Human-led screening is available.</Alert>}
        {config.data && telephony && !phoneConfigured && <Alert tone="warning">Twilio/ElevenLabs telephony is not fully configured, so AI phone calls cannot be placed.</Alert>}
        <div className="flex flex-wrap gap-2">
          <Button disabled={optOut || (Boolean(config.data) && !browserReady)} loading={create.isPending && create.variables?.channel === 'BROWSER_VOICE'} onClick={() => void startBrowserScreening()}>
            Demo browser voice screening
          </Button>
          {telephony && <Button variant="secondary" disabled={optOut} onClick={() => setOpen(true)}>AI phone screening call</Button>}
          <Button variant="secondary" loading={create.isPending && create.variables?.channel === 'HUMAN_LED'} onClick={() => create.mutate({ channel: 'HUMAN_LED', start_call_now: false })}>Human-led screening</Button>
        </div>
        <p className="text-xs text-slate-500">
          Demo browser voice screening runs the ElevenLabs AI agent in this browser. You speak as the simulated candidate through this computer's microphone. No phone call is placed.
        </p>
      </div>
      <Modal open={open} title="Confirm AI screening call" onClose={() => setOpen(false)}>
        <div className="space-y-3 text-sm">
          <p>The AI agent will call <strong>{candidate.phone || 'no phone on file'}</strong> and will:</p>
          <ul className="list-disc space-y-1 pl-5 text-slate-700">
            <li>say it is an AI assistant calling for the recruiting team and explain the purpose</li>
            <li>ask consent to record and transcribe, and stop if it is declined</li>
            <li>ask only the requisition's approved job-related questions</li>
            <li>ask the expected salary range, notice period and interview availability</li>
            <li>decline questions unrelated to the role or the hiring process</li>
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
        <Card key={s.public_id} title={<span className="flex items-center gap-2">{TITLES[s.channel] ?? humanize(s.channel)} · {formatDate(s.created_at)} <Badge value={s.status} /></span>}>
          {s.review && <Alert tone="info">HR decision: {humanize(s.review.decision)} by {s.review.decided_by_name} — {s.review.decision_reason}</Alert>}
          <div className="mt-3"><ScreeningResult screening={s} /></div>
          <div className="mt-3"><AttemptsTable screening={s} /></div>
        </Card>
      ))}
    </div>
  )
}
