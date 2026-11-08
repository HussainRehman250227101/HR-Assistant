import { useState, type FormEvent } from 'react'
import { useUsers, type InterviewPlanInput } from '../../api/hooks'
import { Button, ErrorAlert, DateInput, Field, Input, Select, Textarea } from '../../components/ui'
import { COMMON_TIMEZONES } from '../../lib/format'
import type { Interview, LocalWindow } from '../../lib/types'

const today = () => new Date().toISOString().slice(0, 10)

export function InterviewPlanForm({ initial, availabilityHint, submitLabel, busy, error, onSubmit }: {
  initial?: Interview
  availabilityHint?: string
  submitLabel: string
  busy: boolean
  error: unknown
  onSubmit: (data: InterviewPlanInput) => Promise<unknown>
}) {
  const users = useUsers()
  const [interviewer, setInterviewer] = useState(initial ? String(initial.interviewer) : '')
  const [duration, setDuration] = useState(String(initial?.duration_minutes ?? 45))
  const [tz, setTz] = useState(initial?.timezone ?? 'Asia/Karachi')
  const [mode, setMode] = useState(initial?.mode ?? 'VIDEO')
  const [link, setLink] = useState(initial?.meeting_link ?? '')
  const [whatsapp, setWhatsapp] = useState(initial?.contact_whatsapp ?? '')
  const [location, setLocation] = useState(initial?.location ?? '')
  const [note, setNote] = useState(initial?.candidate_availability_note ?? availabilityHint ?? '')
  const [windows, setWindows] = useState<LocalWindow[]>([{ date: today(), start_time: '10:00', end_time: '17:00' }])

  const setWindow = (i: number, key: keyof LocalWindow, value: string) => setWindows((list) => list.map((w, idx) => (idx === i ? { ...w, [key]: value } : w)))

  async function submit(e: FormEvent) {
    e.preventDefault()
    await onSubmit({
      interviewer: Number(interviewer), duration_minutes: Number(duration), timezone: tz, mode,
      meeting_link: link, contact_whatsapp: whatsapp, location, candidate_availability_note: note, candidate_windows: windows,
    })
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <ErrorAlert error={error} />
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Interviewer">
          <Select required value={interviewer} onChange={(e) => setInterviewer(e.target.value)}
            options={[{ value: '', label: 'Select…' }, ...(users.data ?? []).map((u) => ({ value: String(u.id), label: `${u.full_name || u.username} (${u.role.toLowerCase().replace('_', ' ')})` }))]} />
        </Field>
        <Field label="Duration (minutes)"><Input type="number" min={15} max={240} step={15} value={duration} onChange={(e) => setDuration(e.target.value)} /></Field>
        <Field label="Candidate time zone"><Select value={tz} onChange={(e) => setTz(e.target.value)} options={COMMON_TIMEZONES.map((z) => ({ value: z, label: z }))} /></Field>
        <Field label="Format">
          <Select value={mode} onChange={(e) => setMode(e.target.value as Interview['mode'])} options={[{ value: 'VIDEO', label: 'Video call (link or WhatsApp)' }, { value: 'ONSITE', label: 'On-site' }, { value: 'PHONE', label: 'Phone' }]} />
        </Field>
        {mode === 'VIDEO' && <Field label="Meeting link (or WhatsApp number)"><Input type="url" required={!whatsapp} value={link} onChange={(e) => setLink(e.target.value)} placeholder="https://…" /></Field>}
        {mode === 'VIDEO' && <Field label="WhatsApp number (video call)"><Input type="tel" required={!link} value={whatsapp} onChange={(e) => setWhatsapp(e.target.value)} placeholder="+923001234567" /></Field>}
        {mode === 'ONSITE' && <Field label="Location" className="sm:col-span-2"><Input required value={location} onChange={(e) => setLocation(e.target.value)} /></Field>}
      </div>
      <Field label="Candidate's stated availability (from screening)"><Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      <div>
        <div className="mb-1 text-sm font-medium text-slate-700">Candidate availability windows ({tz})</div>
        <div className="space-y-2">
          {windows.map((w, i) => (
            <div key={i} className="flex flex-wrap items-center gap-2">
              <DateInput required value={w.date} onChange={(iso) => setWindow(i, 'date', iso)} className="w-44" />
              <Input type="time" required value={w.start_time} onChange={(e) => setWindow(i, 'start_time', e.target.value)} className="w-28" />
              <span className="text-slate-400">to</span>
              <Input type="time" required value={w.end_time} onChange={(e) => setWindow(i, 'end_time', e.target.value)} className="w-28" />
              {windows.length > 1 && <Button size="sm" variant="ghost" onClick={() => setWindows((l) => l.filter((_, idx) => idx !== i))}>Remove</Button>}
            </div>
          ))}
        </div>
        <Button size="sm" variant="ghost" className="mt-2" onClick={() => setWindows((l) => [...l, { ...l[l.length - 1] }])}>+ Add window</Button>
      </div>
      <Button type="submit" loading={busy}>{submitLabel}</Button>
    </form>
  )
}
