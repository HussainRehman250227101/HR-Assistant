import { ConversationProvider, useConversation } from '@elevenlabs/react'
import { useEffect, useRef, useState } from 'react'
import { useCompleteBrowserSession, useScreeningAction, useStartBrowserSession } from '../../api/hooks'
import { Alert, Badge, Button, ErrorAlert } from '../../components/ui'
import { errorMessage } from '../../lib/api'
import type { BrowserSessionStart, ClientEndReason, Screening } from '../../lib/types'

const POLL_INTERVAL_MS = 4000
const MAX_POLLS = 45 // about three minutes of "ElevenLabs is still processing"

type Phase = 'idle' | 'requesting-mic' | 'starting' | 'connecting' | 'live' | 'finalizing' | 'processing' | 'stalled' | 'done'

interface LocalSession {
  screeningId: string
  attemptId: string
  conversationId: string | null
  connected: boolean
  finalizing: boolean
  reason: ClientEndReason
}

function microphoneErrorMessage(error: unknown): string {
  const name = (error as { name?: string } | null)?.name
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return 'Microphone access was blocked. Allow microphone access for this site (address-bar padlock → Site settings → Microphone) and try again.'
  }
  if (name === 'NotFoundError' || name === 'OverconstrainedError') return 'No microphone was found. Connect a microphone and try again.'
  if (name === 'NotReadableError') return 'The microphone is in use by another application. Close that application and try again.'
  if (name === 'NotSupportedError') return 'This browser cannot use a microphone on this page. Use a current Chrome, Edge or Firefox on http://localhost or HTTPS.'
  return 'The microphone could not be opened. Check your browser permissions and try again.'
}

async function checkMicrophone() {
  if (!navigator.mediaDevices?.getUserMedia) throw Object.assign(new Error('unsupported'), { name: 'NotSupportedError' })
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  // Only a permission check: release the device so the SDK can open its own WebRTC audio track.
  stream.getTracks().forEach((track) => track.stop())
}

/**
 * Demo browser voice screening (Module 16). The ElevenLabs agent talks to the person at this computer over WebRTC.
 * No phone call is placed. The backend issues a short-lived conversation token and later fetches the authoritative
 * transcript from ElevenLabs, so nothing typed or heard in this page is trusted as the result.
 */
export function BrowserVoiceSession({ screening }: { screening: Screening }) {
  return (
    <ConversationProvider>
      <SessionConsole screening={screening} />
    </ConversationProvider>
  )
}

