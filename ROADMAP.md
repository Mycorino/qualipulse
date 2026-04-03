# AutoInterview — Product Roadmap

> Last updated: 2026-04-03

## Product Vision
A SaaS platform that lets companies run AI-driven voice interviews at scale. Researchers design the guide, share a link, and participants complete interviews in-browser. AI transcribes, analyses, and surfaces insights automatically.

## Current Status: Private Beta

---

## Track 1: Participant Experience
> Everything a research participant sees and interacts with

| # | Feature | Status | Priority | Notes |
|---|---------|--------|----------|-------|
| 1.1 | Consent screen | ✅ Done | P0 | |
| 1.2 | Landing form (name, profession, age range, country, email) | ✅ Done | P0 | All fields optional |
| 1.3 | Screening questions with disqualification | ✅ Done | P0 | One-at-a-time, progress bar, back button |
| 1.4 | Voice interview (record → STT → Claude → TTS) | ✅ Done | P0 | |
| 1.5 | Email-based interview resume | ✅ Done | P1 | Cross-device, shows topics covered + elapsed time |
| 1.6 | Session-storage resume (same device/tab) | ✅ Done | P1 | survives page reload |
| 1.7 | Interview progress label (Q3 of 5 / Follow-up) | ✅ Done | P1 | |
| 1.8 | Progress bar (visual fill across questions) | ✅ Done | P1 | |
| 1.9 | Live time remaining countdown | ✅ Done | P1 | Warning/critical colour states |
| 1.10 | Mic permission error UI | ✅ Done | P1 | |
| 1.11 | Mute TTS button | ✅ Done | P1 | |
| 1.12 | Skip question button (API endpoint) | ✅ Done | P1 | Backend done; UI button not wired in Interview.tsx yet |
| 1.13 | Interview status endpoint | ✅ Done | P2 | `GET /{token}/{pid}/status` |
| 1.14 | Mic test before first question | ⬜ Planned | P0 | Level meter |
| 1.15 | Re-record button before submitting | ⬜ Planned | P0 | Preview state (Submit / Re-record) |
| 1.16 | Retry with same blob on network error | ⬜ Planned | P0 | "Try again" without re-recording |
| 1.17 | TTS "done" signal — record button enables after audio | ⬜ Planned | P1 | |
| 1.18 | Processing step messages (Transcribing → Thinking…) | ⬜ Planned | P1 | |
| 1.19 | Recording time limit (3 min countdown) | ⬜ Planned | P1 | |
| 1.20 | Transcript confirmation after each answer | ⬜ Planned | P2 | Brief flash |
| 1.21 | Better completion screen (personalised, answer count, next steps) | ⬜ Planned | P1 | Currently generic |
| 1.22 | Completion email to participant | ⬜ Planned | P1 | Needs email trigger after complete |
| 1.23 | Skip question — wire UI button in Interview.tsx | ⬜ Planned | P2 | API exists |
| 1.24 | Typing fallback (text input instead of voice) | ⬜ Planned | P2 | Accessibility |
| 1.25 | Warm-up / practice question | ⬜ Planned | P3 | |
| 1.26 | Captions on TTS audio | ⬜ Planned | P3 | Accessibility |
| 1.27 | Keyboard shortcuts (spacebar to record) | ⬜ Planned | P3 | |

---

## Track 2: Researcher Experience
> Everything a researcher / company sees to manage projects and analyse results

