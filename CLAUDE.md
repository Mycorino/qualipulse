# Auto-Interview (Qualipulse) — Claude Code Project Guide

## Working Directory
All work for this project lives at: `/Users/corinofontana/Desktop/auto-interview`

## Project Overview
A SaaS platform that lets companies create AI-driven voice interviews. Researchers build an interview guide, generate a shareable link, and participants complete the interview in-browser. Responses are transcribed, analysed, and stored. Researchers can then review transcripts, tag quotes, add memos, and generate AI analysis reports.

**Stack:**
- **Backend:** FastAPI (Python) + SQLAlchemy + PostgreSQL (prod) / SQLite (dev), JWT auth
- **Frontend:** React 18 + Vite + TypeScript
- **AI:** Claude (`claude-sonnet-4-20250514`) for adaptive interview orchestration + analysis
- **STT:** OpenAI Whisper (`whisper-1`)
- **TTS:** OpenAI TTS (`tts-1`, voice: `alloy`)
- **Infra:** GCP Cloud Run (auto-scaling), Neon PostgreSQL, Cloudflare R2 (audio storage)

## Repository Layout
```
auto-interview/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, CORS, health checks, security headers
│   │   ├── config.py            # Settings (reads .env), APP_BASE_URL
│   │   ├── database.py          # SQLAlchemy engine + session
│   │   ├── dependencies.py      # get_db, get_current_company (JWT)
│   │   ├── limiter.py           # SlowAPI rate limiter instance
│   │   ├── logging_config.py    # JSON structured logging
│   │   ├── models/
│   │   │   ├── __init__.py      # Registers all models for create_all
│   │   │   ├── company.py       # Company + EmailVerificationToken + PasswordResetToken
│   │   │   ├── project.py       # Project + InterviewGuideQuestion + ScreeningQuestion
│   │   │   ├── interview.py     # InterviewLink + Participant + InterviewTurn + ProjectAnalysis + AnalysisThemeAnnotation
│   │   │   ├── coding.py        # ManualCode + QuoteTag (researcher codebook)
│   │   │   ├── memo.py          # ProjectMemo
│   │   │   ├── affiliate.py     # Affiliate + AffiliateReferral + AffiliatePayout
│   │   │   ├── usage.py         # AIUsageLog (cost tracking for Claude, Whisper, TTS)
│   │   │   ├── panel.py         # PanelProfile + PanelTag + ParticipantMagicToken
│   │   │   └── blog.py          # BlogPost (CMS for /blog)
│   │   ├── routers/
│   │   │   ├── auth.py          # /auth/signup, login, verify-email, resend, onboarding, password reset
│   │   │   ├── projects.py      # /projects CRUD, CSV import (feature-gated)
│   │   │   ├── links.py         # /projects/{id}/links (feature-gated per tier)
│   │   │   ├── interview.py     # /interview/{token} public endpoints + screening
│   │   │   ├── analysis.py      # AI synthesis, versioning, annotations, sharing (feature-gated)
│   │   │   ├── export.py        # CSV export, AI quality assessment (feature-gated)
│   │   │   ├── coding.py        # Manual codes + quote tags
│   │   │   ├── memos.py         # Project memos CRUD
│   │   │   ├── responses.py     # Transcript editing
│   │   │   ├── billing.py       # Stripe webhook + subscription tiers
│   │   │   ├── research_assistant.py  # AI brief parsing, suggestions
│   │   │   ├── affiliate.py     # Affiliate program (apply, login, dashboard, admin)
│   │   │   ├── admin.py         # Admin panel (users, stats, costs, tier management)
│   │   │   ├── blog.py          # Blog public + admin CRUD (TipTap HTML content)
│   │   │   └── audio.py         # Audio file serving
│   │   ├── schemas/
│   │   │   ├── auth.py          # SignupRequest, CompanyResponse, OnboardingProfileRequest
│   │   │   ├── project.py       # Pydantic schemas for project + screening questions
│   │   │   └── interview.py     # StartInterviewRequest (with demographics), responses
│   │   └── services/
│   │       ├── interview_engine.py  # Core AI orchestration (Claude)
│   │       ├── analysis.py          # AI synthesis + refined analysis
│   │       ├── quality.py           # Heuristic quality scoring
│   │       ├── feature_gates.py     # Tier-based feature + limit enforcement
│   │       ├── auth.py              # JWT + bcrypt helpers
│   │       ├── email.py             # SendGrid + dev console fallback
│   │       ├── stt.py               # Whisper transcription
│   │       ├── tts.py               # OpenAI TTS generation
│   │       ├── storage.py           # Audio: Cloudflare R2 or local disk
│   │       ├── guide_parser.py      # CSV import parser
│   │       └── usage_logger.py      # Fire-and-forget AI cost logging (Claude/Whisper/TTS)
│   ├── alembic/
│   │   └── versions/
│   │       ├── 0001_add_researcher_features.py
│   │       ├── 0002_iterative_analysis.py
│   │       ├── 0003_email_verification.py
│   │       ├── 0004_company_onboarding_fields.py
│   │       ├── 0005_enhanced_onboarding.py
│   │       ├── 0006_ai_usage_log.py
│   │       ├── 0007_participant_panel.py
│   │       ├── 0008_affiliate_program.py
│   │       └── 0009_blog_posts.py
│   ├── tests/
│   │   ├── conftest.py          # SQLite in-memory fixtures, rate limiter disabled
│   │   ├── test_auth.py         # Signup, login, refresh, email verification, password reset
│   │   ├── test_projects.py     # CRUD, auth isolation, archive, tier limits
│   │   └── test_feature_gates.py # All tier limits + feature gates
│   ├── Dockerfile               # Python 3.11, runs alembic + uvicorn
│   ├── pytest.ini
│   ├── requirements.txt
│   └── .env                     # NOT in git — contains API keys
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   ├── client.ts        # Axios instance (injects Authorization, auto-refresh on 401)
│   │   │   ├── auth.ts          # login, register, refreshToken, onboarding, email verification
│   │   │   ├── projects.ts      # projects CRUD, links, participants, analysis, codes, tags, memos, export
│   │   │   ├── interviews.ts    # getInterviewInfo, getScreeningQuestions, submitScreening, startInterview, submitAudio
│   │   │   ├── research.ts      # AI brief parsing, objective/scope/question suggestions
│   │   │   └── blog.ts          # Blog API (public listing + admin CRUD)
│   │   ├── hooks/
│   │   │   ├── useAuth.ts       # JWT auth state
│   │   │   └── useAudioRecorder.ts  # Safari-compatible MediaRecorder
│   │   ├── utils/
│   │   │   └── errorMessages.ts # Centralized Axios error extraction
│   │   ├── pages/
│   │   │   ├── Login.tsx
│   │   │   ├── Signup.tsx
│   │   │   ├── ForgotPassword.tsx
│   │   │   ├── ResetPassword.tsx
│   │   │   ├── Welcome.tsx           # 4-step onboarding (verify email → profile → use case → ready)
│   │   │   ├── VerifyEmail.tsx       # Token-based email verification page
│   │   │   ├── Terms.tsx             # Terms of Service
│   │   │   ├── Privacy.tsx           # Privacy Policy (GDPR-compliant)
│   │   │   ├── Dashboard.tsx         # Project list + archive + getting-started + trial banner
│   │   │   ├── CreateProjectWizard.tsx  # 4-step wizard (Brief → Objective → Scope → Questionnaire)
│   │   │   ├── ProjectDetail.tsx     # 4-tab detail view (Overview / Setup / Responses / Analysis)
│   │   │   ├── Interview.tsx         # Participant-facing interview (full flow)
│   │   │   ├── AccountSettings.tsx   # Profile + billing
│   │   │   ├── SharedReport.tsx      # Public read-only analysis
│   │   │   ├── Marketing.tsx         # Landing page + pricing
│   │   │   ├── Admin.tsx            # Admin panel (users, affiliates, stats, costs)
│   │   │   ├── AffiliatePortal.tsx  # Affiliate apply / login / dashboard
│   │   │   ├── Blog.tsx            # Public blog listing (/blog)
│   │   │   ├── BlogPost.tsx        # Public article page (/blog/:slug) with SEO
│   │   │   └── AdminBlog.tsx       # Blog editor tab in admin (TipTap + live preview)
│   │   ├── components/
│   │   │   ├── Toast.tsx        # Toast notification system
│   │   │   ├── Skeleton.tsx     # Loading placeholders
│   │   │   └── ErrorBoundary.tsx
│   │   ├── index.css            # Design system (CSS custom properties, no framework)
│   │   ├── Marketing.css
│   │   └── main.tsx
│   ├── Dockerfile               # Multi-stage: Node build → nginx serve
│   ├── nginx.conf               # Local docker-compose (proxy to backend:8000)
│   ├── nginx.conf.template      # Cloud Run (envsubst injects BACKEND_URL at startup)
│   ├── vite.config.ts           # Proxy: /api → localhost:8000 (strips /api prefix)
│   └── package.json
├── deploy/
│   ├── gcp-setup.sh             # One-time GCP infrastructure setup
│   └── deploy.sh                # Manual build + deploy to Cloud Run
├── .github/
│   └── workflows/
│       └── ci.yml               # Backend tests (pytest + postgres) + frontend (tsc + build)
├── cloudbuild.yaml              # GCP Cloud Build — auto-deploy on push to main
├── docker-compose.yml           # Local dev: postgres + backend + frontend
├── .env.example                 # All required env vars documented
└── CLAUDE.md                    # This file
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

---

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

### Running Tests
```bash
cd backend
DATABASE_URL="sqlite:///:memory:" SECRET_KEY="test-secret" \
  ANTHROPIC_API_KEY="" OPENAI_API_KEY="" \
  python -m pytest tests/ -v
