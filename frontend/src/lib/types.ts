export type Role = 'ADMIN' | 'RECRUITER' | 'HIRING_MANAGER'

export interface User {
  id: number
  username: string
  email: string
  first_name: string
  last_name: string
  full_name: string
  role: Role
  department: string
  job_title: string
  is_superuser: boolean
}

export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export type RequisitionStatus = 'DRAFT' | 'OPEN' | 'ON_HOLD' | 'CLOSED'

export type InterviewFormat = 'ONSITE' | 'VIDEO'

export interface Requisition {
  id: number
  reference_code: string
  title: string
  department: string
  location: string
  employment_type: string
  work_mode: string
  description: string
  responsibilities: string
  required_skills: string[]
  preferred_skills: string[]
  screening_questions: string[]
  interview_format: InterviewFormat
  interview_whatsapp_number: string
  minimum_experience_years: string
  education_requirements: string
  salary_min: string | null
  salary_max: string | null
  currency: string
  headcount: number
  status: RequisitionStatus
  created_by: number
  created_by_name: string
  hiring_manager: number | null
  hiring_manager_name: string | null
  target_close_date: string | null
  opened_at: string | null
  closed_at: string | null
  created_at: string
  updated_at: string
}

export type CandidateStatus =
  | 'RESUME_RECEIVED'
  | 'NEEDS_MANUAL_REVIEW'
  | 'SCORED_HR_REVIEW'
  | 'APPROVED_FOR_SCREENING'
  | 'SCREENING_SCHEDULED_PENDING'
  | 'SCREENING_COMPLETED_HR_REVIEW'
  | 'APPROVED_FOR_INTERVIEW'
  | 'INTERVIEW_PROPOSED'
  | 'INTERVIEW_SCHEDULED'
  | 'CLOSED'

export type ConsentStatus = 'PENDING' | 'GRANTED' | 'DECLINED'

export interface ResumeSummary {
  public_id: string
  original_filename: string
  content_type: string
  file_size: number
  processing_status: 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'NEEDS_MANUAL_REVIEW' | 'FAILED'
  warning_messages: string[]
  error_code: string
  error_message: string
  created_at: string
  processed_at: string | null
}

export interface Candidate {
  public_id: string
  requisition: number
  full_name: string
  display_name: string
  email: string | null
  phone: string
  location: string
  linkedin_url: string
  source: string
  contact_consent_status: ConsentStatus
  recording_consent_status: ConsentStatus
  consent_preferences: Record<string, unknown>
  current_status: CandidateStatus
  identity_review_required: boolean
  /** Fields the system read from the candidate's own resume (names only). */
  auto_filled_fields: string[]
  closed_reason: string
  personal_data_erased_at: string | null
  created_by: number
  created_by_name: string
  resume_documents: ResumeSummary[]
  created_at: string
  updated_at: string
}

export interface CandidateEvent {
  id: number
  event_type: string
  actor_name: string | null
  details: Record<string, unknown>
  created_at: string
}

export interface CriterionScore {
  label: string
  weight: number
  score: number | null
  evidence_status: 'SUPPORTED' | 'PARTIAL' | 'NOT_FOUND' | 'UNCLEAR'
  rationale: string
}

export interface EvidenceItem {
  excerpt: string
  relevance: string
  resume_section: string | null
}

export interface Evaluation {
  public_id: string
  candidate_reference: string
  resume_reference: string
  requisition_reference: string
  version: number
  overall_score: number | null
  assessed_weight: number
  criterion_scores: Record<string, CriterionScore>
  evidence: Record<string, EvidenceItem[]>
  missing_or_unclear_items: string[]
  parsing_warnings: string[]
  confidence_level: 'HIGH' | 'MEDIUM' | 'LOW'
  recommendation_for_human_review: string
  overall_assessment: string
  model_version: string
  prompt_version: string
  created_at: string
}

export interface Rubric {
  public_id: string
  requisition_reference: string
  name: string
  weights: Record<string, number>
  version: number
  is_active: boolean
  notes: string
  created_at: string
}

