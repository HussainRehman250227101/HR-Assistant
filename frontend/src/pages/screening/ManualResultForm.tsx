import { useState, type FormEvent } from 'react'
import { useScreeningAction } from '../../api/hooks'
import { Button, ErrorAlert, Field, Input, Select, Textarea } from '../../components/ui'
import type { Screening } from '../../lib/types'

const ANSWER_OPTIONS = [
  { value: 'ANSWERED', label: 'Answered' }, { value: 'UNCLEAR', label: 'Unclear' },
  { value: 'NOT_ASKED', label: 'Not asked' }, { value: 'DECLINED_TO_ANSWER', label: 'Declined to answer' },
]

export function ManualResultForm({ screening }: { screening: Screening }) {
  const action = useScreeningAction()
  const [callStatus, setCallStatus] = useState('COMPLETED')
  const [consent, setConsent] = useState('NOT_ASKED')
  const [answers, setAnswers] = useState(screening.questions.map(() => ({ answer_status: 'ANSWERED', candidate_statement: '', recruiter_note: '' })))
  const [availability, setAvailability] = useState('')
  const [candidateQuestions, setCandidateQuestions] = useState('')
  const [summary, setSummary] = useState('')

  const setAnswer = (i: number, key: string, value: string) => setAnswers((list) => list.map((a, idx) => (idx === i ? { ...a, [key]: value } : a)))

  async function submit(e: FormEvent) {
    e.preventDefault()
    await action.mutateAsync({
      id: screening.public_id, action: 'manual-result', body: {
        call_status: callStatus, consent_status: consent, concise_summary: summary, candidate_stated_availability: availability,
        candidate_questions: candidateQuestions.split('\n').map((s) => s.trim()).filter(Boolean),
        question_answer_pairs: answers.map((a, i) => ({ question_number: i + 1, ...a })),
      },
    })
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <p className="text-sm text-slate-600">Record the outcome of a human-led screening (the alternative route for candidates who decline automated calls or need assistance). Record only what the candidate actually said.</p>
      <ErrorAlert error={action.error} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Outcome">
          <Select value={callStatus} onChange={(e) => setCallStatus(e.target.value)} options={[
            { value: 'COMPLETED', label: 'Completed' }, { value: 'NO_ANSWER', label: 'No answer' },
            { value: 'HUMAN_REQUESTED', label: 'Needs a different recruiter' }, { value: 'STOPPED_BY_CANDIDATE', label: 'Candidate asked to stop' },
            { value: 'RESCHEDULE_REQUESTED', label: 'Reschedule requested' }, { value: 'INCOMPLETE', label: 'Incomplete' }]} />
        </Field>
        <Field label="Recording/notes consent">
          <Select value={consent} onChange={(e) => setConsent(e.target.value)} options={[
            { value: 'NOT_ASKED', label: 'Not recorded / not asked' }, { value: 'GRANTED', label: 'Granted' }, { value: 'DECLINED', label: 'Declined' }, { value: 'UNCLEAR', label: 'Unclear' }]} />
        </Field>
      </div>
      {screening.questions.map((q, i) => (
        <div key={i} className="space-y-2 rounded-md p-3 ring-1 ring-slate-200">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm font-medium">{i + 1}. {q}</span>
            <Select value={answers[i].answer_status} onChange={(e) => setAnswer(i, 'answer_status', e.target.value)} options={ANSWER_OPTIONS} className="max-w-[12rem]" />
          </div>
          <Input placeholder="Candidate's answer (their words)" value={answers[i].candidate_statement} onChange={(e) => setAnswer(i, 'candidate_statement', e.target.value)} />
          <Input placeholder="Recruiter note (your interpretation, optional)" value={answers[i].recruiter_note} onChange={(e) => setAnswer(i, 'recruiter_note', e.target.value)} />
        </div>
      ))}
      <Field label="Candidate stated availability"><Input value={availability} onChange={(e) => setAvailability(e.target.value)} /></Field>
      <Field label="Candidate's questions" hint="One per line"><Textarea value={candidateQuestions} onChange={(e) => setCandidateQuestions(e.target.value)} /></Field>
      <Field label="Concise factual summary"><Textarea required value={summary} onChange={(e) => setSummary(e.target.value)} /></Field>
      <Button type="submit" loading={action.isPending}>Save screening result</Button>
    </form>
  )
}
