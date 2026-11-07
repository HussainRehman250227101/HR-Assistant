# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 1. Project overview (from the SRS)

**AI-Powered HR Hiring Automation System**: a human-supervised, multi-agent hiring workflow. The authoritative spec is **`docs/SRS.docx`** ("Project Brief / SRS", v1.0, October 2026). Three agents:

1. **Resume Scoring Agent**: scores resumes against a job description (JD) and rubric, with evidence. *(SRS §8, Agent 1)*
2. **Candidate Screening Call Agent**: runs a consent-aware structured screening call and writes a summary. *(SRS §8, Agent 2)*
3. **Interview Scheduling & Invitation Agent**: finds slots in the calendar and sends an invitation email once it is approved. *(SRS §8, Agent 3)*

Core principle (SRS §1, §13): this is **decision support, not an autonomous hiring decision-maker**. A human must approve at three gates: shortlist, screening progression, and interview invitation. A score alone must never trigger rejection or outreach.

Objectives (SRS §3):
- Evaluate resumes against job-related criteria.
- Rank candidates and show evidence and missing information.
- Run consent-aware screening calls and summarize them.
- Have a human approve who proceeds.
- Find mutually available interview slots.
- Send invitations only after approval.
- Keep status history, logs, and error handling throughout.

Out of scope unless separately approved (SRS §4.2):
- Final hire/reject decisions made without a human.
- Inferring personality, emotion, or protected traits from voice, accent, face, or similar signals.
- Background checks, payroll, onboarding, or contract generation.
- Contacting real candidates without consent and approved templates.
- Production use with real personal data before a security review.

## 2. Actual architecture and tech stack

The SRS §10 *suggests* Streamlit/FastAPI but explicitly allows justified alternatives. **The team chose the stack below; keep it unless a change is approved.**

| Layer | Implementation (verified in code) |
|---|---|
| Backend/API | Django 6.1 + Django REST Framework 3.18 (`backend/`), JWT via `djangorestframework_simplejwt` (refresh-token blacklist) |
| Orchestration | LangGraph 1.2 with `SqliteSaver` checkpointer (`langgraph-checkpoint-sqlite`), separate SQLite file |
| LLM | Azure OpenAI v1 endpoint through the `openai` SDK; `model` = Azure **deployment name** (GPT-5 mini); Pydantic structured outputs |
| Resume extraction | `pypdf`, `python-docx`, run locally. **No OCR** (scanned PDFs are flagged for manual review) |
| Database | SQLite (`backend/db.sqlite3`); PostgreSQL is planned |
| Frontend | React 19 + TypeScript + Vite 8 + Tailwind CSS v4 (`@tailwindcss/vite`) + TanStack Query v5 + React Router (`frontend/`). The Vite dev server proxies `/api` to Django (same origin, no CORS). JWT is kept in `localStorage` with auto-refresh (`src/lib/api.ts`). |
| Config | `django-environ`, `backend/.env` (template: `backend/.env.example`); settings `config.django.local` (default) / `config.django.production` |
| Voice (Module 10) | ElevenLabs Conversational AI outbound calls over its **native Twilio integration** (`/v1/convai/twilio/outbound-call`); Twilio REST for call status; HMAC-signed post-call webhook. Plain `httpx`, no vendor SDKs (`screening/services/voice.py`). |

### Backend apps (`backend/`)

Each app is mounted under `/api/v1/<prefix>/` in `config/urls.py`. Business logic lives in service modules; views stay thin.

