import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useActivityLog, useEventTypes } from '../api/hooks'
import { Card, Empty, ErrorAlert, Loading, PageHeader, Select, Table, Td } from '../components/ui'
import { formatDate, humanize } from '../lib/format'

function details(d: Record<string, unknown>) {
  return Object.entries(d)
    .filter(([k, v]) => v !== null && v !== '' && !k.endsWith('_id') && !k.endsWith('_reference'))
    .map(([k, v]) => `${k.replaceAll('_', ' ')}: ${typeof v === 'object' ? JSON.stringify(v) : humanize(String(v))}`)
    .join(' · ')
}

/** Append-only audit trail across all visible candidates (FR-14, SRS §13). */
export function ActivityLogPage() {
  const [eventType, setEventType] = useState('')
  const [page, setPage] = useState(1)
  const types = useEventTypes()
  const log = useActivityLog({ event_type: eventType, page })
  return (
    <>
      <PageHeader title="Audit log" subtitle="Every status change, human approval, call attempt, calendar check and email, newest first." />
      <Card>
        <div className="mb-4 max-w-xs">
          <Select value={eventType} onChange={(e) => { setEventType(e.target.value); setPage(1) }}
            options={[{ value: '', label: 'All event types' }, ...(types.data ?? []).map((t) => ({ value: t.value, label: t.label }))]} />
        </div>
        <ErrorAlert error={log.error} />
        {log.isLoading ? <Loading /> : !log.data?.results.length ? <Empty>No events.</Empty> : (
          <Table head={['Time', 'Event', 'Candidate', 'Actor', 'Details']}>
            {log.data.results.map((e) => (
              <tr key={e.id}>
                <Td className="text-xs whitespace-nowrap">{formatDate(e.created_at)}</Td>
                <Td className="font-medium">{humanize(e.event_type)}</Td>
                <Td><Link to={`/candidates/${e.candidate_id}?tab=activity`} className="text-indigo-700 hover:underline">{e.candidate_name}</Link></Td>
                <Td>{e.actor_name ?? 'System'}</Td>
                <Td className="max-w-md text-xs text-slate-600">{details(e.details)}</Td>
              </tr>
            ))}
          </Table>
        )}
        {log.data && (log.data.next || log.data.previous) && (
          <div className="mt-4 flex items-center justify-between text-sm">
            <button disabled={!log.data.previous} onClick={() => setPage((p) => p - 1)} className="text-indigo-700 disabled:text-slate-300">← Newer</button>
            <span className="text-slate-500">Page {page} · {log.data.count} events</span>
            <button disabled={!log.data.next} onClick={() => setPage((p) => p + 1)} className="text-indigo-700 disabled:text-slate-300">Older →</button>
          </div>
        )}
      </Card>
    </>
  )
}
