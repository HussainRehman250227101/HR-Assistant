import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query'
import { api, qs } from '../lib/api'
import type {
  AvailabilitySlot, Candidate, CandidateEvent, CommunicationLog, Evaluation, Interview, LocalWindow, Paginated, Requisition, Rubric, Screening,
  ShortlistQueueItem, ShortlistReview, User, WorkflowRun,
} from '../lib/types'

// Mutations invalidate whole domains so every view of the candidate lifecycle stays consistent.
export const keys = {
  requisitions: ['requisitions'] as const,
  candidates: ['candidates'] as const,
  shortlist: ['shortlist'] as const,
  screening: ['screening'] as const,
  dashboard: ['dashboard'] as const,
  interviews: ['interviews'] as const,
}

export function useApiMutation<TVars, TResult = unknown>(fn: (vars: TVars) => Promise<TResult>, invalidate: QueryKey[] = []) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: async () => {
      await Promise.all(invalidate.map((key) => client.invalidateQueries({ queryKey: key })))
    },
  })
}

const LIFECYCLE: QueryKey[] = [keys.candidates, keys.shortlist, keys.screening, keys.dashboard, keys.interviews]

// ---- Users ----
export const useUsers = (role?: string, enabled = true) =>
  useQuery({ queryKey: ['users', role], queryFn: () => api<User[]>(`/auth/users/${qs({ role })}`), enabled, staleTime: 60_000 })

// ---- Requisitions ----
export const useRequisitions = (params: Record<string, string | number | undefined>) =>
  useQuery({ queryKey: [...keys.requisitions, 'list', params], queryFn: () => api<Paginated<Requisition>>(`/requisitions/${qs(params)}`) })

export const useRequisition = (ref: string | undefined) =>
  useQuery({ queryKey: [...keys.requisitions, ref], queryFn: () => api<Requisition>(`/requisitions/${ref}/`), enabled: Boolean(ref) })

export const useSaveRequisition = () =>
  useApiMutation(
    ({ ref, data }: { ref?: string; data: Partial<Requisition> }) =>
      api<Requisition>(ref ? `/requisitions/${ref}/` : '/requisitions/', { method: ref ? 'PATCH' : 'POST', body: data }),
    [keys.requisitions],
  )

export const useDeleteRequisition = () =>
  useApiMutation((ref: string) => api(`/requisitions/${ref}/`, { method: 'DELETE' }), [keys.requisitions])

export const useRubric = (ref: string | undefined, enabled = true) =>
  useQuery({ queryKey: [...keys.requisitions, ref, 'rubric'], queryFn: () => api<Rubric>(`/scoring/requisitions/${ref}/rubric/`), enabled: Boolean(ref) && enabled })

export const useSaveRubric = (ref: string) =>
  useApiMutation((data: { name: string; weights: Record<string, number>; notes: string }) =>
    api<Rubric>(`/scoring/requisitions/${ref}/rubric/`, { method: 'PUT', body: data }), [keys.requisitions])

// ---- Candidates & resumes ----
export const useCandidates = (params: Record<string, string | number | undefined>) =>
  useQuery({ queryKey: [...keys.candidates, 'list', params], queryFn: () => api<Paginated<Candidate>>(`/candidates/${qs(params)}`) })

export const useCandidate = (id: string | undefined) =>
  useQuery({ queryKey: [...keys.candidates, id], queryFn: () => api<Candidate>(`/candidates/${id}/`), enabled: Boolean(id) })

export const useCandidateEvents = (id: string) =>
  useQuery({ queryKey: [...keys.candidates, id, 'events'], queryFn: () => api<CandidateEvent[]>(`/candidates/${id}/events/`) })

export const useSaveCandidate = () =>
  useApiMutation(
    ({ id, data }: { id?: string; data: Partial<Candidate> }) =>
      api<Candidate>(id ? `/candidates/${id}/` : '/candidates/', { method: id ? 'PATCH' : 'POST', body: data }),
    LIFECYCLE,
  )

export const useUploadResume = (candidateId: string) =>
  useApiMutation((file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api(`/candidates/${candidateId}/resumes/`, { form })
  }, LIFECYCLE)

export const useBatchUpload = (requisitionRef: string) =>
  useApiMutation((files: File[]) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    return api<{ uploaded_count: number }>(`/candidates/requisition/${requisitionRef}/resume-batches/`, { form })
  }, LIFECYCLE)

export const useResumeAction = () =>
  useApiMutation(({ id, action }: { id: string; action: 'process' | 'retry' }) =>
    api(`/candidates/resume-documents/${id}/${action}/`, { method: 'POST' }), LIFECYCLE)

