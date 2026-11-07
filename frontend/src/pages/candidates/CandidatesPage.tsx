import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useCandidates, useRequisitions } from '../../api/hooks'
import { Badge, Card, Empty, ErrorAlert, Input, Loading, PageHeader, Select, Table, Td } from '../../components/ui'
import { CANDIDATE_STATUS_LABELS, formatDate } from '../../lib/format'

export function CandidatesPage() {
  const [params, setParams] = useSearchParams()
  const status = params.get('status') ?? ''
  const requisition = params.get('requisition') ?? ''
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const candidates = useCandidates({ status, requisition, search, page })
  const requisitions = useRequisitions({ page_size: 100 })

  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next)
    setPage(1)
  }

  return (
    <>
      <PageHeader title="Candidates" subtitle="All candidates you are authorised to see, with their current lifecycle status (FR-12)." />
      <Card>
        <div className="mb-4 flex flex-wrap gap-3">
          <Input placeholder="Search name or email…" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }} className="max-w-xs" />
          <Select value={status} onChange={(e) => update('status', e.target.value)} className="max-w-[16rem]"
            options={[{ value: '', label: 'All statuses' }, ...Object.entries(CANDIDATE_STATUS_LABELS).map(([value, label]) => ({ value, label }))]} />
          <Select value={requisition} onChange={(e) => update('requisition', e.target.value)} className="max-w-[16rem]"
            options={[{ value: '', label: 'All requisitions' }, ...(requisitions.data?.results ?? []).map((r) => ({ value: r.reference_code, label: r.title }))]} />
        </div>
        <ErrorAlert error={candidates.error} />
        {candidates.isLoading ? <Loading /> : !candidates.data?.results.length ? <Empty>No candidates match.</Empty> : (
          <Table head={['Candidate', 'Requisition', 'Status', 'Contact', 'Updated']}>
            {candidates.data.results.map((c) => (
              <tr key={c.public_id} className="hover:bg-slate-50">
                <Td>
                  <Link to={`/candidates/${c.public_id}`} className="font-medium text-indigo-700 hover:underline">{c.display_name}</Link>
                  {c.identity_review_required && <span className="ml-2"><Badge tone="amber" label="Identity review" /></span>}
                </Td>
                <Td>{requisitions.data?.results.find((r) => r.id === c.requisition)?.title ?? `#${c.requisition}`}</Td>
                <Td><Badge value={c.current_status} /></Td>
                <Td className="text-xs text-slate-600">{c.email || '—'}<br />{c.phone || ''}</Td>
                <Td>{formatDate(c.updated_at)}</Td>
              </tr>
            ))}
          </Table>
        )}
        {candidates.data && (candidates.data.next || candidates.data.previous) && (
          <div className="mt-4 flex items-center justify-between text-sm">
            <button disabled={!candidates.data.previous} onClick={() => setPage((p) => p - 1)} className="text-indigo-700 disabled:text-slate-300">← Previous</button>
            <span className="text-slate-500">Page {page} · {candidates.data.count} total</span>
            <button disabled={!candidates.data.next} onClick={() => setPage((p) => p + 1)} className="text-indigo-700 disabled:text-slate-300">Next →</button>
          </div>
        )}
      </Card>
    </>
  )
}
