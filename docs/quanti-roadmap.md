# Qualipulse Quanti Roadmap

Post-design-system implementation plan. The 16 components in `frontend/src/components/` and the demo at `/design-system/quanti/report` are presentational primitives — every section below is about wiring them to a real backend, real data, and real billing without breaking the qualitative product or the credits system shipped in Alembic 0022.

This doc is opinionated. Where there's a one-way door, one option is recommended and the others are killed. Where a decision still needs a human, it's in section 6 — not buried in prose.

---

## 1. Data-model decisions (one-way doors)

### 1.1 Survey vs. Project relationship — **Recommend: introduce a `Study` parent**

| Option | Verdict | Reasoning |
|---|---|---|
| `Survey` extends `Project` polymorphically | Reject | `Project` is already overloaded (system_prompt, warmup_enabled, interview_duration_minutes — none of which mean anything for a survey). Polymorphism here metastasises. |
| `Survey` standalone, no shared parent | Reject | Defeats the wedge. The whole strategic point is "show me themes that over-index on respondents who scored ≤6 on Q3" — that join needs a shared parent on day one. |
| **`Study` parent; `Project` (interview) and `Survey` are siblings** | **Pick** | Cleanly encodes the strategy. `Project` keeps its existing routes; `Survey` gets its own table; `Study` is where "instruments" attach and where Participant identity lives. |

**Concrete shape:**