// ---- Scoring / shortlist / workflow ----
export const useEvaluations = (candidateId: string) =>
  useQuery({ queryKey: [...keys.candidates, candidateId, 'evaluations'], queryFn: () => api<Evaluation[]>(`/scoring/candidates/${candidateId}/evaluations/`) })

export const useStartScoring = () =>
  useApiMutation((candidateId: string) => api<WorkflowRun>(`/workflows/candidates/${candidateId}/start-scoring/`, { method: 'POST' }), LIFECYCLE)

export const useRetryWorkflow = () =>
  useApiMutation((runId: string) => api<WorkflowRun>(`/workflows/${runId}/resume/`, { method: 'POST' }), LIFECYCLE)

export const useShortlistQueue = (requisition?: string) =>
  useQuery({ queryKey: [...keys.shortlist, requisition], queryFn: () => api<{ count: number; results: ShortlistQueueItem[] }>(`/reviews/shortlist/${qs({ requisition })}`) })

export const useShortlistHistory = (candidateId: string) =>
  useQuery({ queryKey: [...keys.candidates, candidateId, 'shortlist-history'], queryFn: () => api<ShortlistReview[]>(`/reviews/candidates/${candidateId}/history/`) })

export interface ShortlistDecisionInput {
  evaluation: string
  decision: string
  decision_reason: string
  score_override?: number | null
  score_override_reason?: string
  identity_verified?: boolean
  identity_review_reason?: string
}

export const useShortlistDecision = (candidateId: string) =>
  useApiMutation((data: ShortlistDecisionInput) =>
    api<{ workflow_status: string | null; workflow_run: string | null }>(`/reviews/candidates/${candidateId}/shortlist/`, { body: data }), LIFECYCLE)

// ---- Screening (Module 10) ----
export const useCandidateScreenings = (candidateId: string) =>
  useQuery({ queryKey: [...keys.screening, 'candidate', candidateId], queryFn: () => api<Screening[]>(`/screening/candidates/${candidateId}/`) })

export const useScreeningQueue = (params: Record<string, string | undefined>) =>
  useQuery({ queryKey: [...keys.screening, 'queue', params], queryFn: () => api<Screening[]>(`/screening/${qs(params)}`) })

export const useCreateScreening = (candidateId: string) =>
  useApiMutation((data: { channel: string; start_call_now: boolean }) =>
    api<Screening>(`/screening/candidates/${candidateId}/`, { body: data }), LIFECYCLE)

export const useScreeningAction = () =>
  useApiMutation(({ id, action, body }: { id: string; action: 'call' | 'sync' | 'retry-analysis' | 'cancel' | 'manual-result' | 'review'; body?: unknown }) =>
    api<Screening>(`/screening/${id}/${action}/`, { method: 'POST', body: body ?? {} }), LIFECYCLE)

export interface AgentConfig {
  integration: Record<string, boolean | string | string[]>
  script_version: string
  dynamic_variables: string[]
  calling_policy: Record<string, number | string>
  agent_first_message?: string
  agent_system_prompt?: string
}

export const useAgentConfig = () => useQuery({ queryKey: ['agent-config'], queryFn: () => api<AgentConfig>('/screening/agent-config/') })

export const useLLMStatus = (enabled: boolean) =>
  useQuery({ queryKey: ['llm-status'], queryFn: () => api<Record<string, unknown>>('/ai/status/'), enabled })

// ---- Scheduling (Module 12) ----
export const useAvailability = (interviewer?: number) =>
  useQuery({ queryKey: [...keys.interviews, 'availability', interviewer], queryFn: () => api<AvailabilitySlot[]>(`/scheduling/availability/${qs({ interviewer })}`) })

export const useAddAvailability = () =>
  useApiMutation((data: LocalWindow & { timezone: string; interviewer?: number }) =>
    api<AvailabilitySlot>('/scheduling/availability/', { body: data }), [keys.interviews])

export const useDeleteAvailability = () =>
  useApiMutation((id: string) => api(`/scheduling/availability/${id}/`, { method: 'DELETE' }), [keys.interviews])

export const useInterviews = (params: Record<string, string | undefined>) =>
  useQuery({ queryKey: [...keys.interviews, 'list', params], queryFn: () => api<Interview[]>(`/scheduling/interviews/${qs(params)}`) })

export const useCandidateInterviews = (candidateId: string) =>
  useQuery({ queryKey: [...keys.interviews, 'candidate', candidateId], queryFn: () => api<Interview[]>(`/scheduling/candidates/${candidateId}/interviews/`) })