| App (URL prefix) | Responsibility | Key files |
|---|---|---|
| `config` | settings (`django/base.py`, `local.py`, `production.py`), env, root URLs | `config/django/base.py` |
| `accounts` (`auth/`) | custom `accounts.User` (`AUTH_USER_MODEL`) with `role`; JWT token/refresh/logout/me | `models.py`, `permissions.py` |
| `requisitions` (`requisitions/`) | job requisitions + lifecycle DRAFT→OPEN/CLOSED, OPEN⇄ON_HOLD, any→CLOSED (CLOSED is terminal; only DRAFT deletable) | `views.py` (transition map), `serializers.py` |
| `candidates` (`candidates/`) | candidates, private resume storage, extraction pipeline, `CandidateEvent` audit log | `services/extraction.py`, `services/processing.py`, `validators.py`, `management/commands/process_pending_resumes.py` |
| `llm` (`ai/`) | shared Azure client, prompt guardrail, admin-only status/test endpoints | `services.py`, `prompts.py`, `exceptions.py` |
| `scoring` (`scoring/`) | versioned per-requisition rubrics, Agent 1 implementation, immutable evaluations | `services/agent.py`, `services/rubrics.py`, `schemas.py` |
| `reviews` (`reviews/`) | shortlist queue + append-only recruiter decisions / score overrides | `views.py` |
| `workflows` (`workflows/`) | LangGraph graph + `WorkflowRun` records; pause/resume at HR gate | `graph.py`, `services.py` |
| `screening` (`screening/`) | Agent 2: `Screening` (SRS Screening entity) + append-only `ScreeningCallAttempt`; AI-voice or human-led channel; safeguarded calls, sync/webhook, transcript analysis | `services/calls.py` (state machine + safeguards), `services/voice.py`, `services/analysis.py`, `services/phone.py`, `script.py` (approved agent prompt), `management/commands/sync_screening_calls.py` |

| `scheduling` (`scheduling/`) | Agent 3 part 1: `AvailabilitySlot` (internal calendar, UTC + entry tz) and `Interview` (SRS Interview entity; one active per candidate); slot engine; confirm both parties | `services/slots.py`, `services/interviews.py` |

| `communications` (`communications/`) | SRS `CommunicationLog`: invitation, reschedule and cancellation emails; draft → HR approve → idempotent send through `EMAIL_BACKEND` with ICS; failures keep the draft | `services.py`, `templates_text.py` |

Shared helper: `candidates/services/status.py` → `change_candidate_status()` / `record_event()`; use it for every new status change.

### Frontend (`frontend/src/`)

`lib/api.ts` (fetch + JWT refresh + DRF error flattening), `lib/types.ts` (API types — keep in sync with serializers), `api/hooks.ts` (all TanStack Query hooks; mutations invalidate whole domains via `keys`), `components/ui.tsx` (Tailwind primitives), `pages/*` (one folder per domain). Candidate detail is tabbed (`?tab=`). Role gating mirrors the backend (`useAuth().isRecruiter/isAdmin`) but the backend remains the authority.

Other paths: `docs/SRS.docx` (spec), `README.md` (per-module API documentation, the de-facto API reference), `backend/media/resumes/` (private uploads, git-ignored), `backend/langgraph-checkpoints.sqlite3` (git-ignored runtime state).

### End-to-end flow implemented so far (SRS §6 steps 1–4)

1. **Requisition** must be `OPEN` before candidates or resumes are attached.
2. **Intake**:
   - Uploads are validated (suffix, file signature, size, DOCX zip integrity/decompression limits) and stored privately under opaque paths as `PENDING` `ResumeDocument`s.
   - Batch upload creates placeholder candidates with `identity_review_required=True`. Names and emails are never fabricated.
3. **Extraction** is asynchronous. It runs from the `process_pending_resumes` command or the per-document `process`/`retry` endpoints. The atomic claim on `PENDING` makes processing idempotent. Content errors (password-protected, scanned, or corrupt files) go to `NEEDS_MANUAL_REVIEW`. Unexpected errors go to `FAILED`, which can be retried.
4. **Scoring** (`scoring/services/agent.py`):
   - Redacts name, email, and phone before sending text to the LLM.
   - The LLM returns per-criterion `evidence_status`, score, and excerpts.
   - **Every excerpt is verified to appear in the resume.** Unverifiable evidence is downgraded to `UNCLEAR`.
   - The weighted score is **computed in Python**. `NOT_FOUND`/`UNCLEAR` criteria are excluded from the denominator. No assessable evidence → `overall_score=None`.
   - Confidence comes from the assessed weight (≥80 HIGH, ≥50 MEDIUM).
   - Each evaluation stores `provider`, `model_version`, `prompt_version` and `input_sha256`.