| # | Feature | Status | Priority | Notes |
|---|---------|--------|----------|-------|
| 2.1 | Signup / login (JWT) | ✅ Done | P0 | |
| 2.2 | Refresh token + auto-refresh on 401 | ✅ Done | P0 | Axios interceptor |
| 2.3 | Password reset flow | ✅ Done | P0 | ForgotPassword + ResetPassword pages; console email in dev |
| 2.4 | Project creation wizard (4 steps: Brief → Objective → Scope → Questionnaire) | ✅ Done | P0 | |
| 2.5 | AI brief parsing (from text + uploaded files) | ✅ Done | P1 | `/research/parse-brief` |
| 2.6 | AI-suggested research objective + learning goals | ✅ Done | P1 | `/research/suggest-objective` |
| 2.7 | AI-suggested scope (audience, duration, language, participant count) | ✅ Done | P1 | `/research/suggest-scope` |
| 2.8 | AI-generated interview guide from objective | ✅ Done | P1 | `/research/suggest-questions` |
| 2.9 | CSV import/export for interview guides | ✅ Done | P2 | |
| 2.10 | Shareable interview links (multiple per project) | ✅ Done | P0 | |
| 2.11 | Link toggle (active/inactive) | ✅ Done | P1 | |
| 2.12 | Screening question editor (Setup tab) | ✅ Done | P1 | Inline collapse/expand, toggle disqualifying per option |
| 2.13 | Per-question notes, desired learning, deprecation (Setup tab) | ✅ Done | P2 | |
| 2.14 | Welcome message per project | ✅ Done | P2 | |
| 2.15 | System prompt editing per project | ✅ Done | P2 | |
| 2.16 | Overview tab (stats, completion rate, link management) | ✅ Done | P1 | |
| 2.17 | Responses tab (participant list, demographics, quality badges) | ✅ Done | P1 | |
| 2.18 | Transcript viewer with full turn-by-turn display | ✅ Done | P1 | |
| 2.19 | Transcript editing (manual corrections, saved to DB) | ✅ Done | P1 | |
| 2.20 | Quote tagging + codebook (select text → assign code) | ✅ Done | P1 | CRUD codes + tags |
| 2.21 | AI analysis report (themes, JTBDs, tensions, recommendations) | ✅ Done | P1 | Background thread + 5-min watchdog |
| 2.22 | Segment heatmap (profession / age / country vs themes) | ✅ Done | P2 | |
| 2.23 | Analysis filtering by demographic segment | ✅ Done | P2 | `filter_by` + `filter_values` params |
| 2.24 | Project memos (general, theme/JTBD/tension-linked) | ✅ Done | P2 | CRUD memos |
| 2.25 | AI quality assessment per participant (Claude-powered) | ✅ Done | P2 | `/participants/{pid}/quality` |
| 2.26 | CSV export of all transcripts | ✅ Done | P2 | Streaming response |
| 2.27 | Account & billing settings page (Profile + Plan tabs) | ✅ Done | P1 | |
| 2.28 | Resume summary endpoint for researchers | ✅ Done | P2 | Shows covered questions + elapsed time |
| 2.29 | Email verification on signup | ⬜ Planned | P1 | Needs email service |
| 2.30 | Interview link expiration dates | ⬜ Planned | P2 | |
| 2.31 | Interview link max-uses limit | ⬜ Planned | P2 | |
| 2.32 | Email invitations to participants | ⬜ Planned | P1 | Template exists (`send_interview_invite`) |
| 2.33 | Soft deletes (archive vs. hard delete) | ⬜ Planned | P2 | |
| 2.34 | Audit log (who changed what, when) | ⬜ Planned | P2 | |
| 2.35 | Dashboard analytics (cross-project) | ⬜ Planned | P2 | |
| 2.36 | Multi-language TTS voices | ⬜ Planned | P3 | Language field exists on projects |
| 2.37 | Analysis export (JSON download, Markdown copy) | ⬜ Planned | P2 | |
| 2.38 | Save profile changes (name) in AccountSettings | ⬜ Planned | P1 | UI exists, API call not yet wired |
| 2.39 | Change password from AccountSettings | ⬜ Planned | P1 | UI exists, API call not yet wired |

---

## Track 3: Team & Collaboration
> Multi-user access within a company account

| # | Feature | Status | Priority | Notes |
|---|---------|--------|----------|-------|
| 3.1 | Single-user company accounts | ✅ Done | P0 | Current model |
| 3.2 | Team members field in tier limits | ✅ Done | P1 | Defined in feature_gates; not enforced |
| 3.3 | Team member invite flow | ⬜ Planned | P1 | |
| 3.4 | Role-based access (owner/editor/viewer) | ⬜ Planned | P1 | |
| 3.5 | Project-level sharing | ⬜ Planned | P2 | |
| 3.6 | Comment threads on transcripts | ⬜ Planned | P3 | |
| 3.7 | @mentions in memos | ⬜ Planned | P3 | |

---

## Track 4: Security & Compliance
> Production-readiness, data protection, trust