export interface InterviewPlanInput {
  interviewer?: number
  duration_minutes?: number
  timezone?: string
  mode?: string
  meeting_link?: string
  location?: string
  candidate_availability_note?: string
  candidate_windows?: LocalWindow[]
}

export const usePlanInterview = (candidateId: string) =>
  useApiMutation((data: InterviewPlanInput) => api<Interview>(`/scheduling/candidates/${candidateId}/interviews/`, { body: data }), LIFECYCLE)

export const useInterviewAction = () =>
  useApiMutation(({ id, action, body }: { id: string; action: string; body?: unknown }) =>
    api<Interview>(`/scheduling/interviews/${id}/${action}/`, { method: 'POST', body: body ?? {} }), LIFECYCLE)

// ---- Communications (Module 13) ----
export const useCommunications = (params: Record<string, string | undefined>, enabled = true) =>
  useQuery({ queryKey: [...keys.interviews, 'communications', params], queryFn: () => api<CommunicationLog[]>(`/communications/${qs(params)}`), enabled })

export const useDraftInvitation = () =>
  useApiMutation((interviewId: string) => api<CommunicationLog>(`/communications/interviews/${interviewId}/draft/`, { method: 'POST' }), LIFECYCLE)

export const useUpdateDraft = () =>
  useApiMutation(({ id, subject, body }: { id: string; subject: string; body: string }) =>
    api<CommunicationLog>(`/communications/${id}/`, { method: 'PATCH', body: { subject, body } }), LIFECYCLE)

export const useCommunicationAction = () =>
  useApiMutation(({ id, action }: { id: string; action: 'approve-send' | 'discard' }) =>
    api<CommunicationLog>(`/communications/${id}/${action}/`, { method: 'POST', body: action === 'approve-send' ? { confirm: true } : {} }), LIFECYCLE)

// ---- Dashboard (Module 14) ----
export interface DashboardSummary {
  generated_at: string
  total_candidates: number
  active_candidates: number
  open_requisitions: number
  by_status: { status: string; label: string; count: number }[]
  attention: { key: string; label: string; link: string; severity: 'critical' | 'warning' | 'info'; count: number }[]
  upcoming_interviews: { interview_id: string; candidate_id: string; candidate_name: string; requisition_title: string; interviewer_name: string; start: string; timezone: string; mode: string }[]
}

export interface PipelineRow {
  public_id: string
  name: string
  requisition_title: string
  requisition_reference: string
  current_status: string
  score: number | null
  confidence: string | null
  screening_status: string | null
  screening_call_status: string | null
  interview_status: string | null
  interview_start: string | null
  interview_timezone: string | null
  updated_at: string
}

export type ActivityRow = CandidateEvent & { candidate_id: string; candidate_name: string }

export const useDashboardSummary = (requisition?: string) =>
  useQuery({ queryKey: [...keys.dashboard, 'summary', requisition], queryFn: () => api<DashboardSummary>(`/dashboard/summary/${qs({ requisition })}`), refetchInterval: 60_000 })

export const usePipeline = (params: Record<string, string | number | undefined>) =>
  useQuery({ queryKey: [...keys.dashboard, 'pipeline', params], queryFn: () => api<Paginated<PipelineRow>>(`/dashboard/pipeline/${qs(params)}`) })

export const useActivityLog = (params: Record<string, string | number | undefined>) =>
  useQuery({ queryKey: [...keys.dashboard, 'activity', params], queryFn: () => api<Paginated<ActivityRow>>(`/dashboard/activity/${qs(params)}`) })

export const useEventTypes = () =>
  useQuery({ queryKey: ['event-types'], queryFn: () => api<{ value: string; label: string }[]>('/dashboard/event-types/'), staleTime: Infinity })

// ---- Hardening (Module 15) ----
export const useCandidatePrivacyAction = (candidateId: string) =>
  useApiMutation(({ action, reason }: { action: 'close' | 'erase-personal-data'; reason: string }) =>
    api<Candidate>(`/candidates/${candidateId}/${action}/`, { body: { reason } }), LIFECYCLE)

export interface SystemAuditEvent {
  id: string
  action: string
  entity_type: string
  entity_id: string
  actor_name: string
  details: Record<string, unknown>
  created_at: string
}

export const useSystemAudit = (params: Record<string, string | number | undefined>, enabled: boolean) =>
  useQuery({ queryKey: ['system-audit', params], queryFn: () => api<Paginated<SystemAuditEvent>>(`/audit/${qs(params)}`), enabled })