5. **Recruiter review** (`reviews`):
   - Decisions are `APPROVE_FOR_SCREENING`, `DECLINE` (→ `CLOSED`) or `HOLD_FOR_REVIEW`, and must reference the latest evaluation. A reason is mandatory.
   - A score override needs its own reason and never modifies the AI evaluation.
   - Approving a `None` score requires a human override. Approving a placeholder candidate requires identity verification.
6. **Workflow** (`workflows`):
   - Graph: `score_resume → wait_for_hr_review (interrupt()) → finalize_review`.
   - The review view resumes the paused run with `Command(resume=...)`.
   - If resuming fails, the decision is still durable and `POST /api/v1/workflows/<uuid>/resume/` retries.

## 3. Requirements traceability (SRS §7 FR-01…FR-15)

Status as verified on 2026-11-07 (Module 10 branch). **Update this table when a module changes requirement coverage.**

| ID | Requirement (abridged) | Status | Where |
|---|---|---|---|
| FR-01 | Requisition with title, JD, required/preferred skills, min experience, location/work arrangement, screening questions | Done | `requisitions/models.py`; rubric in `scoring/models.ScoringRubric` |
| FR-02 | PDF/DOCX intake, type/size validation, extraction, report unparseable files | Done (no OCR) | `candidates/validators.py`, `services/extraction.py` |
| FR-03 | Total + criterion scores, evidence, gaps, confidence/quality warnings | Done | `scoring/services/agent.py` |
| FR-04 | HR review / override / shortlist / decline with reason | Done | `reviews/views.py`, `reviews/models.py` |
| FR-05 | Contact only recruiter-approved candidates via approved template/channel | Done (M10) | `screening/services/calls.py` (`APPROVED_FOR_SCREENING` only, versioned `script.py`, +92 only) |
| FR-06 | Screening call: structured questions, no-answer/retry/escalation, AI/recording disclosure | Done (M10; live call unverified) | `calls.py` attempt limits/interval/window, opt-out, human-led route; disclosure + consent in `script.py` |
| FR-07 | Factual screening summary; candidate statements vs. agent interpretation | Done (M10) | `screening/services/analysis.py` (quotes verified against transcript) |
| FR-08 | HR reviews screening and explicitly approves next stage | Done (M11) | `screening/services/review.py`, append-only `ScreeningReview`; UI `ScreeningReviewForm` |
| FR-09 | Candidate + interviewer availability, time zones, duration | Done (M12) | `scheduling/services/slots.py` (internal availability calendar, clearly labelled; no Google/MS integration), `services/interviews.py` |
| FR-10 | Invitation draft with all required fields | Done (M13) | `communications/templates_text.py` (versioned template + ICS), required-field guard on send |
| FR-11 | Human confirmation before sending invitation | Done (M13) | `communications/services.approve_and_send` (explicit `confirm`, approver recorded, idempotent send) |
| FR-12 | Status + event history from resume received → interview scheduled | Partial | All 10 SRS §9 statuses exist in `CandidateStatus`; transitions implemented only up to `APPROVED_FOR_SCREENING`/`CLOSED`; history in `CandidateEvent` |
| FR-13 | Actionable errors; safe retries without duplicate outreach | Partial | Extraction retry, workflow resume retry, one active `WorkflowRun` per candidate; call/calendar/email N/A yet |
| FR-14 | Who approved, timestamps, model/provider versions, changes | Partial | `ShortlistReview.decided_by`, evaluation version fields, rubric `updated_by`; no generic audit for config changes |
| FR-15 | Restrict candidate data/config to authorized users | Done for implemented resources | `accounts/permissions.py`, `candidates_visible_to()` |

SRS §11 data model → code: Requisition → `requisitions.Requisition` (+`scoring.ScoringRubric`); Candidate → `candidates.Candidate` (+`ResumeDocument`); ResumeEvaluation → `scoring.ResumeEvaluation`; AuditEvent → `candidates.CandidateEvent` (candidate-scoped only) + `reviews.ShortlistReview`. Screening → `screening.Screening` (+`ScreeningCallAttempt`, the call log). Interview → `scheduling.Interview` (+`AvailabilitySlot`); CommunicationLog → `communications.CommunicationLog`.

