import { Fragment, useState } from 'react'
import { Link } from 'react-router-dom'
import { useScreeningAction, useScreeningQueue } from '../../api/hooks'
import { QuickDecision } from '../../components/QuickDecision'
import type { Screening } from '../../lib/types'
import { Badge, Card, Empty, ErrorAlert, Loading, PageHeader, Select, Table, Td } from '../../components/ui'
import { formatDate, humanize } from '../../lib/format'
import { ScreeningJobPanel } from './ScreeningJobPanel'
import { ScreeningResult } from './ScreeningResult'
import { ScreeningReviewForm } from './ScreeningReviewForm'

const STATUSES = ['', 'AWAITING_HR_REVIEW', 'PENDING_CALL', 'CALL_IN_PROGRESS', 'ANALYSIS_FAILED', 'AWAITING_MANUAL_RESULT']

function RowActions({ screening }: { screening: Screening }) {
  const action = useScreeningAction()
  const review = (body: object) => action.mutateAsync({ id: screening.public_id, action: 'review', body })
  return (
    <QuickDecision
      pending={action.isPending}
      error={action.error}
      onApprove={() => review({ decision: 'APPROVE_FOR_INTERVIEW', decision_reason: '' })}
      onReject={(reason) => review({ decision: 'DECLINE', decision_reason: reason })}
    />
  )
}

export function ScreeningQueuePage() {
  const [status, setStatus] = useState('AWAITING_HR_REVIEW')
  const [open, setOpen] = useState<string | null>(null)
  const queue = useScreeningQueue({ status: status || undefined })
  return (
    <>
      <PageHeader title="Screening" subtitle="Screening results awaiting your decision, AI screenings to run (browser sessions or calls), and failures needing action (FR-05–FR-08)." />
      <Card>
        <div className="mb-4 max-w-xs">
          <Select value={status} onChange={(e) => setStatus(e.target.value)} options={STATUSES.map((s) => ({ value: s, label: s ? humanize(s) : 'All active' }))} />
        </div>
        <ErrorAlert error={queue.error} />
        {queue.isLoading ? <Loading /> : !queue.data?.length ? <Empty>Nothing here.</Empty> : (
          <Table head={['Candidate', 'Requisition', 'Channel', 'Status', 'Call / session result', 'Recommended next step', 'Updated', '']}>
            {queue.data.map((s) => (
              <Fragment key={s.public_id}>
                <tr className="hover:bg-slate-50">
                  <Td><Link to={`/candidates/${s.candidate_reference}?tab=screening`} className="font-medium text-indigo-700 hover:underline">{s.candidate_name || 'Candidate'}</Link></Td>
                  <Td>{s.requisition_title}</Td>
                  <Td>{s.channel === 'AI_VOICE' ? `AI call (${s.attempt_count}/${s.max_attempts})` : s.channel === 'BROWSER_VOICE' ? `Browser session (${s.attempt_count}/${s.max_attempts})` : 'Human-led'}</Td>
                  <Td><Badge value={s.status} /></Td>
                  <Td>
                    <Badge value={s.call_status} />
                    {s.channel === 'BROWSER_VOICE' && ['PENDING_CALL', 'CALL_IN_PROGRESS'].includes(s.status) && (
                      <Link to={`/screening/${s.public_id}/browser`} className="ml-2 text-xs text-indigo-700 hover:underline">Open session</Link>
                    )}
                  </Td>
                  <Td className="text-xs">{humanize(s.recommended_next_step_for_human_review)}</Td>
                  <Td>{formatDate(s.updated_at)}</Td>
                  <Td>
                    {s.status === 'AWAITING_HR_REVIEW' && (
                      <div className="space-y-2">
                        <RowActions screening={s} />
                        <button className="text-sm text-indigo-700 hover:underline" onClick={() => setOpen(open === s.public_id ? null : s.public_id)}>
                          {open === s.public_id ? 'Close' : 'Detailed review'}
                        </button>
                      </div>
                    )}
                  </Td>
                </tr>
                {open === s.public_id && (
                  <tr>
                    <td colSpan={8} className="bg-white p-4">
                      <div className="grid gap-6 lg:grid-cols-2">
                        <ScreeningResult screening={s} />
                        <div className="space-y-6">
                          <ScreeningJobPanel screening={s} />
                          <ScreeningReviewForm screening={s} />
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </Table>
        )}
      </Card>
    </>
  )
}
