# Auto-Interview (Qualipulse) — Claude Code Project Guide

## Working Directory
All work for this project lives at: `/Users/corinofontana/Desktop/auto-interview`

## Session Start Checklist (READ FIRST)
**Every Claude Code session must begin from a fresh branch off the current `origin/main`.** The repo uses a lot of parallel worktrees under `.claude/worktrees/` and they accumulate stale state fast — pick up an old one and you'll be coding against a world that doesn't exist anymore. When in doubt, assume your local state is wrong and check `origin/main`, never local `main`.

**At the start of every session, run these four commands before touching anything:**

```bash
cd /Users/corinofontana/Desktop/auto-interview
git fetch origin                        # pull in anything merged since you last looked
git log --oneline origin/main -5        # what's actually on production-ready main?
git rev-list --left-right --count HEAD...origin/main  # am I ahead / behind?
```

If the third command reports `0  N` (zero ahead, N behind), your local branch is stale — you are missing N commits that are on `origin/main`. **Do not start work from a stale branch.** Fast-forward or create a fresh worktree first.

### Good practices for sessions

1. **One task = one worktree off fresh `origin/main`.** Don't reuse a worktree from a previous task — create a new one: `git fetch origin && git worktree add .claude/worktrees/<new-name> -b claude/<task-slug> origin/main`. Stale worktrees are the #1 cause of "it works on my machine but production shows something else."
2. **Trust `origin/main`, not local `main`.** Local `main` is only as fresh as your last `git pull`. When a session asks "what's on main?", the correct answer comes from `git log origin/main`, never `git log main`.
3. **Don't trust `CLAUDE.md` in an old worktree.** This file gets updated alongside features. If your worktree is 40 commits behind, your `CLAUDE.md` is too — cross-check against `git show origin/main:CLAUDE.md` if something looks off.
4. **Re-sync long-running sessions.** If a session runs for more than a few hours while other PRs are merging, periodically `git fetch origin && git merge origin/main` (or rebase) to keep your branch current. Otherwise you'll write code against assumptions that no longer hold.
5. **Before opening a PR**, rebase onto the current `origin/main` one last time: `git fetch origin && git rebase origin/main`. This catches conflicts before CI instead of after.
6. **Delete worktrees when the PR merges.** `git worktree remove .claude/worktrees/<name>` + `git branch -d claude/<name>`. Don't let branches pile up — every dead worktree is a trap for the next session.
7. **Never treat a local worktree's state as authoritative about production.** Production state lives in Cloud Run revisions, which are built from `origin/main`. The only way to know what's live is `gcloud run services describe ...` or `curl https://api.qualipulse.com/`.
8. **If you see dark mode or any other "fixed" issue reappear**, it's almost certainly a stale worktree, not a regression. Check the current branch's commit ancestry for `c1b99fc` (the dark-mode-kill commit) via `git merge-base --is-ancestor c1b99fc HEAD && echo "has kill" || echo "STALE"` before filing a bug.

### Recovering a stale setup
If you realise the main repo or a worktree is behind `origin/main`, the safe recovery is:

```bash
# From an up-to-date worktree (check with git rev-parse origin/main first)
cd <stale-worktree-or-main-repo>
git status                              # see what's dirty
git stash push -u -m "pre-sync"         # preserve uncommitted work (or git reset --hard if writing it off)
git fetch origin
git reset --hard origin/main            # snap to origin/main exactly
```

For bulk recovery of all worktrees at once, the pattern is `for wt in $(git worktree list --porcelain | awk '/^worktree /{print $2}'); do (cd "$wt" && git reset --hard origin/main); done` — skip the worktree you're currently working in.

## Project Overview
A SaaS platform that lets companies create AI-driven voice interviews. Researchers build an interview guide, generate a shareable link, and participants complete the interview in-browser. Responses are transcribed, analysed, and stored. Researchers can then review transcripts, tag quotes, add memos, and generate AI analysis reports.

**Stack:**
- **Backend:** FastAPI (Python) + SQLAlchemy + PostgreSQL (prod) / SQLite (dev), JWT auth
- **Frontend:** React 18 + Vite + TypeScript
- **AI:** all model ids resolve through `services/ai_models.py` (env-overridable pins; see that file for the source of truth)
  - Interview orchestration + analysis + translation etc.: Claude Sonnet (`claude-sonnet-4-6`)
  - Research Copilot (survey + interview-guide surfaces): Claude **Opus** (`claude-opus-4-8`) with adaptive thinking (`thinking: {type: "adaptive"}`), `output_config: {effort: "high"}`, and a split system prompt: stable base+methodology block behind the prompt-cache breakpoint, volatile memory+snapshot block after it, plus a cache marker on the message tail per agent-loop iteration
  - Lightweight tasks (transcript cleanup, name lookup, question coach, onboarding suggestions): Claude Haiku (`claude-haiku-4-5`)
  - Sampling params go through `ai_models.temperature_kwargs()` so model upgrades can't 400 on removed `temperature`
  - Anthropic SDK pinned at **`anthropic==0.102.0`** (0.43.x lacked `output_config` / adaptive thinking)
- **STT:** OpenAI Whisper (`whisper-1`)
- **TTS:** OpenAI TTS (`gpt-4o-mini-tts`, voice: `coral`, per-language native-accent instructions; env-overridable via `TTS_MODEL` / `TTS_VOICE`, falls back to `tts-1`/`alloy` on failure)
- **Infra:** GCP Cloud Run (auto-scaling), Neon PostgreSQL, Cloudflare R2 (audio storage)

## Copy Conventions

**No em dashes (`—`) — or any "double dash" — in user-facing copy.** The em
dash reads as an AI tell and is banned from all product copy: the i18n locale
files under `frontend/src/locales/**/*.json`, marketing/blog copy, and email
templates. This also covers the visually-similar en dash (`–`) and the literal
double hyphen (`--`) in prose.

Rewrite instead of transliterating:
- `word — word` → a comma (`word, word`) in the common case, or a colon where
  the dash introduces/explains something. Pick whichever reads naturally; don't
  mechanically swap the glyph.
- A standalone `—` used as an empty-cell / "none" placeholder → a single
  hyphen `-` (or better, real words like "None").
- A leading `— hint` label separator → drop the dash entirely.

**Scope carve-outs (leave these alone):** a single hyphen in compound words
(`follow-up`, `mixed-methods`) is fine — it is not a dash. Do **not** strip
`--` from code: CLI flags (`--dry-run`), SQL, and shell examples in comments
are legitimate. The ban is about *prose the user reads*, not code.

When editing an AI system prompt that shapes a user-facing deliverable
(analysis reports, interview questions, decision memos), add an explicit
"never use em dashes; use commas or colons" instruction so the model doesn't
reintroduce them downstream.

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
│   │       ├── interview_engine.py  # Core AI orchestration (Claude Sonnet)
│   │       ├── analysis.py          # AI synthesis + refined analysis
│   │       ├── copilot.py           # Research Copilot turn engine (Opus, SSE streaming, scoped memory, tool dispatch, proposal-turn filter)
│   │       ├── copilot_interview.py # INTERVIEW_ADAPTER (guide/screener/analysis proposals) for the project surface
│   │       ├── ai_models.py         # Single source of truth for Claude model ids (env-overridable pins + temperature_kwargs guard)
│   │       ├── company_name_lookup.py  # Haiku-only backfill of business_summary + industry from a typed company name (for freemail signups)
│   │       ├── signup_prefetch.py   # W2.5 — background website pre-fetch keyed off the user's email domain at signup
│   │       ├── analytics.py         # Funnel-event INFO logger (signup / onboarding_completed / study_created / link_shared / participant_completed / paid_converted)
│   │       ├── quality.py           # Heuristic quality scoring
│   │       ├── feature_gates.py     # Legacy tier-based limits (used by legacy plans only)
│   │       ├── billing_plans.py     # Credits-based plan catalogue (8 plans, 76 entitlements)
│   │       ├── billing_service.py   # Credits-based billing: seed/backfill/quota/consume
│   │       ├── auth.py              # JWT + bcrypt helpers
│   │       ├── email.py             # SendGrid + dev console fallback
│   │       ├── stt.py               # Whisper transcription
│   │       ├── tts.py               # OpenAI TTS generation
│   │       ├── storage.py           # Audio: Cloudflare R2 or local disk
│   │       ├── guide_parser.py      # CSV import parser
│   │       ├── usage_logger.py      # Fire-and-forget AI cost logging (Claude/Whisper/TTS)
│   │       ├── website_intelligence.py  # Onboarding: scrape + summarise a company website
│   │       ├── workspace.py         # Team workspace membership + permission helpers
│   │       ├── demo_seeder.py       # Seeds the onboarding showcase demo project
│   │       ├── _demo_data_fr.py     # French transcripts for the showcase demo (fixture)
│   │       ├── _demo_data_en.py     # English transcripts for the showcase demo (fixture)
│   │       ├── translation.py       # Claude-based transcript translation (researcher reading aid)
│   │       └── transcript_cleanup.py # Haiku ASR sense-check (fixes STT proper-noun/term errors; reading aid)
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
│   │       ├── 0009_blog_posts.py
│   │       ├── 0010_add_preferred_language.py
│   │       ├── 0011_add_slack_webhook_url.py
│   │       ├── 0012_team_collaboration.py
│   │       ├── 0013_add_demo_project_flag.py
│   │       ├── 0014_onboarding_audit_fields.py
│   │       ├── 0015_current_priority.py
│   │       ├── 0016_onboarding_redesign_fields.py
│   │       ├── 0017_quality_assessment_columns.py
│   │       ├── 0018_transcript_translation_columns.py
│   │       ├── 0019_warmup_enabled.py
│   │       ├── 0020_fix_audio_recording_urls.py
│   │       ├── 0021_response_segments.py
│   │       ├── 0022_credits_system.py
│   │       ├── 0023_google_sso.py
│   │       ├── 0024-0033_*.py        # iterative onboarding + billing schema
│   │       ├── 0034_paywall_visibility.py    # has_ever_paid + free_preview_full_email_sent_at
│   │       ├── 0035_copilot_conversation_version.py
│   │       ├── 0036_onboarding_personalisation_cache.py  # welcome_greeting_text / starter_suggestions_json on Company
│   │       └── 0037_research_plan.py  # ResearchPlan + ResearchPlanStep (Wave E)
│   ├── tests/
│   │   ├── conftest.py          # SQLite in-memory fixtures, rate limiter disabled
│   │   ├── test_auth.py         # Signup, login, refresh, email verification, password reset
│   │   ├── test_projects.py     # CRUD, auth isolation, archive, tier limits
│   │   ├── test_feature_gates.py # All tier limits + feature gates (legacy plans)
│   │   ├── test_billing_credits.py # Credits-based billing (PR 1: foundation)
│   │   └── test_demo_seeder.py  # Showcase demo project seeding + quota exclusion
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
│   │   │   ├── copilot.ts       # Research Copilot SSE client (fetch + ReadableStream, status/delta/done handlers)
│   │   │   └── blog.ts          # Blog API (public listing + admin CRUD)
│   │   ├── copilot/
│   │   │   ├── nextAction.ts        # Deterministic NBA resolvers (project / survey / workspace / study summary)
│   │   │   ├── signals.ts           # Client-side nudge detection (localStorage diff, 5 event types, 24h TTL)
│   │   │   └── useNudgeAnnounce.ts  # aria-live polite announcer for new nudges
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
│   │   │   ├── Welcome.tsx           # Conversational onboarding: chat with Copilot + milestone bar + "What I know" sidebar + chips + website lookup → first study
│   │   │   ├── VerifyEmail.tsx       # Token-based email verification page
│   │   │   ├── Terms.tsx             # Terms of Service
│   │   │   ├── Privacy.tsx           # Privacy Policy (GDPR-compliant)
│   │   │   ├── LegalDocument.tsx     # DPA, subprocessors, participant notice, AI use policy, retention policy
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
│   │   │   ├── ResearchCopilotPanel.tsx  # Always-on Copilot dock + open panel (mission, NBA starter, nudges, streaming)
│   │   │   ├── NextActionChip.tsx        # Renders one resolved NBA (inline button or compact dock pill)
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
# Publishable key — enables in-app Embedded Checkout (served to the frontend
# via GET /billing/config). Blank = hosted checkout.stripe.com redirect.
STRIPE_PUBLISHABLE_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_STARTER=
STRIPE_PRICE_PRO=

