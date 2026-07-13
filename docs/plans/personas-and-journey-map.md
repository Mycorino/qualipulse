# Plan A — Personas & Journey/Emotion map (the "crafted with care" work)

**Why this plan is different:** these are the two exhibits the deep-research benchmark names as the
*shared standard* across McKinsey, Bain, BCG and Kantar — and the two most easily done badly. A
persona that invents a person, or a journey map forced onto a non‑experiential study, destroys the
credibility our verified‑quote pipeline earns everywhere else. **The design goal is: personas and
journeys that are as auditable as our themes.** Every persona maps to named real participants; every
journey stage carries a verified verbatim quote. If the evidence isn't there, the section does not
render. No decoration masquerading as insight.

Both live inside the existing PDF renderer + analysis pipeline. **No DB migration**
(`ProjectAnalysis.report` is JSON).

---

## Core design principles (apply to both)

1. **Grounded or absent.** A persona lists the `Pn` identifiers it is built from; a journey stage
   lists the participant behind its anchor quote. If a persona would rest on 1 participant, or a
   journey can't be traced to transcript evidence, drop it. This is the same discipline as the
   "≥2 participants or it's a tension, not a theme" rule (`analysis.py:176`).
2. **N‑gated.** Personas over‑fit at small N. Journeys are meaningless for attitudinal (non‑process)
   studies. The model must be *allowed and instructed* to return an empty array — and the renderer
   omits empty sections exactly like `tensions_section`/`jtbd_section` do today (`report_export.py:680,694`).
3. **Verified quotes.** Persona `anchor_quote` and journey stage `quote` pass through the existing
   verbatim verifier (extended — see §4). Unverified → flagged in the PDF, never silently trusted.
4. **Consistent with the themes.** Personas and journeys are derived in the **same LLM call** as the
   themes (not a second pass) so they share one evidence lens and can't drift from the findings.
   (Trade‑off + fallback discussed in §5.)

---

## PART 1 — PERSONAS

### 1.1 What a persona is here

A grounded archetype synthesised from clusters of real participants. NOT a stock marketing persona.
Target **2–4** (benchmark: "2–4 personas"). Fields:

```jsonc
"personas": [
  {
    "name": "Evocative archetype label, ≤4 words — e.g. 'The Reluctant Switcher'. Not a real person's name.",
    "grounded_in": ["P1", "P4"],            // real participant identifiers this persona synthesises (≥2)
    "one_liner": "One sentence capturing who they are in this study's context.",
    "segment": "The demographic/behavioural cluster — e.g. 'Designers, <2y tenure' or null if cross-cutting.",
    "goals": ["What they are trying to achieve (user outcome, not company metric)."],
    "frustrations": ["Concrete pains grounded in what these participants said."],
    "behaviours": ["Observable behaviours/workarounds they described."],
    "primary_job": "The dominant JTBD for this persona (may reference the jobs_to_be_done list).",
    "anchor_quote": {
      "text": "verbatim quote that best captures this persona",
      "participant_identifier": "P1"
    }
  }
]
```

### 1.2 Rules to add to `_ANALYSIS_RULES_BLOCK`

```
PERSONA RULES:
- Produce personas ONLY when the sample supports distinct archetypes. Each persona must be
  grounded_in ≥2 named participants. If N<4 or participants don't cluster, return "personas": [].
  An honest empty array beats an invented persona.
- name is an archetype label, never a real or fabricated person's name.
- Every field must trace to what grounded_in participants actually said. Do not import
  stock-persona clichés ("tech-savvy millennial") that the transcripts don't support.
- anchor_quote.text must be a verbatim substring of that participant's transcript.
- Personas must partition or overlap real participants honestly — do not claim a participant
  for a persona whose profile they contradict.
```

### 1.3 Rendering (`report_export.py`)

New `personas_section`, inserted after `jtbd_section` (personas ≈ "who", jobs ≈ "why"). Card grid
reusing the `.jtbd-grid`/`.jtbd` visual family so it's consistent and no new CSS system is needed.