Acceptance criteria (SRS §15): AC-01–AC-04 are covered by the implemented modules. AC-05–AC-08 and AC-11 depend on the screening and scheduling agents. AC-09 needs a dashboard (no frontend yet). AC-10 is partially covered. AC-12 (README) is maintained per module.

### Implementation constraints from the SRS (apply to all new work)

- **Human gates are mandatory** (SRS §13): shortlist, screening progression, and invitation sending. Agents may draft and propose but never progress, reject, contact, or send on their own.
- **Agent 2** (§8):
  - Disclose AI use and the call's purpose.
  - Ask for consent before recording; offer a human or non-recorded alternative if the candidate declines.
  - Ask only job-related questions, never protected or sensitive ones.
  - Handle voicemail, no-answer, poor audio, stop requests, and requests for a human.
  - Never fabricate answers; mark unclear ones.
  - Never reject a candidate.
  - Minimum output fields are listed in SRS §8.
- **Agent 3** (§8):
  - Offer only genuinely available slots, from a real or *clearly labelled mock* calendar.
  - Respect time zones.
  - HR must confirm before sending.
  - Prevent duplicate invitations.
  - Support rescheduling and cancellation.
  - If something fails, never claim the invitation was sent.
  - Minimum output fields are listed in SRS §8.
- **Reliability** (§12, §14): workflow state persists across restarts. Use idempotency checks so a retry never repeats a call or email.
- **Privacy/security** (§12–13):
  - Never log resume text, contact details, transcripts, or keys.
  - Treat resumes, emails, and transcripts as untrusted input (prompt injection).
  - Use only synthetic or consented data.
  - Define retention and deletion (not yet implemented).
- **Mocks are allowed** for calling, calendar, and email, but must be clearly labelled as simulated (SRS §4.1, §10, §17).

## 4. Coding conventions and architectural rules (follow the existing code)

- **Public IDs are UUIDs.** Requisitions use `reference_code`; everything else uses `public_id`. Never expose integer PKs in URLs or responses. Look objects up by UUID.
- **RBAC.** Roles are `ADMIN`, `RECRUITER`, and `HIRING_MANAGER` (`accounts.models.UserRole`); superuser counts as admin.
  - Use the permission classes in `accounts/permissions.py`.
  - Hiring managers see only requisitions where `hiring_manager == user`. Scope querysets with helpers such as `candidates_visible_to()`, or check explicitly as `scoring/views.py` does.
  - DRF defaults are JWT auth, `IsAuthenticated`, and anon/user throttles.
- **Candidate `current_status` is read-only through the intake API.** Only domain services and views (scoring, reviews, future agents) change it, and **every change writes a `CandidateEvent`**: `STATUS_CHANGED` plus a domain event. Add new `EventType` values for new actions.
- **Audit records are append-only.** Evaluations are versioned per resume, rubrics are versioned (the old one is deactivated and a new one created), and shortlist reviews are never edited.
- **All LLM calls go through `llm.services.get_llm_provider()`** (`generate_text` / `generate_structured`) and `llm.prompts.build_messages()`, which appends the untrusted-content guardrail.
  - Validate output with Pydantic schemas.
  - Compute scores and decisions in code, not in the model.
  - Logs record only deployment name and exception type.
- **Errors.** Map `LLMConfigurationError`/`LLMProviderError` to generic API errors, and keep the user-facing `error_code`/`error_message` on models. Never surface exception text containing PII.
- **LangGraph.**
  - Build graphs with an injectable checkpointer and dependencies (see the `scorer=` parameter).
  - State must contain only serializable primitives (`LANGGRAPH_STRICT_MSGPACK` is forced on).
  - **Every key a node returns must be declared in the state `TypedDict`**, or LangGraph silently drops it.
  - Pause human gates with `interrupt()` and resume only from a persisted Django decision record.
- **State changes that span models** use `transaction.atomic()`. Claims and retries use conditional `filter(...).update(...)` for idempotency.
- **Settings.** New config goes in `config/django/base.py` via `env(...)` and in `backend/.env.example` (placeholder values only). Secrets never go in source.
- **Upload limits** come from settings (`RESUME_MAX_*`). Files stay private and are served only through authenticated views with `no-store` headers.
- **Migrations** are committed with each module. Don't delete a database that holds real data. `--fake-initial` was used historically for the accounts migration.

