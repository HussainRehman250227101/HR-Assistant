import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useRequisitions } from '../../api/hooks'
import { useAuth } from '../../auth/AuthContext'
import { Badge, Card, Empty, ErrorAlert, Input, Loading, PageHeader, Select, Table, Td } from '../../components/ui'
import { formatDate } from '../../lib/format'

export function RequisitionsPage() {
  const { hasFullAccess } = useAuth()
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const query = useRequisitions({ status, search, page })

  return (
    <>
      <PageHeader
        title="Job requisitions"
        subtitle="Define roles, job requirements and approved screening questions (FR-01)."
        actions={hasFullAccess && <Link to="/requisitions/new" className="rounded-md bg-indigo-600 px-3.5 py-2 text-sm font-medium text-white hover:bg-indigo-700">New requisition</Link>}
      />
      <Card>
        <div className="mb-4 flex flex-wrap gap-3">
          <Input placeholder="Search title, department, location…" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }} className="max-w-xs" />
          <Select
            value={status}
            onChange={(e) => { setStatus(e.target.value); setPage(1) }}
            className="max-w-[12rem]"
            options={[{ value: '', label: 'All statuses' }, ...['DRAFT', 'OPEN', 'ON_HOLD', 'CLOSED'].map((s) => ({ value: s, label: s.replace('_', ' ') }))]}
          />
        </div>
        <ErrorAlert error={query.error} />
        {query.isLoading ? <Loading /> : query.data && query.data.results.length === 0 ? <Empty>No requisitions found.</Empty> : (
          <Table head={['Title', 'Department', 'Location', 'Status', 'Hiring manager', 'Created']}>
            {query.data?.results.map((r) => (
              <tr key={r.reference_code} className="hover:bg-slate-50">
                <Td><Link className="font-medium text-indigo-700 hover:underline" to={`/requisitions/${r.reference_code}`}>{r.title}</Link></Td>
                <Td>{r.department}</Td>
                <Td>{r.location || '—'} · {r.work_mode.toLowerCase()}</Td>
                <Td><Badge value={r.status} /></Td>
                <Td>{r.hiring_manager_name ?? '—'}</Td>
                <Td>{formatDate(r.created_at, false)}</Td>
              </tr>
            ))}
          </Table>
        )}
        {query.data && (query.data.next || query.data.previous) && (
          <div className="mt-4 flex items-center justify-between text-sm">
            <button disabled={!query.data.previous} onClick={() => setPage((p) => p - 1)} className="text-indigo-700 disabled:text-slate-300">← Previous</button>
            <span className="text-slate-500">Page {page} · {query.data.count} total</span>
            <button disabled={!query.data.next} onClick={() => setPage((p) => p + 1)} className="text-indigo-700 disabled:text-slate-300">Next →</button>
          </div>
        )}
      </Card>
    </>
  )
}