Per card: archetype name (serif) · segment chip · `grounded_in` chips (P1, P4 — clickable-feeling,
reinforces traceability) · goals / frustrations / behaviours as short labelled lists · a serif italic
blockquote for `anchor_quote` (reuse `.quote` styling, incl. the unverified warning at line 65).

New `_STRINGS` keys (EN/FR): `personas_title` ("Personas"/"Personas"),
`personas_sub` ("Archetypes synthesised from real participants; each names the interviews it is built from."
/ "Archétypes synthétisés à partir de participants réels ; chacun nomme les entretiens dont il est issu."),
`persona_goals`, `persona_frustrations`, `persona_behaviours`, `persona_built_from`
("Built from"/"Construit à partir de").

Omit the whole section when `personas` is empty.

---

## PART 2 — JOURNEY / EMOTION MAP

### 2.1 What it is here

A stage‑by‑stage map of the experience the interviews describe, with an **emotion curve** as its
signature row (the benchmark lists "courbe d'émotion / moments de vérité" — we fuse them into one
exhibit). Target **4–6 stages**. Only for studies where participants describe a *process/experience
over time* (onboarding, purchase, switching, support). For purely attitudinal studies → empty.

```jsonc
"journey": {
  "applicable": true,                        // model's honest call; false → section omitted
  "label": "Short name for the journey — e.g. 'Switching grocery providers'.",
  "stages": [
    {
      "name": "Stage label, ≤4 words.",
      "goal": "What the participant is trying to do at this stage.",
      "emotion": -2,                          // integer -2..+2 (frustrated → delighted)
      "quote": {
        "text": "verbatim quote anchoring this stage's emotional reality",
        "participant_identifier": "P3"
      },
      "pain": "The dominant friction here, or empty string.",
      "opportunity": "The improvement this friction implies, or empty string."
    }
  ]
}
```

### 2.2 Rules to add to `_ANALYSIS_RULES_BLOCK`

```
JOURNEY RULES:
- Only build a journey when the interviews describe an experience that unfolds over time
  (a process with stages). For attitudinal/opinion studies with no temporal arc, set
  "applicable": false and stages: []. Do not force a journey.
- 4-6 stages. Derive stages from the experience participants describe, NOT from the interview
  guide's section order (the guide is our question flow, not the customer's journey).
- emotion is an integer -2..+2 grounded in tone/words, not a guess. quote.text must be a verbatim
  substring of that participant's transcript and should justify the emotion score.
- pain/opportunity may be empty for smooth stages. Do not manufacture friction.
```

### 2.3 Rendering — the SVG (the careful part)

New `_svg_journey_map(journey, L, accent)` beside the other SVG helpers (~line 1492). Conventions:
`viewBox="0 0 680 H"`, `_accent("qual")`, `svg text { font-family: var(--sans) }`, print‑safe colors.

Layout (top→bottom), stages as equal‑width columns:
1. **Stage header row** — stage name + one‑line goal.
2. **Emotion curve** — polyline across stage midpoints, Y mapped from emotion −2..+2. Fill a soft
   area under the line in the tint color; mark each point with a dot; color dots by valence
   (negative = copper/warning, neutral = ink, positive = accent green). This is the "wow" exhibit —
   give it the vertical space (~180px band) and gridlines at emotion 0.
3. **Quote callout row** — the stage's verbatim quote (truncate via `_truncate_label`, full text in a
   sibling HTML list below the SVG so it's selectable/searchable and verifiable).
4. **Pain / opportunity row** — small copper "friction" marker + opportunity beneath, only where present.

Accessibility: `role="img"` + an `<title>`/`aria-label` summarising the arc; also render the stages
as an HTML table beneath the SVG (name · emotion · quote · pain · opportunity) so the data is not
locked in the graphic and survives screen readers / copy‑paste. The table doubles as the verified‑quote
surface (with the unverified flag where needed).

New `_STRINGS` keys (EN/FR): `journey_title` ("Experience journey"/"Parcours d'expérience"),
`journey_sub`, `journey_emotion` ("Emotional arc"/"Courbe émotionnelle"),
`journey_pain` ("Friction"), `journey_opportunity` ("Opportunity"/"Opportunité"),
`journey_stage` ("Stage"/"Étape"), plus emotion tick labels if shown.

