import { useEffect, useState, type FormEvent } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { keys, useAutoScoring, useEvaluations, useShortlistDecision, useShortlistHistory, useStartScoring } from '../../api/hooks'
import { Alert, Badge, Button, Card, Empty, ErrorAlert, Field, Input, Loading, Select, Textarea } from '../../components/ui'
import { formatDate, humanize } from '../../lib/format'
import type { Candidate, Evaluation } from '../../lib/types'

export function EvaluationView({ evaluation }: { evaluation: Evaluation }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-4">
        <div className="text-3xl font-semibold text-slate-900">{evaluation.overall_score ?? '—'}<span className="text-base text-slate-400">/100</span></div>
        <Badge value={evaluation.confidence_level} label={`${humanize(evaluation.confidence_level)} evidence coverage`} />
        <Badge value={evaluation.recommendation_for_human_review === 'REVIEW_RECOMMENDED' ? 'COMPLETED' : 'NEEDS_MANUAL_REVIEW'} label={humanize(evaluation.recommendation_for_human_review)} />
        <span className="text-xs text-slate-500">v{evaluation.version} · {evaluation.model_version} · {evaluation.prompt_version} · {formatDate(evaluation.created_at)}</span>
      </div>
      {evaluation.overall_score === null && <Alert tone="warning">No assessable evidence — the AI did not produce an overall score. Approval requires a reasoned human score.</Alert>}
      <p className="text-sm whitespace-pre-line text-slate-700">{evaluation.overall_assessment}</p>
      <div className="grid gap-3 lg:grid-cols-2">
        {Object.entries(evaluation.criterion_scores).map(([key, c]) => (
          <div key={key} className="rounded-md p-3 ring-1 ring-slate-200">
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-medium">{c.label} <span className="text-xs text-slate-400">(weight {c.weight})</span></span>
              <span className="flex items-center gap-2"><Badge value={c.evidence_status} /><span className="font-semibold">{c.score ?? '—'}</span></span>
            </div>
            <p className="mt-1 text-xs text-slate-600">{c.rationale}</p>
            {(evaluation.evidence[key] ?? []).map((e, i) => (
              <blockquote key={i} className="mt-2 border-l-2 border-indigo-300 pl-2 text-xs text-slate-700">
                “{e.excerpt}” <span className="text-slate-400">— {e.relevance}</span>
              </blockquote>
            ))}
          </div>
        ))}
      </div>
      {evaluation.missing_or_unclear_items.length > 0 && (
        <div>
          <h4 className="mb-1 text-xs font-semibold text-slate-500 uppercase">Missing or unclear (not proof of absence)</h4>
          <ul className="list-disc space-y-0.5 pl-5 text-xs text-slate-600">{evaluation.missing_or_unclear_items.map((m, i) => <li key={i}>{m}</li>)}</ul>
        </div>
      )}
      {evaluation.parsing_warnings.length > 0 && <Alert tone="warning">{evaluation.parsing_warnings.join(' ')}</Alert>}
    </div>
  )
}

/** Human gate 1 (FR-04): one click approves; decline, hold and score overrides are under "Other decisions". */
const DECLINE_WARNING =
  'Declining closes this candidate and sends them a friendly rejection email. Their resume, contact details, screening answers and evaluation notes are then permanently deleted; only their name is kept for HR. This cannot be undone.'

export function ShortlistDecisionForm({ candidate, evaluation, onDone }: { candidate: Pick<Candidate, 'public_id' | 'email' | 'phone'>; evaluation: Evaluation; onDone?: () => void }) {
  const decide = useShortlistDecision(candidate.public_id)
  const [showOther, setShowOther] = useState(false)
  const [decision, setDecision] = useState('DECLINE')
  const [reason, setReason] = useState('')
  const [override, setOverride] = useState('')
  const [overrideReason, setOverrideReason] = useState('')
  const [result, setResult] = useState<string | null>(null)
  const noContact = !candidate.email && !candidate.phone
  const noScore = evaluation.overall_score === null

  function done(res: { workflow_status: string | null }) {
    setResult(res.workflow_status && res.workflow_status !== 'COMPLETED'
      ? `Decision saved. Workflow status: ${res.workflow_status} — retry the workflow resume from the scoring panel.`
      : 'Decision recorded.')
    onDone?.()
  }

  async function approve() {
    done(await decide.mutateAsync({ evaluation: evaluation.public_id, decision: 'APPROVE_FOR_SCREENING', decision_reason: '' }))
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (decision === 'DECLINE' && !confirm(DECLINE_WARNING)) return
    done(await decide.mutateAsync({
      evaluation: evaluation.public_id, decision, decision_reason: reason,
      score_override: override === '' ? null : Number(override), score_override_reason: overrideReason,
    }))
    setReason('')
  }

  return (
    <div className="space-y-3">
      <ErrorAlert error={decide.error} />
      {result && <Alert tone="success">{result}</Alert>}
      {noContact && <Alert tone="warning">No email or phone number was found in this resume. Add one with Edit details, then approve.</Alert>}
      {noScore && <Alert tone="info">The AI could not calculate a score. To approve, enter a score override under Other decisions.</Alert>}
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={approve} loading={decide.isPending && !showOther} disabled={noContact || noScore}>Approve this candidate</Button>
        <button type="button" className="text-sm text-slate-600 hover:underline" onClick={() => setShowOther(!showOther)}>
          {showOther ? 'Hide other decisions' : 'Other decisions (decline, hold, score override)'}
        </button>
      </div>
      {showOther && (
        <form onSubmit={submit} className="space-y-3 rounded-md bg-slate-50 p-3 ring-1 ring-slate-200">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Decision">
              <Select value={decision} onChange={(e) => setDecision(e.target.value)} options={[
                { value: 'DECLINE', label: 'Decline (rejection email + data deletion)' },
                { value: 'HOLD_FOR_REVIEW', label: 'Hold for manual review' },
                { value: 'APPROVE_FOR_SCREENING', label: 'Approve with a score override' }]} />
            </Field>
            <Field label="Score override (optional)" hint="Never changes the AI evaluation; stored separately">
              <Input type="number" min={0} max={100} value={override} onChange={(e) => setOverride(e.target.value)} />
            </Field>
          </div>
          {decision === 'DECLINE' && <Alert tone="warning">{DECLINE_WARNING}</Alert>}
          <Field label={decision === 'APPROVE_FOR_SCREENING' ? 'Reason (optional)' : 'Reason (required)'}>
            <Textarea required={decision !== 'APPROVE_FOR_SCREENING'} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Job-related reason for this decision" />
          </Field>
          {override !== '' && <Field label="Override reason"><Textarea required value={overrideReason} onChange={(e) => setOverrideReason(e.target.value)} /></Field>}
          <Button type="submit" loading={decide.isPending && showOther} variant={decision === 'DECLINE' ? 'danger' : 'primary'}>Record decision</Button>
        </form>
      )}
    </div>
  )
}

