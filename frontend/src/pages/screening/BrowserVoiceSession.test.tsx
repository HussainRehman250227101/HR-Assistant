import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError } from '../../lib/api'
import type { BrowserSessionResult, BrowserSessionStart, Screening } from '../../lib/types'
import { BrowserVoiceSession } from './BrowserVoiceSession'

// ---- Fake @elevenlabs/react: lets each test drive connection status, speaking mode and callbacks. -------------------
type SdkState = { status: 'disconnected' | 'connecting' | 'connected' | 'error'; mode: 'speaking' | 'listening'; isMuted: boolean }
type SdkCallbacks = {
  onConnect?: (props: { conversationId: string }) => void
  onDisconnect?: (details: { reason: 'user' | 'agent' | 'error' }) => void
  onError?: (message: string) => void
}

const sdk = vi.hoisted(() => ({
  startSession: vi.fn(),
  endSession: vi.fn(),
  setMuted: vi.fn(),
  callbacks: {} as SdkCallbacks,
  update: (() => undefined) as (patch: Partial<SdkState>) => void,
}))

vi.mock('@elevenlabs/react', async () => {
  const React = await import('react')
  const initial: SdkState = { status: 'disconnected', mode: 'listening', isMuted: false }
  const Ctx = React.createContext<SdkState>(initial)
  function ConversationProvider({ children }: { children: ReactNode }) {
    const [state, setState] = React.useState(initial)
    React.useEffect(() => {
      sdk.update = (patch) => setState((s) => ({ ...s, ...patch }))
    }, [])
    return <Ctx.Provider value={state}>{children}</Ctx.Provider>
  }
  function useConversation(options: SdkCallbacks) {
    const state = React.useContext(Ctx)
    React.useEffect(() => {
      sdk.callbacks = options
    })
    return {
      ...state,
      isSpeaking: state.mode === 'speaking',
      isListening: state.mode === 'listening',
      startSession: sdk.startSession,
      endSession: sdk.endSession,
      setMuted: (muted: boolean) => {
        sdk.setMuted(muted)
        sdk.update({ isMuted: muted })
      },
    }
  }
  return { ConversationProvider, useConversation }
})

// ---- Fake REST API (the real fetch wrapper is replaced; error formatting stays real). ----------------------------
vi.mock('../../lib/api', async (importOriginal) => ({ ...(await importOriginal<typeof import('../../lib/api')>()), api: vi.fn() }))
const apiMock = vi.mocked(api)

const START: BrowserSessionStart = {
  screening_id: 's1', attempt_id: 'a1', attempt_number: 1, max_attempts: 3, conversation_id: 'conv_1',
  conversation_token: 'webrtc-token', connection_type: 'webrtc',
  dynamic_variables: { candidate_name: 'Ali', role_title: 'Backend Engineer' },
}

function screening(overrides: Partial<Screening> = {}): Screening {
  return {
    public_id: 's1', candidate_reference: 'c1', candidate_name: 'Ali Khan', requisition_reference: 'r1', requisition_title: 'Backend Engineer',
    channel: 'BROWSER_VOICE', status: 'PENDING_CALL', call_status: 'NOT_STARTED', consent_status: 'NOT_ASKED', ai_disclosure_confirmed: null,
    questions: ['Years of Django experience?'], script_version: 'screening-browser-v2', max_attempts: 3, attempt_count: 0,
    job: {
      title: 'Backend Engineer', department: 'Eng', location: 'Lahore', employment_type: 'FULL_TIME', work_mode: 'HYBRID',
      description: 'Build APIs', responsibilities: '', required_skills: ['Python'], preferred_skills: [], minimum_experience_years: '2.0',
      education_requirements: '', salary_min: null, salary_max: null, currency: 'PKR',
    },
    availability_statement: '', expected_salary_min: null, expected_salary_max: null, expected_salary_currency: '',
    expected_salary_period: '', expected_salary_statement: '', notice_period: '', notice_period_statement: '',
    next_attempt_not_before: null, question_answer_pairs: [], candidate_stated_availability: '', role_requirement_responses: [],
    candidate_questions: [], unresolved_questions: [], concise_summary: '', recommended_next_step_for_human_review: '', call_timestamp: null,
    transcript: [], analysis_warnings: [], analysis_model_version: '', analysis_prompt_version: '', error_code: '', error_message: '',
    created_by_name: 'rec', result_recorded_by_name: null, call_attempts: [], review: null, created_at: '', updated_at: '',
    ...overrides,
  }
}

