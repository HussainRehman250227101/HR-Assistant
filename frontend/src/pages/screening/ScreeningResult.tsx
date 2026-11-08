import { useState } from 'react'
import { Alert, Badge, KeyValue } from '../../components/ui'
import { expectedSalaryText, formatDate, humanize, screeningChannelLabel } from '../../lib/format'
import type { Screening } from '../../lib/types'

function StandardAnswer({ label, value, quote }: { label: string; value: string; quote: string }) {
  return (
    <div className="rounded-md p-3 text-sm ring-1 ring-slate-200">
      <div className="text-xs font-semibold text-slate-500 uppercase">{label}</div>
      <div className={value ? 'mt-1 font-medium text-slate-900' : 'mt-1 text-slate-400'}>{value || 'Not stated'}</div>
      {quote && <p className="mt-1 text-slate-600"><span className="text-xs font-semibold text-emerald-700 uppercase">Candidate said: </span>“{quote}”</p>}
    </div>
  )
}

/** SRS §8 Agent 2 output fields; candidate statements are shown separately from interpretations (FR-07). */
export function ScreeningResult({ screening }: { screening: Screening }) {
  const [showTranscript, setShowTranscript] = useState(false)
  const browser = screening.channel === 'BROWSER_VOICE'
  const aiVoice = screening.channel !== 'HUMAN_LED'
  return (
    <div className="space-y-4">
      <KeyValue items={[
        [browser ? 'Session status' : 'Call status', <Badge key="c" value={screening.call_status} />],
        ['Consent', <Badge key="k" value={screening.consent_status} />],
        ['Channel', screeningChannelLabel(screening.channel)],
        [browser ? 'Session time' : 'Call time', formatDate(screening.call_timestamp)],
        ['AI disclosure detected', screening.ai_disclosure_confirmed === null ? 'n/a' : screening.ai_disclosure_confirmed ? 'Yes' : 'No'],
        ['Recommended next step (for HR)', humanize(screening.recommended_next_step_for_human_review)],
        ['Recorded by', screening.result_recorded_by_name ?? (screening.analysis_model_version ? `AI summary · ${screening.analysis_model_version}` : '')],
      ]} />
      <div>
        <h4 className="mb-2 text-xs font-semibold text-slate-500 uppercase">Salary, notice period and interview availability</h4>
        <div className="grid gap-2 sm:grid-cols-3">
          <StandardAnswer label="Expected salary" value={expectedSalaryText(screening)} quote={screening.expected_salary_statement} />
          <StandardAnswer label="Notice period / start" value={screening.notice_period} quote={screening.notice_period_statement} />
          <StandardAnswer label="Interview availability" value={screening.candidate_stated_availability} quote={screening.availability_statement} />
        </div>
      </div>
      {screening.concise_summary && (
        <div>
          <h4 className="mb-1 text-xs font-semibold text-slate-500 uppercase">Summary</h4>
          <p className="text-sm whitespace-pre-line text-slate-800">{screening.concise_summary}</p>
        </div>
      )}
      {screening.analysis_warnings.length > 0 && <Alert tone="warning">{screening.analysis_warnings.join(' ')}</Alert>}
      {screening.question_answer_pairs.length > 0 && (
        <div>
          <h4 className="mb-2 text-xs font-semibold text-slate-500 uppercase">Questions and answers</h4>
          <ol className="space-y-2">
            {screening.question_answer_pairs.map((qa) => (
              <li key={qa.question_number} className="rounded-md p-3 text-sm ring-1 ring-slate-200">
                <div className="flex items-start justify-between gap-2">
                  <span className="font-medium">{qa.question_number}. {qa.question}</span>
                  <Badge value={qa.answer_status} />
                </div>
                {qa.candidate_statement && <p className="mt-1"><span className="text-xs font-semibold text-emerald-700 uppercase">Candidate said: </span>“{qa.candidate_statement}”</p>}
                {qa.agent_interpretation && <p className="mt-1 text-slate-600"><span className="text-xs font-semibold text-slate-500 uppercase">{aiVoice ? 'AI interpretation' : 'Recruiter note'}: </span>{qa.agent_interpretation}</p>}
              </li>
            ))}
          </ol>
        </div>
      )}
      {screening.role_requirement_responses.length > 0 && (
        <div>
          <h4 className="mb-1 text-xs font-semibold text-slate-500 uppercase">Role requirement responses</h4>
          <ul className="space-y-1 text-sm">
            {screening.role_requirement_responses.map((r, i) => (
              <li key={i}><Badge value={r.status === 'CONFIRMED' ? 'COMPLETED' : r.status} label={humanize(r.status)} /> {r.requirement}{r.candidate_statement && <> — “{r.candidate_statement}”</>}</li>
            ))}
          </ul>
        </div>
      )}
      {(screening.unresolved_questions.length > 0 || screening.candidate_questions.length > 0) && (
        <div className="grid gap-4 sm:grid-cols-2">
          {screening.unresolved_questions.length > 0 && (
            <div><h4 className="mb-1 text-xs font-semibold text-amber-700 uppercase">Unresolved — needs human follow-up</h4>
              <ul className="list-disc pl-5 text-sm">{screening.unresolved_questions.map((q, i) => <li key={i}>{q}</li>)}</ul></div>
          )}
          {screening.candidate_questions.length > 0 && (
            <div><h4 className="mb-1 text-xs font-semibold text-slate-500 uppercase">Candidate's questions</h4>
              <ul className="list-disc pl-5 text-sm">{screening.candidate_questions.map((q, i) => <li key={i}>{q}</li>)}</ul></div>
          )}
        </div>
      )}
      {screening.transcript.length > 0 && (
        <div>
          <button className="text-sm text-indigo-700 hover:underline" onClick={() => setShowTranscript((v) => !v)}>
            {showTranscript ? 'Hide' : 'Show'} {browser ? 'session' : 'call'} transcript ({screening.transcript.length} turns)
          </button>
          {showTranscript && (
            <div className="mt-2 max-h-96 space-y-1 overflow-y-auto rounded-md bg-slate-50 p-3 text-sm">
              {screening.transcript.map((t, i) => (
                <p key={i}><span className={`font-semibold ${t.role === 'user' ? 'text-emerald-700' : 'text-indigo-700'}`}>{t.role === 'user' ? 'Candidate' : 'AI agent'}:</span> {t.message}</p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
