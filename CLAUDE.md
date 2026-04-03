# Auto-Interview — Claude Code Project Guide

## Working Directory
All work for this project lives at: `/Users/corinofontana/Desktop/auto-interview`

## Project Overview
A SaaS platform that lets companies create AI-driven voice interviews. Researchers build an interview guide, generate a shareable link, and participants complete the interview in-browser. Responses are transcribed, analysed, and stored. Researchers can then review transcripts, tag quotes, add memos, and generate AI analysis reports.

**Stack:**
- **Backend:** FastAPI (Python) + SQLAlchemy + SQLite, JWT auth
- **Frontend:** React 18 + Vite + TypeScript
- **AI:** Claude (`claude-sonnet-4-20250514`) for adaptive interview orchestration + analysis
- **STT:** OpenAI Whisper (`whisper-1`)
- **TTS:** OpenAI TTS (`tts-1`, voice: `alloy`)

## Repository Layout
```
auto-interview/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, CORS, static audio serving, create_all
│   │   ├── config.py            # Settings (reads .env)
│   │   ├── database.py          # SQLAlchemy engine + session
│   │   ├── models/
│   │   │   ├── __init__.py      # Registers all models for create_all
│   │   │   ├── company.py       # Company (auth) model
│   │   │   ├── project.py       # Project + InterviewGuideQuestion + ScreeningQuestion
│   │   │   ├── interview.py     # InterviewLink + Participant + InterviewTurn + ProjectAnalysis
│   │   │   ├── coding.py        # ManualCode + QuoteTag (researcher codebook)
│   │   │   └── memo.py          # ProjectMemo
│   │   ├── routers/
│   │   │   ├── auth.py          # /auth/register, /auth/login
│   │   │   ├── projects.py      # /projects CRUD, CSV import/export, analysis, codes, tags, memos
│   │   │   └── interview.py     # /interview/{token} public endpoints + screening
│   │   ├── schemas/
│   │   │   ├── project.py       # Pydantic schemas for project + screening questions
│   │   │   └── interview.py     # StartInterviewRequest (with demographics), responses
│   │   └── services/
│   │       ├── interview_engine.py  # Core AI orchestration (Claude)
│   │       ├── stt.py               # Whisper transcription
│   │       ├── tts.py               # OpenAI TTS generation
│   │       └── storage.py           # Audio file path helpers
│   ├── alembic/
│   │   └── versions/
│   │       └── 0001_add_researcher_features.py  # manual_codes, quote_tags, project_memos + columns
│   ├── requirements.txt
│   └── .env                     # NOT in git — contains API keys
└── frontend/
    ├── src/
    │   ├── api/
    │   │   ├── client.ts        # Axios instance (injects Authorization header)
    │   │   ├── auth.ts          # login, register
    │   │   ├── projects.ts      # projects CRUD, links, participants, analysis, codes, tags, memos, export
    │   │   └── interviews.ts    # getInterviewInfo, getScreeningQuestions, submitScreening, startInterview, submitAudio
    │   ├── hooks/
    │   │   ├── useAuth.ts       # JWT auth state
    │   │   └── useAudioRecorder.ts  # Safari-compatible MediaRecorder
    │   ├── pages/
    │   │   ├── Login.tsx
    │   │   ├── Signup.tsx
    │   │   ├── Dashboard.tsx         # Project list
    │   │   ├── CreateProjectWizard.tsx  # 4-step wizard (Brief → Objective → Scope → Questionnaire)
    │   │   ├── ProjectDetail.tsx     # 4-tab detail view (Overview / Setup / Responses / Analysis)
    │   │   └── Interview.tsx         # Participant-facing interview (landing → screening → interview → complete)
    │   ├── index.css            # All styles (no CSS framework)
    │   └── main.tsx
    ├── vite.config.ts           # Proxy: /api → localhost:8000 (strips /api prefix)
    └── package.json
```

## Test Credentials

### Demo Account
| Field | Value |
|---|---|
| **Email** | `demo@autointerview.com` |
| **Password** | `Demo1234!` |
| **Company name** | Test Company |