# Google Sign-In (optional — disables /auth/google/* if any are blank).
# Register the redirect URI in Google Cloud Console → Auth Platform → Clients.
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback

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
- Legal pages (public frontend routes): `/terms`, `/privacy`, `/dpa`, `/subprocessors`, `/participant-notice`, `/ai-use-policy`, `/retention-policy`
- Health checks: `GET /` (shallow), `GET /health` (deep — verifies DB connection)

### Database
- **Dev:** SQLite, auto-created via `Base.metadata.create_all()` on startup
- **Production:** PostgreSQL (Neon or Cloud SQL). Set `DATABASE_URL` to `postgresql://...`
- Alembic migrations run on startup in Docker (`alembic upgrade head`)
- Datetime: use `datetime.utcnow()` (SQLite stores naive UTC — `datetime.now(timezone.utc)` causes issues)

### Billing — dual-track (legacy tiers + credits)

The product runs **two billing tracks side by side**. Existing accounts stay
on legacy tiers (no behavioural change); new accounts will move to
credits-based plans once PR 2 (Stripe + UI) lands. The `Plan.is_legacy`
flag in the `plans` table is the routing switch — `BillingService.can_start_interview`
delegates to the legacy gate when true and runs credit checks otherwise.

#### Legacy tiers (existing accounts)

Defined in `services/feature_gates.py`. Canonical tier names: `starter`,
`team`, `lab`, `enterprise`. Legacy aliases still work in DB: `free` →
starter, `solo` → starter, `pro` → lab.

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

**14-day trial (LEGACY ACCOUNTS ONLY):** Existing Starter-tier accounts
have `trial_ends_at` set 14 days from signup. While the trial is active,
`get_effective_limits()` returns Team-level limits. After expiry, limits
revert to Starter. The credits-native flow **ignores `trial_ends_at`
entirely** — credits gate consumption, not days. `BillingService.can_start_interview`
used to return `reason="trial_expired"`; that branch was retired alongside
the trial-half/trial-end calendar emails. The column stays in the schema
for the legacy `feature_gates.py` upgrade path.

**Where the legacy gates run:**
- `projects.py` → `create_project`, `import_project_from_csv` (project limit + question limit)
- `links.py` → `create_link` (link limit per project)
- `interview.py` → `start_interview_session` calls `BillingService.can_start_interview` first; for legacy plans (`is_legacy=True`) it falls through to `require_participant_limit`
- `analysis.py` → `trigger_analysis`, `trigger_refined_analysis` (ai_analysis feature)
- `export.py` → `export_transcripts_csv` (export_csv feature), `ai_quality_assessment` (ai_analysis)

#### Credits-based plans (V1 foundation, schema only)

Catalogued in `services/billing_plans.py` and synced to the DB on every
API startup via `BillingService.ensure_plans_seeded`. The credit balance
lives on `credit_balances`; every credit movement is appended to
`credit_ledger` (idempotent per participant via a partial unique index).

| Plan | Monthly | Annual | Credits/period | Editors | Overage |
|---|---|---|---|---|---|
| Trial | €0 | — | 3 total (no time expiry) | 1 | — |
| Exploration | €89 | €890 | 10 / month | 1 | €7/credit |
| Team | €299 | €2,990 | 50 / month | 3 | €6/credit |
| Agency | €799 | €7,990 | 150 / month | 8 | €5/credit |
| Enterprise | custom | custom | custom annual | custom | per contract |

Credits-based plans have **no active-project cap** — studies are unlimited
on every plan; usage is gated by interview credits alone. The former
`max_active_projects` column was dropped in Alembic 0055 (it was never
enforced). Legacy tiers still cap projects via `feature_gates.TIER_LIMITS`.

**1 credit = 1 completed participant interview (≤15 min).** Consumed
when `participant.status` flips to `"completed"` in
`process_interview_turn`. Idempotent per participant — replayed or
concurrent completions never double-charge. Screened-out, abandoned,
and technically-failed participants never consume.

**The trial is NOT time-based.** Its 3 credits never expire by calendar.
`bootstrap_trial_subscription` leaves `WorkspaceSubscription.trial_end`
NULL and gives the trial `CreditBalance` a far-future `period_end`
(`TRIAL_CREDIT_HORIZON`, ~10y) purely so the active-balance query keeps
matching — that date is never shown to users. `/billing/status`
suppresses `trial_end` + credit `period_end` for trial plans
(`credit_period == "trial_total"`) and emits a canonical `display` block
(`plan_name` / `is_trial` / `status` / `show_trial_end`) so the account
UI shows "Free trial" with no expiry instead of mixing the legacy tier
with the subscription status. The legacy `Company.trial_ends_at` column
is no longer set on signup (credits gate usage, not days) — it survives
only for pre-credits accounts on the `feature_gates.py` upgrade path.

**Plan name collision:** new plan `team` (€299) ≠ legacy plan `legacy_team` (€99). The legacy plans are prefixed `legacy_*` in the catalogue.

**Backfill on startup:** every existing Company without a
`WorkspaceSubscription` row gets one mapping to its legacy plan
(`Company.subscription_tier` → `legacy_starter` / `legacy_team` /
`legacy_lab` per `LEGACY_TIER_TO_PLAN_ID`). Idempotent — runs every
boot, no-ops after the first.

**State of the rollout:**
- ✅ PR 1 — schema, plan catalogue, `BillingService` (seed/backfill/quota/consume), engine hooks, backfill on startup.
- ✅ PR 2 — Stripe price-id resolver, `/billing/plans` + `/billing/status` + `GET /billing/usage`, credit-plan webhook routing, trial auto-bootstrap on onboarding, AccountSettings credits usage card.
- ✅ PR 3 — marketing pricing page rebuilt for the credits model with monthly/annual toggle ("Save 17%"), prepaid credit packs (`pack_25` / `pack_50` / `pack_100`) with `GET /billing/credit-packs` + `POST /billing/checkout/credits` (one-time Stripe `mode=payment`) + `checkout.session.completed` webhook handler granting via `grant_purchased_credits` (idempotent per Stripe session id), admin `POST /admin/workspaces/{id}/credits/adjust` for support-led top-ups/clawbacks (auditable in `credit_ledger` with `event_type='adjustment_admin'`), `PATCH /billing/overage` toggle, usage-warning emails fire at 80% + 100% credits used (idempotent per period via `usage_events`).
- ✅ V2.1 — frontend completions: credit-pack purchase grid in AccountSettings, admin "Adjust credits" modal in Admin.tsx, dashboard usage warning banner (≥80% dismissable, 100% non-dismissable).
- ✅ V2.2 (this) — rollover policy. Purchased + prior-rollover credits roll forever; included credits expire at period end. Consumption attributes to buckets in this order: included → rollover → purchased, so unused purchased credits survive even when usage exceeds the included grant. Implemented in `grant_period_credits`: at each new period it looks up the most recent prior balance, computes carryover via `_compute_rollover_from_prior_balance`, seeds the new balance's `rollover_credits` bucket, and writes `grant_rollover` + `expire_credits` ledger rows for audit. Idempotent (replay returns existing balance, no double-grant). Tests cover: no-prior, all-unused, partial-overflow, rollover-of-rollover, fully-drained, replay.
- ✅ Launch pricing/marketing/legal refresh — trial lowered to 3 completed interviews; paid monthly included credits lowered to Exploration 10, Team 50, Agency 150. Marketing page now leads with outcome-first AI interviews + decision-ready memo positioning, includes an interview-quality trust section (adaptive follow-ups, browser participant experience, transcript/quote traceability), a pricing FAQ, and direct mobile `/#pricing` anchor support. Legal pack added at `/dpa`, `/subprocessors`, `/participant-notice`, `/ai-use-policy`, `/retention-policy`; interview consent links the participant notice by default.
- ⏳ Deferred — metered overage settlement (Stripe invoice items at period end). Credit-pack flow shipped in V2.1 covers the same need; revisit if real customers ask. The `overage_enabled` toggle stays in the schema but settlement is a no-op.

### Research Copilot architecture
The Research Copilot is an always-on agent surfaced as a dock + open panel on every authenticated page (and as the full-screen `/welcome` conversation for onboarding). It powers free-form chat, surface-aware suggestions, and structured **proposal actions** the user accepts with one click.

**Adapter pattern.** Each surface defines a `CopilotAdapter` in `services/copilot.py` (or a sibling module):
- `INTERVIEW_ADAPTER` (kind=`interview`) — `services/copilot_interview.py`: guides, screeners, settings, analysis proposals
- `SURVEY_ADAPTER` (kind=`survey`) — `services/copilot.py`: survey questions

Each adapter exposes: `methodology` (system prompt fragment with rules and caps), `tools` (JSON Schema), `snapshot(instrument)` (compact state read each turn), `run_tool(name, args, ...)`, and a `stub` reply for tests. The shared `run_copilot_turn` / `run_copilot_turn_stream` in `services/copilot.py` build prompt-cache-friendly system blocks (stable methodology FIRST behind the breakpoint, volatile snapshot AFTER), call Anthropic with Opus 4.7 + adaptive thinking, dispatch tool calls, and persist conversation history.

**Streaming.** All copilot endpoints return **SSE** (`text/event-stream`) with `Cache-Control: no-cache` and `X-Accel-Buffering: no`. Events: `{type: "status", label}` (tool labels via `_TOOL_LABELS`), `{type: "delta", text}` (token-by-token model output), `{type: "done", reply, proposed_actions, memory}`. The frontend `streamCopilot` in `api/copilot.ts` uses `fetch` + `ReadableStream.getReader()` (axios buffers — unsuitable for SSE) with a 90s idle timeout per chunk, an AbortController (Stop button / unmount / navigation cancel), and a one-shot 401 token refresh. **Critical:** the FastAPI generator captures `db.get_bind()` BEFORE returning, then opens a fresh `Session(bind=engine)` inside the stream body — otherwise `Depends(get_db)` closes the session before iteration begins.

**Memory.** `CopilotMemory` rows are scoped at company / study / instrument tiers. The `remember` tool writes durable notes; the snapshot embeds recent memory at each turn. `CopilotConversation` persists turn history per instrument so the panel can reopen mid-thread.

**Proposal-turn filter.** `_filter_proposal_turn_actions` in `services/copilot.py` runs at the end of every turn. When the turn stages any real proposal card (guide question, objective, screener, settings, analysis, survey question…), it strips all `suggest_replies` chip groups so the user's attention stays on the accept CTA. Belt-and-suspenders to the "PROPOSAL TURN OWNS THE SCREEN" methodology rule.

**Guardrails.** Copilot POSTs are rate-limited per account (`RATE_LIMIT_COPILOT`, keyed on the bearer token) and gated by a per-workspace daily spend ceiling (`COPILOT_DAILY_COST_LIMIT_USD`, summed from `AIUsageLog.operation == "copilot"`; 429 `copilot_daily_limit_reached` when hit). Request history is bounded (60 messages × 8k chars in the schema; the engine sends only the recent tail to the model).