function completion(state: BrowserSessionResult['session_state'], status: Screening['status'], outcome = 'COMPLETED'): BrowserSessionResult {
  return {
    ...screening({ status, attempt_count: 1 }), session_state: state,
    session_attempt: {
      public_id: 'a1', attempt_number: 1, provider: 'elevenlabs_webrtc', destination_masked: 'Browser session', status: 'ENDED', outcome,
      provider_status: 'done', telephony_status: '', termination_reason: '', duration_seconds: 60, error_code: '', error_message: '',
      provider_data_deleted: false, initiated_by_name: 'rec', started_at: '', ended_at: null,
    },
  }
}

const getUserMedia = vi.fn()

function renderSession(s: Screening = screening()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}><BrowserVoiceSession screening={s} /></QueryClientProvider>)
}

const startButton = () => screen.getByRole('button', { name: /start interview/i })
const endButton = () => screen.getByRole('button', { name: /end interview/i })
const statusText = () => screen.getByRole('status').textContent
const calls = (suffix: string) => apiMock.mock.calls.filter(([path]) => path.endsWith(suffix))

async function startLiveSession() {
  renderSession()
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(startButton())
  await waitFor(() => expect(sdk.startSession).toHaveBeenCalledTimes(1))
}

beforeEach(() => {
  vi.clearAllMocks()
  sdk.callbacks = {}
  getUserMedia.mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] })
  Object.defineProperty(navigator, 'mediaDevices', { value: { getUserMedia }, configurable: true })
  apiMock.mockImplementation(async (path: string) => {
    if (path.endsWith('/browser-session/')) return START
    if (path.endsWith('/browser-session/complete/')) return completion('concluded', 'AWAITING_HR_REVIEW')
    return undefined
  })
})

afterEach(() => {
  vi.useRealTimers()
})