### Seeded Test Data
- **Project:** "Customer Discovery — Productivity Tools" (20 min, 5 questions across 3 sections)
- **Interview link:** `http://localhost:5173/interview/356icX4dtvHTEgVc-33b0_B1C3clMFUNIKr7A8AyA9o`
- **3 completed participants** with full transcripts:
  - Alice M. — Product Manager, UK
  - Ben K. — Software Engineer, Germany
  - Sarah L. — Freelance Designer, France

> **Note:** To reset the database, stop the backend, delete `backend/auto_interview.db` and `.claude/worktrees/sleepy-cerf/backend/auto_interview.db`, restart the backend (tables auto-recreate), then re-run the seed script or register a new account.

## Dev Server Commands

### Backend
```bash
# The live backend runs from the worktree (keeps main repo clean during dev)
cd /Users/corinofontana/Desktop/auto-interview/.claude/worktrees/sleepy-cerf/backend
uvicorn app.main:app --reload --port 8000
# Python/uvicorn comes from the system Anaconda env (/opt/anaconda3/bin/uvicorn)
```

### Frontend
```bash
cd /Users/corinofontana/Desktop/auto-interview/frontend
npm install   # first time only
npm run dev -- --port 5173
```

Open: http://localhost:5173

## Environment Variables (`backend/.env`)
```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
SECRET_KEY=<random-secret>
DATABASE_URL=sqlite:///./auto_interview.db
UPLOAD_DIR=uploads
```

## Key Architectural Notes

### API Routing
- Frontend calls `/api/...` → Vite proxy strips `/api` → FastAPI receives plain paths
- Auth: `/auth/register`, `/auth/login`
- Projects: `/projects/` (trailing slash required — redirects drop auth header)
- Interview (public, no auth): `/interview/{token}`, `/interview/{token}/screening-questions`, `/interview/{token}/screen`, `/interview/{token}/start`, `/interview/{token}/{participant_id}/respond`
- Research: `/projects/{id}/codes`, `/projects/{id}/tags`, `/projects/{id}/memos`, `/projects/{id}/analysis`, `/projects/{id}/export`, `/projects/{id}/participants/{pid}/transcript`

### Database
- SQLite, auto-created via `Base.metadata.create_all()` on startup — no migrations needed for new installs
- Alembic migration `0001_add_researcher_features.py` handles upgrades from pre-researcher-feature installs
- Datetime: use `datetime.utcnow()` (SQLite stores naive UTC — `datetime.now(timezone.utc)` causes issues)

### Audio Recording (Safari Compatibility)
- `MediaRecorder.start(250)` — timeslice fires `ondataavailable` every 250ms
- MIME type priority: `audio/webm;codecs=opus` → `audio/webm` → `audio/mp4` (Safari) → `audio/ogg`
- File named `recording.{ext}` to help backend/FFmpeg detect format

### Interview Flow (Participant)
```
Landing (name + profession + age_range + country)
  → Start Interview
  → fetch /screening-questions
  → Has questions? → Screening phase (one question at a time, single select)
      → POST /screen → qualified? → create participant → Interview
                     → disqualified? → "Thank you" screen
  → No questions? → create participant → Interview starts immediately
```
- Participant record is only created **after** passing screening (or if no screening)
- Demographics (profession, age_range, country) are collected on landing and saved to the Participant row, powering the segment heatmap in Analysis

### Claude Interview Engine
Claude decides after each response whether to:
- `follow_up` — ask a follow-up on the current topic
- `next_question` — move to the next guide question
- `close` — wrap up warmly when all questions are covered or time is up

### Screening Questions
- Stored in `screening_questions` table, linked to `projects`
- Each question has `options` (JSON array) and `disqualifying_options` (JSON array subset)
- Accessed via `options_list` / `disqualifying_options_list` properties (JSON parsed)
- Managed in Setup tab → inline editor (collapse/expand per question, toggle disqualifying per option)
- Also configurable in wizard Step 3 (Scope)

