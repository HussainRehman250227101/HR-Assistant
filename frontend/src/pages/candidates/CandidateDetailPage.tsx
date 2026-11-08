import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useCandidate, useRequisitions } from '../../api/hooks'
import { useAuth } from '../../auth/AuthContext'
import { Alert, Badge, Button, Card, ErrorAlert, KeyValue, Loading, PageHeader, Tabs } from '../../components/ui'
import { CANDIDATE_STATUS_ORDER, formatDate, humanize } from '../../lib/format'
import type { Candidate } from '../../lib/types'
import { InterviewPanel } from '../interviews/InterviewPanel'
import { ScreeningPanel } from '../screening/ScreeningPanel'
import { ActivityPanel } from './ActivityPanel'
import { CandidateFormModal } from './CandidateFormModal'
import { PrivacyActions } from './PrivacyActions'
import { ResumesPanel } from './ResumesPanel'
import { ScoringPanel } from './ScoringPanel'

type Tab = 'overview' | 'scoring' | 'screening' | 'interview' | 'activity'

function fromResume(c: Candidate, field: string, value: string | null) {
  if (!value) return null
  return c.auto_filled_fields?.includes(field)
    ? <span>{value} <span className="ml-1 rounded bg-slate-100 px-1 text-xs text-slate-500">from resume</span></span>
    : value
}

function Stepper({ status }: { status: string }) {
  const steps = CANDIDATE_STATUS_ORDER.filter((s) => s !== 'CLOSED' && s !== 'NEEDS_MANUAL_REVIEW')
  const index = steps.indexOf(status)
  return (
    <ol className="flex flex-wrap gap-1 text-xs">
      {steps.map((s, i) => (
        <li key={s} className={`rounded px-2 py-1 ${i < index ? 'bg-indigo-100 text-indigo-800' : i === index ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-500'}`}>{humanize(s)}</li>
      ))}
    </ol>
  )
}

export function CandidateDetailPage() {
  const { id } = useParams()
  const [params, setParams] = useSearchParams()
  const { hasFullAccess } = useAuth()
  const candidate = useCandidate(id)
  // The interviewer-only HR Recruiter sees the candidate and the interview, not scoring, screening or the audit trail.
  const visibleTabs: Tab[] = hasFullAccess ? ['overview', 'scoring', 'screening', 'interview', 'activity'] : ['overview', 'interview']
  const requestedTab = params.get('tab') as Tab | null
  const tab: Tab = requestedTab && visibleTabs.includes(requestedTab) ? requestedTab : 'overview'
  const requisitions = useRequisitions({ page_size: 100 })
  const [editOpen, setEditOpen] = useState(false)

  if (candidate.isLoading) return <Loading />
  if (!candidate.data) return <ErrorAlert error={candidate.error} />
  const c = candidate.data
  const requisition = requisitions.data?.results.find((r) => r.id === c.requisition)

  return (
    <>
      <PageHeader
        title={<span className="flex flex-wrap items-center gap-3">{c.display_name} <Badge value={c.current_status} /></span>}
        subtitle={requisition ? <Link className="text-indigo-700 hover:underline" to={`/requisitions/${requisition.reference_code}`}>{requisition.title}</Link> : null}
        actions={<>
          {hasFullAccess && c.current_status !== 'CLOSED' && <Button variant="secondary" onClick={() => setEditOpen(true)}>Edit details</Button>}
          <PrivacyActions candidate={c} />
        </>}
      />
      {c.personal_data_erased_at && <div className="mb-4"><Alert tone="info">Personal data erased on {formatDate(c.personal_data_erased_at)}. Only the audit record{c.full_name ? ' and the name' : ''} remain{c.full_name ? '' : 's'}.</Alert></div>}
      <div className="mb-4"><Stepper status={c.current_status} /></div>
      {c.current_status === 'CLOSED' && <div className="mb-4"><Alert tone="info">Closed: {c.closed_reason || 'no reason recorded'}</Alert></div>}
      {c.identity_review_required && c.current_status !== 'CLOSED' && (
        <div className="mb-4">
          {c.resume_documents.some((d) => d.processing_status === 'COMPLETED')
            ? <Alert tone="warning">No email or phone number could be read from this resume (or the email belongs to another applicant for this job). Add one with Edit details before approving.</Alert>
            : <Alert tone="info">The name and contact details will be read from the resume automatically once it is processed.</Alert>}
        </div>
      )}
      <Tabs<Tab>
        value={tab}
        onChange={(v) => setParams({ tab: v })}
        tabs={([
          { value: 'overview', label: 'Overview & resumes' },
          { value: 'scoring', label: 'Scoring & shortlist' },
          { value: 'screening', label: 'Screening' },
          { value: 'interview', label: 'Interview' },
          { value: 'activity', label: 'Activity' },
        ] as { value: Tab; label: string }[]).filter((t) => visibleTabs.includes(t.value))}
      />
      {tab === 'overview' && (
        <div className="space-y-6">
          <Card title="Candidate details">
            {c.auto_filled_fields?.length > 0 && <p className="mb-3 text-xs text-slate-500">Fields marked “from resume” were read automatically from the candidate's resume.</p>}
            <KeyValue items={[
              ['Name', fromResume(c, 'full_name', c.full_name)], ['Email', fromResume(c, 'email', c.email)],
              ['Phone', fromResume(c, 'phone', c.phone)], ['Location', fromResume(c, 'location', c.location)],
              ['LinkedIn', fromResume(c, 'linkedin_url', c.linkedin_url)],
              ['Source', humanize(c.source)], ['Contact consent', <Badge key="cc" value={c.contact_consent_status} />],
              ['Recording consent', <Badge key="rc" value={c.recording_consent_status} />],
              ['Automated calls', c.consent_preferences?.automated_call_opt_out ? 'Opted out' : 'Allowed'],
              ['Added by', c.created_by_name], ['Added', formatDate(c.created_at)],
            ]} />
          </Card>
          <ResumesPanel candidate={c} canEdit={hasFullAccess} />
        </div>
      )}
      {tab === 'scoring' && <ScoringPanel candidate={c} canEdit={hasFullAccess} />}
      {tab === 'screening' && <ScreeningPanel candidate={c} canEdit={hasFullAccess} />}
      {tab === 'interview' && <InterviewPanel candidate={c} canEdit={hasFullAccess} />}
      {tab === 'activity' && <ActivityPanel candidateId={c.public_id} />}
      <CandidateFormModal open={editOpen} onClose={() => setEditOpen(false)} candidate={c} />
    </>
  )
}
