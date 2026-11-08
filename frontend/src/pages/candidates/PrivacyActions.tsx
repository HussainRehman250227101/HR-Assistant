import { useState } from 'react'
import { useCandidatePrivacyAction } from '../../api/hooks'
import { useAuth } from '../../auth/AuthContext'
import { Alert, Button, ErrorAlert, Field, Modal, Textarea } from '../../components/ui'
import type { Candidate } from '../../lib/types'

/** Authorised closure with a reason, and admin-only erasure of personal data (SRS §9, §12, §13). */
export function PrivacyActions({ candidate }: { candidate: Candidate }) {
  const { hasFullAccess, isAdmin } = useAuth()
  const action = useCandidatePrivacyAction(candidate.public_id)
  const [mode, setMode] = useState<'close' | 'erase-personal-data' | null>(null)
  const [reason, setReason] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  if (!hasFullAccess || candidate.personal_data_erased_at) return null
  const closed = candidate.current_status === 'CLOSED'

  return (
    <>
      {!closed && <Button variant="ghost" onClick={() => { setMode('close'); setReason(''); action.reset() }}>Close candidate</Button>}
      {closed && isAdmin && <Button variant="danger" onClick={() => { setMode('erase-personal-data'); setReason(''); setConfirmed(false); action.reset() }}>Erase personal data</Button>}
      <Modal open={mode !== null} title={mode === 'close' ? 'Close candidate' : 'Erase personal data'} onClose={() => setMode(null)}>
        <div className="space-y-3 text-sm">
          <ErrorAlert error={action.error} />
          {mode === 'close' ? (
            <p>Closing ends this candidate's process. Pending screenings and unsent interviews are cancelled. A scheduled interview must be cancelled first so the candidate is notified.</p>
          ) : (
            <Alert tone="warning">This permanently removes the name, contact details, resume files and text, evidence quotes, call transcripts, answers and email bodies. Statuses, decisions and the audit trail are kept. This cannot be undone.</Alert>
          )}
          <Field label="Reason"><Textarea required value={reason} onChange={(e) => setReason(e.target.value)} placeholder={mode === 'close' ? 'e.g. Candidate withdrew' : 'e.g. Candidate deletion request received on …'} /></Field>
          {mode === 'erase-personal-data' && (
            <label className="flex items-center gap-2"><input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} /> I understand this is irreversible.</label>
          )}
          <Button variant="danger" loading={action.isPending} disabled={!reason.trim() || (mode === 'erase-personal-data' && !confirmed)}
            onClick={async () => { await action.mutateAsync({ action: mode!, reason }); setMode(null) }}>
            {mode === 'close' ? 'Close candidate' : 'Erase permanently'}
          </Button>
        </div>
      </Modal>
    </>
  )
}
