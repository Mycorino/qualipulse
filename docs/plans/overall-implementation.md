# Plan C — Overall implementation plan

Ties together **Plan A** (personas & journey/emotion map) and **Plan B** (recommendation activation +
30‑60‑90 + priority matrix) into one sequenced rollout. Constraint from the product decision:
**PDF renderer only** — everything ships as new blocks in the server‑rendered `report.html`
(`services/report_export.py::render_analysis_report_html`), no slide deck, no new web UI.

Goal: move the qualitative findings PDF from "rigorous research‑lab report" to "client‑grade decision
package" — closing the benchmark gaps in *visualisation* and *activation* without giving up our
evidence‑integrity advantage.

---

## 1. Shared foundations (build once, before either plan)

These cut across both plans — doing them first avoids rework.

### 1.1 `report` stays a JSON blob → no migrations, ever
All schema growth lives in `ProjectAnalysis.report`. Confirmed at `analysis.py:427`
(`analysis.report = json.dumps(report_obj)`). No Alembic work for any of this.

### 1.2 Additive, backward‑compatible rendering
Old analyses lack the new keys. Every new section MUST:
- default missing keys to `[]`/`{}`/`""`,
- omit itself when empty (the `... if x else ""` pattern already used at `report_export.py:680,694`),
- accept legacy shapes (string recommendations alongside object recommendations).

Net effect: **existing reports render unchanged; new fields appear only after re‑generation.** No
backfill required. Optionally expose a "Regenerate analysis" affordance so users can refresh old
studies — but not required for ship.

### 1.3 Token budget (the one real cross‑plan risk)
`max_tokens=8192` today with a truncation guard that fails the analysis cleanly
(`analysis.py:394,405`). Plan B (+object recs) and Plan A (+personas +journey) all add output.

**Action:** before writing Plan A's SVG, run the **max‑size token test** — generate an analysis on the
richest available study (most participants/themes) with the full combined schema and confirm no
`stop_reason == max_tokens`. Raise `max_tokens` to 12288 as part of shared foundations. If the richest
study still truncates, trigger Plan A §5 fallback (dedicated personas/journey pass). Decide this early,
not after building the renderer.

### 1.4 Extend the quote verifier once
`_verify_report_quotes` (`analysis.py:112`) must learn personas + journey quotes (Plan A §4). Do it as
foundation work so both the theme path and the new sections share one guarantee.

### 1.5 Localization discipline
Every new section needs EN **and** FR `_STRINGS` keys, and every new model‑authored text field must be
added to the language instruction (`analysis.py:367‑372`). Canonical enums (`horizon`, `impact`,
`effort`, `emotion`, `applicable`) stay as tokens and map to localized labels at render time. FR NBSP
conventions apply in the FR strings.

### 1.6 Section order (final PDF narrative)
```
cover → exec summary → at a glance → study design
→ themes → evidence map
→ personas            (NEW, Plan A)          "who we heard"
→ journey/emotion map (NEW, Plan A)          "what the experience feels like"
→ JTBD → tensions
→ recommendations     (UPGRADED, Plan B)     "what to do"
→ priority 2×2        (NEW, Plan B)          "what to prioritise"
→ 30-60-90 plan       (NEW, Plan B)          "when"
→ methodology contract → appendix
```
Wire all inserts in the final template (`report_export.py:756‑772`).

---

## 2. Sequencing (why this order)

Ship in three phases, each independently releasable and each a visible upgrade.

### Phase 0 — Foundations (0.5 day)
1.2–1.5 above: verifier extension stub, `max_tokens` bump, token test on richest study, decide
one‑call vs. two‑call for Plan A. **Gate:** token test green.

### Phase 1 — Plan B quick wins (~2.25 days)
Ship recommendation activation + priority 2×2 + 30‑60‑90 first because:
- lowest risk (deterministic exhibits, one schema change),
- highest rubric‑per‑day (Recommendations 2→4, Visualisation 1→3),
- exercises the shared foundations (backward‑compat renderer, dual‑shape handling, token budget) on a
  small surface before the expensive persona/journey work.
