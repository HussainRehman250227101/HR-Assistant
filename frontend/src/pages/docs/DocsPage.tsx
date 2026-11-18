import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

/**
 * Public documentation (no sign-in): what the HR Assistant does and how it is built.
 * Content only; nothing here calls the API or shows configuration values.
 */

const SECTIONS = [
  { id: 'overview', label: 'Overview' },
  { id: 'architecture', label: 'System architecture' },
  { id: 'workflow', label: 'Hiring workflow' },
  { id: 'agents', label: 'The three AI agents' },
  { id: 'human-gates', label: 'Human-in-the-loop controls' },
  { id: 'statuses', label: 'Candidate lifecycle' },
  { id: 'roles', label: 'Roles & access' },
  { id: 'data-model', label: 'Data model' },
  { id: 'security', label: 'Security & privacy' },
  { id: 'reliability', label: 'Reliability' },
  { id: 'tech-stack', label: 'Technology stack' },
  { id: 'deployment', label: 'Deployment' },
] as const

function Icon({ d, className = 'h-5 w-5' }: { d: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden className={className}>
      <path d={d} />
    </svg>
  )
}

const ICON = {
  doc: 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M9 13h6M9 17h4',
  mic: 'M12 3a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5 11a7 7 0 0 0 14 0M12 18v3',
  calendar: 'M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2zM3 10h18M8 3v4M16 3v4',
  shield: 'M12 3l8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6zM9 12l2 2 4-4',
  arrow: 'M5 12h14M13 6l6 6-6 6',
  down: 'M12 5v14M6 13l6 6 6-6',
  check: 'M5 12l5 5L20 7',
  user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21c.8-4 4-6 8-6s7.2 2 8 6',
  lock: 'M6 11h12v10H6zM8 11V7a4 4 0 0 1 8 0v4',
  refresh: 'M20 11a8 8 0 0 0-14.9-4M4 4v4h4M4 13a8 8 0 0 0 14.9 4M20 20v-4h-4',
  book: 'M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2zM4 19V5M8 7h7',
}

function Section({ id, eyebrow, title, intro, children }: { id: string; eyebrow: string; title: string; intro?: ReactNode; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-24 border-t border-slate-200 py-12 first:border-t-0 first:pt-0">
      <p className="text-xs font-semibold tracking-widest text-indigo-600 uppercase">{eyebrow}</p>
      <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl">{title}</h2>
      {intro && <p className="mt-3 max-w-3xl text-[15px] leading-7 text-slate-600">{intro}</p>}
      <div className="mt-8">{children}</div>
    </section>
  )
}

function Box({ title, sub, tone = 'slate', children }: { title: string; sub?: string; tone?: 'slate' | 'indigo' | 'emerald' | 'amber' | 'sky'; children?: ReactNode }) {
  const tones = {
    slate: 'border-slate-200 bg-white',
    indigo: 'border-indigo-200 bg-indigo-50/70',
    emerald: 'border-emerald-200 bg-emerald-50/70',
    amber: 'border-amber-200 bg-amber-50/70',
    sky: 'border-sky-200 bg-sky-50/70',
  }
  return (
    <div className={`rounded-xl border p-3.5 ${tones[tone]}`}>
      <div className="text-sm font-semibold text-slate-900">{title}</div>
      {sub && <div className="mt-0.5 text-xs leading-5 text-slate-500">{sub}</div>}
      {children}
    </div>
  )
}

function Layer({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50/60 p-4">
      <div className="mb-3 text-[11px] font-semibold tracking-widest text-slate-500 uppercase">{label}</div>
      {children}
    </div>
  )
}

function Connector({ label }: { label: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-2 text-xs text-slate-500">
      <Icon d={ICON.down} className="h-4 w-4 text-indigo-400" />
      {label}
    </div>
  )
}

