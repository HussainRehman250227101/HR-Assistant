import { useState, type FormEvent } from 'react'
import { Button, ErrorAlert, Input } from './ui'

export const DECLINE_CONFIRM =
  'Declining closes this candidate and sends them a friendly rejection email. Their resume, contact details, screening answers and evaluation notes are then permanently deleted; only their name is kept for HR. This cannot be undone.'

/**
 * Row-level Approve / Reject. Approval is one click; rejecting asks for the (backend-required) job-related reason
 * inline and a confirmation, so the admin does not need to open the candidate. Detailed review stays available.
 */
export function QuickDecision({ onApprove, onReject, pending, approveDisabled, approveHint, error }: {
  onApprove: () => Promise<unknown>
  onReject: (reason: string) => Promise<unknown>
  pending: boolean
  approveDisabled?: boolean
  approveHint?: string
  error?: unknown
}) {
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState<'approve' | 'reject' | null>(null)

  async function run(kind: 'approve' | 'reject', fn: () => Promise<unknown>) {
    setBusy(kind)
    try { await fn() } catch { /* shown through `error` */ } finally { setBusy(null) }
  }

  function submitReject(e: FormEvent) {
    e.preventDefault()
    if (!confirm(DECLINE_CONFIRM)) return
    void run('reject', () => onReject(reason.trim()))
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="success" title={approveDisabled ? approveHint : undefined}
          disabled={approveDisabled || pending} loading={busy === 'approve'} onClick={() => void run('approve', onApprove)}>Approve</Button>
        <Button size="sm" variant="danger" disabled={pending} onClick={() => setRejecting(!rejecting)}>{rejecting ? 'Cancel' : 'Reject'}</Button>
      </div>
      {approveDisabled && approveHint && <div className="text-xs text-amber-700">{approveHint}</div>}
      {rejecting && (
        <form onSubmit={submitReject} className="flex flex-wrap items-center gap-2">
          <Input required value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Job-related reason (required)" className="min-w-52" />
          <Button size="sm" type="submit" variant="danger" loading={busy === 'reject'} disabled={pending}>Confirm reject</Button>
        </form>
      )}
      <ErrorAlert error={error} />
    </div>
  )
}
