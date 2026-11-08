import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../../lib/api'
import type { AvailabilitySlot, Interview } from '../../lib/types'
import { MySchedulePage } from './MySchedulePage'

vi.mock('../../lib/api', async (importOriginal) => ({ ...(await importOriginal<typeof import('../../lib/api')>()), api: vi.fn() }))
const apiMock = vi.mocked(api)

const auth = vi.hoisted(() => ({ value: { user: { id: 7, role: 'RECRUITER' }, hasFullAccess: true, isAdmin: false } }))
vi.mock('../../auth/AuthContext', () => ({ useAuth: () => auth.value }))

// 2030 keeps the fixtures in the future; Karachi is UTC+5, so 05:00Z is 10:00 local.
const SLOT_BOOKED: AvailabilitySlot = {
  public_id: 'slot-1', interviewer: 7, interviewer_name: 'Rida Khan', start: '2030-11-12T05:00:00Z', end: '2030-11-12T07:00:00Z',
  timezone: 'Asia/Karachi', source: 'INTERNAL_AVAILABILITY', source_label: 'Internal',
}
const SLOT_FREE: AvailabilitySlot = { ...SLOT_BOOKED, public_id: 'slot-2', start: '2030-11-13T05:00:00Z', end: '2030-11-13T07:00:00Z' }

function interview(patch: Partial<Interview>): Interview {
  return {
    public_id: 'i-1', candidate_reference: 'c-1', candidate_name: 'Sara Ahmed', requisition_title: 'Backend Engineer',
    interviewer: 7, interviewer_name: 'Rida Khan', interviewer_email: 'rida@example.test', status: 'SCHEDULED',
    duration_minutes: 45, timezone: 'Asia/Karachi', mode: 'VIDEO', meeting_link: '', contact_whatsapp: '+923001234567',
    auto_scheduled: true, location: '', candidate_availability_note: '', candidate_windows: [], proposed_slots: [],
    calendar_source: 'x', calendar_source_label: 'x', confirmed_start: '2030-11-12T05:30:00Z', confirmed_end: '2030-11-12T06:15:00Z',
    candidate_confirmed_at: null, interviewer_confirmed_at: null, cancellation_reason: '', sequence: 0, created_by_name: 'HR Admin',
    created_at: '2030-11-01T08:00:00Z', updated_at: '2030-11-01T08:00:00Z', ...patch,
  }
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={client}><MemoryRouter><MySchedulePage /></MemoryRouter></QueryClientProvider>,
  )
}

beforeEach(() => {
  apiMock.mockReset()
  apiMock.mockImplementation(async (path: string) => {
    if (path.startsWith('/scheduling/availability/')) return [SLOT_BOOKED, SLOT_FREE] as never
    if (path.startsWith('/scheduling/interviews/')) return [interview({})] as never
    return undefined as never
  })
})

describe('My schedule page', () => {
  it('asks the API only for my own availability and my assigned interviews', async () => {
    renderPage()
    await screen.findByText('Sara Ahmed')
    const paths = apiMock.mock.calls.map((c) => String(c[0]))
    expect(paths.some((p) => p.startsWith('/scheduling/availability/') && p.includes('interviewer=7'))).toBe(true)
    expect(paths.filter((p) => p.startsWith('/scheduling/interviews/')).every((p) => p.includes('mine=1'))).toBe(true)
  })

  it('shows each availability window as free or booked, with dates as DD/MM/YYYY', async () => {
    renderPage()
    const table = await screen.findByRole('table')
    expect(within(table).getByText('Booked: Sara Ahmed')).toBeInTheDocument()
    expect(within(table).getByText('Free')).toBeInTheDocument()
    expect(within(table).getByText(/12\/11\/2030, 10:00/)).toBeInTheDocument()
    expect(within(table).getByText(/13\/11\/2030, 10:00/)).toBeInTheDocument()
  })

  it('shows the details of an assigned interview', async () => {
    renderPage()
    await screen.findByText('Sara Ahmed')
    expect(screen.getByText(/Backend Engineer/)).toBeInTheDocument()
    expect(screen.getByText('WhatsApp video call on +923001234567')).toBeInTheDocument()
    expect(screen.getByText('45 minutes')).toBeInTheDocument()
    expect(screen.getByText('Scheduling agent (automatic)')).toBeInTheDocument()
    expect(screen.getByText(/invitation was sent to the candidate/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Sara Ahmed' })).toHaveAttribute('href', '/candidates/c-1?tab=interview')
  })

  it('shows on-site interviews with their address', async () => {
    apiMock.mockImplementation(async (path: string) => {
      if (path.startsWith('/scheduling/availability/')) return [] as never
      return [interview({ mode: 'ONSITE', location: 'Netsol Lahore', contact_whatsapp: '', auto_scheduled: false })] as never
    })
    renderPage()
    expect(await screen.findByText('On-site: Netsol Lahore')).toBeInTheDocument()
    expect(screen.getByText('You have not added any upcoming availability yet.')).toBeInTheDocument()
  })

  it('links an assigned candidate for an interviewer-only recruiter too', async () => {
    auth.value = { user: { id: 7, role: 'RECRUITER' }, hasFullAccess: false, isAdmin: false }
    renderPage()
    expect(await screen.findByRole('link', { name: 'Sara Ahmed' })).toHaveAttribute('href', '/candidates/c-1?tab=interview')
    auth.value = { user: { id: 7, role: 'RECRUITER' }, hasFullAccess: true, isAdmin: false }
  })

  it('adds availability for me, sending the date as ISO', async () => {
    renderPage()
    await screen.findByText('Sara Ahmed')
    const date = screen.getByPlaceholderText('DD/MM/YYYY')
    await userEvent.clear(date)
    await userEvent.type(date, '14112030')
    await userEvent.click(screen.getByRole('button', { name: 'Add availability' }))
    await waitFor(() => {
      const post = apiMock.mock.calls.find((c) => c[0] === '/scheduling/availability/')
      expect(post).toBeTruthy()
      expect(post?.[1]).toMatchObject({ body: { date: '2030-11-14', start_time: '09:00', end_time: '13:00', interviewer: 7 } })
    })
  })

  it('blocks an end time that is not after the start time', async () => {
    renderPage()
    await screen.findByText('Sara Ahmed')
    const to = screen.getByLabelText('To')
    await userEvent.clear(to)
    await userEvent.type(to, '08:00')
    expect(screen.getByRole('button', { name: 'Add availability' })).toBeDisabled()
    expect(screen.getByText('The end time must be after the start time.')).toBeInTheDocument()
  })
})
