import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../../lib/api'
import type { Interview } from '../../lib/types'
import { ForgotPasswordPage } from '../PasswordPages'
import { MySchedulePage } from './MySchedulePage'

vi.mock('../../lib/api', async (importOriginal) => ({ ...(await importOriginal<typeof import('../../lib/api')>()), api: vi.fn() }))
const apiMock = vi.mocked(api)
vi.mock('../../auth/AuthContext', () => ({ useAuth: () => ({ user: { id: 7, role: 'RECRUITER' }, hasFullAccess: false, isAdmin: false }) }))

const PAST: Interview = {
  public_id: 'i-1', candidate_reference: 'c-1', candidate_name: 'Sara Ahmed', requisition_title: 'Backend Engineer',
  interviewer: 7, interviewer_name: 'Rida Khan', interviewer_email: 'rida@example.test', status: 'SCHEDULED',
  duration_minutes: 45, timezone: 'Asia/Karachi', mode: 'VIDEO', meeting_link: '', contact_whatsapp: '+923001234567',
  auto_scheduled: false, location: '', candidate_availability_note: '', candidate_windows: [], proposed_slots: [],
  calendar_source: 'x', calendar_source_label: 'x', confirmed_start: '2020-01-01T05:00:00Z', confirmed_end: '2020-01-01T05:45:00Z',
  candidate_confirmed_at: null, interviewer_confirmed_at: null, cancellation_reason: '', sequence: 0, created_by_name: 'HR Admin',
  created_at: '2019-12-20T08:00:00Z', updated_at: '2019-12-20T08:00:00Z',
  feedback_questions: ['Technical depth?', 'Communication?'], feedback: null, early_completion_allowed: false,
}

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}><MemoryRouter>{node}</MemoryRouter></QueryClientProvider>)
}

beforeEach(() => {
  apiMock.mockReset()
  apiMock.mockImplementation(async (path: string) => {
    if (path.startsWith('/scheduling/calendar/')) return { url: 'https://api.example.test/feed.ics' } as never
    if (path.startsWith('/scheduling/availability/')) return [] as never
    if (path.startsWith('/scheduling/interviews/') && path.endsWith('/complete/')) return { ...PAST, status: 'COMPLETED' } as never
    if (path.startsWith('/scheduling/interviews/')) return [PAST] as never
    return undefined as never
  })
})

describe('Interviewer marks an interview done', () => {
  it('requires a Poor/Average/Good answer for every question before it can be submitted', async () => {
    wrap(<MySchedulePage />)
    await userEvent.click(await screen.findByRole('button', { name: 'Mark interview done' }))
    expect(screen.getAllByRole('radio')).toHaveLength(6) // 2 questions x 3 options
    const buttons = screen.getAllByRole('button', { name: 'Mark interview done' })
    const modalSubmit = buttons[buttons.length - 1]
    expect(modalSubmit).toBeDisabled()
    const radios = screen.getAllByRole('radio')
    await userEvent.click(radios[2]) // question 1: Good
    expect(modalSubmit).toBeDisabled()
    await userEvent.click(radios[4]) // question 2: Average
    expect(modalSubmit).toBeEnabled()
    await userEvent.click(modalSubmit)
    await waitFor(() => {
      const post = apiMock.mock.calls.find((c) => String(c[0]).endsWith('/complete/'))
      expect(post?.[1]).toMatchObject({ body: { answers: [{ index: 0, rating: 'GOOD' }, { index: 1, rating: 'AVERAGE' }] } })
    })
  })

  it('offers no mark-done button before the interview has started', async () => {
    apiMock.mockImplementation(async (path: string) => {
      if (path.startsWith('/scheduling/calendar/')) return { url: 'x' } as never
      if (path.startsWith('/scheduling/availability/')) return [] as never
      return [{ ...PAST, confirmed_start: '2099-01-01T05:00:00Z', confirmed_end: '2099-01-01T05:45:00Z' }] as never
    })
    wrap(<MySchedulePage />)
    await screen.findByText('Sara Ahmed')
    expect(screen.queryByRole('button', { name: 'Mark interview done' })).not.toBeInTheDocument()
  })
})

describe('Forgot password', () => {
  it('sends the email address and shows the neutral confirmation', async () => {
    apiMock.mockResolvedValue({ detail: 'If that email address belongs to an account, a reset link has been sent.' } as never)
    wrap(<ForgotPasswordPage />)
    await userEvent.type(screen.getByLabelText('Email'), 'rida@example.test')
    await userEvent.click(screen.getByRole('button', { name: 'Send reset link' }))
    expect(await screen.findByText(/reset link has been sent/i)).toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledWith('/auth/password/forgot/', { method: 'POST', body: { email: 'rida@example.test' } })
  })
})
