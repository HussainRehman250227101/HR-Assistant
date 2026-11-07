import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useBatchUpload, useCandidates, useDeleteRequisition, useRequisition, useRubric, useSaveRequisition, useSaveRubric } from '../../api/hooks'
import { useAuth } from '../../auth/AuthContext'
import { CandidateFormModal } from '../candidates/CandidateFormModal'
import { Alert, Badge, Button, Card, Empty, ErrorAlert, Field, Input, KeyValue, Loading, Modal, PageHeader, Table, Td } from '../../components/ui'
import { formatDate } from '../../lib/format'
import type { RequisitionStatus } from '../../lib/types'

const TRANSITIONS: Record<RequisitionStatus, { to: RequisitionStatus; label: string; variant: 'primary' | 'secondary' | 'danger' }[]> = {
  DRAFT: [{ to: 'OPEN', label: 'Open requisition', variant: 'primary' }, { to: 'CLOSED', label: 'Close', variant: 'danger' }],
  OPEN: [{ to: 'ON_HOLD', label: 'Put on hold', variant: 'secondary' }, { to: 'CLOSED', label: 'Close', variant: 'danger' }],
  ON_HOLD: [{ to: 'OPEN', label: 'Re-open', variant: 'primary' }, { to: 'CLOSED', label: 'Close', variant: 'danger' }],
  CLOSED: [],
}

const CRITERIA: Record<string, string> = {
  required_skills: 'Required skills',
  relevant_experience: 'Relevant experience',
  role_related_projects: 'Role-related projects',
  education_certifications: 'Education and certifications',
  other_job_evidence: 'Other job-related evidence',
}

function RubricCard({ reference }: { reference: string }) {
  const rubric = useRubric(reference)
  const save = useSaveRubric(reference)
  const [weights, setWeights] = useState<Record<string, number>>({})
  const [notes, setNotes] = useState('')
  const [editing, setEditing] = useState(false)
  if (rubric.isLoading) return <Loading />
  if (!rubric.data) return <ErrorAlert error={rubric.error} />
  const shown = editing ? weights : rubric.data.weights
  const total = Object.values(shown).reduce((a, b) => a + (Number(b) || 0), 0)
  return (
    <Card
      title={`Scoring rubric v${rubric.data.version}`}
      actions={!editing && <Button size="sm" variant="secondary" onClick={() => { setWeights(rubric.data!.weights); setEditing(true) }}>Edit weights</Button>}
    >
      <ErrorAlert error={save.error} />
      <div className="grid gap-3 sm:grid-cols-5">
        {Object.entries(CRITERIA).map(([key, label]) => (
          <Field key={key} label={label}>
            <Input type="number" min={0} max={100} disabled={!editing} value={shown[key] ?? 0} onChange={(e) => setWeights((w) => ({ ...w, [key]: Number(e.target.value) }))} />
          </Field>
        ))}
      </div>
      {editing && (
        <div className="mt-4 space-y-3">
          <Field label="Change note"><Input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Why the weights changed" /></Field>
          <div className="flex items-center gap-3">
            <Button size="sm" loading={save.isPending} disabled={total !== 100}
              onClick={async () => { await save.mutateAsync({ name: rubric.data!.name, weights, notes }); setEditing(false); setNotes('') }}>
              Save as new version
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setEditing(false)}>Cancel</Button>
            <span className={`text-sm ${total === 100 ? 'text-emerald-700' : 'text-rose-700'}`}>Total {total} / 100</span>
          </div>
        </div>
      )}
      <p className="mt-3 text-xs text-slate-500">Rubrics are versioned; earlier evaluations keep the version they were scored with.</p>
    </Card>
  )
}