Insert `journey_section` after `tensions_section` and before `recos_section` — narrative order:
themes → who (personas) → what the experience feels like (journey) → tensions → what to do (recs).

---

## 3. Prompt plumbing (`services/analysis.py`)

- Extend `_ANALYSIS_SCHEMA_BLOCK` (211‑279) with the `personas` array and `journey` object, plus one
  ACCEPT and one REJECT example each (a REJECT persona built on 1 participant; a REJECT journey forced
  onto an attitudinal study). Examples are what make small‑N behaviour reliable.
- Add `personas` fields and `journey` text fields (`label`, stage `name/goal/pain/opportunity`) to the
  **language instruction** (lines 367‑372) so FR studies localize them; `emotion` and `applicable`
  stay canonical. Quotes stay in source language (already covered).
- Both `run_analysis` and `run_refined_analysis` inherit via the shared constants — verify the refined
  path's summary‑of‑rules line (~596) mentions personas/journey so v2 doesn't silently drop them.

---

## 4. Quote verification (must extend — protects our differentiator)

`_verify_report_quotes` (`analysis.py:112‑156`) currently walks `themes[].quotes[]` only. Extend it to
also walk:
- `personas[].anchor_quote`
- `journey.stages[].quote`

Same normalization + substring match; set `verified: false` on failures. Without this, personas/journey
quotes bypass the guarantee that everything else in the report honors. Update the verification log
line (422‑425) to count these too. **This is non‑negotiable** — it's the reason our reports beat the
benchmark on evidence integrity.

---

## 5. Architecture decision: one call vs. two

**Recommendation: extend the single existing analysis call** (Principle 4).

- *Pro:* one version, one source of truth, one verification pass, personas/journey provably consistent
  with the themes, reuses the transcript context already in the prompt.
- *Con:* output‑token pressure. `max_tokens` is 8192 with a truncation guard (`analysis.py:394,405`);
  a data‑rich study (8 themes + JTBD + tensions + object recs from Plan B + 4 personas + 6 journey
  stages) could approach it.

**Mitigations, in order:**
1. Cap hard in the rules: personas ≤4, journey stages ≤6, list items terse.
2. Raise `max_tokens` to 12288 (still one Sonnet call; cost is trivial vs. the value).
3. **Fallback if truncation persists:** move personas+journey to a dedicated second derivation pass
   keyed to the analysis version — input = the just‑generated themes JSON + the participant roster +
   transcripts (for anchor quotes). Runs in the same background thread after the main synthesis; writes
   `personas`/`journey` back into `analysis.report`. Keep this fallback documented but don't build it
   until §5.2 proves insufficient. (See Plan C for the token‑budget test that decides this.)

---

## 6. Tests (`tests/`)

- **Personas grounded:** every persona's `grounded_in` refers to real `Pn`; ≥2 each; anchor_quote
  verifies. A fixture with N=3, no clustering → asserts `personas == []` and section omitted.
- **Journey applicability:** attitudinal fixture → `applicable:false`, section omitted. Experiential
  fixture → 4–6 stages, emotion in range, each quote verifies, SVG emitted with N stage columns.
- **Verifier extension:** planted non‑verbatim persona/journey quote → `verified:false` + PDF flag.
- **Rendering:** EN + FR snapshots; SVG present; HTML fallback table present; graceful omit paths.
- **Token guard:** a max‑size fixture must not trip `stop_reason == max_tokens` after the cap raise.

---

## 7. Effort

| Task | Est. |
|---|---|
| Persona schema + rules + examples | 0.75 day |
| Persona render + strings (EN/FR) | 0.5 day |
| Journey schema + rules + examples | 0.75 day |
| `_svg_journey_map` (the careful SVG) + HTML fallback table | 1.5 days |
| Journey render wiring + strings | 0.5 day |
| Extend quote verifier + language instruction | 0.5 day |
| Tests (grounding, applicability, verifier, EN/FR snapshots, token guard) | 1.0 day |
| **Total** | **~5.5 days** |

The `_svg_journey_map` is the single most design‑sensitive unit in all three plans — budget real
iteration time there and review it visually in the PDF before wiring the rest.
