import { useState } from 'react'
import { Link } from 'react-router-dom'
import { KeyValue } from '../../components/ui'
import { expectedSalaryText, formatMoneyRange, humanize } from '../../lib/format'
import type { Screening } from '../../lib/types'

function Skills({ items }: { items: string[] }) {
  if (!items.length) return null
  return (
    <span className="flex flex-wrap gap-1">
      {items.map((skill) => <span key={skill} className="rounded bg-white px-1.5 py-0.5 text-xs ring-1 ring-slate-200">{skill}</span>)}
    </span>
  )
}

/** The job description HR compares the screening answers with (FR-08). The budget is never shared with the AI agent. */
export function ScreeningJobPanel({ screening }: { screening: Screening }) {
  const job = screening.job
  const [expanded, setExpanded] = useState(false)
  const budget = formatMoneyRange(job.salary_min, job.salary_max, job.currency)
  const expected = expectedSalaryText(screening)
  const long = job.description.length + job.responsibilities.length > 500
  return (
    <section className="space-y-4 rounded-md bg-slate-50 p-4 ring-1 ring-slate-200">
      <div className="flex items-start justify-between gap-2">
        <h4 className="text-xs font-semibold text-slate-500 uppercase">Job description · {job.title}</h4>
        <Link to={`/requisitions/${screening.requisition_reference}`} className="text-xs text-indigo-700 hover:underline">Open requisition</Link>
      </div>
      <div className="grid gap-3 text-sm sm:grid-cols-2">
        <div className="rounded-md bg-white p-3 ring-1 ring-slate-200">
          <div className="text-xs text-slate-500">Job salary budget</div>
          <div className={budget ? 'font-medium' : 'text-slate-400'}>{budget || 'Not set on the requisition'}</div>
        </div>
        <div className="rounded-md bg-white p-3 ring-1 ring-slate-200">
          <div className="text-xs text-slate-500">Candidate expects</div>
          <div className={expected ? 'font-medium' : 'text-slate-400'}>{expected || 'Not stated'}</div>
        </div>
      </div>
      <KeyValue items={[
        ['Location', [job.location, humanize(job.work_mode), humanize(job.employment_type)].filter((v) => v && v !== '—').join(' · ')],
        ['Minimum experience', `${job.minimum_experience_years} years`],
        ['Required skills', <Skills key="r" items={job.required_skills} />],
        ['Preferred skills', <Skills key="p" items={job.preferred_skills} />],
        ['Education', job.education_requirements],
        ['Department', job.department],
      ]} />
      <div className={`space-y-2 text-sm text-slate-700 ${long && !expanded ? 'max-h-40 overflow-hidden' : ''}`}>
        <p className="whitespace-pre-line">{job.description}</p>
        {job.responsibilities && <p className="whitespace-pre-line text-slate-600">{job.responsibilities}</p>}
      </div>
      {long && (
        <button type="button" className="text-xs text-indigo-700 hover:underline" onClick={() => setExpanded((v) => !v)}>
          {expanded ? 'Show less' : 'Show the full description'}
        </button>
      )}
    </section>
  )
}
