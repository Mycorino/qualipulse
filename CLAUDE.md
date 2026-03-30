# Auto-Interview — Claude Code Project Guide

## Working Directory
All work for this project lives at: `/Users/corinofontana/Desktop/auto-interview`

## Project Overview
A SaaS platform that lets companies create AI-driven voice interviews. Stakeholders build an interview guide, generate a shareable link, and participants complete the interview in-browser. Responses are transcribed, analysed, and stored.

**Stack:**
- **Backend:** FastAPI (Python) + SQLAlchemy + SQLite, JWT auth
- **Frontend:** React 18 + Vite + TypeScript
- **AI:** Claude (`claude-sonnet-4-20250514`) for adaptive interview orchestration
- **STT:** OpenAI Whisper (`whisper-1`)
- **TTS:** OpenAI TTS (`tts-1`, voice: `alloy`)

## Repository Layout
```
auto-interview/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, CORS, static audio serving
│   │   ├── config.py            # Settings (reads .env)
│   │   ├── database.py          # SQLAlchemy engine + session
│   │   ├── models/
│   │   │   ├── user.py          # User model
│   │   │   ├── project.py       # Project + InterviewGuideQuestion
│   │   │   └── interview.py     # Participant + InterviewTurn
│   │   ├── routes/
│   │   │   ├── auth.py          # /auth/register, /auth/login
│   │   │   ├── projects.py      # /projects CRUD, CSV import/export
│   │   │   └── interviews.py    # /interview/{token} public endpoints
│   │   └── services/
│   │       ├── interview_engine.py  # Core AI orchestration
│   │       ├── stt.py               # Whisper transcription
│   │       ├── tts.py               # OpenAI TTS generation
│   │       └── storage.py           # Audio file path helpers
│   ├── requirements.txt
│   └── .env                     # NOT in git — contains API keys
└── frontend/
    ├── src/
    │   ├── api/                 # Axios API clients
    │   ├── hooks/               # useAudioRecorder (Safari-compatible)
    │   ├── pages/               # Dashboard, Projects, Interview
    │   └── components/
    ├── vite.config.ts           # Proxy: /api → localhost:8000 (strips /api prefix)
    └── package.json
```

## Dev Server Commands

### Backend
```bash
cd /Users/corinofontana/Desktop/auto-interview/backend
source .venv/bin/activate   # or: python -m venv .venv && pip install -r requirements.txt
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
DATABASE_URL=sqlite:///./interviews.db
UPLOAD_DIR=uploads
```

## Key Architectural Notes

### API Routing
- Frontend calls `/api/...` → Vite proxy strips `/api` → FastAPI receives plain paths
- Auth endpoints: `/auth/register`, `/auth/login`
- Project endpoints: `/projects/` (trailing slash required — redirects drop auth header)
- Interview endpoints: `/interview/{token}`, `/interview/{token}/start`, `/interview/{token}/{participant_id}/respond`

### Audio Recording (Safari Compatibility)
- `MediaRecorder.start(250)` — timeslice fires `ondataavailable` every 250ms
- MIME type priority: `audio/webm;codecs=opus` → `audio/webm` → `audio/mp4` (Safari) → `audio/ogg`
- File named `recording.{ext}` to help backend/FFmpeg detect format

### Datetime Handling
- SQLite stores naive UTC timestamps — use `datetime.utcnow()` not `datetime.now(timezone.utc)`

### Claude Interview Engine
Claude decides after each response whether to:
- `follow_up` — ask a follow-up on the current topic
- `next_question` — move to the next guide question
- `close` — wrap up warmly when all questions are covered or time is up

## V1 Feature Status
- [x] Company signup / login (JWT)
- [x] Project creation with interview guide (sections + questions)
- [x] CSV import/export for interview guides
- [x] Shareable interview links (UUID tokens)
- [x] Voice interview flow (record → STT → Claude → TTS)
- [x] Adaptive follow-ups via Claude
- [x] Response storage (transcripts + audio)
- [ ] Dashboard analytics / response export
- [ ] Email invitation sending
- [ ] Multi-language TTS voices
- [ ] Participant response viewer UI
