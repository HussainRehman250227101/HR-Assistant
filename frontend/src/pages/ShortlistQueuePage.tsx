import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useRequisitions, useShortlistQueue } from '../api/hooks'
import { Badge, Card, Empty, ErrorAlert, Loading, PageHeader, Select } from '../components/ui'
import { EvaluationView, ShortlistDecisionForm } from './candidates/ScoringPanel'

export function ShortlistQueuePage() {
  const [requisition, setRequisition] = useState('')
  const queue = useShortlistQueue(requisition || undefined)
  const requisitions = useRequisitions({ page_size: 100, status: 'OPEN' })
  const [expanded, setExpanded] = useState<string | null>(null)
  const items = [...(queue.data?.results ?? [])].sort((a, b) => (b.evaluation.overall_score ?? -1) - (a.evaluation.overall_score ?? -1))

  return (
    <>
      <PageHeader title="Shortlist review" subtitle="Candidates ranked by evidence-based score. Every progression requires your explicit decision (FR-04, AC-04)." />
      <div className="mb-4 max-w-xs">
        <Select value={requisition} onChange={(e) => setRequisition(e.target.value)}
          options={[{ value: '', label: 'All open requisitions' }, ...(requisitions.data?.results ?? []).map((r) => ({ value: r.reference_code, label: r.title }))]} />
      </div>
      <ErrorAlert error={queue.error} />
      {queue.isLoading ? <Loading /> : !items.length ? <Card><Empty>No candidates are awaiting shortlist review.</Empty></Card> : (
        <div className="space-y-3">
          {items.map(({ candidate, evaluation }, rank) => (
            <Card key={candidate.public_id}>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <span className="text-sm text-slate-400">#{rank + 1}</span>
                  <span className="text-2xl font-semibold">{evaluation.overall_score ?? '—'}</span>
                  <div>
                    <Link to={`/candidates/${candidate.public_id}?tab=scoring`} className="font-medium text-indigo-700 hover:underline">{candidate.full_name || 'Identity details pending review'}</Link>
                    <div className="text-xs text-slate-500">{candidate.requisition_title}</div>
                  </div>
                  <Badge value={evaluation.confidence_level} label={`${evaluation.confidence_level.toLowerCase()} coverage`} />
                  <Badge value={candidate.current_status} />
                  {candidate.identity_review_required && <Badge tone="amber" label="Identity review" />}
                </div>
                <button className="text-sm text-indigo-700 hover:underline" onClick={() => setExpanded(expanded === candidate.public_id ? null : candidate.public_id)}>
                  {expanded === candidate.public_id ? 'Close' : 'Review evidence & decide'}
                </button>
              </div>
              {expanded === candidate.public_id && (
                <div className="mt-4 grid gap-6 border-t border-slate-100 pt-4 lg:grid-cols-2">
                  <EvaluationView evaluation={evaluation} />
                  <ShortlistDecisionForm candidate={candidate} evaluation={evaluation} onDone={() => setExpanded(null)} />
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </>
  )
}
