import { useCandidateEvents } from '../../api/hooks'
import { Card, Empty, ErrorAlert, Loading } from '../../components/ui'
import { formatDate, humanize } from '../../lib/format'

function describe(details: Record<string, unknown>): string {
  const parts: string[] = []
  if (details.from || details.to) parts.push(`${humanize(String(details.from ?? ''))} → ${humanize(String(details.to ?? ''))}`)
  for (const [key, value] of Object.entries(details)) {
    if (['from', 'to'].includes(key) || value === null || value === '' || (Array.isArray(value) && !value.length)) continue
    if (key.endsWith('_id') || key.endsWith('_reference')) continue
    parts.push(`${key.replaceAll('_', ' ')}: ${Array.isArray(value) ? value.join(', ') : typeof value === 'object' ? JSON.stringify(value) : humanize(String(value))}`)
  }
  return parts.join(' · ')
}

/** Append-only audit trail for the candidate (FR-12, FR-14, AC-09). */
export function ActivityPanel({ candidateId }: { candidateId: string }) {
  const events = useCandidateEvents(candidateId)
  return (
    <Card title="Activity and audit history">
      <ErrorAlert error={events.error} />
      {events.isLoading ? <Loading /> : !events.data?.length ? <Empty>No events.</Empty> : (
        <ol className="relative space-y-4 border-l border-slate-200 pl-5">
          {events.data.map((e) => (
            <li key={e.id} className="text-sm">
              <span className="absolute -left-1.5 mt-1.5 h-3 w-3 rounded-full bg-indigo-400 ring-2 ring-white" />
              <div className="font-medium text-slate-900">{humanize(e.event_type)}</div>
              <div className="text-xs text-slate-500">{formatDate(e.created_at)} · {e.actor_name ?? 'System'}</div>
              {describe(e.details) && <div className="mt-0.5 text-xs text-slate-600">{describe(e.details)}</div>}
            </li>
          ))}
        </ol>
      )}
    </Card>
  )
}
