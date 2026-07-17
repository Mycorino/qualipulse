# Plan E — The "Decision report": compose a true superset (approach B)

**Principle (the user's rule):** the mixed/decision report must be **strictly better than either
single-lens report** — it contains everything the qualitative findings report has (themes, personas,
journey, activated recommendations, priority matrix, 30-60-90 plan) **plus** everything the survey
report has (per-question charts, quantified/validated signal) **plus** the integration that neither
has (verdict, joint display, counter-evidence, gaps). If it isn't a superset, it shouldn't exist.

**Approach B — compose, don't duplicate.** Reuse the deep qual synthesis (`ProjectAnalysis`) as the
single source for the interview dimension; layer the survey evidence and a light integration pass on
top. One qual brain, authored once, reused.

This also delivers the earlier consolidation: three user-facing reports — **Qualitative**, **Survey**,
and one **Decision report** (the superset) — with the mixed single-study case and the cross-study memo
as the same family (single vs multi-study scope). Separate from PR #292; ship after it.

---

## Current state (the duplication)

```
Study
├─ Project (interviews) ─ ProjectAnalysis  ← DEEP qual: themes+quotes, personas, journey,
│                                             JTBD, tensions, ACTIVATED recs, matrix, plan
├─ Survey(s) ─ build_dashboard() + compute_discoveries()   ← survey aggregates + segment lifts
└─ StudyAnalysis  ← RE-READS transcripts, re-synthesizes a THINNER qual layer into a
                     different schema (QuantifiedThemeReport), rendered by render_study_report_html
```

- A ready `ProjectAnalysis` reliably exists for a mixed study — `study_synthesis.py:86–116`.
- `study_analysis._generate_report` re-fetches participants → turns and re-does qual extraction
  (`study_analysis.py:258–306`); its output schema `QuantifiedThemeReport` (`schemas/study.py:205–219`)
  has **no personas / journey / matrix / plan**, and its renderer `render_study_report_html`
  (`report_export.py:2132–2455`) renders none of them.
- Net: the mixed report is **weaker on the qual dimension than the interviews-only report.** Fails the rule.

---

## Target architecture (approach B)

```
Study
├─ Project ─ ProjectAnalysis   ← the ONE qual brain (already Opus 4.8 + structured)
├─ Survey(s) ─ dashboards + discoveries   ← the survey layer (unchanged)
└─ StudyAnalysis.report = INTEGRATION ONLY   ← verdict + theme↔survey joint-display links +
                                                counter-evidence + validation + gaps
                                                (NO re-extraction of qual themes)

Decision report (rendered)  =  qual sections (from ProjectAnalysis)
                            +  survey section (charts from dashboards)
                            +  integration section (verdict up top, joint-display table,
                               validation, gaps)  ⇒  strict superset of both single reports
```

Two consequences that make this clean:
- **StudyAnalysis stops re-reading transcripts.** It becomes a thin *integration* over already-synthesised
  inputs — cheaper, faster, and it can never disagree with the qual report because it doesn't re-derive themes.
- **The qual content is pulled live from `ProjectAnalysis` at render time**, so the Decision report always
  reflects the latest (incl. refined v2) qual synthesis. Integration links key on theme title and degrade
  gracefully if a title no longer matches.

---

## Work breakdown

### 1. Make the qual renderer's sections reusable (`report_export.py`)
The persona / journey / themes / evidence-map / JTBD / tension / recommendation / matrix / plan blocks
currently live as closures **inside** `render_analysis_report_html` (`:522+`). Extract each into a
module-level helper that takes `(report_dict, roster, L)` and returns HTML — then `render_analysis_report_html`
calls them (output must stay **byte-identical**; the existing snapshot tests guard this) and the Decision
renderer calls the same helpers. No behaviour change to report #1; zero duplication for report #3.

### 2. New composed renderer `render_decision_report_html(...)` (`report_export.py`)
Bordeaux identity (the flagship). Assembles, in order:
1. **Verdict + confidence** (from integration) — the board-ready answer up top.
2. **Qual sections** (from `ProjectAnalysis.report` via the §1 helpers): themes+quotes, evidence map,
   **personas**, **journey/emotion map**, JTBD, tensions.
3. **Survey section**: per-question SVG charts (reuse `_svg_choice_bars/_nps_band/_histogram` +
   `build_dashboard` payloads) — the survey report's content.
4. **Joint display** (from integration): a theme × survey-signal table (which qual theme is corroborated
   by which survey signal / segment lift), counter-evidence, respondent validation (Wilson CI).
5. **Activated recommendations + priority 2×2 + 30-60-90 plan** (from `ProjectAnalysis` — reused helpers).
6. **Gaps + methodology contract + evidence index** (surveys + participants).

### 3. Slim the generation to an integration pass (`study_analysis.py`)
`_generate_report` no longer reads transcripts. New inputs: the study's latest ready `ProjectAnalysis.report`
(themes/personas/journey/recs — already synthesised) + survey `dashboards` + `discoveries` + decision context.
The (lighter, still Opus) prompt produces only the **integration JSON**: `verdict`, `joint_display` (per
theme_title → survey_signal + confidence + counter_evidence), `validation` refs, `gaps`, `methodology_note`.
Anchor-quote verification is dropped here (quotes come from the already-verified `ProjectAnalysis`).
- **Prerequisite step:** if the study has interviews but no ready `ProjectAnalysis`, generate it first
  (`analysis.run_analysis`) so the qual brain exists before integration.
- New `StudyAnalysis.report` schema = the integration object (small). Store the `project_analysis_id` it
  integrated against (audit + render lookup).

### 4. Trigger + endpoints (`routers/studies.py`)
- `POST /studies/{id}/analyses` (`:495–514`): ensure ProjectAnalysis → run integration.
- `GET /studies/{id}/analyses/{aid}/report.html` (`:586–693`): fetch `ProjectAnalysis` + dashboards +
  validation + integration, call `render_decision_report_html`.
- Consolidation hook (phase 2): the cross-study memo (`synthesis.py` / `render_decision_memo_html`) becomes
  the **N≥2** mode of the same Decision-report family — same identity, same "verdict + joint evidence" spine,
  aggregating multiple `ProjectAnalysis`es. Single-study (N=1) is this plan.

### 5. Frontend / naming
Present three outputs: **Qualitative**, **Survey**, **Decision report**. The Studies home labels the mixed
output "Decision report" (bordeaux), and the decision-memo section folds into the same family. Small copy +
routing change; no new UI surface.

---

## Backward compatibility & migration
- **Old `StudyAnalysis` reports** are the fat `QuantifiedThemeReport` shape. The Decision renderer must
  detect shape: new (integration) → compose from ProjectAnalysis; legacy → render via the existing
  `render_study_report_html` path (keep it as the legacy branch). Optionally a `backfill_decision_reports.py`
  re-runs integration for existing studies (same pattern as `backfill_demo_reports.py`).
- **No DB migration** for report shape (JSON blob). One nullable `project_analysis_id` column on
  `StudyAnalysis` is worth an Alembic migration for the audit link (or store it inside the report JSON to
  avoid a migration).
- Demo seeder: the seeded mixed study's `StudyAnalysis` fixture updates to the integration shape (and the
  demo already seeds a `ProjectAnalysis` to compose from).

