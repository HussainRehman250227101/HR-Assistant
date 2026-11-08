import { Link, useParams } from 'react-router-dom'
import { useScreening } from '../../api/hooks'
import { useAuth } from '../../auth/AuthContext'
import { Alert, Badge, Card, ErrorAlert, KeyValue, Loading, PageHeader } from '../../components/ui'
import { formatDate, screeningChannelLabel } from '../../lib/format'
import { BrowserVoiceSession } from './BrowserVoiceSession'
import { ScreeningResult } from './ScreeningResult'

/**
 * Demo Browser Screening (Module 16). There is no candidate portal, so the session runs inside the HR workspace and
 * the presenter speaks as the simulated candidate. It is never presented as an outbound telephone call.
 */
export function BrowserScreeningPage() {
  const { id } = useParams()
  const { hasFullAccess } = useAuth()
  const screening = useScreening(id)
  const s = screening.data

  if (screening.isLoading) return <Loading />
  if (!s) return <ErrorAlert error={screening.error ?? new Error('Screening not found.')} />

  const finished = ['AWAITING_HR_REVIEW', 'REVIEWED', 'ANALYSIS_FAILED'].includes(s.status)
  return (
    <>
      <PageHeader
        title={<span className="flex flex-wrap items-center gap-2">Demo browser screening <Badge tone="purple" label="Simulated candidate · no phone call" /></span>}
        subtitle="An AI voice screening held in this browser with the ElevenLabs agent. Speak as the candidate using this computer's microphone."
        actions={<Link to={`/candidates/${s.candidate_reference}?tab=screening`} className="text-sm text-indigo-700 hover:underline">Back to candidate</Link>}
      />
      <div className="space-y-6">
        {s.channel !== 'BROWSER_VOICE' ? (
          <Alert tone="warning">This screening uses the “{screeningChannelLabel(s.channel)}” route, not a browser voice session.</Alert>
        ) : !hasFullAccess ? (
          <Alert tone="warning">Only recruiters and HR admins can run screening sessions.</Alert>
        ) : null}
        <Card title="Candidate and requisition">
          <KeyValue items={[
            ['Candidate', s.candidate_name || 'Candidate'],
            ['Requisition', s.requisition_title],
            ['Screening route', screeningChannelLabel(s.channel)],
            ['Screening status', <Badge key="s" value={s.status} />],
            ['Sessions used', `${s.attempt_count} of ${s.max_attempts}`],
            ['Approved script', s.script_version],
            ['Created', formatDate(s.created_at)],
          ]} />
          <h4 className="mt-4 mb-1 text-xs font-semibold text-slate-500 uppercase">Approved questions the agent will ask</h4>
          <ol className="list-decimal space-y-0.5 pl-5 text-sm text-slate-700">
            {s.questions.map((q, i) => <li key={i}>{q}</li>)}
          </ol>
        </Card>
        {s.channel === 'BROWSER_VOICE' && hasFullAccess && (
          <Card title="AI voice screening session">
            <BrowserVoiceSession screening={s} />
          </Card>
        )}
        {finished && (
          <Card title="Screening result (for HR review)">
            <ScreeningResult screening={s} />
            <p className="mt-4 text-sm">
              <Link to={`/candidates/${s.candidate_reference}?tab=screening`} className="text-indigo-700 hover:underline">Open the candidate's Screening tab</Link> or the{' '}
              <Link to="/screening" className="text-indigo-700 hover:underline">screening queue</Link> to record the HR decision (human gate 2).
            </p>
          </Card>
        )}
      </div>
    </>
  )
}