**Onboarding methodology hard rules** (`_ONBOARDING_METHODOLOGY` in `copilot_onboarding.py`):
- **RULE 1: One question per turn.** Bundling questions ("1. Quel canal... 2. Quelle décision...") is forbidden.
- **RULE 2: Every discrete question MUST attach `suggest_replies`.** Free-text only for genuinely open questions (research goal, success-criterion wording, study objective).
- **Research success criteria = research outcomes, NOT business KPIs.** Chips must be about evidence + decisions (ranked friction list, clear rebuild/iterate decision, citable quotes, mental models) — never conversion lift / NPS / CSAT.
- **Timeline shapes the plan.** 2 weeks → 1-step plan. 1 month → 2-step. 1 quarter → 3-step.
- **PREFERRED proposal path is `propose_research_plan`**, not `propose_study`. A real researcher rarely fires 50 interviews from a 2-minute chat.
- **HYBRID-WIZARD-AWARE.** The wizard captures role / company_size / use_case / decision_role before the chat starts. The agent must NEVER re-ask for these in turn 1 — it should reference them naturally and dive into the research goal.

**Mission + NBA + Nudges.** Each surface declares a one-line **mission** shown in the panel header. A deterministic **NBA resolver** (`frontend/src/copilot/nextAction.ts` — `resolveProjectNextAction`, `resolveSurveyNextAction`, `resolveWorkspaceNextAction`, `resolveStudySummaryAction`) picks a single best next action from a priority ladder — **no LLM call**, runs on every render. Rendered as a chip in the dock or inline in empty states via `NextActionChip`. **Nudges** are localStorage-diffed events (`frontend/src/copilot/signals.ts`, key `copilot_signals_v2`): `analysis_ready`, `analysis_stale`, `data_milestone`, `quality_flag`, `study_report_ready`, `memo_ready`, `memo_stale`. 24h TTL, dismiss persists, and nudges for the current tab auto-suppress to avoid noise. The workspace NBA also carries two cross-study rungs (`generate_memo` when ≥2 studies have a ready analysis and no ready memo exists, `refresh_memo` when a ready memo went stale) — they fire only when no per-study action is more urgent, and route to the Decision-memos section with the create modal opened. New nudges are announced once via aria-live (`useNudgeAnnounce.ts`).

### Onboarding Flow
> **Doc status:** everything below describing a *conversational* Phase 2 (ONBOARDING_ADAPTER, `/onboarding/copilot`, canonical reply chips, research-plan proposals, milestone bar) is a **design that was never merged** — none of it exists in the codebase. What ships today: `/welcome` is the structured wizard (`Welcome.tsx`), personalised via `GET /auth/onboarding/suggestions` (Haiku) and the company-name/domain backfills described below. The historical spec is kept for reference only.

After signup users land on `/welcome`.

**Phase 1 — Structured wizard (`WelcomeSetup.tsx`).** 3 steps capturing the qualification data we need for personalisation:
- Step 1: company name + role chips + team size
- Step 2: use case chips + intent (solo / team) + readiness (concrete / evaluating)
- Step 3: "the deal" screen — 10 free interviews / 3 free transcripts / unlock with plan, plus email-verify CTA

The wizard's "Other" chip on `role` / `use_case` reveals an inline free-text input — the typed value lands in `Company.role` / `Company.use_case` verbatim instead of being lost to the literal "Other".

At step 2 → step 3 transition, the frontend fires `prepWelcomeGreeting()` + `getStarterSuggestions()` in the background so the Phase 2 personalisation cache is warm before the user lands.

**Phase 2 — Conversational chat.** 2-column shell under a milestone bar.
- **Milestone bar** — three deterministic phases (*Tell me about your work → Frame your study → Launch*). Advances based on profile completeness + study/plan proposal — no LLM call.
- **Sticky chat shell** — header / verify-banner / milestone bar are pinned at top, input bar pinned at bottom, only the thread scrolls. Auto-scroll-to-bottom respects `isAtBottomRef` so users scrolled up to re-read don't get yanked back down.
- **Sidebar (left)** — "What I know about you" with rich rows for captured profile fields. Identity rows (name + company) seed from signup data on first render. Click-to-edit on canonical fields (`role`, `company_size`, `use_case`) opens a chip-picker popover; clicking a chip commits immediately. When the saved value is non-canonical (user typed via "Other"), the picker surfaces it as an active italic pill plus a free-text input so the typed string is recoverable.
- **Conversation (right)** — streaming Copilot chat. Personalised first greeting (Haiku, quotes one concrete detail from `business_summary`) replaces the canned bubble once it lands; falls back to static i18n if API fails or wizard was skipped. Goal-chip starters are also Haiku-personalised (3 industry-specific research questions). Assistant turns can carry attachments:
  - **Quick-reply chips** — server-enforced canonical options for profile contexts (locale-aware via `_CANONICAL_REPLIES_EN` / `_CANONICAL_REPLIES_FR`). Synonym dedupe ensures FR users never see `[Autre][Other]` side-by-side. The `suggest_replies` tool's `context` is an `enum`; whenever it matches a profile key the server substitutes the canonical set. Methodology enforces **one question per turn** and **every discrete question MUST attach chips**.
  - **Website-lookup card** — URL input that calls `/auth/website-intel`, persists `business_summary`, and injects the summary into chat.
  - **Participant-demo invite card** — opens an iPhone-framed mock interview (`ParticipantDemoModal`). On close or skip, auto-fires a synthetic user message ("Compris, et le plan ?") so the conversation advances to the plan proposal without a manual nudge.
  - **Research-plan proposal card (PREFERRED)** — `propose_research_plan` emits `create_research_plan`. A 2-3 step timeline shaped by the captured timeline: 2 weeks → 1-step plan, 1 month → 2-step, 1 quarter → 3-step. Each step has method + N + duration_weeks + purpose + deliverable. Step rendered as `<ResearchPlanCard>`. One-click accept hits `POST /onboarding/research-plan`, which creates the `ResearchPlan` + `ResearchPlanStep` rows and drafts the first `voice_interview` step (regardless of position in the plan) as a real Project + interview link. Quant / workshop / etc. steps stay `status="pending"` placeholders for now.
  - **Study proposal card (FALLBACK)** — `propose_study` emits `create_first_study` for users who explicitly want one quick study. One-click accept hits `POST /onboarding/study` (creates Project + guide + link in one transaction).

**Proposal turn owns the screen.** When a turn contains `create_research_plan` or `create_first_study`, server-side `_filter_proposal_turn_actions` strips any `suggest_replies` chips for lightweight-signal contexts (`referral_source`, `current_tool`, `research_experience`) so the user's attention stays on the accept CTA.

**Business-context backfill from typed name.** For freemail signups (gmail / outlook / etc.) the email-domain prefetch is skipped on purpose. `PATCH /auth/onboarding` schedules a background `backfill_business_from_name` (`services/company_name_lookup.py`) — a Haiku call that recognises well-known companies (Legalstart, RATP, BNP Paribas, …) and populates `business_summary` + `industry`. Re-runs whenever the typed name materially changes (case-insensitive) so a domain-prefetched summary doesn't go stale when the user types a different company name in the wizard. For unrecognised names Haiku returns null, leaving prior values intact.

**Personalisation race protection.** Both `prepWelcomeGreeting` and `getStarterSuggestions` poll up to 3 times with 3s/6s back-off — gives the company-name backfill time to land before falling back to static copy.

**Domain pre-fetch at signup (W2.5).** For corporate emails (anything not in the freemail allowlist in `services/signup_prefetch.py`), a background thread fires `fetch_website_summary` against the email's domain right after the Company row commits. Daemonised thread — never blocks signup, swallows every error path.

