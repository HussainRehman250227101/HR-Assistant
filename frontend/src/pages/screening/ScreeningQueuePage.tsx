import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useScreeningQueue } from '../../api/hooks'
import { Badge, Card, Empty, ErrorAlert, Loading, PageHeader, Select, Table, Td } from '../../components/ui'
import { formatDate, humanize } from '../../lib/format'

const STATUSES = ['', 'PENDING_CALL', 'CALL_IN_PROGRESS', 'ANALYSIS_FAILED', 'AWAITING_MANUAL_RESULT', 'AWAITING_HR_REVIEW']

export function ScreeningQueuePage() {
  const [status, setStatus] = useState('')
  const queue = useScreeningQueue({ status: status || undefined })
  return (
    <>
      <PageHeader title="Screening" subtitle="Active screenings: calls to place, calls in progress, failures and results awaiting your review (FR-05–FR-08)." />
      <Card>
        <div className="mb-4 max-w-xs">
          <Select value={status} onChange={(e) => setStatus(e.target.value)} options={STATUSES.map((s) => ({ value: s, label: s ? humanize(s) : 'All active' }))} />
        </div>
        <ErrorAlert error={queue.error} />
        {queue.isLoading ? <Loading /> : !queue.data?.length ? <Empty>No active screenings.</Empty> : (
          <Table head={['Candidate', 'Requisition', 'Channel', 'Status', 'Last call result', 'Attempts', 'Updated']}>
            {queue.data.map((s) => (
              <tr key={s.public_id} className="hover:bg-slate-50">
                <Td><Link to={`/candidates/${s.candidate_reference}?tab=screening`} className="font-medium text-indigo-700 hover:underline">{s.candidate_name || 'Candidate'}</Link></Td>
                <Td>{s.requisition_title}</Td>
                <Td>{s.channel === 'AI_VOICE' ? 'AI call' : 'Human-led'}</Td>
                <Td><Badge value={s.status} /></Td>
                <Td><Badge value={s.call_status} /></Td>
                <Td>{s.channel === 'AI_VOICE' ? `${s.attempt_count}/${s.max_attempts}` : '—'}</Td>
                <Td>{formatDate(s.updated_at)}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </>
  )
}
