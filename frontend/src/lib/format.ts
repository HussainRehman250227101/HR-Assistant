export const CANDIDATE_STATUS_LABELS: Record<string, string> = {
  RESUME_RECEIVED: 'Resume Received',
  NEEDS_MANUAL_REVIEW: 'Needs Manual Review',
  SCORED_HR_REVIEW: 'Scored — HR Review',
  APPROVED_FOR_SCREENING: 'Approved for Screening',
  SCREENING_SCHEDULED_PENDING: 'Screening Scheduled / Pending',
  SCREENING_COMPLETED_HR_REVIEW: 'Screening Completed — HR Review',
  APPROVED_FOR_INTERVIEW: 'Approved for Interview',
  INTERVIEW_PROPOSED: 'Interview Proposed',
  INTERVIEW_SCHEDULED: 'Interview Scheduled',
  CLOSED: 'Closed',
}

export const CANDIDATE_STATUS_ORDER = Object.keys(CANDIDATE_STATUS_LABELS)

export function humanize(value: string | null | undefined): string {
  if (!value) return '—'
  return CANDIDATE_STATUS_LABELS[value] ?? value.toLowerCase().replaceAll('_', ' ').replace(/^\w/, (c) => c.toUpperCase())
}

export function formatDate(value: string | null | undefined, withTime = true): string {
  if (!value) return '—'
  const date = new Date(value)
  return withTime
    ? date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
    : date.toLocaleDateString(undefined, { dateStyle: 'medium' })
}

export function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

type Tone = 'gray' | 'blue' | 'green' | 'amber' | 'red' | 'purple'

const TONES: Record<string, Tone> = {
  RESUME_RECEIVED: 'gray',
  NEEDS_MANUAL_REVIEW: 'amber',
  SCORED_HR_REVIEW: 'blue',
  APPROVED_FOR_SCREENING: 'purple',
  SCREENING_SCHEDULED_PENDING: 'purple',
  SCREENING_COMPLETED_HR_REVIEW: 'blue',
  APPROVED_FOR_INTERVIEW: 'green',
  INTERVIEW_PROPOSED: 'green',
  INTERVIEW_SCHEDULED: 'green',
  CLOSED: 'gray',
  OPEN: 'green',
  DRAFT: 'gray',
  ON_HOLD: 'amber',
  COMPLETED: 'green',
  PENDING: 'gray',
  PROCESSING: 'blue',
  FAILED: 'red',
  GRANTED: 'green',
  DECLINED: 'red',
  HIGH: 'green',
  MEDIUM: 'amber',
  LOW: 'red',
  SUPPORTED: 'green',
  PARTIAL: 'amber',
  NOT_FOUND: 'gray',
  UNCLEAR: 'amber',
  ANSWERED: 'green',
  NOT_ASKED: 'gray',
  PENDING_CALL: 'purple',
  CALL_IN_PROGRESS: 'blue',
  ANALYZING: 'blue',
  ANALYSIS_FAILED: 'red',
  AWAITING_MANUAL_RESULT: 'purple',
  AWAITING_HR_REVIEW: 'amber',
  REVIEWED: 'green',
  CANCELLED: 'gray',
  IN_PROGRESS: 'blue',
  ENDED: 'gray',
  WAITING_HR_REVIEW: 'amber',
  NO_ANSWER: 'amber',
  VOICEMAIL: 'amber',
  CONSENT_DECLINED: 'red',
  HUMAN_REQUESTED: 'amber',
  STOPPED_BY_CANDIDATE: 'red',
  PROPOSED: 'blue',
  CONFIRMED: 'green',
  SENT: 'green',
  DRAFTED: 'blue',
  APPROVED: 'green',
  SCHEDULED: 'green',
  NEEDS_HR_COORDINATION: 'amber',
}

export function toneFor(value: string | null | undefined): Tone {
  return (value && TONES[value]) || 'gray'
}