Once a plan/study is accepted: `POST /auth/onboarding` marks `onboarding_completed = true`, and a completion screen shows the study name + a Haiku-generated memory recap fetched from `GET /onboarding/copilot/memory` (entirely in the user's locale, skips literal "Other"). The CTAs are reordered: **Primary: "Ouvrir votre étude →"** / Secondary: "Copier le lien à partager" / Tertiary: "Tester votre propre entretien" (90s hint, no mention of "Claude"). The header **"Skip — just take me in"** bypasses everything; email verification is non-blocking (yellow banner with Resend link until verified).

Login checks `onboarding_completed` — if false, redirects to `/welcome`.

### Showcase Demo Project (fallback seed)
On the first successful `POST /auth/onboarding`, the backend calls
`seed_demo_project()` **only when no real Project already exists for the
company** (the conversational onboarding usually creates one, in which
case the demo seed is skipped). When it does fire it populates a
read-only example project named
`[Demo] How modern teams work across borders` for the new account.
Idempotent via `Company.demo_seeded_at` — subsequent onboarding completions
skip seeding. Seeder errors are swallowed so a fixture bug never blocks a
real user from finishing onboarding.

Seeding is **mono-language** — driven entirely by `Company.preferred_language`
— and uses real, well-known consumer brands so testers immediately recognise
the topic. EN companies get a **streaming services** study named
`[Demo] How people choose streaming services` (Netflix, Disney+, Prime Video,
HBO Max, Apple TV+). FR companies get a **courses alimentaires en ligne**
study named `[Démo] Courses alimentaires en ligne : habitudes & freins`
(pre-August-2026 accounts have the older em-dash title; the showcase
backfill renames them)
(Carrefour Drive, Picard, Leclerc Drive, Coop@home, Amazon Fresh).

- **Ten mono-language interviews** with a realistic quality spread (4 strong /
  4 good / 2 low) and varied demographics. EN: Priya R. (UK), Marcus T. (US),
  Jen H. (Canada), Alex K. (Australia), Dana W. (US), Tom O. (Ireland),
  Yuki N. (US), Sam B. (UK), Grace A. (Canada), Victor M. (US). FR:
  Camille D., Nadia T., Julien P., Fatou D., Élodie R. (France), Romain B.
  (France), Léa M. + Marc V. (Belgique), Sophie L. + Anaïs G. (Suisse).
  Each has 6–8 turns mixing main questions and adaptive follow-ups.
- **Setup content** — 3 main guide questions across 3 sections (Discovery /
  Experience / Loyalty for EN; Découverte / Expérience / Confiance et retour
  for FR), 1 screening question with a disqualifying option, 1 active
  interview link, 25-minute target duration
- **Coding** — 3 manual codes, localized per language (EN: Trust signal /
  Friction / Price concern; FR: Signal de confiance / Friction / Sensibilité
  prix) and 6 tagged quotes with real character offsets computed via `.find()`
- **Analysis** — 2 versions: `ai_discovery` v1 (with `share_token`) and
  `researcher_refined` v2 parented to v1. 2 annotations (`confirmed`,
  `needs_evidence`) on v2 themes. All analysis quotes are verbatim
  substrings of real participant transcripts.
- **Memos** — 3 project memos (general + theme-linked + tension-linked)
- **Editing state** — one turn flagged `manually_edited=True`
- **Single demo study** — the demo seeds exactly one study (the flagship
  above). A new account lands with one worked example, not two. (Earlier
  revisions seeded a leaner sibling exit-interview study — and, before that,
  a cross-study `CrossStudySynthesis` decision memo across both — but both
  were retired to keep first-run focused; the second study added clutter
  without a connecting memo. Cross-study synthesis is still a real product
  feature, just not seeded into the demo.)
- **Demo CTA banner** — When viewing a demo project, a styled banner
  prompts users to create their first real study

The content lives in `backend/app/services/_demo_data_{en,fr}.py` so the
`demo_seeder.py` logic stays readable. Demo projects set `Project.is_demo=True`
(exposed in `ProjectResponse` API schema) and are **excluded from the tier
project-quota count** in `routers/projects.py` so they never block a user
from creating their first real study. Tests:
`backend/tests/test_demo_seeder.py` (relationship graph, quote-tag
offset integrity, every analysis quote appears verbatim in a real transcript,
quota exclusion, single-study seeding (no sibling study, no cross-study memo),
showcase-backfill round-trip).

**Showcase upgrade (July 2026).** Every demo guide question carries
`interview_notes` (probing instructions) + `desired_learning`, with
`researcher_notes` on key questions; the demo survey is a **ten-question**
instrument that exercises **every question type the product supports**
(frequency mc_single, stack mc_multi, stack-size mc_single kept
per-respondent consistent with the mc_multi answers, a three-item 5-point
likert battery incl. one `reverse_coded` item, a **7-point** satisfaction
likert, NPS, open_text churn question, and a short_text forced-choice
"keep one"); demo transcripts show an explicit "no audio in the demo"
note in the Responses view (`responses.demoNoAudio` i18n key). The
cohort answer plans are cycled deterministically and every statistic the
hand-authored reports quote is reproduced exactly by the analytics layer
(`_survey_signals` in `demo_seeder.py` is the single source of truth —
re-derive its figures if you touch a plan). The seeder assigns
client-side UUIDs and avoids per-row flushes so the ~800-row seed stays
fast against remote Postgres. Because seeding is one-shot per company,
accounts seeded **before** an upgrade are patched by
`backend/scripts/backfill_demo_showcase.py` (idempotent, `--dry-run` /
`--company` flags; fills empty guide notes only, upgrades surveys that
match the legacy five-question OR the showcase eight-question signature
to the current ten-question shape with seeded answers, refreshes the
flagship `decision_v1` StudyAnalysis report from the current fixture).
It does **not** retro-add interviews 5–10 to accounts seeded with the
four-interview demo — only new signups get the ten-interview cast. Run
it once against production after deploy.

### Web analytics & marketing attribution

No third-party analytics SDK ships with the app: **no GA, no Plausible,
no PostHog, no pixel, no cookie banner**. Funnel measurement is entirely
first-party and lands in one place, the `analytics event=…` INFO log
stream produced by `services/analytics.py`.

**Two halves.**

1. **Front of funnel (FE-fired).** `frontend/src/utils/analytics.ts`
   POSTs a closed set of events to `POST /telemetry/event`
   (`page_view`, `cta_signup_click`, `pricing_viewed`,
   `pricing_interval_toggled`, `newsletter_submit`, `analysis_viewed`).
   The backend enforces the catalogue (unknown names are dropped
   silently), filters obvious bots, redacts any non-public path to
   `/redacted`, and stamps an anonymous **daily-rotating visitor hash**
   (`sha256(SECRET_KEY | utc-date | ip | ua)`, truncated) so uniques can
   be counted without a cookie and without storing anything derived from
   an IP. That is what keeps this inside the CNIL audience-measurement
   exemption, i.e. no consent banner. Adding an event name to the
   frontend union type without adding it to `_ALLOWED_EVENTS` in
   `routers/telemetry.py` is a silent no-op.
2. **Back of funnel (server-fired).** The existing `emit_event` milestones
   (`signup`, `onboarding_completed`, `study_created`, `link_shared`,
   `participant_completed`, `paid_converted`).

**Attribution stitches the two.** `frontend/src/utils/attribution.ts`
captures the `utm_*` trio on first touch (60-day localStorage window,
same shape as `utils/referral.ts`), falling back to the referring
hostname so untagged organic/social traffic is still attributable. It is
replayed at signup through **both** paths: the password signup body, and
the signed Google OAuth state (`us` / `um` / `uc` keys, because Google's
redirect drops query params). The backend persists it on
`Company.utm_source/medium/campaign` and echoes it on the `signup` event,
so a `paid_converted` months later is traceable to a channel.
`referral_source` is unrelated: that is what the user *says* when asked
during onboarding, this is what was *measured*.

**Log safety.** `/telemetry/event` is unauthenticated, so every value is
sanitised to a charset that excludes `=`, `?`, `&`, and newlines before
it reaches a log line. Without that, a caller could smuggle a second
`event=…` token in and poison any count built by grepping the stream.
`_fmt` in `analytics.py` strips newlines unconditionally for the same
reason.

**Storage is deliberately doubled up.** Every accepted event is written
to the log stream *and* to the `web_events` table. The log line is the
resilient path (works with the DB down, greppable next to the
server-side milestones); the table is the durable one, since Cloud
Logging drops these after 30 days while the rollup needs months to
answer "did March's channel convert by June?". At marketing-site volume
the table is a few thousand rows a month, which is nothing.

**Reading the data.** Three ways, in descending order of convenience:

1. **Admin panel → Traffic tab** (`GET /admin/traffic?days=`). Pageviews,
   visits, pricing views, CTA clicks, signups, and the signup rate, plus
   breakdowns by CTA location, channel, referrer, and page. Note
   `paid_by_source` is deliberately **not** windowed: first-touch
   attribution exists precisely so a customer who signed up in March and
   paid in June still credits March's channel.
2. **Cloudflare Web Analytics** for raw traffic volume and Web Vitals.
3. **`gcloud logging read`** for anything ad hoc.

`deploy/setup-analytics-sink.sh` sets up a BigQuery sink with a parsed
SQL view over the raw log table. It is written but **not run**: the
`web_events` table already solves retention at this scale. Run it if
event volume outgrows Postgres or you need warehouse joins.

**Cloudflare Web Analytics (optional, free).** The CSP in
`frontend/nginx.conf.template` + `nginx.conf` already allows
`static.cloudflareinsights.com` (script) and `cloudflareinsights.com`
(connect), so enabling cookieless pageview/referrer/country reporting is
a one-line beacon `<script>` in `index.html` with a real token. It is
inert until then. Add it to `/subprocessors` if you turn it on.

### Email Verification
- On signup: `EmailVerificationToken` created (24h expiry). Only the verification email is sent, and it greets by **first name** ("Welcome, Marie") rather than company name (falls back to company name if first name is missing).
- `POST /auth/verify-email?token=...` marks `email_verified = True`
- `POST /auth/resend-verification` (rate-limited 3/min, requires auth)
- `email_verified` exposed in `GET /auth/me` response (CompanyResponse)
- Non-blocking: users can log in and use the app without verifying (frontend shows yellow banner)

### Email Service
- **Provider:** SendGrid (domain-authenticated for `qualipulse.com`)
- **Fallback:** Console logging when `SENDGRID_API_KEY` is not set
- **From:** `noreply@qualipulse.com` (QualiPulse)
- **Templates** (all in `services/email.py` with branded HTML wrapper):
  - `send_verification_email` — email verification link (24h), nominative greeting (first name)
  - `send_personalized_welcome` — fires from `POST /auth/onboarding` once the 4-step wizard completes; Claude generates a **personalised research brief** from role + company + use cases and embeds it in the email body (falls back to generic `send_welcome` if generation fails)
  - `send_welcome` — generic fallback (no longer sent on signup or verify; only used as fallback for `send_personalized_welcome`)
  - `send_password_reset` — password reset link (1h)
  - `send_analysis_ready` — when AI analysis completes
  - `send_interview_invite` — (template exists, not yet wired to an endpoint)
  - `send_newsletter_welcome` — newsletter subscription
- **DNS records** (Namecheap): em9375 CNAME, s1/s2._domainkey CNAME, _dmarc TXT

### Authentication & Security
- JWT access tokens (24h expiry) + refresh tokens (30d expiry), HS256. Every token carries a `tv` (token_version) claim pinned to `Company.token_version` — bumping the column revokes all outstanding tokens. Bumped on password change/reset and `POST /auth/logout-all`; tokens minted pre-0051 (no claim) are treated as tv=0. Impersonation tokens are exempt.
- Auto-refresh on 401 via Axios interceptor (`client.ts`)
- Bcrypt password hashing. Password policy: ≥8 chars with at least one letter and one digit (`validate_password_strength`), enforced at signup / change / reset. Optional haveibeenpwned k-anonymity breach check (`is_password_breached`, fail-open; on in production or via `PASSWORD_BREACH_CHECK`).
- **TOTP 2FA** (pyotp): `POST /auth/2fa/setup` (secret + otpauth URI) → `POST /auth/2fa/enable` (verify code; returns 10 single-use backup codes, stored as SHA-256 hashes) → login becomes two-step (`POST /auth/login` returns `{requires_2fa, pending_token}`, exchanged at `POST /auth/login/2fa` with a TOTP or backup code). `POST /auth/2fa/disable` needs password + valid code. `totp_enabled` exposed in `GET /auth/me`. UI: Account → Security (`AccountSecurity.tsx`) + 2FA step in `Login.tsx`. Schema: Alembic 0051.
- **Account lockout**: 5 consecutive failed password/2FA attempts → 15-min lock (`Company.failed_login_attempts` / `locked_until`, 429 on login). Reset on success; password reset clears it.
- Rate limiting: 10/min on auth, 60/min on public, 120/min on authenticated. **uvicorn runs with `--proxy-headers --forwarded-allow-ips "*"`** (start.sh + docker-compose) so `request.client` is the real client IP behind Cloud Run/nginx — without it all users share one rate-limit bucket.
- Security headers: X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy, HSTS (production), CSP (deny-all on API responses in `main.py`; SPA policy in `frontend/nginx.conf.template` + mirrored in local `nginx.conf`)
- CORS configurable via `ALLOWED_ORIGINS`
- Audio endpoint: directory traversal protection
- **Google Sign-In** (OAuth2 authorization-code flow): `GET /auth/google/login` returns a Google consent URL with a 15-min signed-state JWT (CSRF nonce + sanitized post-login path + UI lang); `GET /auth/google/callback` exchanges the code via `httpx`, fetches `/userinfo`, then upserts the Company (matches by `google_sub` first, then by email — the email fallback only runs when Google attests `email_verified`, and first-time linking to a password account triggers a security-notice email). New Google signups get `email_verified=True` and the same 14-day starter trial as paid signups. Tokens are returned to the frontend via URL fragment to `/auth/google/finish`, which persists them, clears the fragment from history, and routes to `/welcome` (new) or `/dashboard` (returning). `password_hash` is now nullable for OAuth-only accounts; password login + change-password guard against null. Disabled (returns 503) when `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI` are unset. Schema: Alembic 0023 adds `companies.google_sub` (unique index) and makes `password_hash` nullable.

### Audio Recording (Safari Compatibility)
- `MediaRecorder.start(250)` — timeslice fires `ondataavailable` every 250ms
- MIME type priority: `audio/webm;codecs=opus` → `audio/webm` → `audio/mp4` (Safari) → `audio/ogg`
- File named `recording.{ext}` to help backend/FFmpeg detect format
- **Server-side transcode for playback (`services/transcode.py`).** Participant
  browsers record `webm/opus`, which **Safari/iOS cannot play back** — a
  researcher reviewing on a Mac would see "Audio unavailable" even though the
  clip is safely stored in R2. So `respond_to_question` transcodes every
  non-playable recording to **MP3** (via `ffmpeg`, installed in the backend
  Dockerfile) before upload — MP3 plays in every browser and Whisper still
  transcribes it. Any transcode failure (e.g. ffmpeg missing in local dev)
  falls back to the original bytes, so the interview never breaks.
  Legacy webm recordings already in R2 are converted by the one-off
  `backend/scripts/backfill_audio_transcode.py` (idempotent; `--dry-run` +
  `--limit` flags). Tests: `backend/tests/test_transcode.py`.

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
- **Screening answers are persisted on the qualified participant** (Alembic
  0061, `Participant.screening_answers` JSON snapshot of
  `{question_id, question, answer}` with canonical option values, sanitized
  server-side in `/start` against the project's screener). They feed: the
  analysis prompt headers (`screener: Q = A` per participant), segment
  filters (`filter_by="screening:<question_id>"` in `_filter_participants`),
  the heatmap (each screener question is a dimension), the participants
  list/card, and the CSV export. Screened-out participants still leave no
  record. Tests: `backend/tests/test_screening_answers.py`.
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
1. Researcher triggers analysis (optional demographic filters). Before
   triggering, the frontend checks `GET /projects/{id}/analysis/readiness`
   (codebook size, accepted-tag counts, pending-suggestion count,
   `tagging_state`: anchored / partial / untagged). **Untagged studies get a
   readiness-gate modal**: "let AI code first, then analyse" (POSTs
   `auto_tag: true`), "analyse without coding", or "I'll tag myself" — a
   nudge, never a wall (readiness fetch failure falls through to a plain run).
   **Fewer than 3 completed interviews adds a low-N rung to the same modal**
   ("first read, not findings" expectations + "run a first read anyway" /
   "wait for more interviews"); the run itself is never hard-blocked above
   N=0. Ready reports at N<3 carry a deterministic `small_sample: true` flag
   (set in Python by `run_analysis`/`run_refined_analysis`, threshold
   `SMALL_SAMPLE_THRESHOLD` in `services/analysis.py`, participant-count
   fallback for pre-flag reports) rendered as a warning banner in the
   Analysis tab, the public shared report, and the HTML export.
2. Background thread runs a **staged pipeline**; the stage is persisted on
   `ProjectAnalysis.stage` (+ `stage_detail` JSON counters) and rendered by
   the polling frontend as a labelled progress bar: optional `auto_tagging`
   ("interview 3 of 10", runs `suggest_tags_for_participant` over completed
   interviews with no tags and no pending suggestions; suggestions stay
   pending, the codebook is never mutated) → `preparing` → `synthesizing` →
   `verifying`. Stage is cleared on ready/failed/timeout. The watchdog budget
   grows with the cohort when auto-tag is on (300s + 30s/interview, cap 15 min).
   **Live synthesis narration:** `_synthesize_response` takes an
   `on_progress(section, output_tokens)` callback; it already streams from
   Anthropic, so it watches the text deltas for each top-level report key
   in schema order (`REPORT_SECTIONS`) and the throttled
   `_progress_reporter` (≤1 commit / 2s, or on section change) persists
   `stage_detail = {section, output_tokens}`. The UI shows "Writing the key
   themes…" and partially fills the active bar segment. **Time disclaimer:**
   GET analysis returns `elapsed_seconds` (server-side, reload-safe) and
   `estimated_seconds` (median of the last 20 ready runs' created_at →
   generated_at durations, rescaled to the cohort size; fallback 45s +
   10s/interview); readiness returns `estimated_seconds` for the gate
   modal. The UI shows "0:42 elapsed · usually about 1:30" plus "you can
   leave this page, we'll email you" (the analysis-ready email already
   fires on completion).
3. Prompt evidence is **provenance-tiered**: Tier 1 = researcher-accepted tags
   (`_build_codebook_block`, "researcher-verified"), Tier 2 = pending AI
   suggestions (`_build_suggestion_block`, "machine-coded candidates, NOT yet
   reviewed" — never allowed to borrow Tier-1 framing), Tier 3 = the model's
   own reading of transcripts.
4. Claude returns structured JSON: themes, JTBDs, tensions, recommendations, confidence scores
5. Versioned (keeps 5 most recent), can be filtered by segment
6. Researcher can annotate themes (confirmed/disputed/needs_evidence) + add context
7. Refined analysis incorporates annotations and re-analyzes with feedback (same staged progress, no auto-tag stage)
8. Shareable via public token (read-only report page)

Tests: `backend/tests/test_analysis_stages.py`. Schema: Alembic 0060
(`project_analyses.stage` + `stage_detail`).

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
  --port=8080 --cpu=1 --memory=1Gi --min-instances=1 --max-instances=15 \
  --timeout=300s --concurrency=16 --no-cpu-throttling --cpu-boost \
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
| CPU | 1 (always allocated, startup boost) | 1 |
| Memory | 1Gi | 256Mi |
| Min instances | 1 | 0 |
| Max instances | 15 | 5 |
| Timeout | 300s (for Claude/TTS) | 60s |
| Concurrency | 16 | 200 |

> Backend tuning rationale: `--no-cpu-throttling` keeps CPU allocated between
> requests so the in-process daemon threads (analysis, translation, memos,
> transcript cleanup) actually run after their 202 returns; `min-instances=1`
> removes the 15-40s cold start the first user after an idle period used to
> eat; `concurrency=16` reflects real capacity (sync endpoints hold a
> threadpool worker for the whole Whisper→Claude→TTS chain) so the
> autoscaler adds instances before saturation instead of after.
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
- [x] AI brief parsing + objective / scope / question suggestions (now driven by the Research Copilot via tool calls — legacy `/research/*` endpoints removed)
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
- [x] Interview digest per participant: the auto-run completion-time quality pass also returns `key_takeaways` (3-5 substance bullets) + `notable_quotes` (up to 3 verbatim quotes, whitespace-tolerant containment check against raw transcripts drops paraphrases). Shown as a "Key takeaways" panel atop the transcript sidebar. Old participants backfill via the existing "AI assessment" button (it clears the summary to force a re-run). Alembic 0057. Tests: `backend/tests/test_quality_digest.py`.
- [x] Codebook evidence feeds project-level analysis (`_codebook_stats` + `_build_codebook_block` in `services/analysis.py`): both `run_analysis` and `run_refined_analysis` prepend a "RESEARCHER CODEBOOK EVIDENCE" block (per-code participant/quote counts + up to 4 sample quotes, capped at 12 codes) instructing the model to engage with researcher-verified categories, cite them where they support themes, and justify disagreement with heavily tagged categories. Segment-filtered runs only see the included participants' tags. Deterministic Python-computed counts ride along in the report JSON as `codebook_stats` (never model-generated) and render as a "Codebook signals" pill strip atop the Analysis Deep dive AND as a section in the exported/shared findings report HTML (`_codebook_section_html` in `services/report_export.py`, between Study design and Key themes). Tests: `backend/tests/test_analysis_codebook.py`, codebook cases in `test_report_export.py`.
- [x] AI-suggested tags + starter codebook (`services/tag_suggestions.py`): suggestion-only, the codebook is never mutated without an explicit accept. **Hybrid per-interview pass** (auto-runs on interview completion from the same background thread as the quality assessment, but ONLY when the project already has ≥1 code, so codebook-less studies see zero AI-proposed-code noise; also on-demand via the "✨ Suggest tags" button in the transcript codebook panel, `POST /projects/{id}/participants/{pid}/suggest-tags`, sync Sonnet call): deductive core applies existing codes; bounded inductive margin proposes ≤2 new codes (each needs verbatim quotes; dupes vs existing code names filtered before the cap). Quotes resolve to exact offsets in the raw `response_transcript` via `.find()` (tries the model's turn_index first, then all turns); paraphrases and unknown code names are dropped server-side. Suggestions persist as `TagSuggestion` rows (pending/accepted/rejected; re-run replaces pending, keeps reviewed history; overlap with an existing same-code QuoteTag is skipped). Accept (`POST .../tag-suggestions/{sid}/accept`) creates the QuoteTag (`created_by="ai_suggested"`) and materialises the proposed ManualCode (case-insensitive reuse); reject keeps history. UI: dashed pills with ✓/× under each turn. **Starter codebook** (`POST /projects/{id}/codes/suggest`, "✨ Suggest codes" button shown when the codebook is empty): 4-6 cross-cutting evidence codes from objective/decision/audience/guide (prompt forbids restating guide questions/sections), returned as proposals only; checkbox modal creates the selected ones via the normal codes API. Both ops log usage as `tag_suggest` / `codebook_suggest`. Alembic 0058. Tests: `backend/tests/test_tag_suggestions.py`.
- [x] Export CSV (participants + all transcript turns, streaming response)
- [x] Account & billing settings page (Profile tab + Plan & Billing tab)
- [x] Subscription tier model with **enforced** feature gates (solo/team/lab/enterprise)
- [x] 14-day trial: solo users get team-level limits, auto-set on signup
- [x] Stripe Checkout + Customer Portal + webhook handler (needs Stripe keys)
- [x] Profile save + change password in AccountSettings UI (PATCH /auth/me, POST /auth/change-password)
- [x] Analysis-ready email (triggered after AI synthesis completes)
- [x] Feature gates enforced on: projects, questions, links, analysis, export
- [x] Onboarding wizard (`/welcome`): 3-step structured wizard with Haiku-personalised use-case suggestions (`GET /auth/onboarding/suggestions`), company-name/domain business-context backfill, and demo-project seeding on completion. (A conversational copilot onboarding was specced but never merged.)
- [x] Research Copilot (always-on): dock + open panel on every authenticated page; per-surface adapters (interview/survey); SSE streaming (status/delta/done, Stop + retry, abortable); deterministic NBA chip; localized nudge tier with 5 event types and aria-live announcer; mission header per surface; scoped memory (company/study/instrument); Opus 4.8 + adaptive thinking + split-block prompt cache
- [x] Centralized error messages (frontend `utils/errorMessages.ts`)
- [x] Terms of Service + Privacy Policy pages, plus launch legal pack (`LegalDocument.tsx`): DPA, subprocessors, participant interview notice, AI use policy, and data retention policy. Marketing footer links all legal docs; participant consent screen links `/participant-notice` by default.
- [x] SendGrid email integration (domain-authenticated, branded HTML templates)
- [x] Getting-started checklist on empty dashboard
- [x] Auto-seeded showcase demo project on onboarding completion — mono-language by `preferred_language` (EN = streaming-services study, FR = online-grocery study, both using real consumer brands). 10 participants in the company's language with a realistic quality spread (4 strong / 4 good / 2 low), 6–8 turns each, 3 guide questions, 3 codes, 4 tagged quotes, 2 analysis versions with annotations, 3 memos. `is_demo=True` exposed in API, never counts against tier quota. Demo CTA banner prompts first real project creation. Idempotent via `Company.demo_seeded_at`.
- [x] Trial banner on dashboard (visible to solo/free users with active trial)
- [x] Email verification banner (yellow) when unverified
- [x] Admin panel (user management, tier changes, trial management, user deletion)
- [x] Admin stats dashboard (users, tiers, interviews, signups over 7/30 days)
- [x] Admin AI cost reporting (platform-wide + per-company breakdown)
- [x] Affiliate program (apply, magic-link login, dashboard, referral tracking, commission calculation). Attribution: `?ref=` is captured on any public page into localStorage (`qp_ref`, 60-day first-touch window, `utils/referral.ts`), read back at signup, and carried through the Google OAuth round-trip inside the signed state. Self-referrals are ignored. Lifecycle emails (EN/FR per `Affiliate.preferred_language`): application received, approved (with referral link), rejected, magic sign-in link, commission earned, payout recorded. All amounts in euros. Marketing footer links `/affiliate`. Tests: `backend/tests/test_affiliate.py`.
- [x] Affiliate admin management (approve/reject, commission %, payout recording)
- [x] Stripe webhook affiliate conversion tracking (one-time commission on the referred customer's first subscription payment; idempotent per referral, so cancel+resubscribe or replayed webhooks never double-pay; notifies the affiliate by email)
- [x] AI usage tracking (Claude tokens, Whisper seconds, TTS characters → cost_usd)
- [x] Research participant panel (PanelProfile, PanelTag, magic link auth)
- [x] Blog CMS (TipTap WYSIWYG editor, live preview, draft/publish, SEO meta + OG tags)
- [x] Public blog listing (/blog) + article pages (/blog/:slug) with newsletter CTA
- [x] Blog admin tab (create, edit, delete posts, status filter)
- [x] UX audit fixes (82 items): CSS variable cleanup (~50 hardcoded hex→vars), password show/hide + strength indicator, focus-visible outlines, ARIA labels + keyboard nav, sticky TOC on Terms/Privacy, responsive analysis toolbar, 44px touch targets, interview profiling card styling
- [x] EN/FR i18n foundation: react-i18next with namespaced JSON files (`frontend/src/locales/{en,fr}/`) covering marketing, auth, dashboard, project, interview, analysis, settings, affiliate, common
- [x] LanguageSwitcher component (`components/LanguageSwitcher.tsx`): pill-shaped toggle, light/dark variant prop, 44px WCAG touch target, CSS classes (no inline styles), shown on marketing nav and auth pages
- [x] Marketing page fully translated (EN/FR): all hardcoded strings replaced with `t()` calls including outcome-first hero memo preview, interview-quality trust section, output preview section, who-it's-for, differentiator, trust quote, pricing FAQ, **pricing cards** (plan names, features, CTAs)
- [x] Shared report (SharedReport.tsx) fully i18n'd: 17 keys in analysis namespace (EN/FR)
- [x] Project templates language-aware: wizard passes `i18n.language` to template API for FR content
- [x] Transcript translation as researcher reading aid: per-participant pill toggle in the dark participant card (shown only when researcher UI language ≠ project language). Original = data, translation = reading aid. Claude (Sonnet 4) translates all turns in one batched call, preserving voice (hedges, fillers, colloquialisms). Cached on `InterviewTurn.translated_response/translated_question/translation_language` so it never re-translates. `POST /projects/{id}/participants/{pid}/translate` (202, background thread). In translated view, precise text-selection tagging is disabled — researchers tag the **whole turn** via a "Tag turn" button, persisted with `QuoteTag.tagged_from_translation=True` so analysts know the provenance. Quote tags always stored against original text. Alembic 0018. Translation now translates **from `cleaned_response` when present** (see below) so the reading aid inherits ASR fixes.
- [x] Transcript ASR sense-check (`services/transcript_cleanup.py`): a cheap **Haiku** pass that fixes obvious speech-to-text errors (mangled proper nouns / domain homophones — e.g. "la France" → "Air France", "l'Ufthansa" → "Lufthansa", "écho" → "éco/economy") using the study's own context (name / objective / audience / context) as a glossary. **Original `response_transcript` is never overwritten** — corrections live in `InterviewTurn.cleaned_response` (+ `cleaned_at` idempotency stamp), same "original = data, correction = reading aid" principle as translation. Runs **async on interview completion** (daemon thread from `respond_to_question`); also exposed on-demand via `POST /projects/{id}/participants/{pid}/clean-transcript` (202) for backfilling pre-feature interviews. Voice-preserving prompt: fixes only clear errors, never paraphrases/regrades grammar/changes meaning, leaves a turn byte-identical when nothing's wrong; skips `manually_edited` turns. Display + translation-source only — analysis/quality still read the raw verbatim (no quote-offset drift). Responses tab gains a 3-way reading-aid toggle (Raw STT / ✨ Corrected / Reading aid); Corrected shows cleaned-on-top + raw-below with a badge, defaults on when any turn was corrected, and (like translated view) tags the whole turn since offsets map to the raw text. Backfill: `backend/scripts/backfill_transcript_cleanup.py` (`--dry-run` / `--limit` / `--participant`). Alembic 0048. Tests: `backend/tests/test_transcript_cleanup.py`.
- [x] Design system tokens: typography scale (`--text-xs` to `--text-2xl`), font weights (`--weight-*`), line heights (`--leading-*`), semantic colors (`--warning-text`, `--success-text`, `--info-*`), complete brand scale (`--brand-300/400/800`)
- [x] Mobile dashboard hamburger nav (collapses at 640px)
- [x] Auth page logo clickable (links to `/`), signup password toggle keyboard-accessible
- [x] Memo timestamps displayed (relative time) in project detail
- [x] Light-only color scheme (no dark mode)
- [x] Team collaboration: invitations + accept flow (`routers/team.py`, `AccountWorkspace.tsx`, `AcceptInvitation.tsx`), roles enforced — viewers are read-only on every mutating project route via `get_editable_project_or_404` (403 `viewer_read_only`); owner/admin/editor can modify. Tests: `test_workspace_roles.py`.
- [x] Dunning UX: `past_due` triggers a non-dismissable banner on the Studies home + a prominent banner with "Update payment method" (Stripe portal) on `/account/billing`. Only shows when a `stripe_customer_id` exists.
- [x] Abuse/cost protection: per-workspace daily AI-spend ceiling on the public interview loop (`INTERVIEW_DAILY_COST_LIMIT_USD`, default $50; blocks `/start` at 1x, `/respond` at 2x grace), mirroring the copilot's `COPILOT_DAILY_COST_LIMIT_USD`.
- [x] Client-side error reporting: SPA window.onerror/unhandledrejection → `POST /telemetry/client-error` (rate-limited, capped payload) → backend ERROR log → Sentry/Cloud Logging. No frontend SDK (VITE_ vars are baked at build; the pipeline injects no DSN).
- [ ] Usage counters enforcement (`interview_count`, `storage_bytes` fields exist, not yet incremented — dead columns; `/billing` reads them as 0)
- [x] Email invitation sending: manual typed-email invites per link (`POST /projects/{id}/links/{lid}/invites`, max 20, untracked) AND panel recontact invites (below)
- [x] Panel recontact (V1+V2): workspace-scoped pool of past participants who consented to future studies (`PanelProfile.panel_consent` captured post-interview). Send side: `GET /projects/{id}/invite-candidates` (pool minus already-participated / already-invited / 7-day platform cooldown, blocked rows kept with reason), `POST /projects/{id}/invites` (claim-then-send: `StudyInvite` row committed under a `(project_id, email)` unique constraint BEFORE the email, released if the provider refuses; per-workspace daily cap `INVITE_DAILY_LIMIT`, batch max 100, verified email + editor role required, demo projects refused), `GET /projects/{id}/invites` (funnel derived by joining participants on `(project_id, lower(email))` — never stored), `GET /workspace/panel` (V2 Participants page payload). Emails go out in the panelist's `preferred_language` (interview_invite copy in all 6 langs) with a signed one-click opt-out link (`POST /panel/opt-out`, 1y token, flips `panel_consent` + mirrors onto participant rows; frontend page `/panel/optout` requires a button click so scanner prefetch can't unsubscribe). UI: "Invite past participants" modal in the Setup tab's Recruit & share panel; workspace "Participants" rail page at `/pool` (`ParticipantPool.tsx`) with attribute filters + per-person invite/participation history. Logic in `services/panel_invites.py`, router `routers/panel_recontact.py`. Alembic 0062. Tests: `backend/tests/test_panel_recontact.py`.
- [x] Language-aware TTS voice (`gpt-4o-mini-tts` + per-language accent instructions in `services/tts.py`)
- [ ] Dashboard-level analytics across projects

### Participant Side
- [x] Consent screen (decline → thank-you, no record created)
- [x] Interview landing page (name, profession, age range, country, email — all optional)
- [x] Email-based interview resume (cross-device, shows covered topics + elapsed time; resumable up to 7 days idle, pacing clock rebased on resume after a long break)
- [x] Interview reminder emails (2 max, on different days) for verified-email participants who abandoned mid-interview, with a one-click magic resume link (sent by the scheduled-emails cron; see "Lifecycle emails")
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
- [x] Transcript flash ("We heard: …" dismissable confirmation after submit — `/respond` returns the Whisper `transcript` in `TurnResponse`)
- [x] In-flight participant coaching: engine detects short-answer runs (2+ answers ≤15 words); Claude returns a contextual `coaching` line in its decision JSON (sanitized, static localized fallback in `_coaching_hint_for`); shown as a dismissable banner only when a run *starts*, max 2×/interview (`MAX_COACHING_HINTS`). Tests: `backend/tests/test_participant_coaching.py`
- [x] In-app webview interstitial (Instagram/Facebook/TikTok/…): UA + capability detection in `frontend/src/utils/inAppBrowser.ts`, shown before any phase — open-in-browser steps, copy-link, Android Chrome `intent://` escape, "Try here anyway" only when recording APIs are present. QA override: `sessionStorage.qp_force_webview=1`. i18n'd in all 6 participant locales
- [x] Participant completion email (10 languages, sent on completion when the participant left an email)
- [x] Text input fallback (accessibility): `/respond` accepts `text` instead of `audio` (exactly one required; empty text mirrors the silent-audio 422). Interview UI has a "type your answer instead" toggle and the mic-permission-denied panel leads with it. i18n in all 6 participant locales.
- [x] Multi-language interviews (en/fr/de/es/it/pt participant UI; engine prompts in 10 languages; Whisper receives the interview language as a hint). TTS speaks with a native accent per language (`gpt-4o-mini-tts` instructions).

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
- [x] GDPR deletion tooling (single cascade implementation in `services/deletion.py`): researcher-facing `DELETE /projects/{id}` (full study cascade + audio files) and `DELETE /projects/{id}/participants/{pid}`; self-serve `POST /auth/delete-account` (password-confirmed; OAuth-only accounts type DELETE); admin `POST /admin/retention/run` purges participant audio N days after completion (`RETENTION_AUDIO_DAYS`, 0=off, `?dry_run=true`; transcripts kept). CreditLedger/UsageEvent/AIUsageLog audit rows are retained (pseudonymous ids, nulled where FKs say SET NULL). UI: participant delete in Responses, "Delete study permanently" (typed confirmation), Danger zone in Account → Security. Tests: `test_gdpr_deletion.py`.
- [ ] Prometheus metrics / APM dashboards
- [ ] Automated DB backups (Neon handles this for production)

---

## Data Models Summary

### Company (auth)
`id`, `name`, `email`, `password_hash`, `email_verified`, `company_size`, `role`, `industry`, `use_case`, `onboarding_completed`, `subscription_tier` (solo/team/lab/enterprise), `subscription_status`, `stripe_customer_id`, `stripe_subscription_id`, `trial_ends_at` (legacy plans only — credits-native flow ignores it), `interview_count`, `storage_bytes`, `preferred_language` (en/fr), `website_url`, `business_summary`, `research_experience`, `primary_region`, `goals_freeform`, `slack_webhook_url`, `demo_seeded_at`, `has_ever_paid` (sticky paid-once flag for paywall), `welcome_greeting_text` / `welcome_greeting_at` (Haiku-personalised /welcome greeting + 24h cache), `starter_suggestions_json` / `starter_suggestions_at` (Haiku-generated starter chips + 24h cache), `utm_source` / `utm_medium` / `utm_campaign` (measured first-touch attribution, Alembic 0064), `created_at`

### Project
`id`, `company_id`, `name`, `language`, `interview_duration_minutes`, `system_prompt`, `welcome_message`, `research_objective`, `decision_to_inform`, `timeline`, `success_criteria`, `target_customer_description`, `researcher_name`, `researcher_logo_url`, `research_context`, `privacy_policy_url`, `incentive_text`, `is_demo` (excluded from tier project quota), `created_at`, `archived_at`

### ResearchPlan (Wave E)
`id` (uuid str), `company_id` (FK Company, indexed), `name`, `rationale`, `decision_to_inform`, `timeline`, `success_criteria`, `target_customer_description`, `created_at`. The multi-step research program a researcher commits to at the end of onboarding. Has a `steps` relationship to `ResearchPlanStep` ordered by `order_index`.

### ResearchPlanStep (Wave E)
`id` (uuid str), `plan_id` (FK ResearchPlan, indexed), `order_index` (unique within plan), `method` (`voice_interview` | `quant_survey` | `workshop` | `desk_research` | `usability_test`), `title`, `purpose`, `deliverable`, `n_participants`, `duration_weeks`, `project_id` (FK Project, nullable — set when the step has been drafted as a real study), `status` (`pending` | `drafted` | `in_progress` | `completed`), `created_at`. Today V1 only drafts the first `voice_interview` step (regardless of position) as an immediate Project; other-method steps stay `pending` placeholders until those product surfaces ship.

### InterviewGuideQuestion
`id`, `project_id`, `section_index`, `section_title`, `question_index`, `main_question`, `interview_notes`, `desired_learning`, `researcher_notes`, `deprecated_at`, `sort_order`

### ScreeningQuestion
`id`, `project_id`, `question`, `options` (JSON), `disqualifying_options` (JSON), `sort_order`

### InterviewLink
`id`, `project_id`, `token` (unique, urlsafe), `is_active`, `created_at`

### Participant
`id`, `link_id`, `project_id`, `display_name`, `email`, `profession`, `age_range`, `country`, `screening_answers` (JSON snapshot of screener clicks, Alembic 0061), `status` (in_progress/completed), `quality_score`, `quality_label`, `quality_summary`, `quality_strengths`, `quality_issues`, `key_takeaways` (JSON list), `notable_quotes` (JSON list, verbatim), `started_at`, `completed_at`

### InterviewTurn
`id`, `participant_id`, `turn_index`, `question_index`, `is_follow_up`, `follow_up_index`, `question_text`, `response_transcript`, `audio_recording_url`, `tts_audio_url`, `manually_edited`, `edited_at`, `translated_response`, `translated_question`, `translation_language`, `translation_source_language`, `cleaned_response`, `cleaned_at`, `created_at`

### ProjectAnalysis
`id`, `project_id`, `version`, `status` (generating/ready/failed), `participant_count`, `report` (JSON), `filters` (JSON), `researcher_context`, `version_label` (ai_discovery/researcher_refined), `parent_version_id`, `share_token`, `generated_at`, `error`

### AnalysisThemeAnnotation
`id`, `analysis_id`, `theme_title`, `status` (confirmed/disputed/needs_evidence), `researcher_note`, unique on (analysis_id, theme_title)

### CrossStudySynthesis
`id` (uuid str), `company_id` (FK Company, indexed), `name`, `decision_question`, `study_ids` (JSON list of Study ids), `status` (generating/ready/failed), `report` (JSON decision memo — verdict, key_findings with supporting_studies + strength, conflicts, gaps, recommendations, confidence), `error`, `language` (en/fr), `generated_at`, `created_at`. Alembic 0052. See "Cross-study synthesis" in the API reference.

### ManualCode
`id`, `project_id`, `name`, `color` (hex), `sort_order`, `created_at`

### QuoteTag
`id`, `turn_id`, `code_id`, `selected_text`, `start_index`, `end_index`, `tagged_from_translation`, `created_by`, `created_at`

### TagSuggestion
`id`, `participant_id` (FK, indexed), `turn_id` (FK), `manual_code_id` (FK, nullable — set for deductive suggestions), `proposed_code_name` (nullable — set for proposed new codes), `rationale`, `selected_text`, `start_index`, `end_index` (offsets against raw `response_transcript`), `status` (pending/accepted/rejected), `created_at`. Alembic 0058.

### ProjectMemo
`id`, `project_id`, `type` (general/theme_note/tension_note/jtbd_note), `linked_key`, `content`, `created_by`, `created_at`, `updated_at`

### EmailVerificationToken
`id`, `company_id`, `token` (unique, urlsafe), `used`, `expires_at`, `created_at`

### PasswordResetToken
`id`, `company_id`, `token` (unique, urlsafe), `used`, `expires_at`, `created_at`

### Affiliate
`id` (str), `company_id` (FK), `name`, `email` (unique), `code` (unique), `website`, `how_they_found_us`, `commission_pct` (default 20%), `status` (pending/active/rejected), `payout_threshold` (default €50), `total_earned`, `total_paid`, `created_at`, `approved_at`, `notes`, `preferred_language` (en/fr, drives lifecycle emails; Alembic 0059)

### AffiliateReferral
`id` (str), `affiliate_id` (FK), `referred_company_id` (FK, unique), `signed_up_at`, `converted_at`, `commission_amount`, `status` (signed_up/converted/paid)

### AffiliatePayout
`id` (str), `affiliate_id` (FK), `amount`, `paid_at`, `notes`

### AIUsageLog
`id` (int), `company_id` (FK), `project_id` (FK), `participant_id` (FK), `operation` (indexed), `model`, `input_tokens`, `output_tokens`, `characters` (TTS), `audio_seconds` (STT), `cost_usd`, `created_at` (indexed). (No cache-token columns — cache reads/writes are priced into `cost_usd` and visible in log lines only.) **Cost is model-aware** (Opus / Sonnet / Haiku per-token rates in `services/usage_logger.py::_CLAUDE_RATES`) and **cache-aware** (cache writes 1.25× input price, cache reads 0.10×). Each Claude call also emits an INFO log line `"claude usage op=… model=… input=… output=… cache_read=… cache_write=… cost=$…"` so cache-hit rates are visible via `gcloud logging read`.

### EmailSendLog
`id` (str uuid), `company_id` (FK, indexed), `event` (str, indexed — `day_1_followup` | `trial_half_over` | `trial_ending`), `sent_at`. Unique constraint on `(company_id, event)` — append-only log that makes the Wave 3B `/admin/scheduled-emails/run` runner idempotent: a duplicate cron firing in the same window trips the constraint instead of double-sending. Alembic 0032. The Wave 3A first-response email predates this table and uses `Company.first_response_email_sent_at` instead.

### ParticipantEmailLog
Per-participant analogue of EmailSendLog for participant-facing lifecycle emails. `id` (str uuid), `participant_id` (FK, CASCADE, indexed), `event` (indexed — `interview_reminder_1` | `interview_reminder_2`), `sent_at`. Unique on `(participant_id, event)`. Alembic 0062.

### PanelProfile
`id` (int), `email` (unique), `first_name`, `age_range`, `gender`, `country`, `city`, `education`, `employment_status`, `job_function`, `seniority`, `industry`, `company_size`, `panel_consent`, `consent_at`, `consent_interview_token`, `interviews_completed`, `last_active`, `created_at`

### PanelTag
`id`, `name` (unique), `category` (interest/behavior/consumer)

### StudyInvite
`id` (uuid str), `project_id` (FK Project, indexed), `company_id` (workspace owner at send time, indexed), `profile_id` (FK PanelProfile, SET NULL), `email` (lowercased, indexed), `language`, `sent_by` (company id of the sender), `sent_at` (indexed). Unique on `(project_id, email)` — one invite per person per study, enforced at the schema level. Append-only: funnel status (started/completed) is derived by joining `participants` on `(project_id, lower(email))`, never stored. Alembic 0062.

### ParticipantMagicToken
`id`, `email` (indexed), `token` (unique, indexed), `interview_link_token`, `used`, `expires_at`, `created_at`

### BlogPost
`id` (str), `slug` (unique, indexed), `title`, `subtitle`, `content` (HTML from TipTap), `excerpt`, `cover_image_url`, `meta_title`, `meta_description`, `og_image_url`, `author_name`, `tags` (JSON text), `status` (draft/published, indexed), `published_at`, `created_at`, `updated_at`

### WebEvent
`id` (int), `event` (indexed), `location` (which CTA fired it), `path`, `visitor` (daily-rotating anonymous hash, indexed), `referrer`, `utm_source` (indexed), `utm_medium`, `utm_campaign`, `lang`, `created_at` (indexed). Composite index on `(event, created_at)` since every admin-traffic query is "this event, over this window". Written by `POST /telemetry/event`; read by `GET /admin/traffic`. Contains nothing that identifies a person. Alembic 0066.

### Plan (credits-based billing)
`id` (str PK, eg. `team`, `legacy_starter`), `public_name`, `description`, `is_public`, `is_legacy`, `is_custom`, `monthly_price_cents`, `annual_price_cents`, `currency`, `included_credits`, `credit_period` (`trial_total` | `monthly` | `annual` | `custom` | `legacy_none`), `max_editors`, `max_viewers`, `overage_price_cents`, `overage_enabled_default`, `stripe_monthly_price_id`, `stripe_annual_price_id`, `sort_order`, `created_at`, `updated_at`

### PlanEntitlement
`id`, `plan_id` (FK Plan, indexed), `key` (eg. `csv_export`, `custom_branding`, `credit_rollover_days`), `value` (JSON), `created_at`. Unique on `(plan_id, key)`. Catalogue source: `services/billing_plans.py`.

### WorkspaceSubscription
`id` (uuid str), `workspace_id` (FK Company, indexed — the workspace owner's company), `plan_id` (FK Plan), `status` (`trialing` | `active` | `past_due` | `canceled` | `unpaid` | `enterprise_custom` | `legacy`), `billing_interval` (`monthly` | `annual` | `custom` | `legacy`), `current_period_start`, `current_period_end`, `trial_start`, `trial_end`, `stripe_customer_id`, `stripe_subscription_id` (indexed), `stripe_price_id`, `overage_enabled`, `cancel_at_period_end`, `created_at`, `updated_at`

### CreditBalance
`id` (uuid str), `workspace_id` (FK Company, indexed), `subscription_id` (FK WorkspaceSubscription, nullable), `period_start`, `period_end`, `included_credits`, `purchased_credits`, `rollover_credits`, `used_credits`, `overage_credits`, `created_at`, `updated_at`. Unique on `(workspace_id, period_start, period_end)`. The `available` property = `included + purchased + rollover − used`. **Rollover policy (V2.2):** at each period transition, `grant_period_credits` carries unused **purchased + prior-rollover** credits forward into the new balance's `rollover_credits` bucket; **included** credits expire. Consumption is attributed to buckets in order included → rollover → purchased (so unused purchased survives even when usage spills past included).

### CreditLedger
Append-only audit trail. `id` (uuid str), `workspace_id` (FK Company, indexed), `balance_id` (FK CreditBalance, nullable), `participant_id` (str, indexed — not FK because participants can be deleted), `project_id` (str, nullable), `event_type` (`grant_included` | `grant_purchased` | `grant_rollover` | `consume_interview` | `overage_interview` | `refund_interview` | `adjustment_admin` | `expire_credits`, indexed), `credits_delta`, `balance_after`, `source`, `event_metadata` (JSON), `created_at`. **Idempotency:** partial unique index `uq_credit_consumed_per_participant ON (participant_id) WHERE event_type IN ('consume_interview', 'overage_interview')` — both Postgres and SQLite (≥3.8) support the partial index syntax.

### UsageEvent
`id` (uuid str), `workspace_id` (FK Company, indexed), `project_id` (nullable), `participant_id` (nullable), `event_name` (indexed), `quantity`, `billable`, `event_metadata` (JSON), `created_at` (indexed). Distinct from CreditLedger — ledger is the canonical source of truth for balances; usage events are an event-sourced stream for dashboards / alerts / finance reports.

---

## API Endpoints Reference

### Auth (`/auth`)
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/signup` | No | Create account, send nominative verification email, set 14-day trial (welcome-with-brief fires later on onboarding completion) |
| POST | `/auth/login` | No | Login (password step). 2FA accounts get `{requires_2fa, pending_token}` instead of tokens |
| POST | `/auth/login/2fa` | No | Exchange pending token + TOTP/backup code for session tokens |
| POST | `/auth/logout-all` | Yes | Revoke every session (token_version bump) |
| POST | `/auth/2fa/setup` | Yes | Start TOTP enrolment (secret + otpauth URI) |
| POST | `/auth/2fa/enable` | Yes | Confirm code, enable 2FA, return backup codes |
| POST | `/auth/2fa/disable` | Yes | Disable 2FA (password + valid code) |
| POST | `/auth/refresh` | No | Refresh access token |
| GET | `/auth/google/login` | No | Returns Google OAuth authorize URL (signed state with next path + lang) |
| GET | `/auth/google/callback` | No | Google redirect: exchange code, upsert account, bounce to `/auth/google/finish#access_token=...` |
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
| POST | `/auth/delete-account` | Yes (3/min) | GDPR self-serve deletion: password confirm (or literal `DELETE` for OAuth-only accounts), full workspace cascade, 204 |

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
| DELETE | `/projects/{id}` | Yes (editor+) | — | Permanently delete project + all data + audio files |
| DELETE | `/projects/{id}/participants/{pid}` | Yes (editor+) | — | Delete one participant (turns, tags, audio) |

> **Role enforcement:** every mutating project-scoped route (projects, links, analysis, codes/tags, memos, transcripts, quality, deletes) goes through `get_editable_project_or_404` — workspace viewers get 403 `viewer_read_only`; reads stay on `get_accessible_project_or_404`.

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
| POST | `/interview/{token}/resume` | 60/min | Check for in-progress interview. **Requires the magic-link `session_token`** whose email matches — a bare email match no longer returns a participant_id (hijack fix) |
| GET | `/interview/{token}/{pid}/resume-summary` | — | Covered topics + elapsed time |
| POST | `/interview/{token}/start` | 30/min | Create participant + first question |
| POST | `/interview/{token}/{pid}/respond` | 30/min | Submit audio OR typed `text` (exactly one), get next question. Gated by the daily spend ceiling (2x grace in-flight) |
| POST | `/interview/{token}/{pid}/skip` | — | Skip current question |
| GET | `/interview/{token}/{pid}/status` | — | Interview status |

### Analysis (`/projects/{id}/analysis`)
| Method | Path | Gate | Description |
|---|---|---|---|
| POST | `/projects/{id}/analysis` | ai_analysis | Trigger AI synthesis |
| GET | `/projects/{id}/analysis` | — | Get latest analysis (incl. `stage` + `stage_detail` while generating) |
| GET | `/projects/{id}/analysis/readiness` | — | Tagging state for the readiness gate (codebook/tag/suggestion counts, `tagging_state`) |
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
| GET | `/projects/{id}/analysis/report.html` | — | Standalone print/PDF-ready HTML findings report (`?version=` optional; EN/FR by project language; rendered by `services/report_export.py`) |
| GET | `/reports/{share_token}` | No auth | Public shared report |
| GET | `/reports/{share_token}/report.html` | No auth | Print/PDF-ready HTML of a shared report (public variant — participant appendix stripped) |

### Cross-study synthesis (`/synthesis`) — decision memos
One executive memo synthesised across 2–8 completed Studies. Inputs are each study's *final analyses* (latest ready `ProjectAnalysis` + latest ready `StudyAnalysis` when present) — raw transcripts are never re-read, so every memo claim stays walk-back-able to a study report and from there to a verbatim quote. Generated by Claude Sonnet in `services/study_synthesis.py` (rules: named-study grounding, conflicts are first-class, falsifiable recommendations, strength calibrated to cross-study corroboration). Memo language follows `Company.preferred_language`. UI: "Decision memos" section on the Studies home (`DecisionMemoSection.tsx`, shown at ≥2 studies) with a create modal + 5s polling; the memo itself is consumed as a print-ready HTML document rendered by `render_decision_memo_html` in `services/report_export.py`. Schema: Alembic 0052 (`cross_study_syntheses`).

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/synthesis/` | Yes | Start a memo (`study_ids` 2..8, optional `name` + `decision_question`); 400 `studies_not_ready` names studies lacking a ready analysis; 202 + background thread |
| GET | `/synthesis/` | Yes | List memos (status, study names, dates, `stale` — an included study has analysis evidence newer than the memo) |
| GET | `/synthesis/{id}` | Yes | Full memo (parsed report JSON) |
| GET | `/synthesis/{id}/report.html` | Yes | Print/PDF-ready decision memo document |
| DELETE | `/synthesis/{id}` | Yes | Delete a memo |

### Participant review + rewards (compensated studies)
Researcher-only tools, we never move money. `Project.incentive_text` (Setup →
participant-facing settings, max 300 chars) is the opt-in switch: it is shown
verbatim on the consent screen with a "subject to review, the researcher pays"
note, and from then on completions land as `Participant.review_status="pending"`
instead of the default `"approved"`. `Participant.counts_for_research` (hybrid:
`status == "completed" AND review_status != "rejected"`) is the single
definition of "does this interview count" and is what analysis input, study
reports, CSV export, dashboard counts, copilot snapshots and `project_state`
read. Billing, the free-preview paywall and funnel analytics deliberately keep
counting plain completions: **rejecting is never a refund**. The Responses tab
gains "To review" / "To reward" filters (only when an incentive is set),
approve / reject (optional private note) / mark-reward-sent actions on the
participant card, a bulk "mark all sent" + reward-list CSV export, the NBA rungs
`review_interviews` (weight 88, above run_analysis) and `send_rewards` (62), and
the `rewards_pending` nudge. Alembic 0071. Tests:
`backend/tests/test_participant_review.py`.

| Method | Path | Description |
|---|---|---|
| PATCH | `/projects/{id}/participants/{pid}/review` | `{status: pending\|approved\|rejected, note?}`; 400 unless the interview is completed; rejecting clears `reward_sent_at` |
| PATCH | `/projects/{id}/participants/{pid}/reward` | `{sent: bool}`; 400 `participant_not_approved` when marking sent on a non-approved row |
| POST | `/projects/{id}/participants/rewards/bulk` | `{participant_ids, sent}`; skips non-approved ids silently |
| GET | `/projects/{id}/participants/rewards.csv` | Payout list (approved rows, `?pending_only=false` for all); not behind the CSV-export entitlement |

### Export & Responses (`/projects/{id}/participants`)
| Method | Path | Gate | Description |
|---|---|---|---|
| GET | `/projects/{id}/participants` | — | List participants |
| GET | `/projects/{id}/participants/{pid}/transcript` | — | Full transcript |
| GET | `/projects/{id}/export` | export_csv | CSV export |
| POST | `/projects/{id}/participants/{pid}/quality` | ai_analysis | AI quality assessment |
| PUT | `/projects/{id}/participants/{pid}/turns/{tid}` | — | Edit transcript turn |
| POST | `/projects/{id}/participants/{pid}/translate` | — | Translate all turns to target language (Claude, cached, async, idempotent) |

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

### Research Copilot (`/copilot`)
All copilot POST endpoints return **SSE** (`text/event-stream`) — events `status`, `delta`, `done` (the terminal `done` may carry `error: true`). See "Research Copilot architecture" above. There is **no onboarding copilot surface** — onboarding is the `/welcome` wizard plus `GET /auth/onboarding/suggestions` (Haiku).

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/projects/{id}/copilot` | Yes | Run a Copilot turn for a project (interview adapter) — SSE stream. Rate-limited per account + daily spend gate. |
| GET/PUT | `/projects/{id}/copilot/conversation` | Yes | Load / persist the panel thread (optimistic `version`) |
| POST | `/surveys/{id}/copilot` | Yes | Run a Copilot turn for a survey (survey adapter) — SSE stream. Rate-limited per account + daily spend gate. |
| GET/PUT | `/surveys/{id}/copilot/conversation` | Yes | Load / persist the panel thread (optimistic `version`) |

> The legacy `/research/*` endpoints (parse-brief, suggest-objective, suggest-scope, suggest-questions) have been **removed**. Their flow is now driven by the Copilot via tool calls / proposal actions.

### Billing (`/billing`)
| Method | Path | Description |
|---|---|---|
| GET | `/billing/plans` | List subscription tiers |
| GET | `/billing/status` | Current subscription |
| POST | `/billing/checkout` | Create Stripe Checkout session |
| POST | `/billing/portal` | Open Stripe Customer Portal |
| POST | `/billing/webhook` | Stripe webhook handler (subscription create/update/delete, invoice payment succeeded/**failed** → past_due, checkout completed, **charge.refunded** → credit-pack clawback via `revoke_purchased_credits` (idempotent per session, ledger `revoke_purchased`), **charge.dispute.\*** → UsageEvent for admin review) |

### Affiliate (`/affiliates`)
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/affiliates/apply` | No (5/min) | Apply to become affiliate (captures `preferred_language`; sends confirmation email) |
| POST | `/affiliates/login-request` | No (5/min) | Email a 30-min magic sign-in link (always 200; the referral code is public, so it is never a credential) |
| POST | `/affiliates/login/verify` | No (10/min) | Exchange the emailed magic token for a 24h dashboard session |
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

### Panel recontact (`/projects/{id}/invite*` + `/workspace/panel` + `/panel/opt-out`)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/projects/{id}/invite-candidates` | Yes | Workspace pool with per-person `blocked_reason` (already_participated / already_invited / cooldown) + guardrail numbers |
| POST | `/projects/{id}/invites` | Yes (editor, verified email) | Send invites to selected `profile_ids` (claim-then-send, daily cap, 100/batch); returns `{sent, skipped[]}` |
| GET | `/projects/{id}/invites` | Yes | Invite list + derived funnel `{invited, started, completed}` |
| GET | `/workspace/panel` | Yes | Consented pool with participation + invite history (V2 `/pool` page) |
| POST | `/panel/opt-out` | No (20/min) | Withdraw recontact consent via signed token from the invite email footer |

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
| GET | `/admin/traffic` | X-Admin-Key | Marketing-funnel rollup (`?days=`): traffic, CTA clicks, signups, signup rate, per-channel breakdowns |
| GET | `/admin/costs/company/{company_id}` | X-Admin-Key | Per-company cost breakdown |
| POST | `/admin/scheduled-emails/run` | X-Admin-Key | Run the lifecycle-email cron pass (Day-1, Day-7, Day-12). Supports `?dry_run=true`. Idempotent via `email_send_log` unique constraint. Hit hourly by Cloud Scheduler. Returns per-event sent/skipped counts. |
| POST | `/admin/retention/run` | X-Admin-Key | Purge participant audio for interviews completed > `RETENTION_AUDIO_DAYS` days ago (0=disabled). `?dry_run=true`, `?days=` override. Transcripts kept; URLs nulled after file deletion. |

### Lifecycle emails — scheduling
The Wave 3B endpoint `/admin/scheduled-emails/run` is designed to be hit hourly by an external cron (Cloud Run scales to zero, no persistent worker). To wire it up:

```bash
# One-time setup — schedule the hourly cron on Cloud Scheduler.
gcloud scheduler jobs create http qualipulse-lifecycle-emails \
  --schedule="0 * * * *" \
  --uri="https://api.qualipulse.com/admin/scheduled-emails/run" \
  --http-method=POST \
  --headers="Authorization=Bearer $ADMIN_SECRET_KEY" \
  --time-zone="Europe/Paris" \
  --location=europe-west1
```

**Currently sent:**
- `day_1_followup` — 18h–7d after signup, only if `onboarding_completed=true` and email verified
- `interview_reminder_1` / `interview_reminder_2` — participant-facing nudges for interviews abandoned mid-way. Reminder 1 fires after ~1 day idle (22h–4d window since the last answered turn); reminder 2 (final copy) ~2 days after reminder 1 (44h gap), so the two land on different days; both stop 10 days after start. Eligibility: `status=in_progress`, **verified** participant email (the email embeds a 7-day magic link that re-establishes the interview session, so typo'd addresses must never get one), active link, non-archived non-demo project, and no completed participant with the same email on the same link. Idempotent per (participant × event) via `participant_email_log`. Templates in `services/email.py::INTERVIEW_REMINDER_EMAILS` (10 languages, participant's language first, then project language). To make the click actually work, `/interview/{token}/resume` now accepts sessions idle up to 7 days (`RESUME_MAX_IDLE_DAYS`) and **rebases the pacing clock** on resume after >30 min idle (shifts `started_at` so elapsed = time actually spent interviewing, otherwise the engine's close gate would fire instantly). Tests: `backend/tests/test_interview_reminders.py`. Alembic 0062.

**Retired:** `trial_half_over` (Day-7) and `trial_ending` (Day-12) were retired with the credits-native billing model — credits gate usage, not calendar days. Their HTML templates remain in `services/email.py` as dead code in case we revive them, but the cron no longer fires them.

Each Company × event sends at most once thanks to the unique constraint on `email_send_log (company_id, event)`. Test with `?dry_run=true` before flipping on the cron.

### Telemetry (`/telemetry` — public, no auth)
| Method | Path | Rate limit | Description |
|---|---|---|---|
| POST | `/telemetry/client-error` | 10/min | Uncaught SPA errors, logged at ERROR into Sentry + Cloud Logging |
| POST | `/telemetry/event` | 60/min | One anonymous funnel event from the marketing site (see "Web analytics" above) |

### Health
| Method | Path | Description |
|---|---|---|
| GET | `/` | Shallow health check (status + env) |
| GET | `/health` | Deep health check (verifies DB connection) |