describe('BrowserVoiceSession', () => {
  it('requires explicit consent before touching the microphone or the backend', () => {
    renderSession()
    expect(screen.getByText(/AI voice agent/)).toBeInTheDocument()
    expect(screen.getAllByText(/ElevenLabs/).length).toBeGreaterThan(0)
    expect(screen.getByText(/transcript/i, { selector: 'strong' })).toBeInTheDocument()
    expect(screen.getByText(/Microphone access is required/)).toBeInTheDocument()
    expect(startButton()).toBeDisabled()
    fireEvent.click(startButton())
    expect(getUserMedia).not.toHaveBeenCalled()
    expect(apiMock).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('checkbox'))
    expect(startButton()).toBeEnabled()
  })

  it('explains a denied microphone permission and does not start a session', async () => {
    getUserMedia.mockRejectedValueOnce(new DOMException('Permission denied', 'NotAllowedError'))
    renderSession()
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(startButton())
    expect(await screen.findByText(/Microphone access was blocked/)).toBeInTheDocument()
    expect(apiMock).not.toHaveBeenCalled()
    expect(sdk.startSession).not.toHaveBeenCalled()
    expect(startButton()).toBeEnabled()
  })

  it('starts with the server-issued WebRTC token and shows connecting, listening and speaking states', async () => {
    await startLiveSession()
    expect(calls('/browser-session/')[0][1]).toEqual({ body: { consent_acknowledged: true } })
    expect(sdk.startSession).toHaveBeenCalledWith({
      conversationToken: 'webrtc-token', connectionType: 'webrtc', dynamicVariables: START.dynamic_variables, userId: 's1',
    })
    expect(statusText()).toMatch(/Connecting/)
    act(() => {
      sdk.update({ status: 'connected' })
      sdk.callbacks.onConnect?.({ conversationId: 'conv_1' })
    })
    expect(statusText()).toMatch(/Listening/)
    act(() => sdk.update({ mode: 'speaking' }))
    expect(statusText()).toMatch(/Agent speaking/)
    act(() => sdk.update({ mode: 'listening' }))
    fireEvent.click(screen.getByRole('button', { name: /mute microphone/i }))
    expect(sdk.setMuted).toHaveBeenCalledWith(true)
    expect(screen.getByRole('button', { name: /unmute microphone/i })).toBeInTheDocument()
    expect(statusText()).toMatch(/muted/)
  })

  it('ends the interview, asks the backend for the authoritative result once, and reports it is ready for HR', async () => {
    await startLiveSession()
    act(() => {
      sdk.update({ status: 'connected' })
      sdk.callbacks.onConnect?.({ conversationId: 'conv_1' })
    })
    fireEvent.click(endButton())
    expect(sdk.endSession).toHaveBeenCalledTimes(1)
    act(() => {
      sdk.update({ status: 'disconnected' })
      sdk.callbacks.onDisconnect?.({ reason: 'user' }) // the SDK's own disconnect must not complete twice
    })
    expect(await screen.findByText(/waiting for HR review/)).toBeInTheDocument()
    expect(calls('/browser-session/complete/')).toHaveLength(1)
    expect(calls('/browser-session/complete/')[0][1]).toEqual({
      body: { attempt_id: 'a1', client_end_reason: 'user_ended', connected: true, conversation_id: 'conv_1' },
    })
  })

  it('keeps polling while ElevenLabs is still processing the transcript', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const responses = [completion('processing', 'CALL_IN_PROGRESS'), completion('concluded', 'AWAITING_HR_REVIEW')]
    apiMock.mockImplementation(async (path: string) => (path.endsWith('/browser-session/') ? START : responses.shift()))
    await startLiveSession()
    act(() => sdk.callbacks.onConnect?.({ conversationId: 'conv_1' }))
    act(() => sdk.callbacks.onDisconnect?.({ reason: 'agent' }))
    expect(await screen.findByText(/Waiting for ElevenLabs to finish processing/)).toBeInTheDocument()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4500)
    })
    expect(await screen.findByText(/waiting for HR review/)).toBeInTheDocument()
    expect(calls('/browser-session/complete/')).toHaveLength(2)
    expect(calls('/browser-session/complete/')[0][1]).toMatchObject({ body: { client_end_reason: 'agent_ended' } })
  })

  it('shows backend errors and lets the user try again', async () => {
    apiMock.mockRejectedValueOnce(new ApiError(503, { detail: 'Browser voice screening is not configured on the server.' }, 'Request failed (503)'))
    renderSession()
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(startButton())
    expect(await screen.findByText(/not configured on the server/)).toBeInTheDocument()
    expect(sdk.startSession).not.toHaveBeenCalled()
    expect(startButton()).toBeEnabled()
  })

  it('reports a connection failure before the session connected as start_failed', async () => {
    await startLiveSession()
    act(() => sdk.callbacks.onError?.('Could not establish a WebRTC connection'))
    expect(await screen.findByText(/Voice connection problem/)).toBeInTheDocument()
    await waitFor(() => expect(calls('/browser-session/complete/')).toHaveLength(1))
    expect(calls('/browser-session/complete/')[0][1]).toMatchObject({ body: { client_end_reason: 'start_failed', connected: false } })
  })

  it('prevents duplicate session starts', async () => {
    renderSession()
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(startButton())
    fireEvent.click(startButton())
    fireEvent.click(startButton())
    await waitFor(() => expect(sdk.startSession).toHaveBeenCalledTimes(1))
    expect(calls('/browser-session/')).toHaveLength(1)
    expect(startButton()).toBeDisabled()
  })

  it('does not offer a start button for a session that is already open elsewhere', () => {
    renderSession(screening({ status: 'CALL_IN_PROGRESS', attempt_count: 1 }))
    expect(screen.queryByRole('button', { name: /start interview/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /check session result/i })).toBeInTheDocument()
  })
})