```
- 57 tests covering auth, email verification, projects CRUD, and all feature gates
- Rate limiter is disabled in tests (see `tests/conftest.py`)
- Uses in-memory SQLite with `StaticPool` for full test isolation

### Docker Compose (local)
```bash
# Full stack with PostgreSQL
docker-compose up --build
# Open: http://localhost
```

---

## Environment Variables

### Backend (`backend/.env`)
```
# Core (required)
DATABASE_URL=sqlite:///./auto_interview.db    # PostgreSQL in production
SECRET_KEY=change-me-to-a-random-string
ENVIRONMENT=development                        # development | staging | production
APP_BASE_URL=http://localhost:5173             # For email verification links

# AI (required for interview + analysis)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Storage
UPLOAD_DIR=./uploads
MAX_AUDIO_SIZE_MB=50

# CORS
ALLOWED_ORIGINS=*                              # Comma-separated in production

# Email (SendGrid — falls back to console logging if not set)
SENDGRID_API_KEY=
EMAIL_FROM=noreply@qualipulse.com

# Stripe (optional — billing disabled without these)
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_STARTER=
STRIPE_PRICE_PRO=

# Sentry (optional)
SENTRY_DSN=

# Cloudflare R2 (optional — local disk used if not set)
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET=
R2_PUBLIC_URL=

# Rate limits
RATE_LIMIT_PUBLIC=60/minute
RATE_LIMIT_AUTH=10/minute
RATE_LIMIT_DEFAULT=120/minute

