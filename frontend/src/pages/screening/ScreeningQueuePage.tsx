import { Fragment, useState } from 'react'
import { Link } from 'react-router-dom'
import { useScreeningQueue } from '../../api/hooks'
import { Badge, Card, Empty, ErrorAlert, Loading, PageHeader, Select, Table, Td } from '../../components/ui'
import { formatDate, humanize } from '../../lib/format'
import { ScreeningResult } from './ScreeningResult'
import { ScreeningReviewForm } from './ScreeningReviewForm'

const STATUSES = ['', 'AWAITING_HR_REVIEW', 'PENDING_CALL', 'CALL_IN_PROGRESS', 'ANALYSIS_FAILED', 'AWAITING_MANUAL_RESULT']

export function ScreeningQueuePage() {
  const [status, setStatus] = useState('AWAITING_HR_REVIEW')
  const [open, setOpen] = useState<string | null>(null)
  const queue = useScreeningQueue({ status: status || undefined })
  return (
    <>
      <PageHeader title="Screening" subtitle="Screening results awaiting your decision, calls to place, and failures needing action (FR-05–FR-08)." />
      <Card>
        <div className="mb-4 max-w-xs">
          <Select value={status} onChange={(e) => setStatus(e.target.value)} options={STATUSES.map((s) => ({ value: s, label: s ? humanize(s) : 'All active' }))} />
        </div>
        <ErrorAlert error={queue.error} />
        {queue.isLoading ? <Loading /> : !queue.data?.length ? <Empty>Nothing here.</Empty> : (
          <Table head={['Candidate', 'Requisition', 'Channel', 'Status', 'Call result', 'Recommended next step', 'Updated', '']}>
            {queue.data.map((s) => (
              <Fragment key={s.public_id}>
                <tr className="hover:bg-slate-50">
                  <Td><Link to={`/candidates/${s.candidate_reference}?tab=screening`} className="font-medium text-indigo-700 hover:underline">{s.candidate_name || 'Candidate'}</Link></Td>
                  <Td>{s.requisition_title}</Td>
                  <Td>{s.channel === 'AI_VOICE' ? `AI call (${s.attempt_count}/${s.max_attempts})` : 'Human-led'}</Td>
                  <Td><Badge value={s.status} /></Td>
                  <Td><Badge value={s.call_status} /></Td>
                  <Td className="text-xs">{humanize(s.recommended_next_step_for_human_review)}</Td>
                  <Td>{formatDate(s.updated_at)}</Td>
                  <Td>
                    {s.status === 'AWAITING_HR_REVIEW' && (
                      <button className="text-sm text-indigo-700 hover:underline" onClick={() => setOpen(open === s.public_id ? null : s.public_id)}>
                        {open === s.public_id ? 'Close' : 'Review'}
                      </button>
                    )}
                  </Td>
                </tr>
                {open === s.public_id && (
                  <tr>
                    <td colSpan={8} className="bg-white p-4">
                      <div className="grid gap-6 lg:grid-cols-2">
                        <ScreeningResult screening={s} />
                        <ScreeningReviewForm screening={s} />
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