function SessionConsole({ screening }: { screening: Screening }) {
  const startSession = useStartBrowserSession()
  const completeSession = useCompleteBrowserSession()
  const checkStatus = useScreeningAction()
  const [consent, setConsent] = useState(false)
  const [phase, setPhase] = useState<Phase>('idle')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [finalStatus, setFinalStatus] = useState<string | null>(null)
  const session = useRef<LocalSession | null>(null)
  const startLock = useRef(false)
  const pollTimer = useRef<number | undefined>(undefined)
  const polls = useRef(0)

  async function requestResult(current: LocalSession) {
    try {
      const result = await completeSession.mutateAsync({
        id: current.screeningId,
        body: { attempt_id: current.attemptId, client_end_reason: current.reason, connected: current.connected, conversation_id: current.conversationId ?? undefined },
      })
      if (result.session_state === 'processing') {
        polls.current += 1
        if (polls.current > MAX_POLLS) {
          setPhase('stalled')
          return
        }
        setPhase('processing')
        pollTimer.current = window.setTimeout(() => void requestResult(current), POLL_INTERVAL_MS)
        return
      }
      session.current = null
      startLock.current = false
      if (result.status === 'PENDING_CALL') {
        const outcome = result.session_attempt.outcome || result.call_status
        setNotice(`The session ended without usable answers (${outcome.toLowerCase().replaceAll('_', ' ')}). You can start another session: attempt ${result.attempt_count} of ${result.max_attempts} used.`)
        setConsent(false)
        setPhase('idle')
      } else {
        setFinalStatus(result.status)
        setPhase('done')
      }
    } catch (err) {
      setError(`The session result could not be retrieved yet: ${errorMessage(err)}`)
      setPhase('stalled')
    }
  }

  function finalize(reason: ClientEndReason) {
    const current = session.current
    if (!current || current.finalizing) return
    current.finalizing = true
    current.reason = reason
    polls.current = 0
    setPhase('finalizing')
    void requestResult(current)
  }

  const conversation = useConversation({
    onConnect: ({ conversationId }) => {
      if (session.current) {
        session.current.connected = true
        session.current.conversationId ??= conversationId
      }
      setPhase((p) => (p === 'connecting' ? 'live' : p))
    },
    onDisconnect: (details) => finalize(details.reason === 'error' ? 'connection_error' : details.reason === 'agent' ? 'agent_ended' : 'user_ended'),
    onError: (message) => {
      setError(`Voice connection problem: ${message}`)
      if (session.current && !session.current.connected) finalize('start_failed')
    },
  })

  async function start() {
    if (startLock.current || !consent || screening.status !== 'PENDING_CALL') return
    startLock.current = true // blocks double clicks before React re-renders the disabled button
    setError(null)
    setNotice(null)
    setPhase('requesting-mic')
    try {
      await checkMicrophone()
    } catch (err) {
      setError(microphoneErrorMessage(err))
      setPhase('idle')
      startLock.current = false
      return
    }
    setPhase('starting')
    let started: BrowserSessionStart
    try {
      started = await startSession.mutateAsync({ id: screening.public_id })
    } catch (err) {
      setError(errorMessage(err))
      setPhase('idle')
      startLock.current = false
      return
    }
    session.current = { screeningId: started.screening_id, attemptId: started.attempt_id, conversationId: started.conversation_id, connected: false, finalizing: false, reason: 'unknown' }
    setPhase('connecting')
    try {
      conversation.startSession({
        conversationToken: started.conversation_token,
        connectionType: 'webrtc',
        dynamicVariables: started.dynamic_variables,
        userId: started.screening_id,
      })
    } catch (err) {
      setError(`Voice connection problem: ${errorMessage(err)}`)
      finalize('start_failed')
    }
  }

  function end() {
    conversation.endSession()
    finalize('user_ended')
  }

  function retryResult() {
    const current = session.current
    if (!current) return
    setError(null)
    polls.current = 0
    setPhase('finalizing')
    void requestResult(current)
  }

  useEffect(() => () => window.clearTimeout(pollTimer.current), [])

  const live = phase === 'connecting' || phase === 'live'
  // Leaving the page would cut the session off; ask first.
  useEffect(() => {
    if (!live) return
    const warn = (event: BeforeUnloadEvent) => event.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [live])

  const busy = phase !== 'idle' && phase !== 'done'
  const orphaned = phase === 'idle' && screening.status === 'CALL_IN_PROGRESS'
  const canStart = screening.status === 'PENDING_CALL' && phase === 'idle'
  const connected = conversation.status === 'connected'
  const indicator: { label: string; tone: 'gray' | 'blue' | 'green' | 'purple' | 'amber' } =
    phase === 'requesting-mic' ? { label: 'Waiting for microphone permission…', tone: 'amber' }
      : phase === 'starting' ? { label: 'Requesting a secure session…', tone: 'blue' }
        : connected && live ? (conversation.isSpeaking ? { label: 'Agent speaking', tone: 'purple' } : { label: conversation.isMuted ? 'Listening (your microphone is muted)' : 'Listening — speak now', tone: 'green' })
          : live ? { label: 'Connecting…', tone: 'blue' }
            : { label: 'Disconnected', tone: 'gray' }

  return (
    <div className="space-y-4">
      {canStart && (
        <div className="space-y-3 rounded-md bg-slate-50 p-4 text-sm ring-1 ring-slate-200">
          <h4 className="font-semibold text-slate-900">Before you start</h4>
          <ul className="list-disc space-y-1 pl-5 text-slate-700">
            <li>You will talk to an <strong>AI voice agent</strong>, not a person. No phone call is placed.</li>
            <li>Your voice is sent to and processed by <strong>ElevenLabs</strong>, our voice-AI provider. Depending on the organisation's ElevenLabs settings, ElevenLabs may also retain the conversation audio.</li>
            <li>A <strong>transcript</strong> of the conversation is kept for review by the HR team. A human decides the next step; the AI does not.</li>
            <li><strong>Microphone access is required.</strong> Your browser will ask for permission when you press Start Interview.</li>
            <li>You can end the interview at any time with <strong>End Interview</strong>, or ask the agent for a human recruiter instead.</li>
          </ul>
          <label className="flex items-start gap-2">
            <input type="checkbox" className="mt-0.5" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            <span>I understand the above and consent to start this AI voice screening session.</span>
          </label>
        </div>
      )}

      {(busy || canStart) && (
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={() => void start()} disabled={!consent || !canStart} loading={phase === 'requesting-mic' || phase === 'starting'}>Start Interview</Button>
          <Button variant="danger" onClick={end} disabled={!live}>End Interview</Button>
          <Button variant="secondary" onClick={() => conversation.setMuted(!conversation.isMuted)} disabled={!(live && connected)} aria-pressed={conversation.isMuted}>
            {conversation.isMuted ? 'Unmute microphone' : 'Mute microphone'}
          </Button>
          <span role="status" aria-live="polite"><Badge tone={indicator.tone} label={indicator.label} /></span>
        </div>
      )}

      {error && <Alert>{error}</Alert>}
      {notice && <Alert tone="info">{notice}</Alert>}

      {(phase === 'finalizing' || phase === 'processing') && (
        <Alert tone="info">Interview ended. Waiting for ElevenLabs to finish processing the transcript… This usually takes a few seconds.</Alert>
      )}
      {phase === 'stalled' && (
        <div className="flex flex-wrap items-center gap-3">
          <Alert tone="warning">The transcript is not available yet. Nothing has been lost; check again in a moment.</Alert>
          <Button variant="secondary" size="sm" onClick={retryResult} loading={completeSession.isPending}>Check result again</Button>
        </div>
      )}
      {phase === 'done' && finalStatus === 'AWAITING_HR_REVIEW' && (
        <Alert tone="success">Transcript received and summarised. The screening is now waiting for HR review. Nobody is approved or rejected automatically.</Alert>
      )}
      {phase === 'done' && finalStatus === 'ANALYSIS_FAILED' && (
        <Alert tone="warning">The transcript was saved, but the AI summary failed. A recruiter can retry the analysis from the candidate's Screening tab.</Alert>
      )}
      {phase === 'done' && finalStatus && !['AWAITING_HR_REVIEW', 'ANALYSIS_FAILED'].includes(finalStatus) && (
        <Alert tone="info">The session has ended. Current screening status: {finalStatus.toLowerCase().replaceAll('_', ' ')}.</Alert>
      )}

      {orphaned && (
        <div className="space-y-2">
          <Alert tone="warning">A session for this screening is open in another tab or was left open (for example, the page was closed mid-interview). Check its result; sessions that never connected are released after the configured timeout.</Alert>
          <ErrorAlert error={checkStatus.error} />
          <Button variant="secondary" size="sm" loading={checkStatus.isPending} onClick={() => checkStatus.mutate({ id: screening.public_id, action: 'sync' })}>Check session result</Button>
        </div>
      )}
    </div>
  )
}
