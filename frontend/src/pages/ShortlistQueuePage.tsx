import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useRequisitions, useShortlistDecision, useShortlistQueue } from '../api/hooks'
import { QuickDecision } from '../components/QuickDecision'
import type { ShortlistQueueItem } from '../lib/types'
import { Badge, Card, Empty, ErrorAlert, Loading, PageHeader, Select } from '../components/ui'
import { EvaluationView, ShortlistDecisionForm } from './candidates/ScoringPanel'

function RowActions({ item }: { item: ShortlistQueueItem }) {
  const { candidate, evaluation } = item
  const decide = useShortlistDecision(candidate.public_id)
  const noContact = !candidate.email && !candidate.phone
  const noScore = evaluation.overall_score === null
  return (
    <QuickDecision
      pending={decide.isPending}
      error={decide.error}
      approveDisabled={noContact || noScore}
      approveHint={noContact ? 'No email or phone: open the candidate to add one.' : noScore ? 'No AI score: open the candidate to approve with a score override.' : undefined}
      onApprove={() => decide.mutateAsync({ evaluation: evaluation.public_id, decision: 'APPROVE_FOR_SCREENING', decision_reason: '' })}
      onReject={(reason) => decide.mutateAsync({ evaluation: evaluation.public_id, decision: 'DECLINE', decision_reason: reason })}
    />
  )
}

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
          {items.map((item, rank) => {
            const { candidate, evaluation } = item
            return (
            <Card key={candidate.public_id}>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <span className="text-sm text-slate-400">#{rank + 1}</span>
                  <span className="text-2xl font-semibold">{evaluation.overall_score ?? '—'}</span>
                  <div>
                    <Link to={`/candidates/${candidate.public_id}?tab=scoring`} className="font-medium text-indigo-700 hover:underline">{candidate.full_name || `Candidate ${candidate.public_id.slice(0, 8)}`}</Link>
                    <div className="text-xs text-slate-500">{candidate.requisition_title}</div>
                  </div>
                  <Badge value={evaluation.confidence_level} label={`${evaluation.confidence_level.toLowerCase()} coverage`} />
                  <Badge value={candidate.current_status} />
                  {candidate.identity_review_required && <Badge tone="amber" label="Contact details missing" />}
                </div>
                <div className="flex flex-wrap items-start gap-4">
                  <RowActions item={item} />
                  <button className="pt-1 text-sm text-indigo-700 hover:underline" onClick={() => setExpanded(expanded === candidate.public_id ? null : candidate.public_id)}>
                    {expanded === candidate.public_id ? 'Close' : 'Review evidence & decide'}
                  </button>
                </div>
              </div>
              {expanded === candidate.public_id && (
                <div className="mt-4 grid gap-6 border-t border-slate-100 pt-4 lg:grid-cols-2">
                  <EvaluationView evaluation={evaluation} />
                  <ShortlistDecisionForm candidate={candidate} evaluation={evaluation} onDone={() => setExpanded(null)} />
                </div>
              )}
            </Card>
            )
          })}
        </div>
      )}
    </>
  )
}