export interface ShortlistReview {
  public_id: string
  candidate_reference: string
  evaluation_reference: string
  decision: 'APPROVE_FOR_SCREENING' | 'DECLINE' | 'HOLD_FOR_REVIEW'
  decision_reason: string
  score_override: number | null
  score_override_reason: string
  previous_candidate_status: string
  resulting_candidate_status: string
  decided_by_name: string
  created_at: string
}

export interface ShortlistQueueItem {
  candidate: {
    public_id: string
    full_name: string
    email: string | null
    phone: string
    current_status: CandidateStatus
    identity_review_required: boolean
    requisition_reference: string
    requisition_title: string
  }
  evaluation: Evaluation
}

export interface AutoScoringStatus {
  enabled: boolean
  interval_seconds: number
  batch_limit: number
  awaiting_scoring: number
  last_automatic_run_at: string | null
}

export interface WorkflowRun {
  public_id: string
  candidate_reference: string
  resume_reference: string
  evaluation_reference: string | null
  trigger: 'MANUAL' | 'AUTOMATIC'
  status: string
  current_step: string
  error_code: string
  error_message: string
  state_summary: Record<string, unknown>
  started_at: string | null
  completed_at: string | null
  created_at: string
}

export interface QuestionAnswerPair {
  question_number: number
  question: string
  answer_status: 'ANSWERED' | 'UNCLEAR' | 'NOT_ASKED' | 'DECLINED_TO_ANSWER'
  candidate_statement: string
  agent_interpretation: string
}

export interface CallAttempt {
  public_id: string
  attempt_number: number
  provider: string
  destination_masked: string
  status: 'INITIATING' | 'IN_PROGRESS' | 'ENDED' | 'FAILED'
  outcome: string
  provider_status: string
  telephony_status: string
  termination_reason: string
  duration_seconds: number | null
  error_code: string
  error_message: string
  provider_data_deleted: boolean
  initiated_by_name: string
  started_at: string
  ended_at: string | null
}

export type ScreeningStatus =
  | 'PENDING_CALL'
  | 'CALL_IN_PROGRESS'
  | 'ANALYZING'
  | 'ANALYSIS_FAILED'
  | 'AWAITING_MANUAL_RESULT'
  | 'AWAITING_HR_REVIEW'
  | 'REVIEWED'
  | 'CANCELLED'

export interface Screening {
  public_id: string
  candidate_reference: string
  candidate_name: string
  requisition_reference: string
  requisition_title: string
  job: ScreeningJob
  channel: ScreeningChannel
  status: ScreeningStatus
  call_status: string
  consent_status: string
  ai_disclosure_confirmed: boolean | null
  questions: string[]
  script_version: string
  max_attempts: number
  attempt_count: number
  next_attempt_not_before: string | null
  question_answer_pairs: QuestionAnswerPair[]
  candidate_stated_availability: string
  /** Standard answers; *_statement fields are the candidate's own words, verified against the transcript. */
  availability_statement: string
  expected_salary_min: string | null
  expected_salary_max: string | null
  expected_salary_currency: string
  expected_salary_period: '' | 'MONTHLY' | 'ANNUAL' | 'UNSPECIFIED'
  expected_salary_statement: string
  notice_period: string
  notice_period_statement: string
  role_requirement_responses: { requirement: string; candidate_statement: string; status: string }[]
  candidate_questions: string[]
  unresolved_questions: string[]
  concise_summary: string
  recommended_next_step_for_human_review: string
  call_timestamp: string | null
  transcript: { role: 'user' | 'agent'; message: string; time_in_call_secs?: number | null }[]
  analysis_warnings: string[]
  analysis_model_version: string
  analysis_prompt_version: string
  error_code: string
  error_message: string
  created_by_name: string
  result_recorded_by_name: string | null
  call_attempts: CallAttempt[]
  call_error?: string | null
  review?: ScreeningReview | null
  created_at: string
  updated_at: string
}

