import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useDashboardSummary, usePipeline, useRequisitions, type DashboardSummary } from '../api/hooks'
import { Badge, Card, Empty, ErrorAlert, Input, Loading, PageHeader, Select, Table, Td } from '../components/ui'
import { BROWSER_TZ, CANDIDATE_STATUS_LABELS, formatDate, formatInZone, humanize } from '../lib/format'

function StatTile({ label, value, hint }: { label: string; value: number; hint?: string }) {
  return (
    <div className="rounded-lg bg-white p-4 shadow-sm ring-1 ring-slate-200">
      <div className="text-xs font-medium tracking-wide text-slate-500 uppercase">{label}</div>
      <div className="mt-1 text-3xl font-semibold text-slate-900 tabular-nums">{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  )
}

/** Single-series horizontal bars: one hue, value labelled directly, hover tooltip per bar, no legend. */
function StatusFunnel({ rows }: { rows: DashboardSummary['by_status'] }) {
  const max = Math.max(1, ...rows.map((r) => r.count))
  const total = rows.reduce((sum, r) => sum + r.count, 0)
  return (
    <div className="space-y-1.5" role="list" aria-label="Candidates by lifecycle status">
      {rows.map((r) => (
        <Link key={r.status} to={`/candidates?status=${r.status}`} role="listitem" className="group relative grid grid-cols-[11rem_1fr_2.5rem] items-center gap-3 rounded px-1 py-0.5 text-sm hover:bg-slate-50">
          <span className="truncate text-slate-600">{CANDIDATE_STATUS_LABELS[r.status] ?? r.label}</span>
          <span className="h-3 rounded-r bg-slate-100">
            <span className="block h-3 rounded-r bg-indigo-500 group-hover:bg-indigo-600" style={{ width: `${(r.count / max) * 100}%`, minWidth: r.count ? 4 : 0 }} />
          </span>
          <span className="text-right font-medium text-slate-800 tabular-nums">{r.count}</span>
          <span className="pointer-events-none absolute -top-8 left-48 z-10 hidden rounded bg-slate-900 px-2 py-1 text-xs whitespace-nowrap text-white shadow group-hover:block">
            {CANDIDATE_STATUS_LABELS[r.status]}: {r.count} candidate{r.count === 1 ? '' : 's'} ({total ? Math.round((r.count / total) * 100) : 0}%)
          </span>
        </Link>
      ))}
    </div>
  )
}

const SEVERITY = {
  critical: { icon: '⛔', label: 'Error', cls: 'text-rose-700' },
  warning: { icon: '⚠', label: 'Decision needed', cls: 'text-amber-700' },
  info: { icon: '→', label: 'Next action', cls: 'text-sky-700' },
}

function Pipeline({ requisition }: { requisition: string }) {
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const pipeline = usePipeline({ requisition, status, search, page })
  return (
    <Card title="Candidate pipeline">
      <div className="mb-4 flex flex-wrap gap-3">
        <Input placeholder="Search name or email…" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }} className="max-w-xs" />
        <Select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }} className="max-w-[16rem]"
          options={[{ value: '', label: 'All statuses' }, ...Object.entries(CANDIDATE_STATUS_LABELS).map(([value, label]) => ({ value, label }))]} />
      </div>
      <ErrorAlert error={pipeline.error} />
      {pipeline.isLoading ? <Loading /> : !pipeline.data?.results.length ? <Empty>No candidates.</Empty> : (
        <Table head={['Candidate', 'Requisition', 'Status', 'Score', 'Screening', 'Interview', 'Updated']}>
          {pipeline.data.results.map((r) => (
            <tr key={r.public_id} className="hover:bg-slate-50">
              <Td><Link to={`/candidates/${r.public_id}`} className="font-medium text-indigo-700 hover:underline">{r.name}</Link></Td>
              <Td>{r.requisition_title}</Td>
              <Td><Badge value={r.current_status} /></Td>
              <Td className="tabular-nums">{r.score ?? '—'}{r.confidence && <span className="ml-1 text-xs text-slate-400">{r.confidence.toLowerCase()}</span>}</Td>
              <Td>{r.screening_status ? <><Badge value={r.screening_status} /><div className="mt-0.5 text-xs text-slate-500">{humanize(r.screening_call_status)}</div></> : '—'}</Td>
              <Td>{r.interview_status ? <><Badge value={r.interview_status} />{r.interview_start && <div className="mt-0.5 text-xs text-slate-500">{formatInZone(r.interview_start, r.interview_timezone ?? BROWSER_TZ)}</div>}</> : '—'}</Td>
              <Td className="text-xs">{formatDate(r.updated_at)}</Td>
            </tr>
          ))}
        </Table>
      )}
      {pipeline.data && (pipeline.data.next || pipeline.data.previous) && (
        <div className="mt-4 flex items-center justify-between text-sm">
          <button disabled={!pipeline.data.previous} onClick={() => setPage((p) => p - 1)} className="text-indigo-700 disabled:text-slate-300">← Previous</button>
          <span className="text-slate-500">Page {page} · {pipeline.data.count} candidates</span>
          <button disabled={!pipeline.data.next} onClick={() => setPage((p) => p + 1)} className="text-indigo-700 disabled:text-slate-300">Next →</button>
        </div>
      )}
    </Card>
  )
}