### Legacy Project Compatibility
- Older projects may not have `screening_questions` in the API response → always guard with `?? []`
- Example: `(project.screening_questions ?? []).map(...)` — never access `.length` or `.map()` directly

## Feature Status

### Researcher (Company) Side
- [x] Signup / login (JWT) with refresh token + auto-refresh on 401
- [x] Password reset flow (ForgotPassword + ResetPassword pages; console email in dev)
- [x] Project creation wizard (4 steps: Brief → Objective → Scope → Questionnaire)
- [x] AI brief parsing from text and uploaded files (`/research/parse-brief`)
- [x] AI-suggested research objective, learning goals, scope, and full interview guide
- [x] CSV import/export for interview guides
- [x] Shareable interview links (UUID tokens), multiple per project, toggle active/inactive
- [x] Screening questions with disqualifying options (Setup tab inline editor + wizard)
- [x] Per-question notes, desired learning, deprecation (Setup tab)
- [x] Welcome message and system prompt editing per project
- [x] Overview tab: participant stats, completion rate, link management
- [x] Responses tab: participant list with status, demographics, quality badges
- [x] Transcript viewer with full turn-by-turn display
- [x] Transcript editing (manual corrections, `manually_edited` flag, saved to DB)
- [x] Quote tagging + codebook (select text → assign code → codebook panel)
- [x] Analysis tab: AI-generated summary, key themes (with quotes), JTBDs, tensions, recommendations
- [x] Analysis filtering by demographic segment (profession / age_range / country)
- [x] Project memos (general, theme/JTBD/tension-linked) with full CRUD
- [x] Segment heatmap (profession / age_range / country vs themes)
- [x] AI quality assessment per participant (Claude-scored, structured result)
- [x] Export CSV (participants + all transcript turns, streaming response)
- [x] Account & billing settings page (Profile tab + Plan & Billing tab)
- [x] Subscription tier model with feature gates (free/starter/pro/enterprise)
- [x] Stripe Checkout + Customer Portal + webhook handler (needs Stripe keys)
- [x] Usage fields on Company model (`interview_count`, `storage_bytes`) — not yet incremented
- [x] Profile save + change password in AccountSettings UI (PATCH /auth/me, POST /auth/change-password)
- [x] Analysis-ready email (triggered after AI synthesis completes)
- [ ] Usage limits enforcement (gate functions exist but not called on create endpoints)
- [ ] Email invitation sending (template exists, no send endpoint)
- [ ] Multi-language TTS voices (language field exists on projects)
- [ ] Dashboard-level analytics across projects
- [ ] Free trial period (14-day; `trial_ends_at` field exists on Company)

### Participant Side
- [x] Consent screen (decline → thank-you, no record created)
- [x] Interview landing page (name, profession, age range, country, email — all optional)
- [x] Email-based interview resume (cross-device, shows covered topics + elapsed time)
- [x] Session-storage resume (same device/tab, survives page reload)
- [x] Screening questions phase (one at a time, progress bar, back button, disqualification flow)
- [x] Voice interview (record → STT → Claude → TTS)
- [x] Adaptive follow-ups via Claude (`follow_up` / `next_question` / `close`)
- [x] Interview progress label (Q1 of 5 / Follow-up · Q2 of 5) + progress bar fill
- [x] Live time remaining countdown with warning/critical colour states
- [x] Mic permission error UI with refresh prompt
- [x] Mute TTS button
- [x] Skip question (backend + UI button)
- [x] Mic test with AudioContext level meter (auto-pass on speech, manual skip)
- [x] Re-record before submitting (preview state with Submit / ↺ Re-record)
- [x] Retry on network error (blob preserved in lastBlobRef, resubmit without re-recording)
- [x] TTS "done" signal gates record button (disabled during playback)
- [x] Processing step messages (Transcribing → Thinking → Preparing next question)
- [x] 3-minute recording time limit with countdown (last 30s in red, auto-stop)
- [x] Personalised completion screen (name, answer count, "What happens next?" section)
- [x] Transcript flash (4s display of transcribed answer after submit)
- [ ] Participant completion email
