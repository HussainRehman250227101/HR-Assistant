import { useState, type FormEvent } from 'react'
import { useScreeningAction } from '../../api/hooks'
import { Alert, Button, ErrorAlert, Field, Select, Textarea } from '../../components/ui'
import type { Screening } from '../../lib/types'

const OTHER_DECISIONS = [
  { value: 'RESCREEN_HUMAN_LED', label: 'Re-screen: human-led screening' },
  { value: 'RESCREEN_AI_CALL', label: 'Re-screen: new AI voice screening (browser session, or call in telephony mode)' },
  { value: 'DECLINE', label: 'Decline (rejection email + data deletion)' },
]

const DECLINE_WARNING =
  'Declining closes this candidate and sends them a friendly rejection email. Their resume, contact details, screening answers and evaluation notes are then permanently deleted; only their name is kept for HR. This cannot be undone.'

/** Human gate 2 (FR-08): one click approves for interview; the AI recommendation is advisory only. */
export function ScreeningReviewForm({ screening }: { screening: Screening }) {
  const action = useScreeningAction()
  const suggestsRescreen = screening.recommended_next_step_for_human_review === 'OFFER_ALTERNATIVE_SCREENING'
  const [showOther, setShowOther] = useState(suggestsRescreen)
  const [decision, setDecision] = useState(suggestsRescreen ? 'RESCREEN_HUMAN_LED' : 'DECLINE')
  const [reason, setReason] = useState('')

  async function approve() {
    await action.mutateAsync({ id: screening.public_id, action: 'review', body: { decision: 'APPROVE_FOR_INTERVIEW', decision_reason: '' } })
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (decision === 'DECLINE' && !confirm(DECLINE_WARNING)) return
    await action.mutateAsync({ id: screening.public_id, action: 'review', body: { decision, decision_reason: reason } })
  }

  return (
    <div className="space-y-3 rounded-md bg-slate-50 p-4 ring-1 ring-slate-200">
      <h4 className="text-sm font-semibold text-slate-900">Screening decision (human gate 2)</h4>
      <ErrorAlert error={action.error} />
      {screening.call_status !== 'COMPLETED' && (
        <Alert tone="warning">The screening did not complete normally ({screening.call_status.toLowerCase().replaceAll('_', ' ')}). Check the answers before approving.</Alert>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={approve} loading={action.isPending && !showOther}>Approve this candidate</Button>
        <button type="button" className="text-sm text-slate-600 hover:underline" onClick={() => setShowOther(!showOther)}>
          {showOther ? 'Hide other decisions' : 'Other decisions (re-screen, decline)'}
        </button>
      </div>
      {showOther && (
        <form onSubmit={submit} className="space-y-3">
          <Field label="Decision"><Select value={decision} onChange={(e) => setDecision(e.target.value)} options={OTHER_DECISIONS} /></Field>
          {decision === 'DECLINE' && <Alert tone="warning">{DECLINE_WARNING}</Alert>}
          <Field label="Reason (required)">
            <Textarea required value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Job-related reason, recorded in the audit trail" />
          </Field>
          <Button type="submit" loading={action.isPending && showOther} variant={decision === 'DECLINE' ? 'danger' : 'primary'}>Record decision</Button>
        </form>
      )}
    </div>
  )
}
