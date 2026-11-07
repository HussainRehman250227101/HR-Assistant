import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useSaveCandidate } from '../../api/hooks'
import { Button, ErrorAlert, Field, Input, Modal, Select } from '../../components/ui'
import type { Candidate } from '../../lib/types'

const CONSENT = [{ value: 'PENDING', label: 'Pending' }, { value: 'GRANTED', label: 'Granted' }, { value: 'DECLINED', label: 'Declined' }]

type Props = { open: boolean; onClose: () => void; requisitionId?: number; candidate?: Candidate }

export function CandidateFormModal(props: Props) {
  return (
    <Modal open={props.open} onClose={props.onClose} title={props.candidate ? 'Edit candidate details' : 'Add candidate'}>
      {props.open && <CandidateForm {...props} />}
    </Modal>
  )
}

function CandidateForm({ onClose, requisitionId, candidate }: Props) {
  const save = useSaveCandidate()
  const navigate = useNavigate()
  const [form, setForm] = useState<Record<string, string>>(() => ({
    full_name: candidate?.full_name ?? '', email: candidate?.email ?? '', phone: candidate?.phone ?? '',
    location: candidate?.location ?? '', linkedin_url: candidate?.linkedin_url ?? '', source: candidate?.source ?? 'RESUME_UPLOAD',
    contact_consent_status: candidate?.contact_consent_status ?? 'PENDING',
    recording_consent_status: candidate?.recording_consent_status ?? 'PENDING',
  }))

  const set = (key: string) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }))

  async function submit(e: FormEvent) {
    e.preventDefault()
    const data: Partial<Candidate> = { ...form, email: form.email || null } as Partial<Candidate>
    if (!candidate) data.requisition = requisitionId
    const saved = await save.mutateAsync({ id: candidate?.public_id, data })
    onClose()
    if (!candidate) navigate(`/candidates/${saved.public_id}`)
  }

  return (
    <form onSubmit={submit} className="space-y-4">
        <ErrorAlert error={save.error} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Full name"><Input value={form.full_name ?? ''} onChange={set('full_name')} /></Field>
          <Field label="Email"><Input type="email" value={form.email ?? ''} onChange={set('email')} /></Field>
          <Field label="Phone" hint="Screening calls: Pakistani numbers only (+92…)"><Input value={form.phone ?? ''} onChange={set('phone')} placeholder="+923001234567" /></Field>
          <Field label="Location"><Input value={form.location ?? ''} onChange={set('location')} /></Field>
          <Field label="LinkedIn URL" className="sm:col-span-2"><Input type="url" value={form.linkedin_url ?? ''} onChange={set('linkedin_url')} /></Field>
          <Field label="Source">
            <Select value={form.source ?? 'RESUME_UPLOAD'} onChange={set('source')} options={[
              { value: 'RESUME_UPLOAD', label: 'Resume upload' }, { value: 'REFERRAL', label: 'Referral' },
              { value: 'CAREER_PAGE', label: 'Career page' }, { value: 'OTHER', label: 'Other' }]} />
          </Field>
          <Field label="Contact consent"><Select value={form.contact_consent_status ?? 'PENDING'} onChange={set('contact_consent_status')} options={CONSENT} /></Field>
          <Field label="Recording consent"><Select value={form.recording_consent_status ?? 'PENDING'} onChange={set('recording_consent_status')} options={CONSENT} /></Field>
        </div>
        <div className="flex gap-2">
          <Button type="submit" loading={save.isPending}>Save</Button>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
        </div>
    </form>
  )
}