function ArchitectureDiagram() {
  return (
    <figure className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
      <div className="grid gap-6 lg:grid-cols-[1fr_260px]">
        <div>
          <Layer label="People">
            <div className="grid gap-3 sm:grid-cols-2">
              <Box title="HR team" sub="HR Administrators, Hiring Managers and Recruiters (interviewers) sign in to the web app." />
              <Box title="Candidates" sub="Receive emails and join the voice screening from a secure link; they never get an account." />
            </div>
          </Layer>
          <Connector label="HTTPS · same origin" />
          <Layer label="Presentation">
            <Box tone="sky" title="React single-page app" sub="TypeScript, Tailwind CSS, TanStack Query. Talks to the API with short-lived JWTs that refresh automatically." />
          </Layer>
          <Connector label="REST / JSON" />
          <Layer label="Application · Django REST Framework">
            <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-4">
              <Box tone="indigo" title="Requisitions" sub="Jobs, rubrics, questions" />
              <Box tone="indigo" title="Candidates" sub="Intake, extraction, events" />
              <Box tone="indigo" title="Scoring" sub="Agent 1" />
              <Box tone="indigo" title="Reviews" sub="Shortlist decisions" />
              <Box tone="indigo" title="Screening" sub="Agent 2" />
              <Box tone="indigo" title="Scheduling" sub="Agent 3, availability" />
              <Box tone="indigo" title="Communications" sub="Emails + calendar invites" />
              <Box tone="indigo" title="Dashboard & audit" sub="Pipeline, history, logs" />
            </div>
            <p className="mt-3 text-xs leading-5 text-slate-500">Authentication, role-based permissions and per-user data scoping are enforced here, on every request.</p>
          </Layer>
          <Connector label="Services · background jobs" />
          <Layer label="Orchestration">
            <div className="grid gap-3 sm:grid-cols-2">
              <Box tone="emerald" title="LangGraph workflow" sub="Score resume → pause for HR review → finalise. State is checkpointed, so a paused run survives restarts." />
              <Box tone="emerald" title="Celery worker + scheduler" sub="Extracts and scores new resumes, schedules approved candidates and sends declined-candidate emails on a timer." />
            </div>
          </Layer>
          <Connector label="Persistence" />
          <Layer label="Data">
            <div className="grid gap-3 sm:grid-cols-3">
              <Box title="Relational database" sub="Records, decisions and audit trail" />
              <Box title="Workflow checkpoints" sub="LangGraph run state" />
              <Box title="Private file store" sub="Resumes, never publicly served" />
            </div>
          </Layer>
        </div>

        <div className="flex flex-col">
          <div className="mb-3 flex items-center gap-2 text-[11px] font-semibold tracking-widest text-slate-500 uppercase">
            <Icon d={ICON.arrow} className="h-4 w-4 rotate-180 text-indigo-400" /> External services
          </div>
          <div className="flex flex-1 flex-col gap-3 rounded-2xl border border-dashed border-slate-300 p-4">
            <Box tone="amber" title="Azure OpenAI" sub="GPT-5 mini with structured (schema-validated) outputs for scoring, transcript analysis and availability reading." />
            <Box tone="amber" title="ElevenLabs voice agent" sub="Real-time voice screening in the browser over WebRTC. Phone calls via Twilio are optional." />
            <Box tone="amber" title="Email (SMTP)" sub="Invitations, reschedules, cancellations and rejection emails with iCalendar attachments." />
            <Box tone="amber" title="Calendar apps" sub="Each user can subscribe to a private iCalendar feed of their interviews." />
          </div>
          <p className="mt-3 text-xs leading-5 text-slate-500">API keys stay on the server. The browser only ever receives a short-lived voice session token.</p>
        </div>
      </div>
      <figcaption className="mt-5 border-t border-slate-100 pt-4 text-xs text-slate-500">
        Figure 1. Logical architecture. The web app, API and background workers run as one deployable service.
      </figcaption>
    </figure>
  )
}

const FLOW: { title: string; text: string; gate?: string }[] = [
  { title: 'Open a requisition', text: 'HR defines the job, required and preferred skills, experience, location, screening and interview questions.' },
  { title: 'Upload resumes', text: 'PDF or DOCX files are validated, stored privately and their text extracted. Contact details are read from the resume.' },
  { title: 'AI scoring', text: 'Agent 1 scores each resume against the rubric with verified evidence and lists what is missing.' },
  { title: 'Shortlist review', text: 'A recruiter approves, holds or declines. Scores can be overridden with a reason.', gate: 'Gate 1' },
  { title: 'Voice screening', text: 'Agent 2 runs a consent-aware structured call and writes a factual summary.' },
  { title: 'Screening review', text: 'HR reads the answers beside the job description and decides who moves on.', gate: 'Gate 2' },
  { title: 'Interview scheduling', text: 'Agent 3 finds a slot both sides can make and sends the invitation, approved by the Gate 2 decision.', gate: 'Gate 3' },
  { title: 'Interview & feedback', text: 'The interviewer rates each interview question; the hiring decision stays with people.' },
]

