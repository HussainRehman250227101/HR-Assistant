import type { Screening } from './types'

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

const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/

/** "2026-11-08" -> "08/11/2026"; '' when empty or not an ISO date. */
export function isoToDisplayDate(iso: string | null | undefined): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso ?? '')
  return m ? `${m[3]}/${m[2]}/${m[1]}` : ''
}

/** "08/11/2026" -> "2026-11-08"; '' unless it is a real calendar date (31/02/2026 is rejected). */
export function displayToIsoDate(text: string): string {
  const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(text.trim())
  if (!m) return ''
  const [day, month, year] = [Number(m[1]), Number(m[2]), Number(m[3])]
  const date = new Date(Date.UTC(year, month - 1, day))
  const real = date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day
  return real ? `${m[3]}-${m[2]}-${m[1]}` : ''
}

/** Typing helper: keep digits only and add the slashes (0811 -> 08/11, 08112026 -> 08/11/2026). */
export function maskDateInput(raw: string): string {
  const digits = raw.replace(/\D/g, '').slice(0, 8)
  if (digits.length <= 2) return digits
  if (digits.length <= 4) return `${digits.slice(0, 2)}/${digits.slice(2)}`
  return `${digits.slice(0, 2)}/${digits.slice(2, 4)}/${digits.slice(4)}`
}

/** Every date in the app is shown as DD/MM/YYYY (times as 24-hour HH:MM). Date-only values are not time-zone shifted. */
export function formatDate(value: string | null | undefined, withTime = true): string {
  if (!value) return '—'
  if (DATE_ONLY.test(value)) return isoToDisplayDate(value)
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  const day = date.toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit', year: 'numeric' })
  return withTime ? `${day}, ${date.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}` : day
}

/** Format an instant in a specific IANA time zone, e.g. "Tue 10/11/2026, 11:00 (Asia/Karachi)". */
export function formatInZone(value: string | null | undefined, timeZone: string, withZone = true): string {
  if (!value) return '—'
  try {
    const date = new Date(value)
    const weekday = date.toLocaleDateString('en-GB', { timeZone, weekday: 'short' })
    const day = date.toLocaleDateString('en-GB', { timeZone, day: '2-digit', month: '2-digit', year: 'numeric' })
    const time = date.toLocaleTimeString('en-GB', { timeZone, hour: '2-digit', minute: '2-digit' })
    const text = `${weekday} ${day}, ${time}`
    return withZone ? `${text} (${timeZone})` : text
  } catch {
    return formatDate(value)
  }
}

export const BROWSER_TZ = Intl.DateTimeFormat().resolvedOptions().timeZone

export const COMMON_TIMEZONES = Array.from(new Set([
  'Asia/Karachi', BROWSER_TZ, 'UTC', 'Asia/Dubai', 'Asia/Riyadh', 'Europe/London', 'Europe/Berlin',
  'America/New_York', 'America/Chicago', 'America/Los_Angeles', 'Asia/Singapore', 'Australia/Sydney',
]))

/** "250,000 – 300,000 PKR"; one figure when both ends are equal; '' when neither is set. */
export function formatMoneyRange(min: string | null | undefined, max: string | null | undefined, currency = ''): string {
  if (!min && !max) return ''
  const amount = (v: string | null | undefined) => (v ? Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 }) : '?')
  const range = min && max && Number(min) === Number(max) ? amount(min) : `${amount(min)} – ${amount(max)}`
  return currency ? `${range} ${currency}` : range
}

export const SALARY_PERIOD_LABELS: Record<string, string> = { MONTHLY: 'per month', ANNUAL: 'per year' }

/** The candidate's stated salary expectation from a screening, e.g. "250,000 – 300,000 PKR per month". */
export function expectedSalaryText(s: Pick<Screening, 'expected_salary_min' | 'expected_salary_max' | 'expected_salary_currency' | 'expected_salary_period'>): string {
  const range = formatMoneyRange(s.expected_salary_min, s.expected_salary_max, s.expected_salary_currency)
  if (!range) return ''
  const period = SALARY_PERIOD_LABELS[s.expected_salary_period]
  return [range, period, !s.expected_salary_currency && '(currency not stated)'].filter(Boolean).join(' ')
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
  INTERRUPTED: 'amber',
  ABANDONED: 'gray',
  INCOMPLETE: 'amber',
  PROPOSED: 'blue',
  CONFIRMED: 'green',
  SENT: 'green',
  DRAFTED: 'blue',
  APPROVED: 'green',
  SCHEDULED: 'green',
  NEEDS_HR_COORDINATION: 'amber',
}

/** A browser voice session must never be presented as a telephone call. */
export const SCREENING_CHANNEL_LABELS: Record<string, string> = {
  AI_VOICE: 'AI voice call (Twilio + ElevenLabs)',
  BROWSER_VOICE: 'Browser voice session (ElevenLabs, no phone call)',
  HUMAN_LED: 'Human-led screening',
}

export function screeningChannelLabel(channel: string): string {
  return SCREENING_CHANNEL_LABELS[channel] ?? humanize(channel)
}

export function toneFor(value: string | null | undefined): Tone {
  return (value && TONES[value]) || 'gray'
}