# Admin
ADMIN_SECRET_KEY=                              # Required for /admin and /affiliates/admin endpoints
```

See `.env.example` at repo root for Docker/production template.

---

## Key Architectural Notes

### API Routing
- Frontend calls `/api/...` → Vite proxy strips `/api` → FastAPI receives plain paths
- In production: nginx in the frontend container proxies `/api/` → backend Cloud Run service
- Auth: `/auth/signup`, `/auth/login`, `/auth/verify-email`, `/auth/resend-verification`
- Projects: `/projects/` (trailing slash required — redirects drop auth header)
- Interview (public, no auth): `/interview/{token}`, `/interview/{token}/screening-questions`, `/interview/{token}/screen`, `/interview/{token}/start`, `/interview/{token}/{participant_id}/respond`
- Research: `/projects/{id}/codes`, `/projects/{id}/tags`, `/projects/{id}/memos`, `/projects/{id}/analysis`, `/projects/{id}/export`, `/projects/{id}/participants/{pid}/transcript`
- Affiliate (public + affiliate JWT): `/affiliates/apply`, `/affiliates/login`, `/affiliates/me`, `/affiliates/admin/*`
- Admin (X-Admin-Key header): `/admin/users`, `/admin/stats`, `/admin/costs`, `/admin/blog`
- Blog (public): `/blog/posts`, `/blog/posts/:slug`
- Health checks: `GET /` (shallow), `GET /health` (deep — verifies DB connection)

### Database
- **Dev:** SQLite, auto-created via `Base.metadata.create_all()` on startup
- **Production:** PostgreSQL (Neon or Cloud SQL). Set `DATABASE_URL` to `postgresql://...`
- Alembic migrations run on startup in Docker (`alembic upgrade head`)
- Datetime: use `datetime.utcnow()` (SQLite stores naive UTC — `datetime.now(timezone.utc)` causes issues)

### Feature Gates (Subscription Tiers)
Enforced on all create endpoints. Defined in `services/feature_gates.py`.

Canonical tier names: `starter`, `team`, `lab`, `enterprise`.
Legacy aliases still work in DB: `free` → starter, `solo` → starter, `pro` → lab.

| Gate | Starter (€49) | Team (€99) | Lab (€199) | Enterprise |
|---|---|---|---|---|
| Projects | 1 | 5 | Unlimited | Unlimited |
| Participants/project | 10 | 50 | 500 | Unlimited |
| Questions/guide | 10 | 15 | 30 | Unlimited |
| Interview links/project | 2 | 3 | 10 | Unlimited |
| AI Analysis | Yes | Yes | Yes | Yes |
| CSV Export | No | Yes | Yes | Yes |
| Custom Branding | No | No | Yes | Yes |
| Team Members | 1 | 3 | 10 | Unlimited |

**14-day trial:** New signups on Starter tier get `trial_ends_at` set 14 days ahead.
While trial is active, `get_effective_limits()` returns Team-level limits.
After trial expires, limits revert to Starter.

**Where gates are enforced:**
- `projects.py` → `create_project`, `import_project_from_csv` (project limit + question limit)
- `links.py` → `create_link` (link limit per project)
- `interview.py` → `start_interview_session` (participant limit)
- `analysis.py` → `trigger_analysis`, `trigger_refined_analysis` (ai_analysis feature)
- `export.py` → `export_transcripts_csv` (export_csv feature), `ai_quality_assessment` (ai_analysis)

### Onboarding Flow
After signup, users are redirected to `/welcome` (4-step onboarding):
1. **Email verification** — click link in email (auto-skipped if already verified)
2. **Company profile** — team size, role, industry (intermediate save via `PATCH /auth/onboarding`)
3. **Use case** — what they'll use the platform for (completes via `POST /auth/onboarding`, sets `onboarding_completed = true`)
4. **Ready** — trial info, CTA to dashboard

Login checks `onboarding_completed` — if false, redirects to `/welcome` instead of `/dashboard`.

### Email Verification
- On signup: `EmailVerificationToken` created (24h expiry), verification + welcome emails sent
- `POST /auth/verify-email?token=...` marks `email_verified = True`
- `POST /auth/resend-verification` (rate-limited 3/min, requires auth)
- `email_verified` exposed in `GET /auth/me` response (CompanyResponse)
- Non-blocking: users can log in and use the app without verifying (frontend shows yellow banner)

### Email Service
- **Provider:** SendGrid (domain-authenticated for `qualipulse.com`)
- **Fallback:** Console logging when `SENDGRID_API_KEY` is not set
- **From:** `noreply@qualipulse.com` (QualiPulse)
- **Templates** (all in `services/email.py` with branded HTML wrapper):
  - `send_welcome` — after signup
  - `send_verification_email` — email verification link (24h)
  - `send_password_reset` — password reset link (1h)
  - `send_analysis_ready` — when AI analysis completes
  - `send_interview_invite` — (template exists, not yet wired to an endpoint)
  - `send_newsletter_welcome` — newsletter subscription
- **DNS records** (Namecheap): em9375 CNAME, s1/s2._domainkey CNAME, _dmarc TXT

### Authentication & Security
- JWT access tokens (24h expiry) + refresh tokens (30d expiry), HS256
- Auto-refresh on 401 via Axios interceptor (`client.ts`)
- Bcrypt password hashing (min 8 chars)
- Rate limiting: 10/min on auth, 60/min on public, 120/min on authenticated
- Security headers: X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy, HSTS (production)
- CORS configurable via `ALLOWED_ORIGINS`
- Audio endpoint: directory traversal protection

### Audio Recording (Safari Compatibility)
- `MediaRecorder.start(250)` — timeslice fires `ondataavailable` every 250ms
- MIME type priority: `audio/webm;codecs=opus` → `audio/webm` → `audio/mp4` (Safari) → `audio/ogg`
- File named `recording.{ext}` to help backend/FFmpeg detect format

### Interview Flow (Participant)
```
Landing (name + profession + age_range + country + email)
  → Consent (decline → thank-you, no record)
  → Mic test (AudioContext level meter)
  → fetch /screening-questions
  → Has questions? → Screening phase (one at a time, back button)
      → POST /screen → qualified? → create participant → Interview
                     → disqualified? → "Thank you" screen
  → No questions? → create participant → Interview starts immediately
  → Interview: record → STT → Claude → TTS → repeat
  → Completion screen (personalized)
```
- Participant record is only created **after** passing screening (or if no screening)
- Demographics (profession, age_range, country) power the segment heatmap in Analysis
- Session-storage resume (same device) + email-based resume (cross-device)

### Claude Interview Engine
Claude decides after each response whether to:
- `follow_up` — ask a follow-up on the current topic
- `next_question` — move to the next guide question
- `close` — wrap up warmly when all questions are covered or time is up

Pacing safety guards:
- Forces `next_question` if behind schedule
- Close gate: requires 80% time elapsed + all questions covered
- System prompt customizable per project

### Analysis Pipeline
1. Researcher triggers analysis (optional demographic filters)
2. Background thread builds transcript blocks → calls Claude
3. Claude returns structured JSON: themes, JTBDs, tensions, recommendations, confidence scores
4. Versioned (keeps 5 most recent), can be filtered by segment
5. Researcher can annotate themes (confirmed/disputed/needs_evidence) + add context
6. Refined analysis incorporates annotations and re-analyzes with feedback
7. Shareable via public token (read-only report page)

### Screening Questions
- Stored in `screening_questions` table, linked to `projects`
- Each question has `options` (JSON array) and `disqualifying_options` (JSON array subset)
- Accessed via `options_list` / `disqualifying_options_list` properties (JSON parsed)
- Managed in Setup tab → inline editor (collapse/expand per question, toggle disqualifying per option)
- Also configurable in wizard Step 3 (Scope)

### Legacy Project Compatibility
- Older projects may not have `screening_questions` in the API response → always guard with `?? []`
- Example: `(project.screening_questions ?? []).map(...)` — never access `.length` or `.map()` directly

---

## Production Deployment (GCP Cloud Run)

### Live URLs
- **Frontend:** https://app.qualipulse.com
- **Backend API:** https://api.qualipulse.com
- **Direct Cloud Run (frontend):** https://auto-interview-web-488573636859.europe-west1.run.app
- **Direct Cloud Run (backend):** https://auto-interview-api-488573636859.europe-west1.run.app

### Architecture
```
               Namecheap DNS (CNAME → ghs.googlehosted.com)
                         │
               ┌─────────┴─────────┐
               │                   │
         app.qualipulse.com  api.qualipulse.com
               │                   │
       ┌───────┴───────┐   ┌───────┴───────┐
       │  Cloud Run    │   │  Cloud Run    │
       │  (frontend)   │──▶│  (backend)    │
       │  nginx + SPA  │   │  FastAPI      │
       │  0-5 instances│   │  0-10 inst.   │
       └───────────────┘   └───────┬───────┘
                                   │
                   ┌───────────────┼───────────────┐
                   │               │               │
              ┌────┴────┐   ┌─────┴──────┐  ┌─────┴─────┐
              │  Neon   │   │ Cloudflare │  │  Secret   │
              │ Postgres│   │    R2      │  │  Manager  │
              │ AWS     │   │  (audio)   │  │  (keys)   │
              │Frankfurt│   │            │  │           │
              └─────────┘   └────────────┘  └───────────┘
```

### GCP Project & Region
- **Project ID:** `qualipulse-prod`
- **Project Number:** `488573636859`
- **Region:** `europe-west1` (Belgium)
- **Domain registrar:** Namecheap (`qualipulse.com`)
- **Domain verified via:** Google Search Console (TXT record)

### Why This Stack
- **Cloud Run**: True auto-scaling (0→N instances per demand), scale-to-zero = $0 idle cost. Each interview turn is request-response — Cloud Run's sweet spot.
- **Neon PostgreSQL**: Serverless Postgres, free tier, auto-scales, point-in-time recovery. Standard Postgres — code works unchanged. Hosted on AWS Frankfurt (eu-central-1) — 5-10ms cross-cloud latency, negligible vs 2-4s AI API calls.
- **Cloudflare R2**: S3-compatible (existing boto3 code works), no egress fees, encrypted at rest. 5x cheaper than S3.
- **Secret Manager**: No .env files in production. Secrets injected at deploy time.

### GCP Services Enabled
- `run.googleapis.com` — Cloud Run
- `cloudbuild.googleapis.com` — Cloud Build
- `artifactregistry.googleapis.com` — Artifact Registry (Docker images)
- `secretmanager.googleapis.com` — Secret Manager

### Artifact Registry
- **Repository:** `europe-west1-docker.pkg.dev/qualipulse-prod/auto-interview`
- Backend image: `auto-interview-backend:{tag}`
- Frontend image: `auto-interview-frontend:{tag}`

### Secrets in Secret Manager
| Secret Name | Description |
|---|---|
| `secret-key` | JWT signing key (64-char random) |
| `database-url` | Neon PostgreSQL connection string |
| `anthropic-api-key` | Anthropic API key for Claude |
| `openai-api-key` | OpenAI API key for Whisper + TTS |
| `sendgrid-api-key` | SendGrid API key (domain-authenticated for qualipulse.com) |

### IAM Service Accounts
| Service Account | Roles |
|---|---|
| `488573636859-compute@developer.gserviceaccount.com` | `secretmanager.secretAccessor`, `cloudbuild.builds.builder`, `artifactregistry.writer`, `run.admin`, `logging.logWriter` |
| `488573636859@cloudbuild.gserviceaccount.com` | `run.admin`, `iam.serviceAccountUser` |
| `service-488573636859@gcp-sa-cloudbuild.iam.gserviceaccount.com` | `secretmanager.admin` (for GitHub connection) |

### DNS Records (Namecheap → Advanced DNS)
| Type | Host | Value | Purpose |
|---|---|---|---|
| TXT | `@` | `google-site-verification=tYJKv4GNO3cuAYHv...` | Domain verification |
| CNAME | `app` | `ghs.googlehosted.com.` | Frontend → Cloud Run |
| CNAME | `api` | `ghs.googlehosted.com.` | Backend → Cloud Run |
| CNAME | `em9375` | `u77457076.wl077.sendgrid.net.` | SendGrid domain auth |
| CNAME | `s1._domainkey` | `s1.domainkey.u77457076.wl077.sendgrid.net.` | DKIM signing |
| CNAME | `s2._domainkey` | `s2.domainkey.u77457076.wl077.sendgrid.net.` | DKIM signing |
| TXT | `_dmarc` | `v=DMARC1; p=none;` | DMARC policy |

SSL certificates are auto-provisioned by Google after DNS propagation.

### Deploy Commands
```bash
# One-time setup (enables APIs, creates Artifact Registry, configures secrets)
./deploy/gcp-setup.sh qualipulse-prod europe-west1

# Manual deploy — build locally and push to Cloud Run
# (requires Docker installed locally)
./deploy/deploy.sh qualipulse-prod europe-west1

# Manual deploy without local Docker — build on Cloud Build
REGION="europe-west1"
REGISTRY="${REGION}-docker.pkg.dev/qualipulse-prod/auto-interview"
TAG=$(git rev-parse --short HEAD)

# Build images remotely
gcloud builds submit --tag="${REGISTRY}/auto-interview-backend:${TAG}" ./backend --region=${REGION}
gcloud builds submit --tag="${REGISTRY}/auto-interview-frontend:${TAG}" ./frontend --region=${REGION}

# Deploy backend
gcloud run deploy auto-interview-api \
  --image="${REGISTRY}/auto-interview-backend:${TAG}" \
  --region=${REGION} --platform=managed --allow-unauthenticated \
  --port=8080 --cpu=1 --memory=512Mi --min-instances=0 --max-instances=10 \
  --timeout=300s --concurrency=80 \
  --set-secrets="SECRET_KEY=secret-key:latest,ANTHROPIC_API_KEY=anthropic-api-key:latest,OPENAI_API_KEY=openai-api-key:latest,DATABASE_URL=database-url:latest,SENDGRID_API_KEY=sendgrid-api-key:latest" \
  --set-env-vars="ENVIRONMENT=production,UPLOAD_DIR=/tmp/uploads,ALLOWED_ORIGINS=https://app.qualipulse.com,APP_BASE_URL=https://app.qualipulse.com"

# Deploy frontend (get backend URL first)
BACKEND_URL=$(gcloud run services describe auto-interview-api --region=${REGION} --format='value(status.url)')
BACKEND_HOST=$(echo "${BACKEND_URL}" | sed 's|https://||')
gcloud run deploy auto-interview-web \
  --image="${REGISTRY}/auto-interview-frontend:${TAG}" \
  --region=${REGION} --platform=managed --allow-unauthenticated \
  --port=8080 --cpu=1 --memory=256Mi --min-instances=0 --max-instances=5 \
  --concurrency=200 \
  --set-env-vars="BACKEND_URL=${BACKEND_URL},BACKEND_HOST=${BACKEND_HOST}"
```

### CI/CD Pipeline
- **GitHub Actions** (`ci.yml`): runs on every PR to `main` — pytest (with postgres service), TypeScript check, build
- **Cloud Build** (`cloudbuild.yaml`): auto-triggered on push to `main` — builds Docker images, pushes to Artifact Registry, deploys to Cloud Run
- **GitHub connection:** `qualipulse-github` (2nd gen, via Cloud Build connections)
- **Repository link:** `qualipulse-repo` → `github.com/Mycorino/qualipulse`
- **Trigger:** `deploy-on-push-to-main` — branch pattern `^main$`, uses `cloudbuild.yaml`
- **Monitor builds:** https://console.cloud.google.com/cloud-build/builds?project=qualipulse-prod
- Frontend nginx.conf.template uses `envsubst` to inject `BACKEND_URL` at container startup

### Backend Startup (start.sh)
The backend container uses `start.sh` which handles both fresh and existing databases:
1. Tries `alembic upgrade head` first (for existing databases with migration history)
2. If migrations fail (fresh database), falls back to `Base.metadata.create_all()` to build all tables from SQLAlchemy models
3. Stamps Alembic version at `head` so future migrations work correctly
4. Starts uvicorn

### Cloud Run Service Config
| Setting | Backend | Frontend |
|---|---|---|
| Service name | `auto-interview-api` | `auto-interview-web` |
| CPU | 1 | 1 |
| Memory | 512Mi | 256Mi |
| Min instances | 0 | 0 |
| Max instances | 10 | 5 |
| Timeout | 300s (for Claude/TTS) | 60s |
| Concurrency | 80 | 200 |
| Port | 8080 | 8080 |
| CORS | `https://app.qualipulse.com` | — |

### Environment Variables (Production)
**Backend (auto-interview-api):**
| Variable | Value | Source |
|---|---|---|
| `ENVIRONMENT` | `production` | env var |
| `UPLOAD_DIR` | `/tmp/uploads` | env var |
| `ALLOWED_ORIGINS` | `https://app.qualipulse.com` | env var |
| `APP_BASE_URL` | `https://app.qualipulse.com` | env var |
| `SECRET_KEY` | (from secret) | Secret Manager |
| `DATABASE_URL` | (from secret) | Secret Manager |
| `ANTHROPIC_API_KEY` | (from secret) | Secret Manager |
| `OPENAI_API_KEY` | (from secret) | Secret Manager |
| `SENDGRID_API_KEY` | (from secret) | Secret Manager |

**Frontend (auto-interview-web):**
| Variable | Value |
|---|---|
| `BACKEND_URL` | `https://auto-interview-api-488573636859.europe-west1.run.app` |
| `BACKEND_HOST` | `auto-interview-api-488573636859.europe-west1.run.app` |

### Estimated Monthly Cost
| Component | Idle | 50 interviews/mo | 500 interviews/mo |
|---|---|---|---|
| Cloud Run | $0 | ~$7 | ~$50 |
| Neon Postgres | $0 | $0 | ~$19 |
| Cloudflare R2 | $0 | ~$1 | ~$5 |
| SendGrid | $0 | $0 | $0 |
| Sentry | $0 | $0 | $0 |
| **AI APIs** | $0 | **~$25** | **~$250** |
| **Total** | **$0** | **~$33** | **~$324** |

### Custom Domain Setup (Already Done)
```bash
# 1. Verify domain in Google Search Console (add TXT record on Namecheap)
# 2. Create domain mappings
gcloud beta run domain-mappings create --service=auto-interview-web --domain=app.qualipulse.com --region=europe-west1
gcloud beta run domain-mappings create --service=auto-interview-api --domain=api.qualipulse.com --region=europe-west1
# 3. Add CNAME records on Namecheap: app → ghs.googlehosted.com, api → ghs.googlehosted.com
# 4. SSL certificates auto-provisioned by Google (5-15 min)
```

### Updating Secrets
```bash
# Example: update the database URL
echo -n 'postgresql://new-connection-string' | \
  gcloud secrets versions add database-url --data-file=-

# Redeploy to pick up new secret version (or use :latest which auto-updates)
gcloud run services update auto-interview-api --region=europe-west1 \
  --set-secrets="DATABASE_URL=database-url:latest"
```

### Useful Commands
```bash
# Check service status
gcloud run services list --region=europe-west1

# View logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=auto-interview-api" --limit=50 --project=qualipulse-prod

# Check domain mapping status
gcloud beta run domain-mappings describe --domain=app.qualipulse.com --region=europe-west1

# List Cloud Build triggers
gcloud builds triggers list --region=europe-west1

# View recent builds
gcloud builds list --region=europe-west1 --limit=5
```

---

## Feature Status

### Researcher (Company) Side
- [x] Signup / login (JWT) with refresh token + auto-refresh on 401
- [x] Email verification on signup (token-based, 24h expiry, resend endpoint)
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
- [x] Iterative analysis (annotate themes as confirmed/disputed/needs_evidence → refine)
- [x] Analysis versioning (keeps 5 most recent, version lineage tracking)
- [x] Shareable analysis reports (public token, read-only page)
- [x] Project memos (general, theme/JTBD/tension-linked) with full CRUD
- [x] Segment heatmap (profession / age_range / country vs themes)
- [x] AI quality assessment per participant (Claude-scored, structured result)
- [x] Export CSV (participants + all transcript turns, streaming response)
- [x] Account & billing settings page (Profile tab + Plan & Billing tab)
- [x] Subscription tier model with **enforced** feature gates (solo/team/lab/enterprise)
- [x] 14-day trial: solo users get team-level limits, auto-set on signup
- [x] Stripe Checkout + Customer Portal + webhook handler (needs Stripe keys)
- [x] Profile save + change password in AccountSettings UI (PATCH /auth/me, POST /auth/change-password)
- [x] Analysis-ready email (triggered after AI synthesis completes)
- [x] Feature gates enforced on: projects, questions, links, analysis, export
- [x] Multi-step onboarding flow (Welcome page: verify email → profile → use case → ready)
- [x] Centralized error messages (frontend `utils/errorMessages.ts`)
- [x] Terms of Service + Privacy Policy pages
- [x] SendGrid email integration (domain-authenticated, branded HTML templates)
- [x] Getting-started checklist on empty dashboard
- [x] Trial banner on dashboard (visible to solo/free users with active trial)
- [x] Email verification banner (yellow) when unverified
- [x] Admin panel (user management, tier changes, trial management, user deletion)
- [x] Admin stats dashboard (users, tiers, interviews, signups over 7/30 days)
- [x] Admin AI cost reporting (platform-wide + per-company breakdown)
- [x] Affiliate program (apply, login, dashboard, referral tracking, commission calculation)
- [x] Affiliate admin management (approve/reject, commission %, payout recording)
- [x] Stripe webhook affiliate conversion tracking (commission on subscription)
- [x] AI usage tracking (Claude tokens, Whisper seconds, TTS characters → cost_usd)
- [x] Research participant panel (PanelProfile, PanelTag, magic link auth)
- [x] Blog CMS (TipTap WYSIWYG editor, live preview, draft/publish, SEO meta + OG tags)
- [x] Public blog listing (/blog) + article pages (/blog/:slug) with newsletter CTA
- [x] Blog admin tab (create, edit, delete posts, status filter)
- [x] UX audit fixes (82 items): dark mode for marketing/auth, CSS variable cleanup (~50 hardcoded hex→vars), password show/hide + strength indicator, focus-visible outlines, ARIA labels + keyboard nav, sticky TOC on Terms/Privacy, responsive analysis toolbar, 44px touch targets, interview profiling card styling
- [x] EN/FR i18n foundation: react-i18next with namespaced JSON files (`frontend/src/locales/{en,fr}/`) covering marketing, auth, dashboard, project, interview, analysis, settings, affiliate, common
- [x] LanguageSwitcher component (`components/LanguageSwitcher.tsx`): pill-shaped toggle, light/dark variant prop, 44px WCAG touch target, shown in marketing nav and dashboard sidebar
- [x] Marketing page fully translated (EN/FR): all hardcoded strings replaced with `t()` calls including hero widget, output preview section, who-it's-for, differentiator, trust quote
- [ ] Usage counters enforcement (`interview_count`, `storage_bytes` fields exist, not yet incremented)
- [ ] Email invitation sending (template exists, no send endpoint)
- [ ] Multi-language TTS voices (language field exists on projects)
- [ ] Dashboard-level analytics across projects
- [ ] Team collaboration (multi-user, invitations, roles, audit trail)

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
- [ ] Text input fallback (accessibility)
- [ ] Multi-language support

### Infrastructure & DevOps
- [x] Docker: backend + frontend Dockerfiles, docker-compose.yml with PostgreSQL
- [x] GCP Cloud Run: cloudbuild.yaml, deploy scripts, nginx envsubst for backend URL
- [x] CI/CD: GitHub Actions (pytest + tsc + build), Cloud Build (auto-deploy on push)
- [x] Health checks: `GET /` (shallow) + `GET /health` (deep, DB-aware)
- [x] Secret Manager integration (secrets injected at deploy, not in .env)
- [x] Test suite: 57 tests (auth, email verification, feature gates, project CRUD)
- [x] Rate limiting (SlowAPI): public/auth/default tiers
- [x] Security headers middleware
- [x] JSON structured logging (python-json-logger)
- [x] Sentry integration (optional, configurable via SENTRY_DSN)
- [x] Alembic migrations (9 versions)
- [x] SendGrid email delivery (domain-authenticated, 6 email templates)
- [ ] GDPR tooling (data export, participant deletion)
- [ ] Prometheus metrics / APM dashboards
- [ ] Automated DB backups (Neon handles this for production)

---

## Data Models Summary

### Company (auth)
`id`, `name`, `email`, `password_hash`, `email_verified`, `company_size`, `role`, `industry`, `use_case`, `onboarding_completed`, `subscription_tier` (solo/team/lab/enterprise), `subscription_status`, `stripe_customer_id`, `stripe_subscription_id`, `trial_ends_at`, `interview_count`, `storage_bytes`, `created_at`

### Project
`id`, `company_id`, `name`, `language`, `interview_duration_minutes`, `system_prompt`, `welcome_message`, `research_objective`, `researcher_name`, `researcher_logo_url`, `research_context`, `privacy_policy_url`, `created_at`, `archived_at`

### InterviewGuideQuestion
`id`, `project_id`, `section_index`, `section_title`, `question_index`, `main_question`, `interview_notes`, `desired_learning`, `researcher_notes`, `deprecated_at`, `sort_order`

### ScreeningQuestion
`id`, `project_id`, `question`, `options` (JSON), `disqualifying_options` (JSON), `sort_order`

### InterviewLink
`id`, `project_id`, `token` (unique, urlsafe), `is_active`, `created_at`

### Participant
`id`, `link_id`, `project_id`, `display_name`, `email`, `profession`, `age_range`, `country`, `status` (in_progress/completed), `quality_score`, `quality_label`, `started_at`, `completed_at`

### InterviewTurn
`id`, `participant_id`, `turn_index`, `question_index`, `is_follow_up`, `follow_up_index`, `question_text`, `response_transcript`, `audio_recording_url`, `tts_audio_url`, `manually_edited`, `edited_at`, `created_at`

### ProjectAnalysis
`id`, `project_id`, `version`, `status` (generating/ready/failed), `participant_count`, `report` (JSON), `filters` (JSON), `researcher_context`, `version_label` (ai_discovery/researcher_refined), `parent_version_id`, `share_token`, `generated_at`, `error`

### AnalysisThemeAnnotation
`id`, `analysis_id`, `theme_title`, `status` (confirmed/disputed/needs_evidence), `researcher_note`, unique on (analysis_id, theme_title)

### ManualCode
`id`, `project_id`, `name`, `color` (hex), `sort_order`, `created_at`

### QuoteTag
`id`, `turn_id`, `code_id`, `selected_text`, `start_index`, `end_index`, `created_by`, `created_at`

### ProjectMemo
`id`, `project_id`, `type` (general/theme_note/tension_note/jtbd_note), `linked_key`, `content`, `created_by`, `created_at`, `updated_at`

### EmailVerificationToken
`id`, `company_id`, `token` (unique, urlsafe), `used`, `expires_at`, `created_at`

### PasswordResetToken
`id`, `company_id`, `token` (unique, urlsafe), `used`, `expires_at`, `created_at`

### Affiliate
`id` (str), `company_id` (FK), `name`, `email` (unique), `code` (unique), `website`, `how_they_found_us`, `commission_pct` (default 20%), `status` (pending/active/rejected), `payout_threshold` (default $50), `total_earned`, `total_paid`, `created_at`, `approved_at`, `notes`

### AffiliateReferral
`id` (str), `affiliate_id` (FK), `referred_company_id` (FK, unique), `signed_up_at`, `converted_at`, `commission_amount`, `status` (signed_up/converted/paid)

### AffiliatePayout
`id` (str), `affiliate_id` (FK), `amount`, `paid_at`, `notes`

### AIUsageLog
`id` (int), `company_id` (FK), `project_id` (FK), `participant_id` (FK), `operation` (indexed), `model`, `input_tokens`, `output_tokens`, `characters` (TTS), `audio_seconds` (STT), `cost_usd`, `created_at` (indexed)

### PanelProfile
`id` (int), `email` (unique), `first_name`, `age_range`, `gender`, `country`, `city`, `education`, `employment_status`, `job_function`, `seniority`, `industry`, `company_size`, `panel_consent`, `consent_at`, `consent_interview_token`, `interviews_completed`, `last_active`, `created_at`

### PanelTag
`id`, `name` (unique), `category` (interest/behavior/consumer)

### ParticipantMagicToken
`id`, `email` (indexed), `token` (unique, indexed), `interview_link_token`, `used`, `expires_at`, `created_at`

### BlogPost
`id` (str), `slug` (unique, indexed), `title`, `subtitle`, `content` (HTML from TipTap), `excerpt`, `cover_image_url`, `meta_title`, `meta_description`, `og_image_url`, `author_name`, `tags` (JSON text), `status` (draft/published, indexed), `published_at`, `created_at`, `updated_at`

---

## API Endpoints Reference

### Auth (`/auth`)
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/signup` | No | Create account, send verification + welcome emails, set 14-day trial |
| POST | `/auth/login` | No | Login, get access + refresh tokens |
| POST | `/auth/refresh` | No | Refresh access token |
| POST | `/auth/verify-email?token=` | No | Verify email address |
| POST | `/auth/resend-verification` | Yes | Resend verification email (3/min) |
| POST | `/auth/password-reset/request` | No | Request password reset (always 200) |
| POST | `/auth/password-reset/confirm` | No | Confirm reset with token |
| GET | `/auth/me` | Yes | Get current company profile (includes onboarding fields) |
| PATCH | `/auth/me` | Yes | Update profile (name) |
| POST | `/auth/change-password` | Yes | Change password |
| PATCH | `/auth/onboarding` | Yes | Intermediate onboarding save (profile fields) |
| POST | `/auth/onboarding` | Yes | Complete onboarding (sets `onboarding_completed = true`) |
| POST | `/auth/newsletter` | No | Newsletter subscription (5/min) |

### Projects (`/projects`)
| Method | Path | Auth | Gate | Description |
|---|---|---|---|---|
| POST | `/projects/` | Yes | project_limit + question_limit | Create project |
| POST | `/projects/import` | Yes | project_limit + question_limit | Import from CSV |
| GET | `/projects/` | Yes | — | List projects |
| GET | `/projects/{id}` | Yes | — | Get project details |
| PUT | `/projects/{id}` | Yes | — | Update project + questions |
| PATCH | `/projects/{id}/archive` | Yes | — | Archive project |
| PATCH | `/projects/{id}/unarchive` | Yes | — | Unarchive project |
| PATCH | `/projects/{id}/questions/{qid}` | Yes | — | Edit question metadata |

### Links (`/projects/{id}/links`)
| Method | Path | Auth | Gate | Description |
|---|---|---|---|---|
| POST | `/projects/{id}/links` | Yes | link_limit | Create interview link |
| GET | `/projects/{id}/links` | Yes | — | List links |
| PATCH | `/links/{id}` | Yes | — | Toggle active/inactive |

### Interview (`/interview` — public, no auth)
| Method | Path | Rate Limit | Description |
|---|---|---|---|
| GET | `/interview/{token}` | 60/min | Validate link, get project info |
| GET | `/interview/{token}/screening-questions` | 60/min | Get screening questions |
| POST | `/interview/{token}/screen` | 30/min | Check disqualification |
| GET | `/interview/{token}/resume?email=` | 60/min | Check for in-progress interview |
| GET | `/interview/{token}/{pid}/resume-summary` | — | Covered topics + elapsed time |
| POST | `/interview/{token}/start` | 30/min | Create participant + first question |
| POST | `/interview/{token}/{pid}/respond` | 30/min | Submit audio, get next question |
| POST | `/interview/{token}/{pid}/skip` | — | Skip current question |
| GET | `/interview/{token}/{pid}/status` | — | Interview status |

### Analysis (`/projects/{id}/analysis`)
| Method | Path | Gate | Description |
|---|---|---|---|
| POST | `/projects/{id}/analysis` | ai_analysis | Trigger AI synthesis |
| GET | `/projects/{id}/analysis` | — | Get latest analysis |
| GET | `/projects/{id}/analysis/heatmap` | — | Demographic heatmap |
| GET | `/projects/{id}/analysis/versions` | — | List versions |
| GET | `/projects/{id}/analysis/{version}` | — | Get specific version |
| POST | `/projects/{id}/analysis/annotations` | — | Upsert theme annotation |
| DELETE | `/projects/{id}/analysis/annotations/{id}` | — | Delete annotation |
| GET | `/projects/{id}/analysis/annotations/{id}` | — | List annotations for version |
| PATCH | `/projects/{id}/analysis/{v}/context` | — | Save researcher context |
| POST | `/projects/{id}/analysis/refine` | ai_analysis | Trigger refined analysis |
| POST | `/projects/{id}/analysis/share` | — | Generate share token |
| DELETE | `/projects/{id}/analysis/share` | — | Revoke share token |
| GET | `/reports/{share_token}` | No auth | Public shared report |

### Export & Responses (`/projects/{id}/participants`)
| Method | Path | Gate | Description |
|---|---|---|---|
| GET | `/projects/{id}/participants` | — | List participants |
| GET | `/projects/{id}/participants/{pid}/transcript` | — | Full transcript |
| GET | `/projects/{id}/export` | export_csv | CSV export |
| POST | `/projects/{id}/participants/{pid}/quality` | ai_analysis | AI quality assessment |
| PUT | `/projects/{id}/participants/{pid}/turns/{tid}` | — | Edit transcript turn |

### Coding & Memos
| Method | Path | Description |
|---|---|---|
| GET/POST | `/projects/{id}/codes` | List/create codes |
| PATCH/DELETE | `/projects/{id}/codes/{cid}` | Edit/delete code |
| GET | `/projects/{id}/tags` | List all tags |
| POST | `/projects/{id}/turns/{tid}/tags` | Tag a quote |
| DELETE | `/projects/{id}/tags/{tid}` | Delete tag |
| GET/POST | `/projects/{id}/memos` | List/create memos |
| PUT/DELETE | `/projects/{id}/memos/{mid}` | Update/delete memo |

### Research Assistant (`/research`)
| Method | Path | Description |
|---|---|---|
| POST | `/research/parse-brief` | Parse brief from text + files |
| POST | `/research/suggest-objective` | Generate research objective |
| POST | `/research/suggest-scope` | Recommend audience, duration |
| POST | `/research/suggest-questions` | Generate interview guide |

### Billing (`/billing`)
| Method | Path | Description |
|---|---|---|
| GET | `/billing/plans` | List subscription tiers |
| GET | `/billing/status` | Current subscription |
| POST | `/billing/checkout` | Create Stripe Checkout session |
| POST | `/billing/portal` | Open Stripe Customer Portal |
| POST | `/billing/webhook` | Stripe webhook handler |

### Affiliate (`/affiliates`)
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/affiliates/apply` | No (5/min) | Apply to become affiliate |
| POST | `/affiliates/login` | No (10/min) | Login with email + code |
| GET | `/affiliates/me` | Affiliate JWT | Get affiliate stats & earnings |
| GET | `/affiliates/me/link` | Affiliate JWT | Get shareable referral link |
| GET | `/affiliates/me/referrals` | Affiliate JWT | List referred companies |
| GET | `/affiliates/admin/list` | X-Admin-Key | List all affiliates |
| PATCH | `/affiliates/admin/{id}` | X-Admin-Key | Update status/commission |
| POST | `/affiliates/admin/{id}/payout` | X-Admin-Key | Record payout |

### Blog (`/blog` + `/admin/blog`)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/blog/posts` | No | List published posts (paginated, tag filter) |
| GET | `/blog/posts/:slug` | No | Get published post by slug |
| GET | `/admin/blog` | X-Admin-Key | List all posts (draft + published) |
| GET | `/admin/blog/:id` | X-Admin-Key | Get post by ID |
| POST | `/admin/blog` | X-Admin-Key | Create post |
| PUT | `/admin/blog/:id` | X-Admin-Key | Update post |
| DELETE | `/admin/blog/:id` | X-Admin-Key | Delete post |

### Admin (`/admin`)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/admin/users` | X-Admin-Key | List users (search, tier filter, pagination) |
| GET | `/admin/users/{company_id}` | X-Admin-Key | Get user detail with projects |
| PATCH | `/admin/users/{company_id}/tier` | X-Admin-Key | Change subscription tier |
| PATCH | `/admin/users/{company_id}/trial` | X-Admin-Key | Extend/reset/expire trial |
| DELETE | `/admin/users/{company_id}` | X-Admin-Key | Delete user & cascade all data |
| GET | `/admin/stats` | X-Admin-Key | Platform stats (users, tiers, interviews, signups) |
| GET | `/admin/costs` | X-Admin-Key | Platform-wide AI cost report |
| GET | `/admin/costs/company/{company_id}` | X-Admin-Key | Per-company cost breakdown |

### Health
| Method | Path | Description |
|---|---|---|
| GET | `/` | Shallow health check (status + env) |
| GET | `/health` | Deep health check (verifies DB connection) |