---

## Risks
| Risk | Mitigation |
|---|---|
| Extracting qual section closures changes report #1 output | Byte-stable refactor; existing EN/FR snapshot tests must stay green before/after |
| Integration links drift when ProjectAnalysis is regenerated | Key joint-display on theme title; render gracefully when a title is absent; re-run integration on refine |
| Mixed study with no interviews (survey-only) | Decision report degrades to survey section + verdict/gaps (still ≥ survey report); personas/journey omitted |
| Two syntheses' cost | Integration is lighter than the old re-extraction; ProjectAnalysis is reused, not recomputed — net neutral/cheaper |
| Legacy StudyAnalysis reports | Dual-path renderer + optional backfill |

---

## Phasing
- **Phase 1 — renderer refactor (extract qual sections; snapshot-verify report #1 unchanged).** ~1 day.
- **Phase 2 — `render_decision_report_html` composing ProjectAnalysis + survey + a stub integration.** ~1.5 days.
- **Phase 3 — integration generation pass (slim `study_analysis`, drop transcript re-read, ProjectAnalysis prereq).** ~1.5 days.
- **Phase 4 — endpoints, dual-path legacy, demo fixture, tests (superset assertions: every qual section + every survey chart present).** ~1 day.
- **Phase 5 (optional) — fold the cross-study memo into the same family (N≥2 mode).** ~1–2 days.

≈ **5 days** for the single-study superset (phases 1–4); +2 for the cross-study consolidation.

## Definition of done
- The Decision report renders **every** qualitative section (themes, personas, journey, JTBD, tensions,
  activated recs, matrix, plan) **and** every survey chart **and** the integration (verdict, joint display,
  validation, gaps) — provably a superset of reports #1 and #4.
- Qual findings report (#1) output is byte-identical to before (snapshot tests green).
- `StudyAnalysis` no longer re-reads transcripts; the qual dimension is sourced once from `ProjectAnalysis`.
- Users see three reports; the Decision report is always the richest.