export function DashboardPage() {
  const [requisition, setRequisition] = useState('')
  const requisitions = useRequisitions({ page_size: 100 })
  const summary = useDashboardSummary(requisition || undefined)
  const s = summary.data
  const actionCount = s?.attention.reduce((sum, a) => sum + a.count, 0) ?? 0

  return (
    <>
      <PageHeader
        title="Dashboard"
        subtitle="Lifecycle status, pending human decisions, errors and upcoming interviews (AC-09)."
        actions={
          <Select value={requisition} onChange={(e) => setRequisition(e.target.value)} className="min-w-[14rem]"
            options={[{ value: '', label: 'All requisitions' }, ...(requisitions.data?.results ?? []).map((r) => ({ value: r.reference_code, label: r.title }))]} />
        }
      />
      <ErrorAlert error={summary.error} />
      {summary.isLoading || !s ? <Loading /> : (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile label="Active candidates" value={s.active_candidates} hint={`${s.total_candidates} total incl. closed`} />
            <StatTile label="Open requisitions" value={s.open_requisitions} />
            <StatTile label="Items needing action" value={actionCount} />
            <StatTile label="Interviews (next 14 days)" value={s.upcoming_interviews.length} />
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            <Card title="Candidates by lifecycle status">
              <StatusFunnel rows={s.by_status} />
            </Card>
            <Card title="Needs attention">
              {!s.attention.length ? <Empty>Nothing is waiting on you.</Empty> : (
                <ul className="divide-y divide-slate-100">
                  {s.attention.map((a) => (
                    <li key={a.key}>
                      <Link to={a.link} className="flex items-center justify-between gap-3 py-2 text-sm hover:bg-slate-50">
                        <span className="flex items-center gap-2">
                          <span aria-hidden className={SEVERITY[a.severity].cls}>{SEVERITY[a.severity].icon}</span>
                          <span className={`text-xs font-medium ${SEVERITY[a.severity].cls}`}>{SEVERITY[a.severity].label}</span>
                          <span className="text-slate-700">{a.label}</span>
                        </span>
                        <span className="font-semibold text-slate-900 tabular-nums">{a.count}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
          <Card title="Upcoming interviews" actions={<Link to="/interviews" className="text-sm text-indigo-700 hover:underline">All interviews</Link>}>
            {!s.upcoming_interviews.length ? <Empty>No interviews scheduled in the next 14 days.</Empty> : (
              <Table head={['When (candidate time)', 'Your time', 'Candidate', 'Role', 'Interviewer', 'Format']}>
                {s.upcoming_interviews.map((i) => (
                  <tr key={i.interview_id}>
                    <Td>{formatInZone(i.start, i.timezone)}</Td>
                    <Td>{formatInZone(i.start, BROWSER_TZ, false)}</Td>
                    <Td><Link to={`/candidates/${i.candidate_id}?tab=interview`} className="text-indigo-700 hover:underline">{i.candidate_name}</Link></Td>
                    <Td>{i.requisition_title}</Td>
                    <Td>{i.interviewer_name}</Td>
                    <Td>{humanize(i.mode)}</Td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>
          <Pipeline requisition={requisition} />
          <p className="text-right text-xs text-slate-400">Updated {formatDate(s.generated_at)} · refreshes every minute · <Link to="/activity" className="text-indigo-600 hover:underline">Full audit log</Link></p>
        </div>
      )}
    </>
  )
}
