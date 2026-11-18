import { useState } from 'react'
import { useCompleteInterview } from '../../api/hooks'
import { Button, ErrorAlert, Modal, Textarea } from '../../components/ui'
import type { FeedbackRating, Interview } from '../../lib/types'

const OPTIONS: { value: FeedbackRating; label: string }[] = [
  { value: 'POOR', label: 'Poor' },
  { value: 'AVERAGE', label: 'Average' },
  { value: 'GOOD', label: 'Good' },
]

/** The assigned interviewer marks the interview done by rating every question the administrator set. */
export function MarkDoneModal({ interview, open, onClose }: { interview: Interview; open: boolean; onClose: () => void }) {
  const complete = useCompleteInterview()
  const questions = interview.feedback_questions ?? []
  const [ratings, setRatings] = useState<Record<number, FeedbackRating>>({})
  const [comment, setComment] = useState('')
  const answered = questions.every((_, i) => ratings[i])

  function submit() {
    complete.mutate(
      { id: interview.public_id, answers: questions.map((_, i) => ({ index: i, rating: ratings[i] })), comment },
      { onSuccess: onClose },
    )
  }

  return (
    <Modal open={open} title={`Interview done: ${interview.candidate_name || 'Candidate'}`} onClose={onClose} wide>
      <div className="space-y-5">
        {questions.length > 0 ? (
          <p className="text-sm text-slate-600">Rate every question. HR sees your answers; they do not decide anything automatically.</p>
        ) : (
          <p className="text-sm text-slate-600">No feedback questions were set for this role. Confirm that the interview took place.</p>
        )}
        {questions.map((q, i) => (
          <fieldset key={q} className="space-y-2">
            <legend className="text-sm font-medium text-slate-800">{i + 1}. {q}</legend>
            <div className="flex flex-wrap gap-4">
              {OPTIONS.map((o) => (
                <label key={o.value} className="flex cursor-pointer items-center gap-2 text-sm">
                  <input type="radio" name={`q-${i}`} value={o.value} checked={ratings[i] === o.value}
                    onChange={() => setRatings((r) => ({ ...r, [i]: o.value }))} />
                  {o.label}
                </label>
              ))}
            </div>
          </fieldset>
        ))}
        <label className="block text-sm">
          <span className="mb-1 block font-medium text-slate-700">Comment (optional)</span>
          <Textarea rows={3} value={comment} onChange={(e) => setComment(e.target.value)} />
        </label>
        <ErrorAlert error={complete.error} />
        <div className="flex gap-2">
          <Button disabled={!answered} loading={complete.isPending} onClick={submit}>Mark interview done</Button>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </Modal>
  )
}
