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

Batch resume intake creates placeholder candidates with `identity_review_required=true`; it never fabricates names or email addresses from filenames.

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
```

Sign in with a Django user (`python manage.py createsuperuser`, then set `role` in the admin). JWTs are kept in `localStorage` (prototype trade-off; move to httpOnly cookies before production). Set `VITE_API_PROXY_TARGET` to proxy to a different backend.

Screens: requisitions (create/edit/open/hold/close, rubric weights, batch resume upload), candidates (details, consent, resumes, extraction, scoring, shortlist decision, screening, activity history), shortlist queue, screening queue and integration status.

## Module 10 — Candidate Screening Call Agent (Twilio + ElevenLabs)

ElevenLabs Conversational AI places outbound calls through its **native Twilio integration** (`POST /v1/convai/twilio/outbound-call`) using the Twilio number imported into ElevenLabs. Twilio's REST API is queried for the authoritative call status (no-answer, busy, failed). Post-call results arrive by an HMAC-signed ElevenLabs webhook, with polling as a fallback. Azure GPT-5 mini turns the transcript into the SRS §8 output fields. Every quoted candidate statement is verified against the transcript, and unverifiable quotes are downgraded to `UNCLEAR`.

Safeguards:
- Only candidates in `APPROVED_FOR_SCREENING` can be screened.
- The agent uses only the requisition's approved questions and the versioned script `screening-call-v1`.
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
