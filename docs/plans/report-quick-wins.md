# Plan B — Report quick wins: recommendation activation + 30‑60‑90 + priority matrix

**Scope:** three PDF exhibits, one schema change. All inside `services/report_export.py` +
`services/analysis.py`. **No DB migration** (`ProjectAnalysis.report` is a JSON blob).
**No new LLM call** for the two exhibits — they are deterministic renders of one upgraded field.

**Rubric impact (vs. the deep-research benchmark):** Recommendations 2→4, Visualisation 1→3.
This is the cheapest path to "board‑ready decision package" content.

---

## The one insight

Today `recommendations` is `list[str]` (`analysis.py:246`, rendered at `report_export.py:697`).
Upgrading it to `list[object]` powers **three** exhibits from a single change:

1. **Recommendation table** — action + owner + horizon + KPI + falsifier (instead of a bare sentence).
2. **30‑60‑90 plan** — group the same objects by `horizon`. Deterministic, no LLM.
3. **Impact × feasibility 2×2** — plot the same objects by `impact` × `effort`. Deterministic SVG.

---

## 1. Schema change (`services/analysis.py`)

### 1a. `_ANALYSIS_SCHEMA_BLOCK` (lines 246‑248)

Replace the flat string list with an object array:

```jsonc
"recommendations": [
  {
    "action": "Specific, decision-oriented next move. Imperative. No 'consider/explore/leverage'.",
    "rationale": "One line: which theme/behaviour it addresses and why now.",
    "owner_role": "The function that should own it — e.g. 'Product', 'Growth', 'CX', 'Research'. A ROLE, never a person's name (we do not know the client's org).",
    "horizon": "now | 30d | 60_90d | later",
    "impact": "low | medium | high",
    "effort": "low | medium | high",
    "kpi": "The single observable metric or threshold that tells you it worked.",
    "falsifier": "What evidence would prove this recommendation wrong."
  }
]
```

Keep the falsifier — it is our differentiator vs. consulting's prescriptive norm; now it lives in
its own field instead of being buried in prose.

### 1b. `_ANALYSIS_RULES_BLOCK` — RECOMMENDATION RULES (lines 197‑201)

Rewrite to require the new fields and constrain the enums:

```
RECOMMENDATION RULES:
- Each recommendation is an object. action must be imperative and specific — no "consider",
  "explore", "leverage", no motherhood statements.
- owner_role is the responsible FUNCTION (Product / Growth / Marketing / CX / Research / Ops),
  never a person and never the participant.
- horizon reflects urgency AND readiness: "now" = do this week, "30d" = next sprint,
  "60_90d" = this quarter, "later" = needs more evidence first.
- impact = expected effect on the study's decision. effort = build/operational cost to act.
  Be honest — not everything is high-impact-low-effort.
- kpi is one observable metric or threshold, not a vibe.
- falsifier states what would prove the recommendation wrong.
- Calibrate to N: at low N, prefer "60_90d"/"later" + a "validate first" framing over "now".
```

Also update the ACCEPT/REJECT examples (lines 273‑278) to the object shape so the model has a concrete target.

### 1c. Language instruction (lines 367‑372)

`recommendations` is already named. Refine to name the sub‑fields so FR studies translate
`action/rationale/owner_role/kpi/falsifier` but the enums (`horizon/impact/effort`) stay canonical
tokens (they map to localized labels at render time — see §3).

### 1d. Token budget

`max_tokens` is already 8192 with a clean truncation guard (`analysis.py:394,405`). Richer
recommendations add maybe 60‑120 tokens each; low risk alone. Track cumulative budget in Plan C
because personas/journey add more. No change needed for this plan in isolation.

### 1e. Backward compatibility (critical)

Old analyses stored `recommendations` as `list[str]`. **Do not migrate them.** The renderer must
accept both shapes (§3). This mirrors the existing dual‑type handling for quotes
(`report_export.py` already treats a quote as `dict | str`).

---

## 2. `run_refined_analysis` inherits for free

Both `run_analysis` (297) and `run_refined_analysis` (438) build the prompt from the same
`_ANALYSIS_RULES_BLOCK` + `_ANALYSIS_SCHEMA_BLOCK` constants. Changing the constants updates both
paths — verify the refined path's field‑list instruction (line ~575) is regenerated consistently.

---

## 3. Rendering (`services/report_export.py`)

### 3a. Recommendation section (replace lines 696‑706)

Render each recommendation as a card/table row. Handle both shapes:

```python
def _reco_row(r, i, L):
    if isinstance(r, str):                       # legacy
        return f'<li class="reco avoid-break"><span class="reco__num">{i+1}</span><p>{_esc(r)}</p></li>'
    action    = _esc(r.get("action", ""))
    owner     = _esc(r.get("owner_role", ""))
    horizon   = L["horizon_"+r.get("horizon","later").replace("_","")]  # localized label
    kpi       = _esc(r.get("kpi", ""))
    falsifier = _esc(r.get("falsifier", ""))
    # → structured card: action headline, then meta row (owner · horizon), KPI line, falsifier line
```

New `_STRINGS` keys (EN + FR):
`reco_owner` ("Owner"/"Responsable"), `reco_horizon` ("Horizon"), `reco_kpi` ("Success metric"/"Indicateur de succès"),
`reco_falsifier` ("Would be wrong if"/"Serait réfuté si"),
`horizon_now`, `horizon_30d`, `horizon_6090d`, `horizon_later`
("Now/30 days/60‑90 days/Later" · "Maintenant/30 jours/60‑90 jours/Plus tard").

### 3b. 30‑60‑90 plan section (new, deterministic)

Insert **after** the recommendations section (new block before `contract` at line 766). Bucket the
recommendation objects by `horizon` into three columns; skip legacy string recs (they have no horizon
→ drop them into an "Unscheduled" note or omit the section if none carry a horizon).

```python
buckets = {"now": [], "30d": [], "60_90d": []}          # "later" excluded from the roadmap
for r in recommendations:
    if isinstance(r, dict) and r.get("horizon") in buckets:
        buckets[r["horizon"]].append(r)
# render 3 columns; each item = action + owner chip. Omit section if all buckets empty.
```

Strings: `plan_title` ("Activation plan — first 90 days"/"Plan d'activation — 90 premiers jours"),
`plan_sub`, reuse the horizon labels as column headers.

### 3c. Impact × feasibility 2×2 (new SVG exhibit)

Add `_svg_priority_matrix(recommendations, L, accent)` next to the existing SVG helpers
(`_svg_choice_bars` etc., ~line 1492). Same conventions: `viewBox="0 0 680 H"`, `_accent("qual")`,
`svg text { font-family: var(--sans) }`.

- X axis = effort (low→high, so leftward = easier = more feasible). Y axis = impact (low→high).
- Map low/medium/high → {0.17, 0.5, 0.83} of the axis; jitter duplicates so dots don't stack.
- Plot each dict rec as a numbered dot (matching its number in §3a). Quadrant labels:
  top‑left "Quick wins", top‑right "Big bets", bottom‑left "Fill‑ins", bottom‑right "Money pits"
  (localize).
- Legend below = number → action (truncate via existing `_truncate_label`).
- Only render when ≥2 dict recommendations exist; otherwise omit.

Insert this exhibit right above the 30‑60‑90 plan (matrix = "what to prioritise", plan = "when").

### 3d. Template wiring (lines 756‑772)

Insert `{matrix_section}` and `{plan_section}` between `{recos_section}` and `{contract}`.
Order: recommendations → priority matrix → 30‑60‑90 plan → methodology contract.

---

## 4. Consistency with `StudyAnalysis`

`study_analysis.py` already uses a richer recommendation object (`kind/action/rationale/success_test`).
Align names where sensible (`action`, `rationale`; treat `success_test` ≈ `kpi`) so a future shared
renderer is possible. Not required for this plan, but note it to avoid a third naming scheme.

---

## 5. Frontend note (out of scope, non‑breaking)

`SharedReport.tsx` renders recommendations from the JSON as strings. With object recs it would render
`[object Object]`. Since this plan is **PDF‑renderer‑only**, add a one‑line guard in `SharedReport.tsx`
to render `r.action ?? r` (defensive) — 5 minutes, prevents a visible regression on the public web view.
The PDF `report.html` is the deliverable.

---

## 6. Tests

- Extend `tests/` analysis fixtures with an object‑shaped `recommendations`.
- Renderer test: object recs → assert owner/horizon/KPI/falsifier appear; 2×2 SVG present with N dots;
  30‑60‑90 buckets correct.
- **Regression:** legacy string recs still render (no crash, no `[object Object]`), matrix/plan omitted.
- Snapshot both EN and FR.

---

## 7. Effort

| Task | Est. |
|---|---|
| Schema + rules + examples + language line | 0.5 day |
| Recommendation render (dual‑shape) + strings | 0.5 day |
| 30‑60‑90 section | 0.25 day |
| `_svg_priority_matrix` | 0.5 day |
| Tests + FR snapshots + frontend guard | 0.5 day |
| **Total** | **~2.25 days** |