export function RequisitionDetailPage() {
  const { ref } = useParams()
  const navigate = useNavigate()
  const { isRecruiter } = useAuth()
  const requisition = useRequisition(ref)
  const candidates = useCandidates({ requisition: ref, page_size: 100 })
  const save = useSaveRequisition()
  const remove = useDeleteRequisition()
  const upload = useBatchUpload(ref ?? '')
  const [addOpen, setAddOpen] = useState(false)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [files, setFiles] = useState<File[]>([])
  const [uploadResult, setUploadResult] = useState<string | null>(null)

  if (requisition.isLoading) return <Loading />
  if (!requisition.data) return <ErrorAlert error={requisition.error} />
  const r = requisition.data

  return (
    <>
      <PageHeader
        title={<span className="flex items-center gap-3">{r.title} <Badge value={r.status} /></span>}
        subtitle={`${r.department} · ${r.location || 'No location'} · ${r.work_mode.toLowerCase()} · ref ${r.reference_code.slice(0, 8)}`}
        actions={isRecruiter && (
          <>
            {TRANSITIONS[r.status].map((t) => (
              <Button key={t.to} variant={t.variant} loading={save.isPending && save.variables?.data.status === t.to}
                onClick={() => (t.to !== 'CLOSED' || confirm('Closing is permanent. Continue?')) && save.mutate({ ref: r.reference_code, data: { status: t.to } })}>
                {t.label}
              </Button>
            ))}
            {r.status !== 'CLOSED' && <Link to={`/requisitions/${r.reference_code}/edit`} className="rounded-md px-3.5 py-2 text-sm font-medium text-slate-700 ring-1 ring-slate-300 hover:bg-slate-50">Edit</Link>}
            {r.status === 'DRAFT' && (
              <Button variant="ghost" onClick={async () => { if (confirm('Delete this draft?')) { await remove.mutateAsync(r.reference_code); navigate('/requisitions') } }}>Delete draft</Button>
            )}
          </>
        )}
      />
      <div className="space-y-6">
        <ErrorAlert error={save.error ?? remove.error} />
        <Card title="Details">
          <KeyValue items={[
            ['Hiring manager', r.hiring_manager_name],
            ['Employment type', r.employment_type.replace('_', ' ').toLowerCase()],
            ['Minimum experience', `${r.minimum_experience_years} years`],
            ['Education', r.education_requirements],
            ['Required skills', r.required_skills.join(', ')],
            ['Preferred skills', r.preferred_skills.join(', ')],
            ['Salary', r.salary_min || r.salary_max ? `${r.salary_min ?? '?'} – ${r.salary_max ?? '?'} ${r.currency}` : ''],
            ['Headcount', String(r.headcount)],
            ['Opened', formatDate(r.opened_at)],
            ['Target close', formatDate(r.target_close_date, false)],
          ]} />
          <div className="mt-4 text-sm whitespace-pre-line text-slate-700">{r.description}</div>
          {r.responsibilities && <div className="mt-3 text-sm whitespace-pre-line text-slate-600">{r.responsibilities}</div>}
          <h3 className="mt-5 mb-2 text-xs font-semibold text-slate-500 uppercase">Approved screening questions</h3>
          {r.screening_questions.length ? (
            <ol className="list-decimal space-y-1 pl-5 text-sm">{r.screening_questions.map((q) => <li key={q}>{q}</li>)}</ol>
          ) : <Alert tone="warning">No screening questions yet. Screening calls require approved questions.</Alert>}
        </Card>
        {isRecruiter && <RubricCard reference={r.reference_code} />}
        <Card
          title={`Candidates (${candidates.data?.count ?? 0})`}
          actions={isRecruiter && r.status === 'OPEN' && (
            <>
              <Button size="sm" onClick={() => setAddOpen(true)}>Add candidate</Button>
              <Button size="sm" variant="secondary" onClick={() => { setUploadOpen(true); setUploadResult(null) }}>Batch upload resumes</Button>
            </>
          )}
        >
          {r.status !== 'OPEN' && <div className="mb-3"><Alert tone="info">Candidates and resumes can only be added while the requisition is open.</Alert></div>}
          {candidates.isLoading ? <Loading /> : !candidates.data?.results.length ? <Empty>No candidates yet.</Empty> : (
            <Table head={['Candidate', 'Status', 'Resumes', 'Added']}>
              {candidates.data.results.map((c) => (
                <tr key={c.public_id} className="hover:bg-slate-50">
                  <Td>
                    <Link to={`/candidates/${c.public_id}`} className="font-medium text-indigo-700 hover:underline">{c.display_name}</Link>
                    {c.identity_review_required && <span className="ml-2"><Badge tone="amber" label="Identity review" /></span>}
                  </Td>
                  <Td><Badge value={c.current_status} /></Td>
                  <Td>{c.resume_documents.length}</Td>
                  <Td>{formatDate(c.created_at, false)}</Td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
      </div>
      <CandidateFormModal open={addOpen} onClose={() => setAddOpen(false)} requisitionId={r.id} />
      <Modal open={uploadOpen} title="Batch upload resumes" onClose={() => setUploadOpen(false)}>
        <div className="space-y-4">
          <p className="text-sm text-slate-600">Each PDF/DOCX creates a placeholder candidate flagged for identity review. Names and contact details are never guessed.</p>
          <ErrorAlert error={upload.error} />
          {uploadResult && <Alert tone="success">{uploadResult}</Alert>}
          <input type="file" multiple accept=".pdf,.docx" onChange={(e) => setFiles(Array.from(e.target.files ?? []))} className="block w-full text-sm" />
          <Button disabled={!files.length} loading={upload.isPending} onClick={async () => {
            const res = await upload.mutateAsync(files)
            setUploadResult(`${res.uploaded_count} resume(s) uploaded. Process them from each candidate page or run the resume worker.`)
            setFiles([])
          }}>Upload {files.length || ''} file(s)</Button>
        </div>
      </Modal>
    </>
  )
}