| # | Feature | Status | Priority | Notes |
|---|---------|--------|----------|-------|
| 4.1 | JWT authentication (access + refresh tokens) | ✅ Done | P0 | |
| 4.2 | Rate limiting on all public endpoints | ✅ Done | P0 | slowapi — 10/min login, 30/min interview |
| 4.3 | Security headers (X-Frame-Options, X-Content-Type-Options, X-XSS-Protection, Referrer-Policy) | ✅ Done | P0 | |
| 4.4 | HSTS in production | ✅ Done | P0 | Conditional on `is_production` |
| 4.5 | CORS from env var (no wildcard in prod) | ✅ Done | P0 | `ALLOWED_ORIGINS` setting |
| 4.6 | Request size limits (configurable, default 50MB) | ✅ Done | P0 | `MAX_AUDIO_SIZE_MB` setting |
| 4.7 | Structured JSON logging | ✅ Done | P0 | |
| 4.8 | Sentry error tracking (stub) | ✅ Done | P1 | Active when `SENTRY_DSN` is set |
| 4.9 | Docs hidden in production | ✅ Done | P1 | `/docs` and `/redoc` disabled |
| 4.10 | Password reset token-based (1-hour expiry, single-use) | ✅ Done | P0 | |
| 4.11 | Interview turn deduplication | ✅ Done | P1 | Checks last turn before processing |
| 4.12 | Analysis timeout watchdog | ✅ Done | P1 | 5-min limit |
| 4.13 | Directory traversal protection on audio serve | ✅ Done | P0 | |
| 4.14 | Ownership check returns 404 not 403 (prevents enumeration) | ✅ Done | P1 | |
| 4.15 | PostgreSQL migration | ⬜ Planned | P0 | Currently SQLite |
| 4.16 | Database backups | ⬜ Planned | P0 | |
| 4.17 | GDPR data export (participant data) | ⬜ Planned | P1 | |
| 4.18 | GDPR right-to-erasure endpoint | ⬜ Planned | P1 | |
| 4.19 | Consent timestamp recording | ⬜ Planned | P1 | Currently not persisted to DB |
| 4.20 | Data retention policy config | ⬜ Planned | P2 | |
| 4.21 | SOC 2 / penetration test | ⬜ Planned | P3 | Pre-enterprise |

---

## Track 5: Infrastructure & DevOps
> Reliability, scalability, deployment

| # | Feature | Status | Priority | Notes |
|---|---------|--------|----------|-------|
| 5.1 | Local dev environment (SQLite + disk storage) | ✅ Done | P0 | |
| 5.2 | Cloudflare R2 audio storage | ✅ Done | P1 | Falls back to local disk if env vars absent |
| 5.3 | Uvicorn ASGI server | ✅ Done | P0 | Dev only |
| 5.4 | Alembic migration for researcher features | ✅ Done | P1 | `0001_add_researcher_features.py` |
| 5.5 | Auto-create tables on startup (`create_all`) | ✅ Done | P0 | For fresh installs |
| 5.6 | Health check endpoint (`GET /`) | ✅ Done | P0 | |
| 5.7 | PostgreSQL | ⬜ Planned | P0 | Pre-launch |
| 5.8 | Celery + Redis (async task queue) | ⬜ Planned | P1 | Replace background threads for analysis |
| 5.9 | Docker / docker-compose | ⬜ Planned | P1 | |
| 5.10 | CI/CD pipeline (GitHub Actions) | ⬜ Planned | P1 | |
| 5.11 | Staging environment | ⬜ Planned | P1 | |
| 5.12 | Health checks + uptime monitoring | ⬜ Planned | P1 | |
| 5.13 | Prometheus / Grafana metrics | ⬜ Planned | P2 | |
| 5.14 | CDN for frontend | ⬜ Planned | P1 | |
| 5.15 | Auto-scaling | ⬜ Planned | P3 | Post-launch |

---

## Track 6: Monetisation
> Billing, subscriptions, usage tracking