- New table `studies` (`backend/app/models/study.py`): `id`, `company_id`, `name`, `created_at`, `archived_at`. Thin.
- Add nullable `study_id` to `projects` (Alembic 0024). Backfill: each existing project gets its own Study with the same name. Rule: every project belongs to exactly one Study; a Study can have 0–1 Projects (interview track) and 0..N Surveys.
- New `surveys` table (`backend/app/models/survey.py`) keyed to `study_id`.
- Existing `screening_questions` stay on `Project` for now (they're already wired into the interview flow). The new survey type "screener" replaces them functionally — see section 2 for migration.
- Routes: `/studies/{id}` is the new aggregate view; `/projects/{id}` and `/surveys/{id}` keep working for the instrument-specific editors.

**Why not just bolt surveys onto Project:** the existing `Project` model is the *interview track*. Conflating them now creates a refactor debt that every future feature will pay interest on.

### 1.2 Link type — **Recommend: separate `SurveyLink` table**

| Option | Verdict | Reasoning |
|---|---|---|
| Add `link_type` discriminator to `interview_links` | Reject | Token namespace shared (collision risk in section 3), and the per-link config diverges hard — surveys need open/close windows, response caps, anonymous-vs-identified flag; interviews need none of those. Coupling pays no dividend. |
| Polymorphic `study_links` superclass | Reject | All the cost of polymorphism (joined-table or single-table inheritance), zero reuse — the two link types share `token` and `is_active` and nothing else. |
| **New `survey_links` table, parallel to `interview_links`** | **Pick** | Clean separation. Token uniqueness enforced **across both** via a single shared random space (32-byte URL-safe; collision probability is for-all-practical-purposes zero) plus an app-level check on insert. |

**File:** `backend/app/models/survey.py:SurveyLink`. Columns: `id`, `survey_id` (FK), `token` (unique index), `is_active`, `opens_at`, `closes_at`, `target_n` (nullable, for sample-size tracking), `response_cap` (nullable), `is_anonymous` (bool, **default False** — see Decision 3), `created_at`.

**Token collision mitigation:** before insert, check both `interview_links.token` and `survey_links.token`. Cheap (both indexed). Alternative is a shared `tokens` table — overkill for the collision rate.

### 1.3 Participant identity across instruments — **Recommend: `StudyParticipant` promoted to per-Study, joined by `magic_token` first, email second**

This is the most consequential decision in the doc. The wedge requires that the same human's screener answers, interview transcript, and validation survey end up on one row — without tripping the privacy regime that emails imply.

| Option | Verdict | Reasoning |
|---|---|---|
| Keep `Participant` per-link, join across links by email | Reject | Email is dirty (capitalization, plus-addressing, typos). Anonymous surveys break it entirely. Re-consent rules become a nightmare. |
| Magic token only | Reject | Researcher-distributed links (panel sourcing) won't have a token until first response. |
| **`StudyParticipant` per-Study, identified by `magic_token` (preferred) → falling back to normalized email → falling back to anonymous random id; per-link `Participant` rows demoted to "instrument response" rows that FK up** | **Pick** | Solves the wedge. Privacy-clean. Magic token is the strong identity (works for anonymous and panel-sourced); email is the soft join key for cases where the researcher uploads a CSV of emails to invite. |

**Concrete shape:**

- New table `study_participants` (`backend/app/models/study.py`): `id`, `study_id`, `magic_token` (unique, nullable), `email_normalized` (nullable, indexed), `display_name` (nullable), `panel_profile_id` (FK to existing `panel_profiles`, nullable), `created_at`.
- Existing `participants` table gets a nullable `study_participant_id` FK (Alembic 0024 backfill: one StudyParticipant per existing Participant).
- New `survey_responses` table FKs to `study_participants` directly (not to a per-survey participant — that's the whole point).
- Resolution order at write time: (1) magic token from URL? attach. (2) Email provided + matches existing StudyParticipant in this Study? attach + log a `usage_event` for audit. (3) Otherwise create new.
- **Re-consent rule:** an existing StudyParticipant from a *prior Study* in the same workspace, matched by email, requires fresh consent acceptance before any new instrument fires. Encode this as a `consent_acknowledgments` row (`study_participant_id`, `study_id`, `accepted_at`, `consent_text_hash`). Section 3 risk register flags the bad outcome if we skip this.

**Existing `ParticipantMagicToken`:** repurpose for the StudyParticipant case. Add `study_participant_id` FK. Existing rows keep working (token → participant resolution unchanged for in-flight interviews).

### 1.4 Survey question schema — **Recommend: one `survey_questions` table with typed columns + JSON `config`**

| Option | Verdict | Reasoning |
|---|---|---|
| One table per type (likert_questions, mc_questions, …) | Reject | Reorder is `INSERT … SELECT` across N tables. Cross-question analytics queries become unions. Scales horribly. |
| Pure JSON blob per question | Reject | Can't index by `type`. AI question-quality checks have to deserialize every row. |
| **Polymorphic single table: `id`, `survey_id`, `sort_order`, `type` (enum-as-string), `prompt`, `is_required`, `config` (JSON), `created_at`, `deprecated_at`** | **Pick** | Reorder is a single UPDATE. Type-specific config (Likert anchors, MC choices, scale length) goes in JSON. `type` is indexed for the analytics queries that need it. |

**Question types in v1:** `likert` (1–5 or 1–7 anchored), `mc_single`, `mc_multi`, `nps` (0–10), `open_text`, `short_text`. **Killed:** sliders, MaxDiff, conjoint, ranking — see kill list, section 5.

**Config schemas (validated in Pydantic, `backend/app/schemas/survey.py`):**

```
likert: { scale: 5 | 7, anchors: [string, string], reverse_coded: bool }
mc_single: { choices: [{id, label}], randomize: bool, has_other: bool }
mc_multi: same as mc_single + max_selectable: int
nps: { context: string }   # "How likely to recommend X?"
open_text: { max_chars: int, ai_cluster: bool }
short_text: { max_chars: int }
```

**Reorderability:** mid-survey reorder rewrites `sort_order` only. Question deletion is soft via `deprecated_at` — never hard delete a question that has responses, because the response answers FK to it.

### 1.5 Response storage — **Recommend: `survey_responses` (one per completion) + `survey_response_answers` (N per response)**

| Option | Verdict | Reasoning |
|---|---|---|
| Wide-row JSON blob per response | Reject | Every aggregation reads + parses every blob. Cross-tabs are unworkable. AI clustering of open-text needs row-level access, which means re-parsing the blob on every analysis run. |
| **Two-table normalized** | **Pick** | Aggregations are SQL `GROUP BY question_id`. Cross-tabs are joins. AI clustering pulls only `type='open_text'` rows. |

**Schema:**

- `survey_responses`: `id`, `survey_id`, `study_participant_id`, `survey_link_id`, `started_at`, `completed_at` (nullable — partial responses are real), `submission_metadata` (JSON: device, locale, completion_seconds), `is_excluded` (bool, for quality filtering), `quality_flags` (JSON list).
- `survey_response_answers`: `id`, `response_id`, `question_id`, `answered_at`, `value_numeric` (nullable — Likert/NPS), `value_text` (nullable — open/short), `value_choice_ids` (JSON array of choice IDs — MC), `time_to_answer_ms` (for speeder detection).

**Three value columns (numeric / text / choices) is intentional.** It makes type-specific aggregation queries trivial without polymorphism gymnastics. Indexed: `(question_id, value_numeric)` for Likert/NPS, `(question_id)` for everything.

**Partial responses:** kept by default, marked via `completed_at IS NULL`. Methodology surface (section 1.7) reports both "started" and "completed" n — completion rate is part of the trustworthiness contract.

### 1.6 Credit-flow integration — **Recommend: explicit non-integration; document the boundary in code**

Surveys do **not** touch `credit_balances` or `credit_ledger`. Period. The mechanic that drives credit consumption is **conversion from survey → interview** (the Screener Bridge), not survey response volume.

**What we add instead — `survey_quotas` (tracked per WorkspaceSubscription period):**

- New `PlanEntitlement` keys (no schema change to `plan_entitlements`, just new rows seeded):
  - `survey_responses_per_period` (int): Trial 100 / Exploration 500 / Team 2,500 / Agency 10,000 / Enterprise custom. (See Decision 2.)
  - `surveys_active_max` (int): Trial 1 / Exploration 5 / Team 20 / Agency unlimited / Enterprise unlimited.
  - `survey_questions_per_survey_max` (int, soft cap): 30 across all plans.
- Counter is computed from `survey_responses` rows in the current period — no separate counter table. Cheap with a `(workspace_id, completed_at)` index. (`survey_responses` gets `workspace_id` denormalized at insert for this query.)
- When quota exceeded: the public response page shows "This survey is closed." The researcher dashboard shows an upgrade nudge. **No overage billing for surveys in v1.** Hard cap.
- Emit a `usage_event` named `survey_response_received` (billable=False) so finance can see volume without it touching the credit ledger.

**Why this matters in writing:** without an explicit "surveys do not consume credits" rule, future-Claude or future-engineer will inevitably add a `consume_survey` ledger event "for symmetry." That breaks the strategy. The kill list in section 5 carries this forward.

**Credit consumption stays exactly where it is today:** 1 credit on interview completion, charged via the existing `consume_interview` ledger event in `BillingService`. The Screener Bridge "invite 89 filtered respondents to interview" flow creates `interview_links` and consumes credits the same way the existing direct-invite flow does. Zero new code paths in `billing/`.

### 1.7 Methodology metadata — **Recommend: stored on Survey, computed on read**

The methodologist's hard line ("any survey result without sample size, completion rate, fielding window, and CI visible is untrustworthy") is enforced at the **render layer**, but the data has to come from somewhere:

- `surveys.fielding_started_at`, `surveys.fielding_ended_at` — set automatically from first/last `survey_responses.completed_at`. Researcher can override.
- Sample size, completion rate — computed live from `survey_responses` on read. No caching in v1; with proper indexes this is sub-50ms up to ~50k responses. Add a Redis cache later if it bites.
- Wilson 95% CI computation lives in `backend/app/services/stats.py` (new file). **No normal approximation anywhere in the codebase.** Below n=30 segments, the API returns `{count: int, percentage: null, ci: null}` and the frontend renders "23 of 28 respondents" — never `82%`. This rule is enforced backend-side so a frontend bug can't accidentally show forbidden percentages.

---

## 2. Sprint sequencing (PR-sized chunks)

The wedge is screener-survey → interview. Sprint 6 ships a wide vertical slice that proves the wedge works end-to-end with placeholder UI. Subsequent sprints widen the slice. Each sprint is ONE PR.

| Sprint | Deliverable | NOT included | Depends on | Status |
|---|---|---|---|---|
| **6: Schema + minimal API** | Alembic 0024 (`studies`, `surveys`, `survey_questions`, `survey_links`, `survey_responses`, `survey_response_answers`, `study_participants`, `consent_acknowledgments`). FastAPI routes: `POST/GET/PATCH/DELETE /surveys`, `POST/GET /surveys/{id}/questions`, `POST /surveys/{id}/responses` (public). | Frontend. AI question linting. Quotas. Bridge. | Nothing. | ✅ Shipped |
| **7: Survey builder UI** | `/surveys/{id}/edit` wiring `SurveyQuestionEditor`, `QuestionTypeCard`. Drag-reorder. Autosave. `/surveys/{id}/preview`. | Live dashboard preview. Branching. Templates. AI assist. | Sprint 6. | ✅ Shipped |
| **8: Public response + basic dashboard** | `/r/{token}` public response page. `/surveys/{id}/dashboard` renders `DashboardShell` + `StatHero` + `ChartCard` per question + `MethodologyBox`. Wilson CIs. <n=30 rule enforced. | Cross-tabs. Segment compare. AI clustering. Bridge. | Sprint 7. | ✅ Shipped |
| **9: Screener Bridge — the wedge core** | `ScreenerBridge` filters respondents by answer values. Draft+review modal creates one `interview_link` per matched respondent + fires invite emails. Credit consumption reuses existing `consume_interview` ledger event. | Cross-tabs. Validation surveys. Mixed-methods report. | Sprint 8 + existing interview flow. | ✅ Shipped |
| **9.5: Study Overview page** (added after consultant audit) | `/studies/:id` becomes the primary research workspace. Progress checklist (screener live → N responses → segments identified → interviews completed → report ready). Recommended-next-action chip. Tabs: Overview / Surveys / Interviews / Participants / Report. Study creation stays **implicit** (Decision 8) — no "create Study" UI flow. | Progress-driven prompts (Sprint 10). Mixed-methods report tab content (Sprint 11). | Sprint 6 schema. | 🚧 In flight |
| **10: Segment Discoveries** *(was: cross-tabs + compare)* | Backend detects over-indexing segments via cross-tab + chi-square + min-n guard. Frontend leads the dashboard with `SegmentSuggestionCard` per discovery, each carrying a confidence pill (`directional` / `supported` / `strong`) per the methodology contract. "Interview this segment" CTA wires straight to the Bridge from Sprint 9. Power-user manual cross-tab view stays but is demoted below suggestions. **AI detects patterns; researcher chooses what to act on; Claude never authors findings below n=30.** | AI synthesis (Sprint 11). PrioritizationMatrix. Saved segments persisted to DB (Sprint 11). | Sprint 9 (Bridge) + 9.5 (Study Overview). |  |
| **11: Quantified Themes report** *(was: mixed-methods report)* | New `study_analyses` table. `POST /studies/{id}/analyses` triggers Claude with survey aggregates + interview transcripts. Each theme is a structured `QuantifiedTheme` = `{ survey signal (n, pct, segment over-index), interview evidence (X of Y, anchor quote), recommendation (product / marketing / next-research), confidence pill }`. `FindingCard` from the design system gets a stricter prop shape matching this. Print stylesheet exercised end-to-end. **Claude composes, researcher edits.** | Real-time regeneration. Multi-version like `ProjectAnalysis`. Annotation. | Sprints 8 + 9 + 10. |  |
| **12: Pricing/billing wiring** | Seed `PlanEntitlement` rows with Decision 2 numbers. Pricing page copy uses "Up to 2,500 responses every month" framing. Quota-exceeded path on response page. Admin override route. | Survey overage billing (killed). Per-response credits (killed). | Sprints 6 + 8. |  |
| **13: AI question coach** *(was: AI question linting)* | `POST /surveys/{id}/questions/lint` returns flags (double-barreled, leading wording, unbalanced scale, agree/disagree bias) **with prescriptive suggested replacement copy**, not just diagnostic. Renders inline in `SurveyQuestionEditor`. Non-blocking advisory. Feels like a research-quality coach, not a grammar checker. | AI sample-size recommendations (killed). AI-authored statistical claims (killed). | Sprint 7. |  |
| **14: Validation micro-survey — closing the loop** | Post-interview screen offers a "30-second validation survey" auto-generated from the themes identified in Sprint 11. Researcher edits, sends. Validation results land in the same report under a "Theme validation" panel. Joins on `study_participant_id`. **This sprint closes the loop**: quantify → explain → validate. | Auto-send on every interview completion. NPS-only auto-trigger. Real-time validation question generation (manual trigger for v1). | Sprints 8 + 11. |  |

**Why this order:**

- Sprints 6→8 ship a thin vertical slice — by end of Sprint 8 a researcher can build a survey, share a link, and see real data on a real dashboard. That's already a usable product, even before the wedge.
- Sprint 9 is the *wedge*. Earliest possible point we can ship it is after Sprint 8, and we ship it next. Don't widen the dashboard before proving the bridge works.
- **Sprint 9.5 (Study Overview) was inserted after a consultant audit flagged that the "Study" mental model never reached the UI.** Researchers were seeing surveys and projects as separate features. The Study Overview page is the smallest UX change that fixes the mental model — and once it lands, Sprint 10's segment discoveries have a natural home to surface in.
- Sprint 10 is now **segment discoveries** (with cross-tab math as the engine), not just cross-tabs. The product value is "we found 3 segments worth interviewing," not "here are some 2×2 tables."
- Sprint 11 produces **quantified themes** — explicit `survey signal + interview evidence + recommendation` structure — not a generic AI summary. This is the moat: the "consultant in a box" output the design system was always built for.
- Pricing wiring (Sprint 12) sits late on purpose — quotas without a quota-aware product are noise, and the entitlement keys can be added in any order.
- Sprint 14 only earns its keep after Sprint 11 — validation needs a theme to validate. **Sprint 14 is what makes the product story "quantify → explain → validate", which is the durable narrative we go to market with.**

### Product principles (added after consultant audit)

The product should optimize for one loop, repeated until decisions get made:

```
collect signal → detect interesting segment → go deeper → synthesize → recommend action
```

Concrete implications baked into every sprint:

1. **Decision-oriented, not chart-oriented.** Every dashboard surface leads with findings + recommended actions. Per-question charts are detail underneath, not the lede.
2. **The Bridge is the hero moment**, not a filter feature. Survey→interview conversion is where the product becomes mixed-methods, and it should feel like the natural next step after responses land — not a setting in a sub-menu.
3. **AI detects patterns; researchers author claims.** Claude can flag "this segment over-indexes," surface candidate questions for follow-up interviews, and suggest segment cuts. Claude never publishes a statistical claim, never recommends a sample size, never renders a percentage below n=30. This is the methodologist's hard line and the source of every trust signal in the product.
4. **Study is the workspace.** Surveys and projects are *instruments inside a Study*. The Study Overview page (Sprint 9.5) is where this becomes literal.
5. **Don't try to be Typeform.** Survey features serve the wedge or they don't ship. Generic survey polish (custom branding, templates marketplace, complex branching) stays off the roadmap.

---

## 3. Risk register

Ranked by likelihood × blast radius. P = probability, B = blast radius (1=local nuisance, 5=production outage / data loss).

| # | Risk | P | B | Mitigation |
|---|---|---|---|---|
| 1 | **Alembic 0024 fails on Cloud Run startup; `start.sh` falls back to `Base.metadata.create_all()` on prod, leaving migration version unstamped and silently corrupt** | M | 5 | Alembic 0024 must be tested against a Neon snapshot in CI before merge. `start.sh` fallback path should be neutered for known-broken-migration cases (better to fail-fast than silent-create). New checklist item in `QA_CHECKLIST.md`. |
| 2 | **Token namespace collision between `interview_links.token` and `survey_links.token`** | L | 4 | Pre-insert app-level check (section 1.2). 32-byte URL-safe tokens make accidental collision astronomically unlikely; the real risk is a malicious URL guessing attack — same risk as existing interview links, no new attack surface. |
| 3 | **Email-based participant rejoin across studies fires without re-consent → privacy violation** | M | 5 | `consent_acknowledgments` table is required on the write path for any cross-study email match. Backend test that asserts new study + matching email + missing ack → 403. Section 1.3 codifies this. |
| 4 | **Claude open-text analysis cost balloons (10k responses × N tokens × per-call price)** | H | 3 | AI sees aggregates only by default; row-level open-text only inside an explicit "cluster open-text" job that batches with Claude Haiku 4.5 at ≤4k tokens per batch and writes a single `usage_events` row per job (`event_name='ai_open_text_cluster'`). Hard per-workspace daily cap enforceable via `AIUsageLog`. |
| 5 | **Methodological guardrails miss a bad-question pattern users will write (e.g., loaded "Don't you agree that…")** | H | 2 | AI lint is advisory, not authoritative — accept that we'll miss patterns. Add an in-app feedback link on every lint result; iterate the prompt monthly. The hard methodologist rules (n≥30 for percentages, Wilson CI, fielding window visible) are enforced server-side and cover the worst displays. |
| 6 | **Frontend bundle bloat from quanti pages — design system already adds ~5k lines of CSS** | M | 2 | Route-level code split: `/surveys/*` and `/studies/*` lazy-loaded. Recharts is already a dep; don't add a second chart lib. Print stylesheet is already separate. Measure via `vite-bundle-visualizer` before Sprint 11 merges. |
| 7 | **Stripe webhook ordering: a plan upgrade webhook arrives before the previous period's quota counter resets, briefly allowing free responses** | L | 2 | Quota check uses `(workspace_id, completed_at >= subscription.current_period_start)`. When the webhook updates `current_period_start`, the counter naturally resets. Edge case: 0–60s drift between webhook handler and DB write — accept it. |
| 8 | **`SurveyQuestionEditor` reorder race: two researchers reorder concurrently, last write wins, but `sort_order` collisions throw** | L | 1 | `sort_order` is not unique; treat ties as resolved by `created_at`. Frontend reorder posts a full ordering array, backend rewrites all rows in a transaction. |
| 9 | **`/r/{token}` public response page leaks survey existence via 404 vs 200 timing on inactive tokens** | L | 2 | Constant-time response: always return 200 with a generic "This survey is not available" if the token is invalid OR closed OR quota-exceeded. Same pattern as existing `/i/{token}` interview page — copy that handler structure. |
| 10 | **Existing project routes break after `study_id` column is added to `projects`** | M | 4 | Column is nullable in 0024. Backfill script (in 0024 itself) creates one Study per existing Project. Backend tests for all `/projects/{id}` routes pass before merge. **Don't make `study_id` non-nullable until a follow-up migration after Sprint 6 ships and we verify all reads.** |
| 11 | **Researchers expect survey-only product (no interview tie-in) and complain about Study scaffold** | M | 2 | Study creation is implicit on first Survey creation — UI never shows "create a Study, then add a Survey." Study only surfaces in mixed-methods view. Onboard with the term "Study" but don't force it. |
| 12 | **Below-n=30 segments rendered as percentages by a future contributor who doesn't know the rule** | M | 3 | Backend `/cross-tab` endpoint never returns percentage when n<30 (returns null). Frontend has no path to render a percentage that didn't come from the backend. Single-source-of-truth means a future bug can't undo it. |

---

## 4. v1 done definition

A researcher can:

1. Create a new Study in their workspace, named e.g. "Q2 onboarding research."
2. Build a screener survey (5 questions: 1 NPS, 2 Likert, 1 MC, 1 short text) using `SurveyQuestionEditor`.
3. Share the public response link `/r/{token}` and collect 100+ responses.
4. See the dashboard at `/surveys/{id}/dashboard` with `StatHero`, `ChartCard` per question, `MethodologyBox` showing n, completion rate, fielding window, Wilson 95% CIs. Below-n=30 segments show counts only.
5. Use `ScreenerBridge` to filter ("show me respondents who scored ≤6 on Q3 and answered 'Yes' to Q5") and see a count, e.g. "23 matches."
6. Click "Invite to interview." 23 personalized email invites go out, each carrying a `study_participant_id` so when they complete the interview the join is pre-wired. Each completed interview consumes 1 credit via the existing `consume_interview` ledger flow — zero changes to billing.
7. After ≥10 interviews complete, generate a mixed-methods report at `/studies/{id}/report`. Sees `ExecutiveSummary`, `FindingCard`s that cite both survey aggregates and interview verbatim, `PrioritizationMatrix`, all printable via the existing print stylesheet.
8. Hit a quota wall (say, free plan = 100 responses) and see a clear upgrade nudge — no surprise overage charges.

**That's v1.** Not feature complete; **proves the bet.** Estimate: 4–6 weeks of one engineer for Sprints 6–11; Sprints 12–14 are post-v1 polish.

---

## 5. What v1 deliberately doesn't do

Carrying the kill list forward and adding everything surfaced during planning. Future contributors: do not re-introduce these without explicit re-litigation.

- Drag-drop dashboard builder
- Branching / conditional logic beyond a single skip
- NPS gauge widget
- Word clouds
- MaxDiff / conjoint / ranking analysis
- Sliders
- Custom themes / branding for surveys
- Multi-language survey rendering
- Integrations (Zapier, HubSpot, Slack)
- Templated survey libraries
- Standalone NPS tracking dashboard
- **Per-response credit pricing for surveys** (section 1.6)
- **Survey overage billing** (hard cap instead)
- **AI sample-size recommendations** (methodologist hard line)
- **AI-authored statistical claims** (methodologist hard line)
- **Below-n=30 percentages anywhere in the UI** (counts only)
- **Normal-approximation confidence intervals** (Wilson only)
- **Real-time mixed-methods report regeneration** (manual trigger only in v1)
- **Multi-version analyses for studies** (`ProjectAnalysis` has versioning; `StudyAnalysis` deliberately doesn't in v1 — re-run replaces)
- **Annotation / theme confirmation for study analyses** (`AnalysisThemeAnnotation` exists for projects; not extended to studies in v1)
- **Cross-workspace participant identity** — a panel profile is workspace-scoped; we do not let workspaces share participant pools

---

## 6. Decisions log

The 8 questions raised during planning have been resolved. Future contributors: if you want to revisit one of these, that's fine — but treat them as decided, not open. Re-litigation requires the same framing as the kill list (section 5).

| # | Question | Decision | Why |
|---|---|---|---|
| 1 | Screener invite UX: auto-send vs. draft+review | **Draft + review** | Email blasts to 89 panelists aren't undoable. Cost of a wrong-segment send (wasted credits, spammed panelists, brand damage) is too high for default auto-send. Power users can toggle "skip review for similar segments" later. |
| 2 | Trial response caps | **Trial 100 / Exploration 500 / Team 2,500 / Agency 10,000 / Enterprise custom** | Tuned to the *response volume needed to feed an interview wave* (typically 100–500 → 25–50 interviews). Trial 100 is enough to feel real but not enough to ship; Team 2,500 supports ~5 parallel studies. |
| 3 | Anonymous default | **Identified by default; prominent toggle to switch to anonymous** | Anonymous-by-default kills the wedge — you can't bridge to interview without identity. Legitimately-anonymous use cases (HR, sensitive topics) get a clear toggle with a warning: "You won't be able to invite respondents to follow-up interviews." Privacy is preserved by *consent flow*, not by stripping identity from the schema. |
| 4 | Validation survey trigger | **Manual** | Researcher reviews completed interviews, picks themes to validate, fires the survey as a deliberate act. Auto-trigger has email-volume + consent complexity we don't need in v1. Revisit if manual flow shows demand. |
| 5 | Open-text AI clustering | **Opt-in, with one free first run per survey** | Compromise on cost risk #4. Discoverable: shows as "Recommended" in the editor. First run free; subsequent re-runs draw from the workspace's AI budget (existing `AIUsageLog`, not credits). |
| 6 | Re-consent UX across studies | **One-click consent screen on first instrument completion (option b)** | Silently linking is GDPR-risky. Email-confirm adds drop-off. One-click accept is the right friction. Decline path treats them as a new participant (no historical link). |
| 7 | Pricing page copy | **Specific numbers** ("Up to 2,500 responses every month") | Customers who hit quotas with the bold "surveys included" framing feel betrayed. Honest numbers up front are stickier long-term. |
| 8 | `Study` in URL | **Visible (`/studies/{id}`); creation is implicit** | URL is `/studies/{id}` for the aggregate (mixed-methods) view. Study is auto-created on first Survey/Project creation — researchers never see a "create a Study first" flow. UI label is "Study", docs use "Study", so it's a learnable term. Surfaces prominently on the mixed-methods report page, where it earns its keep. |

### Implications carried forward

- **Sprint 9** (Screener Bridge) ships with a draft+review step, not one-click send. Add a "send all" CTA that confirms recipient count + total credit cost before firing.
- **Sprint 12** (pricing/billing wiring) seeds the entitlement rows with the specific numbers from Decision 2.
- **Sprint 6** (schema): `survey_links.is_anonymous` defaults to False (Decision 3). `consent_acknowledgments` table is required from day one (Decision 6).
- **Sprint 11** (mixed-methods report): "Study" is a first-class concept in the URL and IA. Marketing site / docs should adopt the term in lockstep.
- **Sprint 13** (AI question linting): clustering opt-in lives next to the lint advisor in the editor, presented as "Recommended for this question type" rather than as a separate setting page.

---

## Critical files for implementation

- `backend/app/models/survey.py` (new — Survey, SurveyQuestion, SurveyLink, SurveyResponse, SurveyResponseAnswer)
- `backend/app/models/study.py` (new — Study, StudyParticipant, ConsentAcknowledgment)
- `backend/alembic/versions/0024_quanti_schema.py` (new — all tables above + `projects.study_id` nullable + backfill)
- `backend/app/services/stats.py` (new — Wilson CI, n<30 guard, chi-square; the place where the methodology contract lives in code)
- `backend/app/models/billing.py` (modify — new `PlanEntitlement` seed rows for survey quotas; **do not** add new ledger event types)