export function ScoringPanel({ candidate, canEdit }: { candidate: Candidate; canEdit: boolean }) {
  const hasResume = candidate.resume_documents.some((d) => d.processing_status === 'COMPLETED')
  const auto = useAutoScoring()
  const autoCandidate = Boolean(auto.data?.enabled) && candidate.current_status === 'RESUME_RECEIVED' && hasResume
  const evaluations = useEvaluations(candidate.public_id, autoCandidate)
  const history = useShortlistHistory(candidate.public_id)
  const start = useStartScoring()
  const latest = evaluations.data?.[0]
  const scorable = ['RESUME_RECEIVED', 'NEEDS_MANUAL_REVIEW', 'SCORED_HR_REVIEW'].includes(candidate.current_status)
  const reviewable = ['SCORED_HR_REVIEW', 'NEEDS_MANUAL_REVIEW'].includes(candidate.current_status)
  const client = useQueryClient()
  // A background (Celery) score arrived: refresh the candidate so its new status and the shortlist form appear.
  useEffect(() => {
    if (latest && candidate.current_status === 'RESUME_RECEIVED') void client.invalidateQueries({ queryKey: keys.candidates })
  }, [latest, candidate.current_status, client])
  const minutes = Math.max(1, Math.round((auto.data?.interval_seconds ?? 120) / 60))

  return (
    <div className="space-y-6">
      <Card title="AI resume evaluation (Agent 1)" actions={canEdit && scorable && (
        <Button size="sm" disabled={!hasResume} loading={start.isPending} onClick={() => start.mutate(candidate.public_id)}
          title={hasResume ? '' : 'Extract a resume first'}>{latest ? 'Re-score resume' : 'Score resume'}</Button>
      )}>
        <div className="space-y-3">
          <ErrorAlert error={start.error} />
          {start.data && start.data.status !== 'WAITING_HR_REVIEW' && <Alert>{start.data.error_message || 'The scoring workflow did not complete. Check the Azure configuration and retry.'}</Alert>}
          {!hasResume && scorable && <Alert tone="info">A successfully extracted resume is required before scoring.</Alert>}
          {autoCandidate && !latest && !start.isPending && (
            <Alert tone="info">
              Automatic scoring is on: new resumes are scored about every {minutes} minute{minutes === 1 ? '' : 's'} while the Celery worker and beat are running. This page updates when the score is ready; you can also click Score resume now. The score still needs your shortlist decision.
            </Alert>
          )}
          {evaluations.isLoading ? <Loading /> : latest ? <EvaluationView evaluation={latest} /> : <Empty>Not scored yet.</Empty>}
        </div>
      </Card>
      {canEdit && reviewable && latest && (
        <Card title="Recruiter shortlist decision (human gate 1)">
          <p className="mb-3 text-sm text-slate-600">The AI score is decision support only. No candidate is contacted until you approve.</p>
          <ShortlistDecisionForm candidate={candidate} evaluation={latest} />
        </Card>
      )}
      <Card title="Shortlist decision history">
        {!history.data?.length ? <Empty>No decisions yet.</Empty> : (
          <ul className="space-y-3 text-sm">
            {history.data.map((h) => (
              <li key={h.public_id} className="rounded-md p-3 ring-1 ring-slate-200">
                <div className="flex flex-wrap items-center gap-2"><Badge value={h.decision === 'DECLINE' ? 'DECLINED' : h.decision === 'APPROVE_FOR_SCREENING' ? 'APPROVED' : 'ON_HOLD'} label={humanize(h.decision)} /> by {h.decided_by_name} · {formatDate(h.created_at)}</div>
                <p className="mt-1 text-slate-700">{h.decision_reason || <em className="text-slate-400">No reason given</em>}</p>
                {h.score_override !== null && <p className="text-xs text-slate-500">Score override {h.score_override}: {h.score_override_reason}</p>}
              </li>
            ))}
          </ul>
        )}
      </Card>
      {evaluations.data && evaluations.data.length > 1 && (
        <Card title="Earlier evaluations">
          <ul className="space-y-1 text-sm">{evaluations.data.slice(1).map((e) => <li key={e.public_id}>v{e.version} · {e.overall_score ?? '—'}/100 · {humanize(e.confidence_level)} · {formatDate(e.created_at)}</li>)}</ul>
        </Card>
      )}
    </div>
  )
}
