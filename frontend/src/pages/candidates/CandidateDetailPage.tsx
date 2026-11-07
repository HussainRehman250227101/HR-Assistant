import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useCandidate, useRequisitions } from '../../api/hooks'
import { useAuth } from '../../auth/AuthContext'
import { Alert, Badge, Button, Card, ErrorAlert, KeyValue, Loading, PageHeader, Tabs } from '../../components/ui'
import { CANDIDATE_STATUS_ORDER, formatDate, humanize } from '../../lib/format'
import { InterviewPanel } from '../interviews/InterviewPanel'
import { ScreeningPanel } from '../screening/ScreeningPanel'
import { ActivityPanel } from './ActivityPanel'
import { CandidateFormModal } from './CandidateFormModal'
import { ResumesPanel } from './ResumesPanel'
import { ScoringPanel } from './ScoringPanel'

type Tab = 'overview' | 'scoring' | 'screening' | 'interview' | 'activity'

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
  const tab = (params.get('tab') as Tab) || 'overview'
  const { isRecruiter } = useAuth()
  const candidate = useCandidate(id)
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
        actions={isRecruiter && c.current_status !== 'CLOSED' && <Button variant="secondary" onClick={() => setEditOpen(true)}>Edit details</Button>}
      />
      <div className="mb-4"><Stepper status={c.current_status} /></div>
      {c.current_status === 'CLOSED' && <div className="mb-4"><Alert tone="info">Closed: {c.closed_reason || 'no reason recorded'}</Alert></div>}
      {c.identity_review_required && <div className="mb-4"><Alert tone="warning">Identity details pending review. Enter the candidate's name and contact details before approving screening.</Alert></div>}
      <Tabs<Tab>
        value={tab}
        onChange={(v) => setParams({ tab: v })}
        tabs={[
          { value: 'overview', label: 'Overview & resumes' },
          { value: 'scoring', label: 'Scoring & shortlist' },
          { value: 'screening', label: 'Screening' },
          { value: 'interview', label: 'Interview' },
          { value: 'activity', label: 'Activity' },
        ]}
      />
      {tab === 'overview' && (
        <div className="space-y-6">
          <Card title="Candidate details">
            <KeyValue items={[
              ['Email', c.email], ['Phone', c.phone], ['Location', c.location], ['LinkedIn', c.linkedin_url],
              ['Source', humanize(c.source)], ['Contact consent', <Badge key="cc" value={c.contact_consent_status} />],
              ['Recording consent', <Badge key="rc" value={c.recording_consent_status} />],
              ['Automated calls', c.consent_preferences?.automated_call_opt_out ? 'Opted out' : 'Allowed'],
              ['Added by', c.created_by_name], ['Added', formatDate(c.created_at)],
            ]} />
          </Card>
          <ResumesPanel candidate={c} canEdit={isRecruiter} />
        </div>
      )}
      {tab === 'scoring' && <ScoringPanel candidate={c} canEdit={isRecruiter} />}
      {tab === 'screening' && <ScreeningPanel candidate={c} canEdit={isRecruiter} />}
      {tab === 'interview' && <InterviewPanel candidate={c} canEdit={isRecruiter} />}
      {tab === 'activity' && <ActivityPanel candidateId={c.public_id} />}
      <CandidateFormModal open={editOpen} onClose={() => setEditOpen(false)} candidate={c} />
    </>
  )
}