**Gate:** legacy string recs still render; EN/FR snapshots pass; a real study PDF reviewed by eye.

### Phase 2 — Personas (~2 days)
The lower‑risk half of Plan A (card grid, no bespoke SVG). Validates the grounding/omit discipline and
the extended verifier on real output before the journey SVG.
**Gate:** small‑N fixture yields `personas: []` and omitted section; anchor quotes verify; FR renders.

### Phase 3 — Journey / emotion map (~3.5 days)
The design‑sensitive `_svg_journey_map` + applicability gating. Do last so the token budget, verifier,
and localization are all proven. Budget real visual iteration on the SVG.
**Gate:** attitudinal fixture → omitted; experiential fixture → correct arc; visual PDF review; a11y
fallback table present.

Total ≈ **8.25 engineering days**, releasable at each phase boundary.

---

## 3. Files touched (whole initiative)

| File | Change |
|---|---|
| `backend/app/services/analysis.py` | `_ANALYSIS_RULES_BLOCK`, `_ANALYSIS_SCHEMA_BLOCK`, examples, language instruction, `max_tokens`, extend `_verify_report_quotes` |
| `backend/app/services/report_export.py` | new sections (personas, journey, 2×2, 30‑60‑90), upgraded recommendation render, new `_svg_journey_map` + `_svg_priority_matrix`, `_STRINGS` EN/FR keys, template wiring |
| `backend/app/services/study_analysis.py` | *(optional)* align recommendation field names for a future shared renderer |
| `backend/tests/` | new fixtures + renderer/verifier/omit/EN‑FR/token tests |
| `frontend/src/pages/SharedReport.tsx` | *(defensive, 5 min)* render `r.action ?? r` so object recs don't break the public web view |

No new endpoints, no migrations, no model changes.

---

## 4. Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Output truncation from combined schema | Medium | Phase 0 token test; `max_tokens`→12288; hard caps (personas ≤4, stages ≤6); fallback to 2nd pass |
| Invented/over‑fit personas at small N | Medium | Grounding rule (≥2 named participants), N‑gate, honest‑empty examples, verifier on anchor quotes |
| Forced journey on attitudinal study | Medium | `applicable:false` path + REJECT example + renderer omits |
| Legacy string recs break render / web view | Low | Dual‑shape renderer; frontend defensive guard; regression test |
| Journey SVG looks amateur (undermines credibility) | Medium | Treat `_svg_journey_map` as its own unit with visual review gate before wiring |
| Unverified quotes slip into new sections | Low | Extend verifier in Phase 0; PDF flag reused |
| FR localization drift | Low | Strings added with each section; EN+FR snapshot tests mandatory |

---

## 5. Definition of done

- A data‑rich experiential study renders a PDF with: upgraded recommendations, priority 2×2, 30‑60‑90
  plan, 2–4 grounded personas, and a journey/emotion map — all with verified quotes and FR parity.
- A thin attitudinal study renders cleanly with personas and journey **omitted** (no forced exhibits).
- A pre‑change analysis renders identically to before (no regressions).
- All new quotes flow through the verifier; unverifiable ones are flagged, not hidden.
- Every phase merged behind a green CI run (pytest + tsc + build) with EN/FR snapshots.

---

## 6. What this deliberately does NOT do (deferred)

- Slide/deck renderer (revisit only if users ask for a boardroom deck).
- Workshop / action‑plan‑with‑named‑owners artifact.
- Theme‑montage video/audio clips.
- Persisted case×theme framework matrix + inter‑rater reliability.
- Web‑app (non‑PDF) rendering of personas/journey.

These are real benchmark gaps but out of scope for the PDF‑only track; captured here so the boundary is
explicit.
