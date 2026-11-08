import { useState } from 'react'
import { useCommunicationAction, useCommunications, useDraftInvitation, useUpdateDraft } from '../../api/hooks'
import { Alert, Badge, Button, Card, Empty, ErrorAlert, Field, Input, Modal, Textarea } from '../../components/ui'
import { formatDate, humanize } from '../../lib/format'
import type { CommunicationLog, Interview } from '../../lib/types'

/** Draft → edit → explicit HR approval → send (FR-10, FR-11, AC-08). */
export function MessageEditor({ log }: { log: CommunicationLog }) {
  const update = useUpdateDraft()
  const action = useCommunicationAction()
  const [subject, setSubject] = useState(log.subject)
  const [body, setBody] = useState(log.body)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [confirmed, setConfirmed] = useState(false)
  const editable = log.approval_status === 'DRAFT'
  const dirty = subject !== log.subject || body !== log.body
  const canSend = log.send_status === 'NOT_SENT' || log.send_status === 'FAILED'

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge value={log.approval_status === 'DRAFT' ? 'PENDING' : log.approval_status} label={humanize(log.approval_status)} />
        <Badge value={log.send_status === 'NOT_SENT' ? 'PENDING' : log.send_status} label={humanize(log.send_status)} />
        <span className="text-slate-500">{humanize(log.kind)} · to {log.recipient}{log.cc.length ? ` · cc ${log.cc.join(', ')}` : ''} · template {log.template_version}</span>
      </div>
      <ErrorAlert error={update.error ?? action.error} />
      {log.send_status === 'FAILED' && <Alert>{log.error_message} The invitation has NOT been sent.</Alert>}
      <Field label="Subject"><Input value={subject} disabled={!editable} onChange={(e) => setSubject(e.target.value)} /></Field>
      <Field label="Body"><Textarea rows={14} value={body} disabled={!editable} onChange={(e) => setBody(e.target.value)} className="font-mono text-xs" /></Field>
      {canSend && (
        <div className="flex flex-wrap gap-2">
          {editable && <Button variant="secondary" disabled={!dirty} loading={update.isPending} onClick={() => update.mutate({ id: log.public_id, subject, body })}>Save draft</Button>}
          <Button variant="success" disabled={dirty} title={dirty ? 'Save your edits first' : ''} onClick={() => { setConfirmed(false); setConfirmOpen(true) }}>
            {log.send_status === 'FAILED' ? 'Retry sending' : 'Approve and send'}
          </Button>
          {editable && <Button variant="ghost" loading={action.isPending && action.variables?.action === 'discard'} onClick={() => action.mutate({ id: log.public_id, action: 'discard' })}>Discard draft</Button>}
        </div>
      )}
      {log.send_status === 'SENT' && (
        <Alert tone="success">Sent {formatDate(log.sent_at)} · {log.auto_sent ? `sent automatically by the scheduling agent after ${log.approved_by_name} approved the screening` : `approved by ${log.approved_by_name}`} · provider {log.provider} · message id {log.provider_message_id}</Alert>
      )}
      <Modal open={confirmOpen} title="Confirm sending" onClose={() => setConfirmOpen(false)}>
        <div className="space-y-3 text-sm">
          <p>This email will be sent to <strong>{log.recipient}</strong> with a calendar attachment. Your approval is recorded in the audit trail.</p>
          <label className="flex items-start gap-2"><input type="checkbox" className="mt-1" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} /> I reviewed the candidate, interviewer, date, time zone, meeting details and email content.</label>
          <Button variant="success" disabled={!confirmed} loading={action.isPending}
            onClick={async () => { try { await action.mutateAsync({ id: log.public_id, action: 'approve-send' }) } finally { setConfirmOpen(false) } }}>
            Approve and send now
          </Button>
        </div>
      </Modal>
    </div>
  )
}

export function InvitationSection({ interview }: { interview: Interview }) {
  const logs = useCommunications({ interview: interview.public_id })
  const draft = useDraftInvitation()
  const open = logs.data?.find((l) => l.approval_status !== 'DISCARDED' && l.sequence === interview.sequence && l.kind !== 'INTERVIEW_CANCELLATION')
  if (interview.status !== 'SLOT_CONFIRMED') return null
  return (
    <div className="space-y-3 rounded-md bg-slate-50 p-4 ring-1 ring-slate-200">
      <h4 className="text-sm font-semibold">{interview.sequence > 0 ? 'Updated invitation' : 'Interview invitation'} (human gate 3)</h4>
      <ErrorAlert error={draft.error} />
      {open ? <MessageEditor key={open.public_id + open.subject + open.body} log={open} /> : (
        <Button loading={draft.isPending} onClick={() => draft.mutate(interview.public_id)}>Draft invitation email</Button>
      )}
    </div>
  )
}

export function CommunicationsCard({ candidateId }: { candidateId: string }) {
  const logs = useCommunications({ candidate: candidateId })
  const pending = logs.data?.filter((l) => l.kind === 'INTERVIEW_CANCELLATION' && l.send_status !== 'SENT' && l.approval_status !== 'DISCARDED')
  return (
    <Card title="Communication log">
      <div className="space-y-4">
        {pending?.map((l) => (
          <div key={l.public_id} className="rounded-md bg-amber-50 p-4 ring-1 ring-amber-200">
            <p className="mb-2 text-sm font-medium text-amber-900">A cancellation notice is waiting for your approval.</p>
            <MessageEditor key={l.public_id + l.subject + l.body} log={l} />
          </div>
        ))}
        {!logs.data?.length ? <Empty>No candidate communications yet.</Empty> : (
          <ul className="divide-y divide-slate-100 text-sm">
            {logs.data.map((l) => (
              <li key={l.public_id} className="py-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span>{humanize(l.kind)} · {l.subject}</span>
                  <span className="flex items-center gap-2 text-xs text-slate-500">
                    {l.auto_sent && <Badge value="INFO" label="Sent automatically" />}
                    <Badge value={l.send_status === 'NOT_SENT' ? 'PENDING' : l.send_status} label={humanize(l.send_status)} />
                    {l.sent_at ? formatDate(l.sent_at) : formatDate(l.created_at)}
                  </span>
                </div>
                <details className="mt-1 text-xs text-slate-600">
                  <summary className="cursor-pointer text-indigo-700">Read the email (to {l.recipient})</summary>
                  <pre className="mt-2 rounded-md bg-slate-50 p-3 font-mono whitespace-pre-wrap ring-1 ring-slate-200">{l.body}</pre>
                </details>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  )
}
