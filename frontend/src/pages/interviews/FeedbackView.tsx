import { Badge } from '../../components/ui'
import { formatDate, humanize } from '../../lib/format'
import type { FeedbackRating, InterviewFeedback } from '../../lib/types'

const TONE: Record<FeedbackRating, 'red' | 'amber' | 'green'> = { POOR: 'red', AVERAGE: 'amber', GOOD: 'green' }

/** The interviewer's Poor / Average / Good answers, so HR can see how the interview went (decision support only). */
export function FeedbackView({ feedback }: { feedback: InterviewFeedback }) {
  return (
    <div className="mt-4 border-t border-slate-100 pt-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-sm font-semibold text-slate-800">Interviewer feedback</h4>
        <div className="flex items-center gap-2 text-xs text-slate-500">
          {feedback.overall_rating && <Badge tone={TONE[feedback.overall_rating]} label={`Overall: ${humanize(feedback.overall_rating)}`} />}
          <span>{feedback.submitted_by_name} · {formatDate(feedback.submitted_at)}</span>
        </div>
      </div>
      {feedback.answers.length > 0 ? (
        <ul className="space-y-1.5 text-sm">
          {feedback.answers.map((a) => (
            <li key={a.question} className="flex items-start justify-between gap-3">
              <span className="text-slate-700">{a.question}</span>
              <Badge tone={TONE[a.rating]} label={humanize(a.rating)} />
            </li>
          ))}
        </ul>
      ) : <p className="text-sm text-slate-500">No feedback questions were set for this role.</p>}
      {feedback.comment && <p className="mt-3 text-sm whitespace-pre-line text-slate-700">{feedback.comment}</p>}
    </div>
  )
}
