# AI-Powered HR Hiring Assistant

A human-supervised hiring workflow with three specialized agents: resume scoring, candidate screening calls, and interview scheduling/invitations.

## Architecture and delivery

The project is developed in 15 independently tested modules. The backend is Django, the frontend React + TypeScript, orchestration LangGraph, and local development uses SQLite before the planned PostgreSQL migration. Azure GPT-5 mini is the configured LLM deployment. Pakistan (+92) is the current calling destination.

## Module 02 — Authentication & RBAC

Roles:
- **ADMIN**: HR Administrator (Django staff/superuser permissions remain separate).
- **RECRUITER**: HR Recruiter.
- **HIRING_MANAGER**: Hiring Manager.

JWT endpoints:
- `POST /api/v1/auth/token/` — obtain access and refresh tokens.
- `POST /api/v1/auth/token/refresh/` — refresh access token.
- `POST /api/v1/auth/logout/` — blacklist refresh token.
- `GET /api/v1/auth/me/` — authenticated user profile.

Role permissions are reusable classes in `accounts/permissions.py`. All API endpoints default to authenticated access. Django admin access is separately controlled by Django's staff/superuser flags.

## Backend setup (Windows PowerShell)

Use Python 3.12 and run from `backend`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set a locally generated `SECRET_KEY` in `.env`. Never commit secrets.

### Module 02 first migration (SQLite only)

This module introduces `AUTH_USER_MODEL=accounts.User`. Django custom user models must be present before the initial auth migrations. If you have only the disposable Module 01 SQLite database, remove it and rebuild:

```powershell
Remove-Item .\db.sqlite3 -ErrorAction SilentlyContinue
python manage.py makemigrations accounts
python manage.py migrate
python manage.py createsuperuser
python manage.py check
python manage.py test accounts
python manage.py runserver
```

Do not delete a database containing valuable data. For a database with data, plan a dedicated user-model migration instead of resetting it.

## API usage

Login:
```http
POST /api/v1/auth/token/
Content-Type: application/json

{"username":"your_username","password":"your_password"}
```

Authenticated profile:
```http
GET /api/v1/auth/me/
Authorization: Bearer <access_token>
```

Logout:
```http
POST /api/v1/auth/logout/
Authorization: Bearer <access_token>
Content-Type: application/json

{"refresh":"<refresh_token>"}
```

Use HTTPS in production, protect refresh tokens, rotate secrets, and never store tokens in source control. The frontend token-storage strategy will be designed in its dedicated frontend/auth integration work rather than assuming localStorage is secure.


## Module 03 — Requisition Management

The requisitions API manages job requests before candidate intake. It includes a UUID reference, role title, department, location, employment type, work mode, job description, responsibilities, required skills, minimum experience, education requirements, optional salary range/currency, headcount, hiring manager, target close date, status, and system timestamps.

Lifecycle statuses are **DRAFT**, **OPEN**, **ON_HOLD**, and **CLOSED**. A closed requisition cannot be reopened. Only draft requisitions can be deleted; active roles should be closed rather than deleted. The API records the opening/closing timestamp when the status changes.

Access:
- **HR Administrator / superuser:** read and manage all requisitions.
- **HR Recruiter:** read and manage all requisitions.
- **Hiring Manager:** read only requisitions assigned to that manager.
- Anonymous users: no access.

Endpoints under `/api/v1/requisitions/`:
- `GET /` — paginated list; optional `status`, `department`, and `search` filters.
- `POST /` — create a draft requisition (or explicitly create with another allowed status).
- `GET /<reference_code>/` — retrieve.
- `PUT/PATCH /<reference_code>/` — update, subject to role and lifecycle rules.
- `DELETE /<reference_code>/` — delete draft requisitions only.

### Module 03 database migration

The Module 02 `accounts/0001_initial.py` migration is included in the latest base commit. Generate and commit the requisitions migration on this feature branch:

```powershell
python manage.py makemigrations requisitions
python manage.py migrate --fake-initial
python manage.py makemigrations --check --dry-run
```

`--fake-initial` also supports a local Module 02 SQLite database whose accounts table was created before its initial migration was committed. Back up any important database before running migrations.

Run tests with:

```powershell
python manage.py check
python manage.py test accounts requisitions
```


## Modules 04–06 — Candidate Intake, Resume Processing and LLM Infrastructure

### Module 04 — Candidate & Resume Intake

Candidate records are linked to an **OPEN** requisition. Candidate identity/contact fields include full name, email, phone, location and LinkedIn URL. Contact and recording consent both start as **PENDING**; creating a record never assumes consent. Candidate status uses the lifecycle names in the project brief and is read-only through the intake API. Later workflow modules own human-approved progression.

