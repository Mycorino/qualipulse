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

## Dev Server Commands

### Backend
```bash
cd /Users/corinofontana/Desktop/auto-interview/backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
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
- [x] Signup / login (JWT)
- [x] Project creation wizard (4 steps: Brief → Objective → Scope → Questionnaire)
- [x] AI-assisted objective, scope, and question generation
- [x] CSV import/export for interview guides
- [x] Shareable interview links (UUID tokens), multiple per project
- [x] Screening questions with disqualifying options (Setup tab + wizard)
- [x] Overview tab: participant stats, completion rate, link management
- [x] Setup tab: screening question editor, interview guide with Note/Deprecate per question
- [x] Responses tab: participant list with status/demographics, transcript viewer
- [x] Transcript editing (manual corrections, saved to DB)
- [x] Quote tagging + codebook (select text → assign code → view in codebook panel)
- [x] Analysis tab: AI-generated summary, key themes, JTBDs, tensions, recommendations
- [x] Memos (+ Note inline on themes/JTBDs/tensions, general notes section)
- [x] Segment heatmap (profession / age_range / country breakdowns)
- [x] Export CSV (participants + transcript turns)
- [ ] Email invitation sending
- [ ] Multi-language TTS voices
- [ ] Dashboard-level analytics across projects

### Participant Side
- [x] Interview landing page (name + profession + age range + country)
- [x] Screening questions phase (styled, progress bar, disqualification flow)
- [x] Voice interview (record → STT → Claude → TTS)
- [x] Adaptive follow-ups via Claude
- [x] Completion screen
