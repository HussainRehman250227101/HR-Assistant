import { useState, type FormEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useRequisition, useSaveRequisition, useUsers } from '../../api/hooks'
import { Button, Card, ErrorAlert, Field, Input, Loading, PageHeader, Select, Textarea } from '../../components/ui'
import type { Requisition } from '../../lib/types'

type FormState = Record<string, string>

const EMPTY: FormState = {
  title: '', department: '', location: '', employment_type: 'FULL_TIME', work_mode: 'ONSITE', description: '',
  responsibilities: '', required_skills: '', preferred_skills: '', screening_questions: '', minimum_experience_years: '0',
  education_requirements: '', salary_min: '', salary_max: '', currency: 'PKR', headcount: '1', hiring_manager: '', target_close_date: '',
}

const lines = (value: string) => value.split('\n').map((s) => s.trim()).filter(Boolean)

function toForm(r: Requisition): FormState {
  return {
    title: r.title, department: r.department, location: r.location, employment_type: r.employment_type, work_mode: r.work_mode,
    description: r.description, responsibilities: r.responsibilities, required_skills: r.required_skills.join('\n'),
    preferred_skills: r.preferred_skills.join('\n'), screening_questions: r.screening_questions.join('\n'),
    minimum_experience_years: r.minimum_experience_years, education_requirements: r.education_requirements,
    salary_min: r.salary_min ?? '', salary_max: r.salary_max ?? '', currency: r.currency, headcount: String(r.headcount),
    hiring_manager: r.hiring_manager ? String(r.hiring_manager) : '', target_close_date: r.target_close_date ?? '',
  }
}

export function RequisitionFormPage() {
  const { ref } = useParams()
  const existing = useRequisition(ref)
  if (ref && existing.isLoading) return <Loading />
  if (ref && !existing.data) return <ErrorAlert error={existing.error} />
  return <RequisitionForm key={ref ?? 'new'} reference={ref} initial={existing.data ? toForm(existing.data) : EMPTY} />
}

function RequisitionForm({ reference: ref, initial }: { reference?: string; initial: FormState }) {
  const navigate = useNavigate()
  const managers = useUsers('HIRING_MANAGER')
  const save = useSaveRequisition()
  const [form, setForm] = useState<FormState>(initial)

  const set = (key: string) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }))

  async function submit(e: FormEvent) {
    e.preventDefault()
    const data: Partial<Requisition> = {
      title: form.title, department: form.department, location: form.location, employment_type: form.employment_type,
      work_mode: form.work_mode, description: form.description, responsibilities: form.responsibilities,
      required_skills: lines(form.required_skills), preferred_skills: lines(form.preferred_skills),
      screening_questions: lines(form.screening_questions), minimum_experience_years: form.minimum_experience_years || '0',
      education_requirements: form.education_requirements, salary_min: form.salary_min || null, salary_max: form.salary_max || null,
      currency: form.currency, headcount: Number(form.headcount) || 1,
      hiring_manager: form.hiring_manager ? Number(form.hiring_manager) : null, target_close_date: form.target_close_date || null,
    }
    const saved = await save.mutateAsync({ ref, data })
    navigate(`/requisitions/${saved.reference_code}`)
  }

  return (
    <>
      <PageHeader title={ref ? 'Edit requisition' : 'New requisition'} subtitle="Screening questions are the approved list the screening agent must follow (SRS §8)." />
      <form onSubmit={submit} className="space-y-6">
        <ErrorAlert error={save.error} />
        <Card title="Role">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Job title"><Input required value={form.title} onChange={set('title')} /></Field>
            <Field label="Department"><Input required value={form.department} onChange={set('department')} /></Field>
            <Field label="Location"><Input value={form.location} onChange={set('location')} /></Field>
            <Field label="Work arrangement">
              <Select value={form.work_mode} onChange={set('work_mode')} options={[{ value: 'ONSITE', label: 'On-site' }, { value: 'HYBRID', label: 'Hybrid' }, { value: 'REMOTE', label: 'Remote' }]} />
            </Field>
            <Field label="Employment type">
              <Select value={form.employment_type} onChange={set('employment_type')} options={['FULL_TIME', 'PART_TIME', 'CONTRACT', 'TEMPORARY', 'INTERNSHIP'].map((v) => ({ value: v, label: v.replace('_', ' ').toLowerCase() }))} />
            </Field>
            <Field label="Hiring manager">
              <Select value={form.hiring_manager} onChange={set('hiring_manager')} options={[{ value: '', label: '— None —' }, ...(managers.data ?? []).map((u) => ({ value: String(u.id), label: u.full_name || u.username }))]} />
            </Field>
            <Field label="Headcount"><Input type="number" min={1} value={form.headcount} onChange={set('headcount')} /></Field>
            <Field label="Target close date"><Input type="date" value={form.target_close_date} onChange={set('target_close_date')} /></Field>
          </div>
        </Card>
        <Card title="Job description and requirements">
          <div className="grid gap-4">
            <Field label="Job description"><Textarea required rows={6} value={form.description} onChange={set('description')} /></Field>
            <Field label="Responsibilities"><Textarea rows={4} value={form.responsibilities} onChange={set('responsibilities')} /></Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Required skills" hint="One per line"><Textarea rows={5} value={form.required_skills} onChange={set('required_skills')} /></Field>
              <Field label="Preferred skills" hint="One per line"><Textarea rows={5} value={form.preferred_skills} onChange={set('preferred_skills')} /></Field>
              <Field label="Minimum experience (years)"><Input type="number" step="0.5" min={0} value={form.minimum_experience_years} onChange={set('minimum_experience_years')} /></Field>
              <Field label="Education requirements"><Input value={form.education_requirements} onChange={set('education_requirements')} /></Field>
            </div>
            <Field label="Approved screening questions" hint="One per line. Job-related only — never protected or sensitive topics.">
              <Textarea rows={6} value={form.screening_questions} onChange={set('screening_questions')} />
            </Field>
          </div>
        </Card>
        <Card title="Compensation">
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Salary min"><Input type="number" min={0} value={form.salary_min} onChange={set('salary_min')} /></Field>
            <Field label="Salary max"><Input type="number" min={0} value={form.salary_max} onChange={set('salary_max')} /></Field>
            <Field label="Currency"><Input maxLength={3} value={form.currency} onChange={set('currency')} /></Field>
          </div>
        </Card>
        <div className="flex gap-2">
          <Button type="submit" loading={save.isPending}>Save requisition</Button>
          <Button variant="secondary" onClick={() => navigate(-1)}>Cancel</Button>
        </div>
      </form>
    </>
  )
}