## 5. Commands

Backend (Windows PowerShell, from `backend/`). The existing virtualenv is **`backend/myenv`** (Python 3.14.7). The README's instructions create `.venv` with Python 3.12, so use whichever exists.

```powershell
.\myenv\Scripts\Activate.ps1            # or: py -3.12 -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env             # first time only; set SECRET_KEY (required)

python manage.py migrate
python manage.py runserver              # API at http://127.0.0.1:8000/api/v1/
python manage.py check
python manage.py makemigrations --check --dry-run

python manage.py test accounts requisitions candidates llm scoring reviews workflows screening   # full suite (Django runner, no pytest)
python manage.py test scoring                                                          # one app
python manage.py test scoring.tests.ScoringCalculationTests.test_missing_evidence_is_excluded_from_weighted_denominator

python manage.py process_pending_resumes --limit 20    # resume extraction worker
python manage.py sync_screening_calls --limit 20       # poll in-progress screening calls (webhook fallback)
```

Screening tests use `FakeVoiceClient` / `FakeLLM` (`screening/tests.py`) and must `override_settings` empty ElevenLabs keys whenever a code path could reach the real client, because a developer `.env` may hold live keys.

Tests never call Azure. Patch `scoring.services.agent.get_llm_provider` or `llm.services.OpenAI`, use `override_settings` (a temporary `MEDIA_ROOT` for uploads), and give LangGraph tests a temporary `SqliteSaver` path. `POST /api/v1/ai/test/` makes a **live, billed** Azure call, so only use it deliberately.

Frontend (from `frontend/`): `npm install`, `npm run dev` (port 5173, proxies `/api` → `127.0.0.1:8000`; override with `VITE_API_PROXY_TARGET`), `npm run build` (runs `tsc -b`, i.e. the type check), `npm run lint` (includes the strict `react-hooks` rules: no `setState` inside effects; seed forms through `useState` initializers or keyed components). There's no frontend test runner yet.

## 6. Known issues (verified 2026-11-07)

- **Encoding pitfall (Windows PowerShell 5.1):** `Get-Content` reads BOM-less UTF-8 as ANSI, so a `Get-Content | Set-Content` round trip garbles non-ASCII text (§, →, —). Edit files with the editor tools or Python instead. This happened once to this file and was repaired.
- The README says Python 3.12, but the existing `myenv` is Python 3.14.7.
- There's no OCR, no retention/deletion policy, and no generic audit for configuration changes (all SRS items).
- **Live Twilio/ElevenLabs calls have not been verified** (no credentials in this environment). The ElevenLabs request/response shapes in `voice.py` follow the public API docs; confirm them on the first live call. The webhook needs a public URL (tunnel); otherwise run `sync_screening_calls`.
- Screening is orchestrated by a persisted Django state machine (`Screening.status` + atomic claims), not LangGraph. Only resume scoring runs in a LangGraph graph.
- Fixed in M10: the LangGraph test `KeyError: 'decision'` (the state keys are now declared in `RecruitmentWorkflowState`).

## 7. Rules for consulting the SRS before implementing features

1. **Read the relevant SRS sections before designing any feature.** The SRS is a .docx and can't be read directly. Extract its text to a scratch location, never into the repo:
   - Unzip `word/document.xml`, or
   - run `python -c "import docx; d=docx.Document(r'..\docs\SRS.docx'); print('\n'.join(p.text for p in d.paragraphs))"` from `backend/` with the venv active. Tables need iterating over `d.tables` as well.
2. Map the work to **FR-xx / AC-xx IDs** and the SRS § numbers (§6 workflow, §8 agent output fields, §9 statuses, §11 data model, §13 controls, §14 edge cases). Reference those IDs in commit messages or PR descriptions.
3. Implement the SRS **minimum output fields** for each agent. Reuse the existing `CandidateStatus` values; don't invent parallel status sets.
4. If the SRS, README, and code disagree, **ask the user**. Don't silently pick one. Don't add features the SRS lists as out of scope (§4.2) or future work.
5. The SRS's suggested stack (Streamlit, FastAPI) is **not** a mandate. The approved stack is Django/DRF + React + LangGraph + Azure OpenAI.