| # | Feature | Status | Priority | Notes |
|---|---------|--------|----------|-------|
| 6.1 | Subscription tier model (free/starter/pro/enterprise) | ✅ Done | P0 | Defined in `feature_gates.py` |
| 6.2 | Feature gates service (`require_feature`, `require_project_limit`, `require_participant_limit`) | ✅ Done | P0 | Functions exist; not called from all endpoints yet |
| 6.3 | Billing status API (`GET /billing/status`) | ✅ Done | P0 | |
| 6.4 | Plans list API (`GET /billing/plans`) | ✅ Done | P0 | |
| 6.5 | Account & billing UI | ✅ Done | P1 | |
| 6.6 | Stripe Checkout integration | ✅ Done | P0 | Needs `STRIPE_SECRET_KEY` + price IDs |
| 6.7 | Stripe Customer Portal | ✅ Done | P1 | |
| 6.8 | Stripe webhook handler (subscription created/updated/deleted) | ✅ Done | P0 | |
| 6.9 | Usage fields on Company model (`interview_count`, `storage_bytes`) | ✅ Done | P1 | Fields exist; not incremented yet |
| 6.10 | Usage limits enforcement (gates called at request time) | ⬜ Planned | P0 | Gate functions exist but not enforced on create endpoints |
| 6.11 | Free trial period (14 days) | ⬜ Planned | P1 | `trial_ends_at` field exists on Company |
| 6.12 | Overage alerts | ⬜ Planned | P2 | |
| 6.13 | Annual billing discount | ⬜ Planned | P2 | |
| 6.14 | Usage invoice / receipt emails | ⬜ Planned | P2 | |
| 6.15 | Increment `interview_count` and `storage_bytes` on use | ⬜ Planned | P1 | Fields exist; write logic missing |

---

## Track 7: Email & Notifications
> Transactional and operational emails

| # | Feature | Status | Priority | Notes |
|---|---------|--------|----------|-------|
| 7.1 | Email service abstraction (console fallback / SendGrid) | ✅ Done | P0 | |
| 7.2 | Welcome email on signup | ✅ Done | P1 | Console in dev |
| 7.3 | Password reset email | ✅ Done | P0 | |
| 7.4 | Analysis ready notification (template) | ✅ Done | P1 | `send_analysis_ready` exists; trigger not wired |
| 7.5 | Interview invite email (template) | ✅ Done | P1 | `send_interview_invite` exists; no send endpoint yet |
| 7.6 | SendGrid account setup | ⬜ Planned | P0 | External — set `SENDGRID_API_KEY` |
| 7.7 | Participant completion email | ⬜ Planned | P1 | Template needed + trigger at interview complete |
| 7.8 | Email templates (branded HTML) | ⬜ Planned | P2 | Currently plain inline HTML |
| 7.9 | Unsubscribe / opt-out | ⬜ Planned | P1 | CAN-SPAM compliance |
| 7.10 | Wire analysis-ready email on analysis completion | ⬜ Planned | P1 | Template exists |
| 7.11 | Weekly digest for researchers | ⬜ Planned | P3 | |

---

## Launch Checklist (Private Beta → Public Beta)

### Must have before launch
- [ ] 4.15 PostgreSQL migration
- [ ] 5.9 Docker / docker-compose
- [ ] 5.10 CI/CD pipeline
- [ ] 6.10 Usage limits enforcement (gates called on create endpoints)
- [ ] 7.6 SendGrid account setup + `SENDGRID_API_KEY` configured
- [ ] 4.17 GDPR data export
- [ ] `ALLOWED_ORIGINS` set to production domain (not wildcard)
- [ ] `SECRET_KEY` rotated from default
- [ ] Stripe keys + price IDs configured

### Should have at launch
- [ ] 5.11 Staging environment
- [ ] 3.3 Team member invite flow
- [ ] 2.32 Email invitations to participants (endpoint needed)
- [ ] 6.11 Free trial period (use existing `trial_ends_at` field)
- [ ] 4.16 Database backups
- [ ] 6.15 Increment usage counters
- [ ] 2.38 Wire profile save in AccountSettings
- [ ] 2.39 Wire change password in AccountSettings

### Nice to have
- [ ] 1.14 Mic test before first question
- [ ] 1.15 Re-record before submitting
- [ ] 1.21 Personalised completion screen
- [ ] 5.8 Celery + Redis for async analysis

---

## Pricing Model

| Tier | Price | Projects | Participants/Project | Questions/Guide | Links/Project | AI Analysis | CSV Export | Team |
|------|-------|----------|----------------------|-----------------|---------------|-------------|------------|------|
| Free | $0 | 1 | 10 | 5 | 1 | No | No | 1 |
| Starter | $49/mo | 5 | 50 | 15 | 3 | Yes | Yes | 3 |
| Pro | $149/mo | Unlimited | 500 | 30 | 10 | Yes | Yes | 10 |
| Enterprise | Custom | Unlimited | Unlimited | Unlimited | Unlimited | Yes | Yes | Unlimited |