/** The requisition's job description, shown beside the candidate's answers on the screening review. */
export interface ScreeningJob {
  title: string
  department: string
  location: string
  employment_type: string
  work_mode: string
  description: string
  responsibilities: string
  required_skills: string[]
  preferred_skills: string[]
  minimum_experience_years: string
  education_requirements: string
  salary_min: string | null
  salary_max: string | null
  currency: string
}

/** AI_VOICE = Twilio phone call (optional telephony mode); BROWSER_VOICE = ElevenLabs WebRTC session, no phone call. */
export type ScreeningChannel = 'AI_VOICE' | 'BROWSER_VOICE' | 'HUMAN_LED'

/** POST /screening/<id>/browser-session/ — a short-lived ElevenLabs WebRTC token; never the API key. */
export interface BrowserSessionStart {
  screening_id: string
  attempt_id: string
  attempt_number: number
  max_attempts: number
  conversation_id: string | null
  conversation_token: string
  connection_type: 'webrtc'
  dynamic_variables: Record<string, string>
}

export type BrowserSessionState = 'processing' | 'concluded' | 'already_concluded'

export type ClientEndReason = 'user_ended' | 'agent_ended' | 'connection_error' | 'start_failed' | 'page_closed' | 'unknown'

export interface BrowserSessionComplete {
  attempt_id?: string
  client_end_reason: ClientEndReason
  connected?: boolean | null
  conversation_id?: string
}

export type BrowserSessionResult = Screening & { session_state: BrowserSessionState; session_attempt: CallAttempt }

export interface ScreeningReview {
  public_id: string
  decision: string
  decision_reason: string
  previous_candidate_status: string
  resulting_candidate_status: string
  decided_by_name: string
  created_at: string
}

export interface AvailabilitySlot {
  public_id: string
  interviewer: number
  interviewer_name: string
  start: string
  end: string
  timezone: string
  source: string
  source_label: string
}

export interface Slot {
  start: string
  end: string
}

export type InterviewStatus = 'PROPOSED' | 'NEEDS_HR_COORDINATION' | 'SLOT_CONFIRMED' | 'SCHEDULED' | 'CANCELLED'

export interface Interview {
  public_id: string
  candidate_reference: string
  candidate_name: string
  requisition_title: string
  interviewer: number
  interviewer_name: string
  interviewer_email: string
  status: InterviewStatus
  duration_minutes: number
  timezone: string
  mode: 'VIDEO' | 'ONSITE' | 'PHONE'
  meeting_link: string
  contact_whatsapp: string
  auto_scheduled: boolean
  location: string
  candidate_availability_note: string
  candidate_windows: Slot[]
  proposed_slots: Slot[]
  calendar_source: string
  calendar_source_label: string
  confirmed_start: string | null
  confirmed_end: string | null
  candidate_confirmed_at: string | null
  interviewer_confirmed_at: string | null
  cancellation_reason: string
  sequence: number
  created_by_name: string
  created_at: string
  updated_at: string
}

export interface LocalWindow {
  date: string
  start_time: string
  end_time: string
}

export interface CommunicationLog {
  public_id: string
  candidate_reference: string
  interview_reference: string | null
  channel: string
  kind: 'INTERVIEW_INVITATION' | 'INTERVIEW_RESCHEDULE' | 'INTERVIEW_CANCELLATION'
  template_version: string
  sequence: number
  recipient: string
  cc: string[]
  subject: string
  body: string
  meeting_details: Record<string, string | number>
  approval_status: 'DRAFT' | 'APPROVED' | 'DISCARDED'
  approved_by_name: string | null
  auto_sent: boolean
  approved_at: string | null
  send_status: 'NOT_SENT' | 'SENDING' | 'SENT' | 'FAILED'
  send_attempts: number
  provider: string
  provider_message_id: string
  sent_at: string | null
  error_code: string
  error_message: string
  created_by_name: string
  created_at: string
}