## 8. Continuity across sessions

- At the start of a session, read this file. Then check `git status`, `git log --oneline -15`, and `git branch -a` to find the current module and branch, and the newest `README.md` module section for API details.
- **Delivery model:** about 15 numbered modules (the README says 15; only Modules 01–10 are defined in the repo).
  - 01 foundation, 02 auth/RBAC, 03 requisitions, 04 candidate intake, 05 resume processing, 06 LLM infrastructure, 07 scoring, 08 recruiter review, 09 LangGraph workflow: all **done and merged**.
  - 10 screening call agent (Twilio + ElevenLabs) + React frontend foundation: done on `feature/module-10-screening-call-agent`.
  - 11 Screening Review: done on `feature/module-11-screening-review` (branched from the Module 10 branch).
  - 12 Scheduling & Calendar Agent: done on `feature/module-12-scheduling-calendar`.
  - 13 Email Invitation Agent: done on `feature/module-13-email-invitations`.
  - Remaining modules, as named by the user on 2026-11-07: 14 Dashboard & Candidate Lifecycle Tracking, 15 Production Hardening & QA.
  - Every module ships both backend and frontend UI (see "Development Workflow — Mandatory" below). Branches are not merged into `main` automatically.
- **Branch convention:** `feature/module-NN-<slug>` or `feature/modules-NN-NN-NN-<slug>` off `main`, merged with a merge commit.
- **Definition of done for a module:**
  - migrations committed;
  - `makemigrations --check` clean, `check` clean, full test suite passing;
  - a README section added (endpoints, access rules, env vars, verification commands);
  - the traceability table (§3) and known issues (§6) in this file updated.
- Keep this file the single persistent project-memory document. Update its status tables instead of creating status files.

## 9. Before modifying anything

- **Inspect the existing code first.** Read the relevant models, services, views, serializers, and tests, and search for existing helpers (visibility scoping, permissions, event logging, LLM provider, rubric handling) before writing new ones.
- Make **minimal, targeted changes**. Don't rewrite, reformat, or restructure working modules, rename apps or endpoints, or change established decisions (Django/DRF, UUID public IDs, append-only audit, Python-computed scores, LangGraph interrupt gates, Azure deployment-name model selection) without explicit user approval.
- Extend existing models and enums with migrations instead of replacing them. New agents should follow the `scoring` pattern: a service module, a Pydantic schema, immutable result records, and a human-review gate in a LangGraph graph.
- Run the full test suite before and after changes. Don't "fix" unrelated failing tests without saying so.

## Development Workflow — Mandatory

### Module Implementation
For every new module or feature:
1. Read the relevant SRS requirements before implementation.
2. Inspect the existing backend, frontend, API serializers, models, permissions, and tests.
3. Preserve all existing user changes and architectural decisions.
4. Implement the backend functionality, including models, migrations, serializers, services, API endpoints, permissions, and tests as applicable.
5. Implement the corresponding frontend UI in the existing `frontend/` application using:
   - React
   - TypeScript (`.tsx` for components)
   - Tailwind CSS
   - TanStack Query for API requests, caching, mutations, loading states, and invalidation
6. Integrate the UI with the actual Django REST Framework APIs. Do not use mock data as a substitute for working functionality.
7. Ensure the UI supports practical end-to-end testing without requiring users to manually construct API requests.
8. Run backend tests, Django checks, frontend type checks, and frontend production builds as applicable.
9. Fix implementation-related failures before declaring the module complete.
10. Update `CLAUDE.md` with verified architectural or development changes when necessary.

### Git and Change Preservation
- Never discard, overwrite, reset, or revert existing user changes without explicit permission.
- Inspect `git status` and the current diff before modifying files.
- Do not use destructive Git commands.
- Do not merge into `main` automatically.
- Use feature branches and create logical commits only when requested or authorized.

### Module Completion
A module is not complete merely because code has been written.
It must include backend functionality, corresponding frontend UI, integration with existing modules, tests, and verification of the relevant requirements.

Do not proceed to the next module if the current module has unresolved implementation failures unless explicitly instructed.
