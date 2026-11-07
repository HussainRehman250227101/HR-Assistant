import { useState, type FormEvent } from 'react'
import { useScreeningAction } from '../../api/hooks'
import { Alert, Button, ErrorAlert, Field, Select, Textarea } from '../../components/ui'
import type { Screening } from '../../lib/types'

const DECISIONS = [
  { value: 'APPROVE_FOR_INTERVIEW', label: 'Approve for interview scheduling' },
  { value: 'RESCREEN_HUMAN_LED', label: 'Re-screen: human-led screening' },
  { value: 'RESCREEN_AI_CALL', label: 'Re-screen: new AI call' },
  { value: 'DECLINE', label: 'Decline (closes candidate)' },
]

/** Human gate 2 (FR-08): the AI recommendation is advisory; only this decision progresses the candidate. */
export function ScreeningReviewForm({ screening }: { screening: Screening }) {
  const action = useScreeningAction()
  const [decision, setDecision] = useState(
    screening.recommended_next_step_for_human_review === 'OFFER_ALTERNATIVE_SCREENING' ? 'RESCREEN_HUMAN_LED' : 'APPROVE_FOR_INTERVIEW',
  )
  const [reason, setReason] = useState('')
  const reasonRequired = decision !== 'APPROVE_FOR_INTERVIEW' || screening.call_status !== 'COMPLETED'

  async function submit(e: FormEvent) {
    e.preventDefault()
    await action.mutateAsync({ id: screening.public_id, action: 'review', body: { decision, decision_reason: reason } })
  }

  return (
    <form onSubmit={submit} className="space-y-3 rounded-md bg-slate-50 p-4 ring-1 ring-slate-200">
      <h4 className="text-sm font-semibold text-slate-900">Screening decision (human gate 2)</h4>
      <ErrorAlert error={action.error} />
      {screening.call_status !== 'COMPLETED' && (
        <Alert tone="warning">The screening did not complete normally ({screening.call_status.toLowerCase().replaceAll('_', ' ')}). Follow up with the candidate before progressing.</Alert>
      )}
      <Field label="Decision"><Select value={decision} onChange={(e) => setDecision(e.target.value)} options={DECISIONS} /></Field>
      <Field label={reasonRequired ? 'Reason (required)' : 'Reason (optional)'}>
        <Textarea required={reasonRequired} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Job-related reason, recorded in the audit trail" />
      </Field>
      <Button type="submit" loading={action.isPending} variant={decision === 'DECLINE' ? 'danger' : 'primary'}>Record decision</Button>
    </form>
  )
}