function WorkflowDiagram() {
  return (
    <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {FLOW.map((step, i) => (
        <li key={step.title} className={`relative rounded-2xl border p-4 ${step.gate ? 'border-amber-300 bg-amber-50/60' : 'border-slate-200 bg-white'}`}>
          <div className="flex items-center justify-between">
            <span className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold ${step.gate ? 'bg-amber-500 text-white' : 'bg-indigo-600 text-white'}`}>{i + 1}</span>
            {step.gate && (
              <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-800">
                <Icon d={ICON.shield} className="h-3.5 w-3.5" /> {step.gate} · human
              </span>
            )}
          </div>
          <h3 className="mt-3 text-sm font-semibold text-slate-900">{step.title}</h3>
          <p className="mt-1 text-[13px] leading-6 text-slate-600">{step.text}</p>
        </li>
      ))}
    </ol>
  )
}

function Bullets({ items }: { items: ReactNode[] }) {
  return (
    <ul className="space-y-2">
      {items.map((item, i) => (
        <li key={i} className="flex gap-2.5 text-[13.5px] leading-6 text-slate-600">
          <Icon d={ICON.check} className="mt-1 h-4 w-4 shrink-0 text-emerald-500" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  )
}

function AgentCard({ icon, number, name, purpose, inputs, steps, outputs, guardrails }: {
  icon: string; number: number; name: string; purpose: string; inputs: string[]; steps: string[]; outputs: string[]; guardrails: string[]
}) {
  return (
    <article className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
      <header className="flex items-start gap-4 border-b border-slate-100 bg-gradient-to-r from-indigo-50 to-white p-5 sm:p-6">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-md shadow-indigo-200">
          <Icon d={icon} />
        </div>
        <div>
          <p className="text-xs font-semibold tracking-widest text-indigo-600 uppercase">Agent {number}</p>
          <h3 className="text-lg font-semibold text-slate-900">{name}</h3>
          <p className="mt-1 text-sm leading-6 text-slate-600">{purpose}</p>
        </div>
      </header>
      <div className="grid gap-6 p-5 sm:p-6 md:grid-cols-2">
        <div>
          <h4 className="text-xs font-semibold tracking-wider text-slate-500 uppercase">Inputs</h4>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {inputs.map((x) => <span key={x} className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-700">{x}</span>)}
          </div>
          <h4 className="mt-5 text-xs font-semibold tracking-wider text-slate-500 uppercase">How it works</h4>
          <ol className="mt-2 space-y-2">
            {steps.map((s, i) => (
              <li key={s} className="flex gap-2.5 text-[13.5px] leading-6 text-slate-600">
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-[11px] font-semibold text-indigo-700">{i + 1}</span>
                <span>{s}</span>
              </li>
            ))}
          </ol>
        </div>
        <div>
          <h4 className="text-xs font-semibold tracking-wider text-slate-500 uppercase">Outputs</h4>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {outputs.map((x) => <span key={x} className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs text-emerald-800 ring-1 ring-emerald-200">{x}</span>)}
          </div>
          <h4 className="mt-5 text-xs font-semibold tracking-wider text-slate-500 uppercase">Guardrails</h4>
          <div className="mt-2"><Bullets items={guardrails} /></div>
        </div>
      </div>
    </article>
  )
}

const STATUSES: { name: string; text: string; tone: string }[] = [
  { name: 'Resume Received', text: 'File stored, waiting for extraction and scoring.', tone: 'bg-slate-400' },
  { name: 'Needs Manual Review', text: 'Unreadable, scanned or protected file; a person takes over.', tone: 'bg-rose-400' },
  { name: 'Scored, HR Review', text: 'AI score ready; waiting at Gate 1.', tone: 'bg-indigo-500' },
  { name: 'Approved for Screening', text: 'Recruiter approved; screening invitation sent.', tone: 'bg-indigo-500' },
  { name: 'Screening Scheduled / Pending', text: 'Voice session or call in progress.', tone: 'bg-sky-500' },
  { name: 'Screening Completed, HR Review', text: 'Summary ready; waiting at Gate 2.', tone: 'bg-sky-500' },
  { name: 'Approved for Interview', text: 'HR approved; scheduling begins.', tone: 'bg-emerald-500' },
  { name: 'Interview Proposed', text: 'A slot is held and awaiting confirmation.', tone: 'bg-emerald-500' },
  { name: 'Interview Scheduled', text: 'Confirmed and invitation sent.', tone: 'bg-emerald-600' },
  { name: 'Closed', text: 'Declined or withdrawn. Declined candidates are emailed, then their personal data is erased.', tone: 'bg-slate-600' },
]

const ENTITIES: { name: string; text: string }[] = [
  { name: 'Requisition', text: 'Job, skills, location, interview format, screening and interview questions.' },
  { name: 'Scoring rubric', text: 'Versioned, weighted criteria per requisition.' },
  { name: 'Candidate', text: 'Contact details, current status and pipeline position.' },
  { name: 'Resume document', text: 'Private file, extraction status and text.' },
  { name: 'Resume evaluation', text: 'Immutable score, evidence, gaps, confidence and model version.' },
  { name: 'Shortlist review', text: 'Append-only recruiter decision and optional score override.' },
  { name: 'Screening', text: 'Questions, consent, transcript analysis and answers.' },
  { name: 'Call attempt', text: 'One row per voice session or phone call, with its outcome.' },
  { name: 'Screening review', text: 'Append-only Gate 2 decision.' },
  { name: 'Availability slot', text: 'Interviewer free time, stored in UTC with its time zone.' },
  { name: 'Interview', text: 'Interviewer, time, format, confirmations and status.' },
  { name: 'Interview feedback', text: 'Per-question ratings and an overall rating.' },
  { name: 'Communication log', text: 'Every email: draft, approver, send result.' },
  { name: 'Candidate event / audit event', text: 'The full history of who did what, and when.' },
  { name: 'Workflow run', text: 'Each scoring run, its trigger and its outcome.' },
]

const STACK: { group: string; items: string[] }[] = [
  { group: 'Frontend', items: ['React 19', 'TypeScript', 'Vite', 'Tailwind CSS v4', 'TanStack Query', 'React Router'] },
  { group: 'Backend', items: ['Python', 'Django 6', 'Django REST Framework', 'Simple JWT'] },
  { group: 'AI & orchestration', items: ['Azure OpenAI (GPT-5 mini)', 'Pydantic structured outputs', 'LangGraph', 'ElevenLabs Agents'] },
  { group: 'Background work', items: ['Celery worker', 'Celery beat scheduler'] },
  { group: 'Documents', items: ['pypdf', 'python-docx'] },
  { group: 'Data & hosting', items: ['SQLite (PostgreSQL planned)', 'Docker', 'Railway', 'Gunicorn', 'WhiteNoise'] },
]

export function DocsPage() {
  return (
    <div className="min-h-screen bg-white text-slate-800">
      <header className="sticky top-0 z-20 border-b border-slate-200/80 bg-white/85 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <Link to="/docs" className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-400 to-indigo-600 text-xs font-bold text-white shadow-md shadow-indigo-200">HR</span>
            <span className="leading-tight">
              <span className="block text-sm font-semibold text-slate-900">HR Assistant</span>
              <span className="block text-[11px] text-slate-500">Documentation</span>
            </span>
          </Link>
          <Link to="/login" className="rounded-lg bg-indigo-600 px-3.5 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-500">
            Sign in
          </Link>
        </div>
      </header>

      <div className="relative overflow-hidden bg-gradient-to-b from-slate-900 to-slate-950 text-white">
        <div className="pointer-events-none absolute -top-32 left-1/2 h-96 w-[48rem] -translate-x-1/2 rounded-full bg-indigo-500/25 blur-3xl" aria-hidden />
        <div className="relative mx-auto max-w-7xl px-4 py-16 sm:px-6 sm:py-20">
          <span className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs font-medium text-indigo-200 ring-1 ring-white/15">
            <Icon d={ICON.book} className="h-3.5 w-3.5" /> Architecture & product guide
          </span>
          <h1 className="mt-5 max-w-3xl text-3xl font-semibold tracking-tight sm:text-5xl">
            AI-assisted hiring, with people making every decision.
          </h1>
          <p className="mt-5 max-w-2xl text-base leading-7 text-slate-300">
            HR Assistant is a human-supervised, multi-agent hiring workflow. Three AI agents score resumes, run screening
            calls and schedule interviews. People approve every step that moves a candidate forward.
          </p>
          <div className="mt-8 grid max-w-3xl gap-3 sm:grid-cols-3">
            {[
              ['3', 'AI agents'],
              ['3', 'human approval gates'],
              ['10', 'tracked candidate statuses'],
            ].map(([n, label]) => (
              <div key={label} className="rounded-2xl bg-white/5 p-4 ring-1 ring-white/10">
                <div className="text-2xl font-semibold">{n}</div>
                <div className="text-sm text-slate-400">{label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="mx-auto grid max-w-7xl gap-10 px-4 py-12 sm:px-6 lg:grid-cols-[220px_minmax(0,1fr)]">
        <nav aria-label="Documentation" className="hidden lg:block">
          <div className="sticky top-24">
            <p className="text-[11px] font-semibold tracking-widest text-slate-400 uppercase">On this page</p>
            <ul className="mt-3 space-y-1 border-l border-slate-200">
              {SECTIONS.map((s) => (
                <li key={s.id}>
                  <a href={`#${s.id}`} className="-ml-px block border-l border-transparent py-1 pl-4 text-sm text-slate-600 hover:border-indigo-500 hover:text-indigo-700">
                    {s.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </nav>

        <main className="min-w-0">
          <Section id="overview" eyebrow="Introduction" title="Overview"
            intro="The assistant is decision support, not an autonomous decision-maker. It reads, summarises, proposes and handles routine logistics; a person decides who moves forward. A score on its own never rejects or contacts anyone.">
            <div className="grid gap-4 md:grid-cols-3">
              {[
                { icon: ICON.doc, title: 'Evaluate fairly', text: 'Score resumes against job-related criteria only, and show the evidence and the gaps behind every number.' },
                { icon: ICON.mic, title: 'Screen consistently', text: 'Every candidate gets the same approved questions, with AI disclosure and consent before recording.' },
                { icon: ICON.calendar, title: 'Schedule without the back-and-forth', text: 'Match the candidate’s stated availability with interviewer calendars across time zones.' },
              ].map((c) => (
                <div key={c.title} className="rounded-2xl border border-slate-200 p-5">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600"><Icon d={c.icon} /></div>
                  <h3 className="mt-4 text-sm font-semibold text-slate-900">{c.title}</h3>
                  <p className="mt-1.5 text-[13.5px] leading-6 text-slate-600">{c.text}</p>
                </div>
              ))}
            </div>
          </Section>

          <Section id="architecture" eyebrow="Architecture" title="System architecture"
            intro="A layered web application: a React client, a Django REST API holding the business rules, an orchestration layer for AI workflows and background jobs, and private storage. AI providers are called only from the server.">
            <ArchitectureDiagram />
            <div className="mt-8 grid gap-4 md:grid-cols-3">
              <Box title="Thin views, service modules" sub="Each Django app keeps its business logic in services; API views only validate input and check permissions." />
              <Box title="AI behind one gateway" sub="Every model call goes through a single provider client that adds a prompt-injection guardrail and validates the response against a schema." />
              <Box title="Code decides, not the model" sub="Weighted scores, statuses and scheduling choices are computed in Python from the model’s structured, verified output." />
            </div>
          </Section>

          <Section id="workflow" eyebrow="Process" title="Hiring workflow"
            intro="From requisition to interview in eight steps. Amber steps are human approval gates; a candidate cannot pass them without a recorded decision.">
            <WorkflowDiagram />
          </Section>

          <Section id="agents" eyebrow="Agents" title="The three AI agents"
            intro="Each agent has a narrow job, works from untrusted input with guardrails, writes immutable result records and stops at a human gate.">
            <div className="space-y-6">
              <AgentCard icon={ICON.doc} number={1} name="Resume Scoring Agent"
                purpose="Scores each resume against the job description and the requisition’s weighted rubric, with evidence."
                inputs={['Extracted resume text', 'Job description', 'Versioned rubric']}
                steps={[
                  'Removes the name, email, phone, LinkedIn and location before any text leaves the server.',
                  'The model returns, per criterion, an evidence status, a score and quoted excerpts.',
                  'Every quoted excerpt is checked against the resume; anything that cannot be found is downgraded to “unclear”.',
                  'The weighted total is computed in code. Criteria with no evidence are left out rather than scored as zero.',
                  'The run pauses at the shortlist gate until a recruiter decides.',
                ]}
                outputs={['Overall score', 'Per-criterion scores', 'Verified evidence', 'Gaps & missing info', 'Confidence', 'Model & prompt version']}
                guardrails={[
                  'Runs automatically for new resumes, or on demand.',
                  'No assessable evidence means no score, and approval then needs a human override.',
                  'Scanned or protected files go to manual review instead of being guessed at.',
                ]}
              />
              <AgentCard icon={ICON.mic} number={2} name="Candidate Screening Call Agent"
                purpose="Holds a short, structured voice conversation with approved candidates and produces a factual summary."
                inputs={['HR-approved questions', 'Role title', 'Missing contact fields']}
                steps={[
                  'The candidate opens a secure link and talks to the voice agent in the browser; phone calls are an optional mode.',
                  'The agent says it is an AI calling on behalf of HR, explains the purpose and asks for consent to record.',
                  'It asks only the approved, job-related questions plus interview availability, at most three times each.',
                  'The transcript is fetched server-side and analysed; every candidate quote is verified against it.',
                  'HR reviews the summary next to the job description at Gate 2.',
                ]}
                outputs={['Consent record', 'Answers with quotes', 'Salary & notice period', 'Availability', 'Unresolved questions', 'Call outcome']}
                guardrails={[
                  'A refusal or a request to stop ends the session at once; a human-led route is always offered.',
                  'Off-topic questions are politely refused; protected or sensitive topics are never asked.',
                  'Unclear answers are marked unclear, never filled in. The agent never rejects anyone.',
                  'No inference of personality, emotion or protected traits from voice.',
                ]}
              />
              <AgentCard icon={ICON.calendar} number={3} name="Interview Scheduling & Invitation Agent"
                purpose="Finds a time that works for the candidate and an interviewer, books it and sends the invitation."
                inputs={['Candidate’s stated availability', 'Interviewer calendars', 'Interview format']}
                steps={[
                  'Reads the availability the candidate gave in screening; dates, times and zones are validated in code.',
                  'Picks an interviewer with an overlapping free slot, the hiring manager first, then the least booked.',
                  'Books the earliest genuinely free slot, preventing double booking.',
                  'Sends the invitation with a calendar attachment (on-site address or video call details) and notifies the interviewer.',
                  'Supports rescheduling, reassignment and cancellation.',
                ]}
                outputs={['Interview record', 'Invitation email + .ics', 'Interviewer notice', 'Send status']}
                guardrails={[
                  'Only acts after HR approves the screening (Gate 2).',
                  'Anything it cannot resolve goes back to HR; a failed send is never reported as sent.',
                  'Idempotent sending prevents duplicate invitations.',
                ]}
              />
            </div>
          </Section>

          <Section id="human-gates" eyebrow="Controls" title="Human-in-the-loop controls"
            intro="Three gates where only a person can move a candidate forward. Every decision is stored with who made it and when, and is never edited afterwards.">
            <div className="grid gap-4 md:grid-cols-3">
              {[
                { gate: 'Gate 1', title: 'Shortlist', text: 'Approve for screening, hold or decline. Declines and holds need a reason; overriding the AI score needs its own reason and never alters the original evaluation.' },
                { gate: 'Gate 2', title: 'Screening progression', text: 'Approve for interview, request a re-screen or decline, with the job description and budget shown beside the candidate’s answers.' },
                { gate: 'Gate 3', title: 'Interview invitation', text: 'The Gate 2 approval authorises the scheduling agent to send the invitation. A stricter mode requires a separate approval for every email.' },
              ].map((g) => (
                <div key={g.gate} className="rounded-2xl border border-amber-200 bg-gradient-to-b from-amber-50 to-white p-5">
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-800">
                    <Icon d={ICON.shield} className="h-3.5 w-3.5" /> {g.gate}
                  </span>
                  <h3 className="mt-3 text-sm font-semibold text-slate-900">{g.title}</h3>
                  <p className="mt-1.5 text-[13.5px] leading-6 text-slate-600">{g.text}</p>
                </div>
              ))}
            </div>
          </Section>

          <Section id="statuses" eyebrow="Lifecycle" title="Candidate lifecycle"
            intro="Every candidate is in exactly one status. Each change writes an event with the actor and timestamp, so the full history is always visible on the candidate and in the audit log.">
            <ol className="relative space-y-1 border-l-2 border-slate-200 pl-6">
              {STATUSES.map((s) => (
                <li key={s.name} className="relative py-2">
                  <span className={`absolute top-3.5 -left-[31px] h-3 w-3 rounded-full ring-4 ring-white ${s.tone}`} />
                  <div className="text-sm font-semibold text-slate-900">{s.name}</div>
                  <div className="text-[13.5px] text-slate-600">{s.text}</div>
                </li>
              ))}
            </ol>
          </Section>

          <Section id="roles" eyebrow="Access" title="Roles & access"
            intro="Permissions are enforced by the API on every request; the interface only mirrors them.">
            <div className="overflow-x-auto rounded-2xl border border-slate-200">
              <table className="w-full min-w-[560px] text-left text-sm">
                <thead className="bg-slate-50 text-xs tracking-wider text-slate-500 uppercase">
                  <tr><th className="px-4 py-3 font-semibold">Role</th><th className="px-4 py-3 font-semibold">Can see</th><th className="px-4 py-3 font-semibold">Can do</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  <tr><td className="px-4 py-3 font-medium text-slate-900">HR Administrator</td><td className="px-4 py-3 text-slate-600">Everything</td><td className="px-4 py-3 text-slate-600">All decisions, plus user management, personal-data erasure and AI diagnostics</td></tr>
                  <tr><td className="px-4 py-3 font-medium text-slate-900">Hiring Manager</td><td className="px-4 py-3 text-slate-600">All requisitions and candidates</td><td className="px-4 py-3 text-slate-600">All hiring decisions, adding recruiters, interviewing</td></tr>
                  <tr><td className="px-4 py-3 font-medium text-slate-900">HR Recruiter</td><td className="px-4 py-3 text-slate-600">Only candidates they interview</td><td className="px-4 py-3 text-slate-600">Manage their own availability and record interview feedback</td></tr>
                </tbody>
              </table>
            </div>
          </Section>

          <Section id="data-model" eyebrow="Data" title="Data model"
            intro="Records are identified publicly by random UUIDs. Evaluations, rubrics and decisions are versioned or append-only, so the history can be reconstructed at any time.">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {ENTITIES.map((e) => (
                <div key={e.name} className="rounded-xl border border-slate-200 p-4">
                  <div className="font-mono text-[13px] font-semibold text-indigo-700">{e.name}</div>
                  <div className="mt-1 text-[13px] leading-5 text-slate-600">{e.text}</div>
                </div>
              ))}
            </div>
          </Section>

          <Section id="security" eyebrow="Trust" title="Security & privacy">
            <div className="grid gap-6 md:grid-cols-2">
              <div className="rounded-2xl border border-slate-200 p-5">
                <div className="flex items-center gap-2 text-sm font-semibold text-slate-900"><Icon d={ICON.lock} className="h-4 w-4 text-indigo-600" /> Security</div>
                <div className="mt-3"><Bullets items={[
                  'HTTPS enforced, with secure cookies.',
                  'Short-lived access tokens with refresh-token rotation and revocation on sign-out.',
                  'Role-based access checked on the server for every record.',
                  'Uploads checked by type, file signature, size and archive limits; files are never publicly reachable.',
                  'Request throttling, including on sign-in and password reset.',
                  'Provider keys stay on the server and out of logs.',
                ]} /></div>
              </div>
              <div className="rounded-2xl border border-slate-200 p-5">
                <div className="flex items-center gap-2 text-sm font-semibold text-slate-900"><Icon d={ICON.shield} className="h-4 w-4 text-indigo-600" /> Privacy</div>
                <div className="mt-3"><Bullets items={[
                  'Personal identifiers are removed before resume text is sent for scoring.',
                  'Resumes, transcripts and emails are treated as untrusted input, guarding against prompt injection.',
                  'Resume text, contact details and transcripts are never written to logs.',
                  'Declined candidates receive a courteous email; their resume and personal data are then erased.',
                  'A retention policy erases closed candidates after a set period.',
                  'Every privacy action is recorded in the audit log.',
                ]} /></div>
              </div>
            </div>
          </Section>

          <Section id="reliability" eyebrow="Operations" title="Reliability"
            intro="Designed so a crash, restart or retry never loses a decision and never contacts a candidate twice.">
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              {[
                ['Durable workflows', 'Workflow state is checkpointed, so a run paused for review survives restarts and resumes from the stored decision.'],
                ['Idempotent actions', 'Calls and emails are claimed atomically before they run, so a retry can never repeat them.'],
                ['Safe retries', 'Extraction, scoring, analysis and email sending can each be retried from the interface.'],
                ['Needs attention', 'Failures surface on the dashboard with a clear error, never silently.'],
              ].map(([title, text]) => (
                <div key={title} className="rounded-2xl border border-slate-200 p-5">
                  <Icon d={ICON.refresh} className="h-5 w-5 text-indigo-600" />
                  <h3 className="mt-3 text-sm font-semibold text-slate-900">{title}</h3>
                  <p className="mt-1.5 text-[13.5px] leading-6 text-slate-600">{text}</p>
                </div>
              ))}
            </div>
          </Section>

          <Section id="tech-stack" eyebrow="Stack" title="Technology stack">
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {STACK.map((g) => (
                <div key={g.group} className="rounded-2xl border border-slate-200 p-5">
                  <h3 className="text-xs font-semibold tracking-wider text-slate-500 uppercase">{g.group}</h3>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {g.items.map((i) => <span key={i} className="rounded-lg bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700">{i}</span>)}
                  </div>
                </div>
              ))}
            </div>
          </Section>

          <Section id="deployment" eyebrow="Hosting" title="Deployment"
            intro="The application ships as a single Docker image: the React app is built and served by the same origin as the API, and the web server, background worker and scheduler run side by side, sharing a persistent volume for the database and private files.">
            <div className="flex flex-col items-stretch gap-3 md:flex-row md:items-center">
              {['Source repository', 'Docker build (frontend + backend)', 'Database migrations', 'Web server + worker + scheduler', 'HTTPS on a custom domain'].map((step, i, all) => (
                <div key={step} className="flex items-center gap-3 md:flex-1">
                  <div className="flex-1 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-center text-[13px] font-medium text-slate-700">{step}</div>
                  {i < all.length - 1 && <Icon d={ICON.arrow} className="hidden h-4 w-4 shrink-0 text-indigo-400 md:block" />}
                </div>
              ))}
            </div>
          </Section>

          <div className="mt-4 flex flex-col items-start justify-between gap-4 rounded-3xl bg-gradient-to-r from-indigo-600 to-indigo-500 p-6 text-white sm:flex-row sm:items-center sm:p-8">
            <div>
              <h2 className="text-lg font-semibold">Part of the HR team?</h2>
              <p className="mt-1 text-sm text-indigo-100">Sign in with the account your administrator created for you.</p>
            </div>
            <Link to="/login" className="rounded-lg bg-white px-4 py-2 text-sm font-semibold text-indigo-700 shadow-sm hover:bg-indigo-50">Go to sign in</Link>
          </div>
        </main>
      </div>

      <footer className="border-t border-slate-200 py-8 text-center text-xs text-slate-500">
        HR Assistant · Decision support for hiring teams. AI proposes, people decide.
      </footer>
    </div>
  )
}