Batch resume intake creates placeholder candidates with `identity_review_required=true`; it never fabricates names or email addresses from filenames. Their details are read from the resume itself after extraction (see [Candidate details from the resume](#candidate-details-from-the-resume-and-one-click-approvals)).

Access:
- HR Administrator and Recruiter: create, update and view candidate records.
- Hiring Manager: read only candidates linked to requisitions assigned to that manager.
- Resume file download: HR Administrator and Recruiter only.

### Module 05 — Resume Processing Pipeline

PDF and DOCX uploads are checked for file suffix, signature/container, non-zero size, DOCX archive integrity and decompression limits. Default limits are 10 MB per file, 20 files per batch and 50 MB aggregate per batch; settings are configurable in `.env`.

Uploaded files are stored privately under `MEDIA_ROOT/resumes/` using opaque server-generated paths. The API does not expose file paths or extracted resume text. Downloads use an authenticated endpoint with private/no-store response headers.

Text extraction is local using `pypdf` and `python-docx`; resume contents are not sent to Azure during intake or extraction. Password-protected, corrupted, scanned PDFs without selectable text and unreadable documents are flagged for **Needs Manual Review**. OCR is not included in this module.

Resume uploads are persisted as **PENDING** jobs. Process them in a separate worker process:

```powershell
python manage.py process_pending_resumes --limit 20
```

An authorized recruiter can also process one pending document with `POST /api/v1/candidates/resume-documents/<resume_uuid>/process/`. An unexpected processing failure can be retried using `POST /api/v1/candidates/resume-documents/<resume_uuid>/retry/`. Content-related errors such as scanned/password-protected documents need manual intervention or a new copy. The management command provides a database-backed worker loop for the prototype; a production deployment should run it under a process supervisor or move the queue to a managed job system and add malware scanning before accepting real applicant files.

### Candidate API

Base URL: `/api/v1/candidates/`

- `GET /` — paginated candidate list; optional `status`, `requisition` (requisition UUID) and `search`.
- `POST /` — create candidate against an open requisition.
- `GET /<candidate_uuid>/` — candidate profile and resume metadata.
- `PATCH /<candidate_uuid>/` — update candidate profile; lifecycle status is read-only.
- `POST /<candidate_uuid>/resumes/` — upload a PDF/DOCX (multipart field `file`).
- `POST /requisition/<requisition_uuid>/resume-batches/` — batch upload (multipart field `files`, repeat for each resume).
- `GET /<candidate_uuid>/events/` — event history.
- `GET /resume-documents/<resume_uuid>/` — processing state and sanitized extraction metadata.
- `GET /resume-documents/<resume_uuid>/download/` — HR-only private file download.
- `POST /resume-documents/<resume_uuid>/process/` — process one pending document.
- `POST /resume-documents/<resume_uuid>/retry/` — retry an unexpected processing failure.

### Module 06 — LLM Infrastructure

The reusable client uses the OpenAI Python SDK with the Azure OpenAI v1 API endpoint `https://<resource>.openai.azure.com/openai/v1/`. Its `model` parameter is the exact Azure deployment name supplied in `AZURE_OPENAI_CHAT_DEPLOYMENT`; it is not hard-coded to a model identifier.

The shared service provides:
- Plain-text chat generation.
- Pydantic-validated structured output.
- Configurable timeout, retries, reasoning effort and completion-token budget.
- Logging of provider/deployment and exception type only; no prompts, resume content, contact information or API keys.
- A reusable guardrail treating uploaded candidate documents as untrusted data.
- Admin-only configuration status and optional connectivity-check endpoints.

`GET /api/v1/ai/status/` reports deployment configuration without exposing secrets. `POST /api/v1/ai/test/` sends one small structured-output request and consumes model quota. Automated unit tests mock the SDK and do not call Azure.

This module creates shared LLM infrastructure only. Resume scoring remains Module 07 and must be explainable, evidence-based and a prioritization aid—not an autonomous hiring decision.

### Added environment variables

```dotenv
AZURE_OPENAI_ENDPOINT=https://YOUR-RESOURCE-NAME.openai.azure.com
AZURE_OPENAI_API_KEY=your-key-in-local-env-only
AZURE_OPENAI_CHAT_DEPLOYMENT=YOUR-GPT-5-MINI-DEPLOYMENT-NAME
AZURE_OPENAI_TIMEOUT_SECONDS=30
AZURE_OPENAI_MAX_RETRIES=2
AZURE_OPENAI_REASONING_EFFORT=low
AZURE_OPENAI_MAX_COMPLETION_TOKENS=2000
RESUME_MAX_FILE_SIZE_MB=10
RESUME_MAX_BATCH_FILES=20
RESUME_MAX_BATCH_TOTAL_MB=50
```

Never commit `.env` or real candidate resumes. Use synthetic or consented test data. Set an approved retention/deletion policy, HTTPS, encrypted storage and malware scanning before production use.


### Verifying Modules 04–06 locally

From `backend`, after installing `requirements.txt`, generate the candidate schema migration and apply it:

```powershell
python manage.py makemigrations candidates
python manage.py migrate
python manage.py makemigrations --check --dry-run
python manage.py check
python manage.py test accounts requisitions candidates llm
```

The Azure connectivity test is an explicit live request and is not called during automated tests. Use `GET /api/v1/ai/status/` to check configuration first, then `POST /api/v1/ai/test/` only when you intend to consume model quota.


### Using resume upload from the DRF Browsable API

The batch endpoint has a serializer-backed multipart form. Open it in the browser while authenticated as an HR Administrator or Recruiter:

`GET /api/v1/candidates/requisition/<OPEN_REQUISITION_UUID>/resume-batches/`

The browsable API displays a file picker named `files`. Select one PDF/DOCX resume and press **POST**. For the browsable form, submit one resume per request; repeat for each file. API clients can submit repeated multipart `files` parts in one request to use the batch limit.

To find a valid UUID, open `GET /api/v1/requisitions/` and copy the `reference_code` of a requisition whose status is exactly `OPEN`. Draft, on-hold, closed, or unknown requisition UUIDs are not eligible for candidate intake and return 404. The UUID in the browser address bar must be the requisition reference code, not a candidate ID or database integer ID.

The endpoint accepts multipart form data, not a pasted path or raw JSON. The candidate resume endpoint also renders a file picker at `POST /api/v1/candidates/<CANDIDATE_UUID>/resumes/`.


## Modules 07–09 — Resume Scoring, Recruiter Review and Workflow Orchestration

### Module 07 — Explainable Resume Scoring Agent

The scoring agent evaluates only job-related evidence against the requisition. The default SRS rubric is configurable per requisition and totals 100%:

| Criterion | Default weight |
|---|---:|
| Required skills | 40% |
| Relevant experience | 25% |
| Role-related projects | 20% |
| Education and certifications | 10% |
| Other explicitly job-related evidence | 5% |

The model returns a structured assessment for every criterion, including an evidence status, rationale, short resume excerpt, and missing/unclear items. The application computes the weighted score; the model does not calculate the final total.

**Missing-information handling:** criteria marked NOT_FOUND or UNCLEAR are excluded from the weighted denominator rather than treated as proof that the candidate lacks the skill. The result records the assessed weight and an evidence-coverage confidence level. When no criterion has assessable evidence, `overall_score` is `null` (not a fabricated zero) and the recommendation requires manual review.

The scoring prompt excludes candidate name/contact fields, treats resume content as untrusted, and prohibits protected-trait or personality inference. The score is a recruiter prioritization aid only—not an automatic rejection or hiring decision.

Rubric endpoints:
- `GET /api/v1/scoring/requisitions/<requisition_uuid>/rubric/`
- `PUT /api/v1/scoring/requisitions/<requisition_uuid>/rubric/`

Evaluation endpoints:
- `POST /api/v1/scoring/candidates/<candidate_uuid>/evaluate/`
- `GET /api/v1/scoring/candidates/<candidate_uuid>/evaluations/`
- `GET /api/v1/scoring/evaluations/<evaluation_uuid>/`

Evaluation history is immutable and versioned per resume. It records the selected rubric/version, criterion scores, evidence excerpts, missing information, warnings, assessed-weight coverage, confidence, deployment name, prompt version and input hash. Human score overrides are not written back to the AI evaluation.

### Module 08 — Recruiter Review & Shortlisting

The shortlist queue is available at `GET /api/v1/reviews/shortlist/`. A recruiter can explicitly:
- Approve a candidate for screening.
- Decline a candidate (a reason is mandatory).
- Hold a candidate for manual review.
- Record a manual score override, separately from the AI score, with a mandatory explanation.

Decision endpoint:
- `POST /api/v1/reviews/candidates/<candidate_uuid>/shortlist/`

Review history:
- `GET /api/v1/reviews/candidates/<candidate_uuid>/history/`

Only HR Administrator and Recruiter roles can make shortlist decisions. Hiring Managers can read evaluations for requisitions assigned to them but cannot approve, decline, or override a shortlist. Decisions are append-only audit records and each decision must reference the candidate's latest evaluation.

Batch-upload placeholder candidates cannot be approved until a recruiter confirms identity, enters a candidate name and at least one contact method, and records why identity/contact information was verified. The original AI score remains unchanged when a human override is stored.

### Module 09 — LangGraph Workflow Orchestration

The first LangGraph workflow coordinates:
1. Validate the candidate and completed resume.
2. Execute the resume scoring agent.
3. Persist the evaluation.
4. Pause at a checkpoint waiting for recruiter shortlist review.
5. Resume only after the Module 08 review decision is durably saved.
6. Complete the scoring/shortlist workflow stage.

The workflow uses LangGraph `interrupt()` and `Command(resume=...)` with a persistent SQLite checkpointer for local development. WorkflowRun records store candidate, resume, evaluation, thread ID, state summary, status, error code and timestamps. The SQLite checkpoint file is local runtime state and is excluded from Git.

Workflow endpoints:
- `POST /api/v1/workflows/candidates/<candidate_uuid>/start-scoring/`
- `GET /api/v1/workflows/<workflow_run_uuid>/`
- `POST /api/v1/workflows/<workflow_run_uuid>/resume/` — retries resumption after a saved HR decision if a transient error interrupted it.

The SQLite checkpointer is intended for local development and lightweight prototype execution. For multi-worker production deployment, move LangGraph checkpoint storage to PostgreSQL and use a managed worker/process supervisor. Candidate communication, calling, and scheduling are not performed by this workflow.

### Planned Module 10 voice-provider decision

The candidate screening module will use **Twilio for telephony/call control** and **ElevenLabs Conversational AI for the voice agent**. Provider credentials and call initiation will be implemented in Module 10, not in the scoring workflow. Calls must remain behind recruiter approval and candidate consent checks. The integration can use ElevenLabs' native Twilio-number integration, or its register-call approach when custom Twilio call control is required.

### Install and verify Modules 07–09

```powershell
pip install -r requirements.txt
python manage.py makemigrations candidates scoring reviews workflows
python manage.py migrate
python manage.py makemigrations --check --dry-run
python manage.py check
python manage.py test accounts requisitions candidates llm scoring reviews workflows
```

The scoring API requires a configured Azure GPT-5 mini deployment. The LangGraph workflow uses the local SQLite checkpoint file and does not call Twilio or ElevenLabs.


### Requisition context fields added for Modules 07–10

Requisitions now also accept optional `preferred_skills` and `screening_questions` lists (up to 50 preferred skills and 30 questions). The scoring agent receives preferred skills as contextual information without treating them as mandatory skills. Screening questions will be made available to the Module 10 screening workflow. These fields do not create automatic rejection rules.


### Testing Module 07–09 in the DRF Browsable API

Use ModHeader to attach your recruiter JWT to the local DRF pages.

1. Inspect the rubric: `GET /api/v1/scoring/requisitions/<requisition_uuid>/rubric/`.
2. Run scoring: `POST /api/v1/scoring/candidates/<candidate_uuid>/evaluate/`. The optional `resume_document` form field accepts a resume-document UUID; leave it blank to use the latest completed resume.
3. Start the full scoring workflow: `POST /api/v1/workflows/candidates/<candidate_uuid>/start-scoring/`. No request body is required. The response should be `WAITING_HR_REVIEW` after scoring and checkpoint creation.
4. Review the queue: `GET /api/v1/reviews/shortlist/`.
5. Record the decision: `POST /api/v1/reviews/candidates/<candidate_uuid>/shortlist/`. The `evaluation` field expects the evaluation's public UUID (not its integer database ID). Choose a decision and provide the required reason. A score override and its reason are optional; identity verification fields are required only for placeholder candidates.
6. Inspect workflow state: `GET /api/v1/workflows/<workflow_run_uuid>/`. After a saved recruiter decision, the workflow should be `COMPLETED`. A failed resume after an already-saved decision can be retried using `POST /api/v1/workflows/<workflow_run_uuid>/resume/`.

Do not merge the feature branch until local migrations and the full test suite pass.


## Frontend — React HR workspace

`frontend/` is a React 19 + TypeScript + Vite app styled with Tailwind CSS v4, using TanStack Query for API state and React Router for navigation. It replaces the DRF Browsable API for day-to-day recruiting work.

```powershell
# terminal 1 (backend/)
python manage.py runserver
# terminal 2 (frontend/)
npm install
npm run dev            # http://localhost:5173 ; /api is proxied to http://127.0.0.1:8000
npm run build          # type-check + production build
npm run lint
npm test               # Vitest + Testing Library (jsdom)
```

Sign in with a Django user (`python manage.py createsuperuser`, then set `role` in the admin). JWTs are kept in `localStorage` (prototype trade-off; move to httpOnly cookies before production). Set `VITE_API_PROXY_TARGET` to proxy to a different backend.

Screens: requisitions (create/edit/open/hold/close, rubric weights, batch resume upload), candidates (details, consent, resumes, extraction, scoring, shortlist decision, screening, activity history), shortlist queue, screening queue (including the Module 16 demo browser voice screening page) and integration status.

## Module 10 — Candidate Screening Call Agent (Twilio + ElevenLabs)

> **Optional since Module 16.** The default AI screening route is now the browser voice session (see [Module 16](#module-16--browser-voice-screening-elevenlabs-webrtc)). Everything in this section applies only with `SCREENING_VOICE_MODE=telephony`; in the default browser mode, no Twilio call is placed and no Twilio setting is needed.

ElevenLabs Conversational AI places outbound calls through its **native Twilio integration** (`POST /v1/convai/twilio/outbound-call`) using the Twilio number imported into ElevenLabs. Twilio's REST API is queried for the authoritative call status (no-answer, busy, failed). Post-call results arrive by an HMAC-signed ElevenLabs webhook, with polling as a fallback. Azure GPT-5 mini turns the transcript into the SRS §8 output fields. Every quoted candidate statement is verified against the transcript, and unverifiable quotes are downgraded to `UNCLEAR`.

Safeguards:
- Only candidates in `APPROVED_FOR_SCREENING` can be screened.
- The agent uses only the requisition's approved questions and the versioned script `screening-call-v1` (now `screening-call-v2`, which adds the standard salary, notice-period and availability questions; see "Screening: salary, notice period and interview availability" below).
- Destinations are limited to `SCREENING_ALLOWED_DIAL_PREFIXES` (default `+92`, validated as `+92` plus 10 digits).
- Calls are allowed only inside a calling window (09:00–19:00 Asia/Karachi by default).
- At most `SCREENING_MAX_CALL_ATTEMPTS` attempts are made, with a minimum `SCREENING_RETRY_INTERVAL_MINUTES` between them.
- An atomic claim ensures only one call can be in flight per screening, and each candidate has at most one active screening.
- Candidates who opted out or declined consent are blocked from automated calls.
- If consent is declined during a call, the transcript is discarded and the ElevenLabs conversation is deleted.
- If the candidate asks to stop, an automated-call opt-out is recorded.
- Every attempt is logged in `ScreeningCallAttempt` and as a candidate event.
- A human-led screening route exists for candidates who decline automated calls or need assistance.

The agent never rejects a candidate; results go to `SCREENING_COMPLETED_HR_REVIEW`.

Endpoints (`/api/v1/screening/`):

| Method | Path | Purpose |
|---|---|---|
| GET | `` | Active screening queue (`?status=`, `?requisition=`) |
| GET/POST | `candidates/<candidate_uuid>/` | List / create (`channel` = `AI_VOICE` or `HUMAN_LED`, `start_call_now`) |
| GET | `<screening_uuid>/` | Detail (transcripts hidden from hiring managers) |
| POST | `<screening_uuid>/call/` | Place the next safeguarded call attempt |
| POST | `<screening_uuid>/sync/` | Fetch provider status / conclude a finished call |
| POST | `<screening_uuid>/retry-analysis/` | Re-run transcript analysis without calling again |
| POST | `<screening_uuid>/manual-result/` | Record a human-led screening result |
| POST | `<screening_uuid>/cancel/` | Cancel a pending screening (`reason`) |
| GET | `agent-config/` | Integration status (booleans only) and, for admins, the agent prompt to paste into ElevenLabs |
| POST | `webhooks/elevenlabs/` | ElevenLabs post-call webhook (`ElevenLabs-Signature` HMAC) |

Configure `ELEVENLABS_API_KEY`, `ELEVENLABS_AGENT_ID`, `ELEVENLABS_AGENT_PHONE_NUMBER_ID`, `ELEVENLABS_WEBHOOK_SECRET`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` and `TWILIO_PHONE_NUMBER` in `backend/.env`.

ElevenLabs agent setup:
1. Paste the first message and system prompt from **Integrations** (or the `agent-config/` endpoint) into the agent.
2. Enable dynamic variables.
3. Point the post-call webhook to `https://<public-host>/api/v1/screening/webhooks/elevenlabs/`.

Without a public webhook, run `python manage.py sync_screening_calls` periodically. The UI also polls while a call is live.

Live Twilio/ElevenLabs calls are **not** covered by automated tests; the tests use fake provider clients.


## Module 11 — Screening Review (human gate 2)

`POST /api/v1/screening/<screening_uuid>/review/` (recruiter/admin) records an append-only `ScreeningReview` for a screening in `AWAITING_HR_REVIEW`.

Request body: `{ "decision": ..., "decision_reason": "..." }`. The decisions are:

| Decision | Effect |
|---|---|
| `APPROVE_FOR_INTERVIEW` | Candidate moves to `APPROVED_FOR_INTERVIEW` |
| `RESCREEN_AI_CALL` | Creates a new screening; blocked if the candidate opted out |
| `RESCREEN_HUMAN_LED` | Creates a new screening |
| `DECLINE` | Candidate moves to `CLOSED`, with the reason stored |

Rules:
- A reason is required for every decision except approving a call that completed normally.
- The screening becomes `REVIEWED` and is returned with its `review`.
- Each screening can be decided only once, and only while the candidate is in `SCREENING_COMPLETED_HR_REVIEW`.
- The AI's `recommended_next_step_for_human_review` is advisory only.

UI:
- **Screening** (queue, filtered to results awaiting review by default) → **Review**.
- Or open the candidate's **Screening** tab. The result view shows the candidate's statements separately from the AI interpretation, unresolved questions, warnings and the transcript (recruiters only).


## Module 12 — Scheduling & Calendar Agent

The `scheduling` app (`/api/v1/scheduling/`) implements the availability half of Agent 3 (FR-09, SRS §8).

**Calendar source:** the internal availability calendar (`AvailabilitySlot`), labelled as such in every API response and screen. No Google/Microsoft calendar is connected. Interviewers (any staff user) maintain their own windows; recruiters can maintain anyone's. All times are stored in UTC. Each window and each candidate time zone is an IANA zone, and the UI shows times in the candidate's zone and the viewer's own zone.

**Flow:**
1. **Plan.** `POST candidates/<candidate_uuid>/interviews/` (recruiter; candidate must be `APPROVED_FOR_INTERVIEW`). Body: interviewer, duration, candidate time zone, format plus link/location, and candidate availability windows (`[{date, start_time, end_time}]` in the candidate's zone).
2. **Slot calculation.** The engine intersects the candidate's windows with the interviewer's availability. It excludes booked interviews, respects `SCHEDULING_MIN_NOTICE_HOURS`, and steps by `SCHEDULING_SLOT_STEP_MINUTES`, returning up to `SCHEDULING_MAX_PROPOSED_SLOTS` slots.
   - With slots, the interview is `PROPOSED`.
   - With none, it is `NEEDS_HR_COORDINATION` (the SRS §14 HR task).
   - Either way, the candidate moves to `INTERVIEW_PROPOSED`. Every calendar check is audited.
3. **Re-propose.** `POST interviews/<uuid>/propose/` re-runs the check with updated details or windows.
4. **Confirm.** `POST interviews/<uuid>/confirm-slot/` takes `{slot_start, candidate_confirmed, interviewer_confirmed}`. Both confirmations are required, the slot must be one of the proposed slots, and it is re-checked against the calendar so it can't be double-booked. The interview becomes `SLOT_CONFIRMED`.
5. **Cancel.** `POST interviews/<uuid>/cancel/` (`reason`) returns the candidate to `APPROVED_FOR_INTERVIEW`.

**Other endpoints:**
- `GET/POST availability/`, `DELETE availability/<uuid>/`
- `GET interviews/?status=ACTIVE|<status>&mine=1`
- `GET interviews/<uuid>/`

**UI:**
- The **Interviews & Availability** page lists active and scheduled interviews and lets users manage availability.
- The candidate **Interview** tab covers planning, slot confirmation, re-proposing and cancelling.


## Module 13 — Email Invitation Agent

The `communications` app (`/api/v1/communications/`, recruiters/admins) implements the SRS §11 `CommunicationLog` and the invitation half of Agent 3 (FR-10, FR-11, AC-07, AC-08).

**Flow:**
1. **Draft.** `POST interviews/<interview_uuid>/draft/` is available once the slot is `SLOT_CONFIRMED`. It renders the versioned template `interview-email-v1` with role, date/time, time zone, duration, format, meeting link/location, interviewer, and rescheduling contact (`INVITATION_RESCHEDULE_CONTACT`). The candidate is the recipient and the interviewer is cc'd. Drafting is idempotent and never sends.
2. **Edit.** `PATCH <uuid>/` (`subject`, `body`) is allowed only while the message is a draft. Sending is refused if an edit removed a required detail.
3. **Approve and send.** `POST <uuid>/approve-send/` with `{"confirm": true}` records the approver and time, then sends through Django's `EMAIL_BACKEND` with an iCalendar attachment (`METHOD:REQUEST`, stable UID, `SEQUENCE`).
   - **Success:** `SENT` with `provider_message_id` and `sent_at`. The interview becomes `SCHEDULED` and the candidate `INTERVIEW_SCHEDULED`.
   - **Failure:** `FAILED`. The draft and approval are kept, nothing is marked as scheduled, and the same endpoint retries.
   - **Duplicates:** an atomic claim plus a unique constraint on sent messages (per interview, kind and sequence) prevent duplicate invitations.
4. **Reschedule.** For a `SCHEDULED` interview, `POST /api/v1/scheduling/interviews/<uuid>/propose/` increments the sequence and returns the candidate to `INTERVIEW_PROPOSED`. Confirming a new slot then drafts an `INTERVIEW_RESCHEDULE` update.
5. **Cancel.** Cancelling an interview after an invitation was sent automatically drafts an `INTERVIEW_CANCELLATION` notice (`METHOD:CANCEL`), which still needs HR approval to send.
6. **Discard / list.** `POST <uuid>/discard/` discards a draft. `GET ?candidate=&interview=&pending=1` lists messages.

**Email delivery:** console output by default. Set `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` with `EMAIL_HOST*` for real delivery. SMTP reports only acceptance by the provider, not final delivery.

**UI:** the candidate **Interview** tab has the invitation editor ("Approve and send" requires a confirmation checkbox), retry after failure, reschedule, and a communication log, including cancellation notices waiting for approval.


## Module 14 — Dashboard & Candidate Lifecycle Tracking

The read-only `dashboard` app (`/api/v1/dashboard/`) is available to all authenticated roles. All data is scoped by `candidates_visible_to`, so hiring managers see only their requisitions. It covers AC-09, FR-12, FR-13 and FR-14.

| Endpoint | Returns |
|---|---|
| `summary/?requisition=` | Counts for all 10 SRS §9 statuses, total/active candidates, open requisitions, a **needs attention** list and interviews in the next 14 days |
| `pipeline/?status=&search=&requisition=&page=` | One row per candidate: status, latest score and confidence, latest screening outcome, latest interview slot |
| `activity/?event_type=&candidate=&page=` | The append-only audit trail across candidates (status changes, approvals, call attempts, calendar checks, emails) |
| `event-types/` | Labels for the audit-log filter |

The needs attention list covers:
- **Pending human decisions:** shortlist, screening review, invitation approval, cancellation notices.
- **Errors with retries:** resume extraction, scoring workflow, screening analysis, email sending.
- **Next actions:** resumes to extract, calls to place, interviews to plan, slots to confirm, coordination tasks.

**UI:**
- **Dashboard** (home page): stat tiles, a lifecycle status bar list (click a bar to filter candidates), linked attention items labelled by severity, upcoming interviews in candidate and local time, and a filterable pipeline table. It refreshes every minute.
- **Audit Log:** a paginated, filterable event history.


## Module 15 — Production Hardening & QA

**System audit (SRS §11 `AuditEvent`, FR-14).** The `audit` app records requisition create/update/delete (with changed fields and status transitions), every rubric version change (old and new weights), and personal-data erasure. View it at `GET /api/v1/audit/?action=&entity_type=&entity_id=` (recruiters/admins), or in the UI under **Audit Log → Requisition & configuration changes**.

**Candidate closure and privacy (SRS §9, §12, §13):**
- `POST /api/v1/candidates/<uuid>/close/` (recruiter, `reason` required) closes a candidate.
  - Pending screenings and unsent interviews are cancelled.
  - It refuses while a call is live, or while an interview is `SCHEDULED` (cancel that first so the candidate is notified).
- `POST /api/v1/candidates/<uuid>/erase-personal-data/` (HR admin, closed candidates only, `reason` required) erases personal data:
  - **Removed:** name, contact details, resume files and text, evidence quotes, transcripts, answers, availability, email bodies and recipients.
  - **Kept:** statuses, decisions, timestamps, actors and model versions.
  - Afterwards the record can no longer be edited.
- `python manage.py apply_retention_policy [--dry-run]` erases candidates closed for longer than `CANDIDATE_RETENTION_DAYS` (default 365). Schedule it daily.
- `closed_reason` is now read-only through the candidate API; it is set only by decisions or closure.

**Production settings (`DJANGO_SETTINGS_MODULE=config.django.production`):**
- `DEBUG` is off.
- Startup fails without a unique `SECRET_KEY` and `ALLOWED_HOSTS`.
- Secure cookies and SSL redirect are on; `USE_X_FORWARDED_PROTO` is optional for a TLS proxy.
- JWT access tokens last 15 minutes and refresh tokens 12 hours; the SPA refreshes automatically.
- In telephony mode (`SCREENING_VOICE_MODE=telephony`) with ElevenLabs configured, `ELEVENLABS_WEBHOOK_SECRET` is required. Browser mode (the default) needs no webhook.
- A console email backend triggers a warning.
- `python manage.py check --deploy` reports only the HSTS subdomain/preload options. Set those for your domain.

**Frontend:** a global error boundary; admin-only **Erase personal data** and recruiter **Close candidate** actions on the candidate page.

**QA:**
- `dashboard/test_end_to_end.py` drives the complete AC-11 flow through the REST API with synthetic data: requisition → DOCX resume upload → extraction → LangGraph scoring → shortlist approval → AI screening call → transcript analysis → screening approval → availability → slot proposal and confirmation → invitation draft → approval → send (and the duplicate send is refused). Only Azure, ElevenLabs/Twilio and SMTP are faked. This test runs in telephony mode. The browser-session flow through HR approval is covered by `screening/test_browser_voice.py`.
- The full backend suite is 138 tests (Module 16 added 20, automatic scoring 14, resume details 12, standard screening answers 10): `python manage.py test accounts requisitions candidates llm scoring reviews workflows screening scheduling communications dashboard audit`.

### Acceptance criteria status (SRS §15)

| AC | Status | Evidence |
|---|---|---|
| AC-01–AC-03 | Met | Requisitions, resume intake/extraction, evidence-based scoring (Modules 03–07) |
| AC-04 | Met | Shortlist gate; nothing is contacted from a score alone |
| AC-05 | Met in code; live session not verified | Approved scripts, consent, escalation, attempt limits (Modules 10, 16). Browser mode needs only ElevenLabs credentials for a live demo; telephony needs Twilio too |
| AC-06 | Met | Verified candidate statements kept separate from AI interpretation; HR review (Module 11) |
| AC-07 | Met (internal calendar) | Mutual availability, time zones, confirmation of both parties (Module 12) |
| AC-08 | Met | Invitation only after recorded approval; idempotent send (Module 13) |
| AC-09 | Met | Dashboard and audit logs (Module 14) |
| AC-10 | Met | Retries without duplicate calls/emails: atomic claims, unique constraints, durable state |
| AC-11 | Met with fakes | Automated end-to-end test; a live demo needs provider credentials |
| AC-12 | Met | This README |

**Not done / external:**
- A live ElevenLabs browser session needs ElevenLabs credentials. Live Twilio calls (optional telephony mode) and SMTP delivery need credentials, and telephony also needs a public webhook URL.
- No Google/Microsoft calendar integration (the internal calendar is labelled as such).
- No OCR.
- SQLite remains the database.
- No measured performance benchmark against live Azure.
- Frontend unit tests cover only the browser voice session component (Module 16).
- JWTs are stored in `localStorage`.


## Module 16 — Browser Voice Screening (ElevenLabs WebRTC)

AI screening no longer needs a telephone. With `SCREENING_VOICE_MODE=browser` (the default), the ElevenLabs agent talks to the candidate inside the HR app over WebRTC, using the official `@elevenlabs/react` SDK. Twilio is used only when `SCREENING_VOICE_MODE=telephony` ([Module 10](#module-10--candidate-screening-call-agent-twilio--elevenlabs)). There is no candidate portal yet, so the session runs in the HR workspace as a clearly labelled **Demo browser screening** ("Simulated candidate · no phone call"). It is never shown as a phone call.

### How it works

1. **Create.** On the candidate's **Screening** tab (candidate in `APPROVED_FOR_SCREENING`), a recruiter chooses **Demo browser voice screening**. This creates a `BROWSER_VOICE` screening (script `screening-browser-v2`); the candidate moves to `SCREENING_SCHEDULED_PENDING`. No phone number is needed or used.
2. **Consent.** The page `/screening/<screening_uuid>/browser` shows the candidate and requisition, the approved questions and the disclosure: an AI voice agent will ask the questions, voice is processed by ElevenLabs, the transcript is kept for HR review, and a microphone is required. **Start Interview** stays disabled until the consent box is ticked. The session never starts by itself.
3. **Start.** The browser checks microphone permission and then calls `POST /api/v1/screening/<uuid>/browser-session/` with `{"consent_acknowledged": true}`. The backend:
   - checks the role (recruiter/admin), visibility, channel, screening and candidate status, the open requisition, opt-out/consent blockers and the attempt limit;
   - atomically claims one attempt (`ScreeningCallAttempt`, provider `elevenlabs_webrtc`), so double clicks cannot start two sessions;
   - requests a single-use conversation token with `GET https://api.elevenlabs.io/v1/convai/conversation/token?agent_id=<ELEVENLABS_AGENT_ID>` and the server-side `xi-api-key` header;
   - returns only `screening_id`, `attempt_id`, `conversation_id`, `conversation_token`, `connection_type: "webrtc"` and the script's dynamic variables (candidate **first name** only, role title, organisation, approved questions, human contact). The API key and agent ID never reach the browser, and no resume, email or phone number is sent to ElevenLabs.
4. **Talk.** The SDK connects with `startSession({ conversationToken, connectionType: "webrtc", dynamicVariables })`. The page shows Connecting, Agent speaking, Listening, Muted and Disconnected states, with **Mute** and **End Interview** buttons. Leaving the page during a live session triggers a browser warning.
5. **Complete.** When the session ends (button, agent hang-up, connection loss or a start failure), the browser calls `POST /api/v1/screening/<uuid>/browser-session/complete/` with `attempt_id`, `client_end_reason` and `connected`. **It never sends a transcript.** The backend fetches `GET /v1/convai/conversations/{conversation_id}` from ElevenLabs:
   - `initiated` / `in-progress` / `processing` → `202` with `session_state: "processing"`; the page polls every few seconds and offers **Check result again** if ElevenLabs is slow.
   - `done` with candidate speech → outcome `COMPLETED`; the transcript is stored and Azure analysis runs (quotes are verified against the transcript).
   - `failed`, or a connection loss after the candidate spoke → `INTERRUPTED`. It is never shown as completed, and analysis adds a warning.
   - The session never connected or the candidate never spoke → `ABANDONED` (or `FAILED` if the browser reported a start/connection error).
   - Unsuccessful sessions return the screening to `PENDING_CALL` for another attempt, or escalate to human follow-up once `SCREENING_MAX_CALL_ATTEMPTS` is used.
   - Completing twice is safe: a conditional update makes the first call win, and the second returns the stored result.
6. **HR review.** The analysed session lands in `AWAITING_HR_REVIEW` (candidate `SCREENING_COMPLETED_HR_REVIEW`), the same queue and gate as Module 11. The result also distinguishes `INCOMPLETE` (from the analysis). Nothing is approved or rejected automatically.

Recovery:
- If the page is closed mid-session, the candidate's Screening tab and the browser page show **Check session result** (`POST <uuid>/sync/`), which concludes the session from ElevenLabs.
- A session that never connected, or whose page was closed before it connected, is released after `SCREENING_BROWSER_SESSION_TIMEOUT_MINUTES` (default 15).
- `sync_screening_calls` and the webhook also conclude browser sessions, but neither is required in browser mode.

Every step writes `CandidateEvent`s: `SCREENING_BROWSER_SESSION_STARTED`, `SCREENING_BROWSER_SESSION_FAILED`, `SCREENING_BROWSER_SESSION_ENDED`, plus the existing status-change and analysis events.

### Endpoints (`/api/v1/screening/`, recruiter/admin)

| Method | Path | Purpose |
|---|---|---|
| POST | `candidates/<candidate_uuid>/` | Create a screening; `channel` defaults to `BROWSER_VOICE` in browser mode (`AI_VOICE` is refused unless telephony mode) |
| POST | `<screening_uuid>/browser-session/` | Start a session: `{consent_acknowledged: true}` → `201` with the token and IDs (`Cache-Control: no-store`) |
| POST | `<screening_uuid>/browser-session/complete/` | Conclude: `{attempt_id?, client_end_reason, connected?, conversation_id?}` → `200` concluded, or `202` still processing |
| POST | `<screening_uuid>/sync/` | Recover a session whose page was closed |
| GET | `agent-config/` | Voice mode, readiness booleans, browser policy and, for admins, the active script to paste into ElevenLabs |

Errors: `503` if ElevenLabs is not configured (no attempt is used), `502` if ElevenLabs is unreachable or rejects the request. A `502` on completion loses nothing; try again shortly.

### Environment variables

| Variable | Browser mode | Notes |
|---|---|---|
| `SCREENING_VOICE_MODE` | `browser` | `browser` (default) or `telephony` |
| `ELEVENLABS_API_KEY` | Required | Server-side only |
| `ELEVENLABS_AGENT_ID` | Required | Server-side only; the frontend never hardcodes it |
| `SCREENING_BROWSER_SESSION_TIMEOUT_MINUTES` | Optional | Default 15 |
| `ELEVENLABS_API_BASE_URL`, `VOICE_PROVIDER_TIMEOUT_SECONDS`, `SCREENING_MAX_CALL_ATTEMPTS`, `SCREENING_ORGANIZATION_NAME`, `SCREENING_HUMAN_CONTACT` | Optional | Shared with telephony mode |

**Not needed in browser mode** (leave empty): `TELEPHONY_PROVIDER`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`, `ELEVENLABS_AGENT_PHONE_NUMBER_ID`, `ELEVENLABS_WEBHOOK_SECRET`, `SCREENING_ALLOWED_DIAL_PREFIXES`, `SCREENING_RETRY_INTERVAL_MINUTES`, `SCREENING_CALL_TIMEZONE`, `SCREENING_CALL_WINDOW_START_HOUR`, `SCREENING_CALL_WINDOW_END_HOUR`. The production settings no longer require the webhook secret in browser mode. Existing phone-call records are kept and still display.

### ElevenLabs agent setup (manual, in the ElevenLabs dashboard)

1. **Create the agent.** Go to **ElevenLabs Agents** (Conversational AI) and create a blank agent.
2. **Script.** In the HR app, open **Integrations** as an admin and copy the **browser** first message and system prompt (also available from `GET /api/v1/screening/agent-config/`). Paste them into the agent's *First message* and *System prompt*. Keep the `{{...}}` placeholders: they are dynamic variables filled per session (`candidate_name`, `role_title`, `organization_name`, `screening_questions`, `question_count`, `human_contact`).
3. **End call tool.** Enable the built-in **End call** system tool so the agent can close the session when the candidate declines, asks for a human or finishes.
4. **Agent ID.** Copy the agent ID (`agent_...`) from the agent's page or URL into `ELEVENLABS_AGENT_ID` in `backend/.env`.
5. **Authentication.** In the agent's **Security** settings, enable **authentication**. The agent then accepts only sessions started with a token issued by our backend, so a copied agent ID cannot be used to start sessions. If you also use the host allowlist, add the host you open the app on (for example `localhost:5173`).
6. **API key.** Under your profile → **API keys**, create a key with access to ElevenLabs Agents. The backend uses it to request tokens, read conversations and, if a candidate declines consent, delete the conversation. Put it in `ELEVENLABS_API_KEY` in `backend/.env`. Never put it in frontend code or `.env` files under `frontend/`.
7. **Privacy and retention.** Review the agent's privacy and retention settings yourself. The backend fetches the transcript from ElevenLabs after each session, so the transcript must stay retrievable until then (a zero-retention mode would leave HR with no transcript). This app does not verify or control how long ElevenLabs keeps audio, and the disclosure does not claim it is deleted.

Restart `runserver` after editing `.env`. **Integrations** should then show *Browser voice sessions: Ready*.

### Testing the microphone locally

- Open the app at `http://localhost:5173`. Browsers allow microphone access only on secure contexts, and `localhost` counts as one. A LAN IP over plain HTTP will not work.
- The first **Start Interview** triggers the browser's permission prompt. If you denied it, the page explains how to fix it: allow the microphone in the site settings (the icon in the address bar) and try again. A missing or busy microphone gets its own message.
- Use headphones to stop the agent hearing itself.

### Running the tests

```powershell
# backend/ (ElevenLabs HTTP is mocked; no network, no billing)
python manage.py test screening.test_browser_voice
# frontend/ (the ElevenLabs SDK and the API are mocked)
npm test
```

Neither suite contacts ElevenLabs. A real session, real microphone audio and the actual ElevenLabs dashboard behaviour can only be verified manually with credentials.


## Automatic resume scoring (Celery worker)

New resumes no longer wait for someone to click **Score resume**. A Celery beat scheduler enqueues a scoring cycle every `AUTO_SCORING_INTERVAL_SECONDS` (default 120). The worker then:

1. **Extracts** resumes still waiting for text extraction (the same service as `process_pending_resumes`).
2. **Releases** scoring runs stuck in `PENDING`/`RUNNING` for over 15 minutes (for example, the worker was killed mid-run). They become `FAILED` with `WORKFLOW_STALE`, so HR can re-score.
3. **Scores** every new resume through the existing LangGraph workflow (`score_resume → wait_for_hr_review`), up to `AUTO_SCORING_BATCH_LIMIT` per cycle. A resume is new when its candidate is in `RESUME_RECEIVED`, the requisition is `OPEN`, and the latest extracted resume has never had a workflow run.

Rules:
- **The human gate is unchanged.** Automatic scoring moves a candidate only to `SCORED_HR_REVIEW` (or `NEEDS_MANUAL_REVIEW`), exactly like the button. It never approves, declines or contacts anyone.
- **Each resume is scored automatically once.** If that run fails (Azure down, bad configuration), it is left `FAILED` for HR to retry with **Score resume**, so an outage can't cause a billed call every 2 minutes.
- **No duplicates.** A database constraint allows one active workflow run per candidate, so the worker and a recruiter (or two workers) can't score the same candidate twice.
- **Audit.** Automatic runs have `trigger=AUTOMATIC` and no `created_by`. The `WORKFLOW_STARTED`/`WORKFLOW_FAILED` candidate events carry the trigger. Manual runs are `trigger=MANUAL`.
- Every automatic run is a live, billed Azure OpenAI call. Set `AUTO_SCORING_ENABLED=False` to turn it off.

### Running it (Windows, from `backend/`, venv active, three terminals)

```powershell
python manage.py runserver
celery -A config worker --pool=solo --loglevel=info   # Windows needs the solo pool
celery -A config beat --loglevel=info                 # the scheduler; on Windows it can't be combined with the worker (-B)
```

Without Celery, `python manage.py auto_score_resumes [--limit N]` runs one cycle immediately (same code). After fixing an outage or a configuration error, `python manage.py auto_score_resumes --retry-failed` also re-scores resumes whose earlier runs all failed. The failed runs stay in the audit trail.

Restart the worker after changing `backend/.env`. Settings such as the Azure endpoint are read once, when the worker starts.

**Azure endpoint:** `AZURE_OPENAI_ENDPOINT` must be only the resource URL, for example `https://<resource>.services.ai.azure.com` or `https://<resource>.openai.azure.com`. Don't paste a full target URL such as `.../openai/v1/responses`; the app appends `/openai/v1` itself, and the extra path causes a 404 on every scoring call.

**Broker:** by default, the queue is a local SQLite file (`backend/celery-broker.sqlite3`, through SQLAlchemy), so no extra service is needed. For production, use Redis: `pip install redis` and set `CELERY_BROKER_URL=redis://localhost:6379/0`. On this machine, Redis can run in Docker (`docker run -d -p 6379:6379 redis:7`). Task results are not stored. The broker file and `celerybeat-schedule` are git-ignored.

### Settings (`backend/.env`)

| Variable | Default | Purpose |
|---|---|---|
| `AUTO_SCORING_ENABLED` | `True` | Turn the scheduled scoring on or off |
| `AUTO_SCORING_INTERVAL_SECONDS` | `120` | How often beat enqueues a cycle (minimum 30) |
| `AUTO_SCORING_BATCH_LIMIT` | `10` | Maximum resumes scored (and extracted) per cycle |
| `CELERY_BROKER_URL` | empty = SQLite file | Message broker URL |

### API and UI

- `GET /api/v1/workflows/auto-scoring/` (any signed-in user) returns `enabled`, `interval_seconds`, `batch_limit`, `awaiting_scoring` and `last_automatic_run_at`. The counts are scoped to the candidates the user can see.
- Workflow runs now include `trigger` (`MANUAL` or `AUTOMATIC`).
- **Integrations** shows an *Automatic resume scoring — Celery* card: status, interval, resumes waiting and the last automatic run.
- On a candidate's **Scoring & shortlist** tab, an unscored resume shows that automatic scoring is on. The tab refreshes itself when the score arrives. **Score resume** still scores immediately.

Tests: `python manage.py test workflows` (Azure is mocked; the Celery task is run with `.apply()`, so no broker is needed).


## Automatic interview scheduling (Agent 3)

**What it does.** When HR approves a screening, the scheduling agent matches the candidate's stated availability with an interviewer's calendar and emails the invitation, with no further clicks.

1. **Interview format (per requisition).** The requisition form has an *Interview* section: **On-site** (the requisition *Location* is the address, so it is required) or **Video call (WhatsApp)** (a WhatsApp number with country code is required, e.g. `+923001234567`). API fields: `interview_format` (`ONSITE`/`VIDEO`), `interview_whatsapp_number`.
2. **Candidate availability.** Every screening ends with the standard question *"Which days and times in the next two weeks would suit you for an interview, and in which time zone?"* (added automatically to the approved questions). The answer is read into windows by Azure (only that text is sent; dates, times and zones are validated in code; unknown zones fall back to `SCHEDULING_DEFAULT_TIMEZONE`).
3. **Matching.** Interviewers are active users with future availability slots (*Interviews → availability*). The requisition's hiring manager is tried first, then the least-booked others. The earliest slot inside both the candidate's windows and the interviewer's free time (minus booked interviews) is booked.
4. **Email.** Template `interview-email-v3`: on-site → address and date/time; video → *WhatsApp video call on +92…* and date/time; plus an ICS attachment. The interviewer is cc'd.
5. **Safeguards.** No availability, no overlap, no interviewer calendar, a missing email/location/WhatsApp number or a send failure leave the candidate with HR (reason shown on the candidate's Interview tab, "Needs attention" on the dashboard); the invitation is never reported as sent. One active interview per candidate and one sent message per interview/kind/sequence keep retries from duplicating anything.

**Human gate.** HR's screening approval is the gate; there is no separate send approval (SRS FR-11 asked for one; this is a user decision of 2026-11-08). Messages are marked `auto_sent`, events carry `automatic=true`. Set `INTERVIEW_AUTO_SCHEDULING_ENABLED=false` to go back to draft → HR approves → send.

**Run it.** Celery worker and beat must run (see *Automatic resume scoring*): the approval queues the task immediately and beat sweeps every `AUTO_SCORING_INTERVAL_SECONDS`. `POST /api/v1/scheduling/candidates/<uuid>/interviews/auto/` (recruiter/admin; the **Run scheduling agent now** button) re-runs it after HR fixes something.

**Env.** `INTERVIEW_AUTO_SCHEDULING_ENABLED` (default true), `SCHEDULING_DEFAULT_TIMEZONE` (default `Asia/Karachi`), `SCHEDULING_DEFAULT_DURATION_MINUTES` (45). Dev email goes to the console backend; set `EMAIL_BACKEND`/`EMAIL_HOST*` for real delivery.

**Verify.** `python manage.py test scheduling.test_auto_schedule` (fake Azure and email).

## Declined candidates: friendly rejection and automatic deletion

When HR **declines** a candidate (shortlist review or screening review) the system, without further clicks:

1. closes the candidate and records a `REJECTION_PENDING` marker;
2. emails a friendly rejection notice (template `rejection-email-v1`). It thanks the candidate, says the application will not move forward, and states that their resume, contact details, screening answers and evaluation notes were deleted from the HR system. It does not give HR's reason, any score, or mention that the name is kept;
3. **after the email backend accepts it**, erases the candidate's data with `erase_personal_data(keep_name=True)`. Resume files and text, contact details, evidence excerpts, transcripts and answers, and email bodies are removed; the **name**, statuses, decisions, timestamps and model versions stay so HR can tell who was declined.

Safeguards: a send failure keeps the data and retries (beat sweep, `REJECTION_MAX_EMAIL_ATTEMPTS`, default 5; the dashboard shows failed emails); a candidate without an email is erased immediately; the email goes out at most once; a running scoring workflow delays the deletion; candidates closed manually or declined before this feature are never touched. The decline forms warn that the action cannot be undone and ask for confirmation.

Env: `REJECTION_AUTO_ENABLED` (default true), `REJECTION_MAX_EMAIL_ATTEMPTS` (5). Celery worker and beat must run. Verify: `python manage.py test candidates.test_decline`.

## Candidate details from the resume and one-click approvals

HR no longer types in a candidate's name or contact details. The two selection steps are a single **Approve this candidate** button.

### Details are read from the resume (SRS §4.1)

Right after a resume's text is extracted, and before it is scored, `candidates/services/contact_details.py` fills the candidate's **empty** fields:

| Field | How |
|---|---|
| Email, phone, LinkedIn URL | Local pattern matching, with no AI call. The top of the resume is used first. Further down, a value is used only if it is the only one in the document, so a referee's email or phone isn't taken. |
| Name, location | Azure OpenAI reads only the first 2,500 characters. A value is kept only if it appears word for word in the resume (SRS §14: nothing is invented). Without Azure, the name comes from the first line that looks like a name, and the location stays empty. |

Rules:
- Values a recruiter entered are never overwritten. Fields filled this way show a *from resume* tag on the candidate page. Editing a field removes its tag.
- The "Contact details missing" flag (`identity_review_required`) clears automatically once an email or phone is found. It stays on only when the resume has no contact details, or when the email already belongs to another applicant for the same job (likely the same person applying twice). Only in those cases does HR add details with **Edit details**.
- Every fill writes a `CANDIDATE_DETAILS_FROM_RESUME` event listing the field **names**. Values are never logged.
- Scoring now also hides the detected name (including all-caps or extra-space variants), the stored location and LinkedIn URLs before its Azure call.
- To fill candidates processed before this change: `python manage.py fill_candidate_details [--limit N]`. This makes Azure calls for name and location.

### One-click approvals (both human gates)

- **Shortlist (gate 1):** **Approve this candidate** posts `{"evaluation": ..., "decision": "APPROVE_FOR_SCREENING"}`. No reason or identity checkbox is needed. Approving confirms the details read from the resume, and the approver and time are recorded. It is refused only when the resume had no email or phone, or when there is no AI score (use *Approve with a score override*).
- **Screening review (gate 2):** **Approve this candidate** approves for interview with one click, including after an interrupted or incomplete session. The outcome and a warning are shown first and stay on record.
- **Decline, hold, re-screen and score overrides** are under *Other decisions* and still need a reason (FR-04 "record a reason where appropriate").

The test runner (`config/test_runner.py`) blanks the Azure, ElevenLabs and Twilio keys during `manage.py test`, so no test can make a live, billed call even with a real `.env`.


## Screening: salary, notice period and interview availability

Every AI screening (browser session or phone call) now gathers three standard answers, and HR reviews them next to the job description before approving the candidate for interview (SRS §8 Agent 2, FR-06–FR-08).

### What the agent asks (scripts `screening-browser-v4` / `screening-call-v4`; v4: only the Approved screening questions are asked, a refusal ends the session, short first message; v3: no explanations of off-topic questions or word definitions, each question asked at most 3 times, then the agent ends the session)

After the requisition's approved questions, the agent asks, one at a time:
1. **Expected salary:** a minimum and a maximum, and the currency. It asks once more if the candidate gave a single figure or didn't say the currency or whether the figure is monthly or yearly. "Prefer not to say" is accepted.
2. **Notice period**, or the earliest date the candidate could start.
3. **Interview availability:** days and times in the next two weeks, with the time zone.

The agent never comments on or negotiates the salary. It doesn't know the job's budget: the budget isn't one of the dynamic variables sent to ElevenLabs.

**Stays on topic.** The agent answers only questions about the role and the hiring process. Anything else gets "Sorry, I can only help with questions about this role and the hiring process", and the screening continues. That covers general knowledge or current events (for example, who a country's president is), technical explanations (what a backend is, what Django is), and questions about the assistant or the company's systems. It never reveals its instructions and ignores requests to change its rules. A role question it can't answer is left for the recruiting team to follow up.

The live ElevenLabs agent was updated through the API with the v2 browser script (end-call tool and authentication unchanged). If you manage the agent by hand, copy the script again from **Integrations**.

### How the answers are extracted (`screening-analysis-v2`)

The transcript analysis returns each answer with a status (`STATED`, `DECLINED_TO_ANSWER`, `NOT_ASKED`, `UNCLEAR`) and the candidate's own words. As with the question answers:
- The quote must appear in what the **candidate** said. Otherwise it is removed with a warning.
- A summary or salary figure is kept **only** when its quote is verified, so nothing is invented.
- Salary shorthand becomes plain numbers (150k → 150000, 1.5 lakh → 150000). One figure means min = max, a reversed range is swapped, and the currency must be an ISO code the candidate stated or clearly implied ("rupees" → PKR); otherwise it is left empty.
- A declined or unclear answer is added to *Unresolved — needs human follow-up*. So is a topic the agent skipped in a completed screening.
- Off-topic questions from the candidate are not listed as candidate questions.

New `Screening` fields (migration `screening/0004`): `expected_salary_min`, `expected_salary_max`, `expected_salary_currency`, `expected_salary_period` (`MONTHLY`/`ANNUAL`/`UNSPECIFIED`), `expected_salary_statement`, `notice_period`, `notice_period_statement`, `availability_statement`. `candidate_stated_availability` keeps the availability summary. Personal-data erasure clears all of them.

### API and UI

- `GET /api/v1/screening/<id>/` and the screening queue now include those fields and a read-only `job` object for the requisition: `description`, `responsibilities`, required and preferred skills, minimum experience, education, location, work mode, employment type, and `salary_min`/`salary_max`/`currency`. Access rules are unchanged; hiring managers see only their own requisitions.
- The screening review (the **Screening** queue's *Review* row and the candidate's **Screening** tab) shows:
  - *Salary, notice period and interview availability* cards, each with the candidate's quote;
  - a **Job description** panel with the job's salary budget next to the candidate's expected salary, plus the skills, location, work mode and full description.
  
  The comparison is shown, not computed. The requisition has no pay period, so the app doesn't label a candidate "within budget"; HR decides.
- The human-led result form has optional salary (from, to, currency, per month or year), notice-period and interview-availability fields. A range whose minimum exceeds its maximum is refused.

Tests: `python manage.py test screening.test_structured_answers` (Azure and ElevenLabs are faked).

### My Schedule page (`/my-schedule`)

Any signed-in user who interviews (admin, recruiter, hiring manager) can open **My Schedule** to add the dates and times they are free (`POST /api/v1/scheduling/availability/`, `interviewer` = themselves) and to see the interviews assigned to them (`GET /api/v1/scheduling/interviews/?mine=1[&status=ACTIVE|SCHEDULED|CANCELLED]`). Availability can be listed per person with `?interviewer=<id>`. The admin "Interviews & Availability" page is unchanged: admins can still add availability for any user, including recruiters. Dates are DD/MM/YYYY. Tests: `python manage.py test scheduling.test_my_schedule`, `npm test`.

### Roles and access (2026-11-08)

| Role | Access |
|---|---|
| HR Administrator | Everything (plus administrator-only items: AI test endpoint, erase personal data, agent prompt view). Can also be an interviewer. |
| Hiring Manager | Full access to all requisitions, candidates, reviews, scheduling and communications. Can also be an interviewer. |
| HR Recruiter | Interviewer only: sees just the candidates with an interview assigned to them (plus their requisitions and the interview), adds and removes only their own availability on **My Schedule**, and cannot create, edit, review or send anything. |

Backend: `accounts.permissions.has_full_access` / `IsHRStaff`; `candidates_visible_to`, `interviews_visible_to`. Frontend: `useAuth().hasFullAccess`.
