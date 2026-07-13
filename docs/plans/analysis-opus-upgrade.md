# Plan D — Move the analysis engine to Opus 4.8 and pull the best out of it

**Goal:** run `run_analysis` / `run_refined_analysis` on **Claude Opus 4.8** with the model's
strongest levers switched on — adaptive thinking, the right effort, guaranteed-valid structured
output, and streaming — so the richer report schema (themes + JTBD + tensions + object
recommendations + personas + journey) is synthesised at the highest quality the model can give.

Applies to `backend/app/services/analysis.py` only. The Copilot already runs Opus 4.8 + adaptive
thinking; this brings the *analysis* path up to the same tier. **No DB migration** (report is JSON).

---

## Why Opus 4.8 for this specifically

Our synthesis is intelligence-sensitive judgment, not an agentic tool-loop: calibrate confidence to
N, ground each persona in ≥2 named participants, decide whether a journey is even applicable, keep
every quote verbatim, make each recommendation falsifiable, surface disconfirming evidence. That is
precisely where Opus 4.8 + thinking outperforms a no-thinking Sonnet pass. Cost is the tradeoff
(§Cost) — acceptable because analysis is infrequent (per-study, researcher-triggered), not per-request.

---

## The levers (what "best of Opus 4.8" means here)

| Lever | Change | Why |
|---|---|---|
| **Model** | `ai_models.sonnet()` → an analysis-specific resolver defaulting to `claude-opus-4-8`, env-overridable | Highest-tier synthesis; keep an escape hatch to dial back to Sonnet |
| **Adaptive thinking** | add `thinking: {type: "adaptive"}` | The judgment work (grounding, calibration, applicability) happens in thinking, not guesswork |
| **Effort** | `output_config: {effort: "high"}` (default); allow `xhigh` for the richest / refined runs | Migration guidance: minimum `high` for intelligence-sensitive work; `xhigh` for the hardest |
| **Structured output** | `output_config: {format: {type: "json_schema", schema: REPORT_SCHEMA}}` | Guarantees a valid report object — removes the fence-stripping hack and the parse-failure path entirely |
| **Streaming** | switch the call to `client.messages.stream(...)` + `get_final_message()` | Opus turns run longer; streaming lifts the non-stream HTTP-timeout ceiling and lets `max_tokens` go high |
| **max_tokens** | raise to ~24–32K (safe once streaming) | Thinking tokens share the output budget; leave room so the JSON never truncates mid-object |
| **Temperature** | drop the explicit `0.3` | `temperature` is **rejected (400)** on Opus 4.8 — our `ai_models.temperature_kwargs()` guard already omits it, so this is automatic, but verify |

---

## P0 — a hard blocker that ships with thinking

**`response.content[0].text` is wrong once thinking is on.** With adaptive thinking, a `thinking`
block precedes the `text` block, so `content[0]` may be the thinking block (empty text under the
default `display: "omitted"`). Both `run_analysis` (~line 411) and `run_refined_analysis` (~line 623)
do `response.content[0].text.strip()`.

Fix (both call sites) — select the text block explicitly:

```python
raw = next((b.text for b in response.content if b.type == "text"), "").strip()
```

This is non-negotiable the moment thinking is enabled, independent of every other lever.

---

## Structured output — the reliability win

Today we prompt for JSON, strip markdown fences, then `json.loads` and hope. Opus 4.8 supports
**structured outputs**, which constrains the response to a schema at the API layer:

- Guarantees a parseable object → delete the fence-stripping block and the "parse error → failed"
  branch.
- Compatible with **thinking and streaming** (per the API docs) and lives in the same `output_config`
  as `effort`.
- Schema limits to respect: no `minLength`/`maxLength`, no numeric `minimum`/`maximum`, no recursion —
  our schema is nested objects/arrays of strings + enums, all supported. The Python SDK strips any
  unsupported constraint client-side. Not compatible with citations/prefill (we use neither).

**Build `REPORT_SCHEMA`** mirroring `_ANALYSIS_SCHEMA_BLOCK` (summary, themes[], jobs_to_be_done[],
tensions[], recommendations[] as objects, personas[], journey{}, confidence, confidence_rationale,
participant_count). Make optional sections nullable/empty-allowed (personas: [], journey.applicable:
false) so the "honest empty" paths still validate. Keep the prose schema block in the prompt too — it
documents intent and examples the schema can't express (the ACCEPT/REJECT examples still steer quality).

*Note the first request on a new schema pays a one-time compile latency (24h cached) — harmless for a
background thread.*

---

## Prompt re-tuning for Opus 4.8 (small, high-leverage)

Opus 4.8 follows instructions more literally, writes warmer/longer prose, and — with thinking **off** —
can leak reasoning into the visible answer. With adaptive thinking **on**, reasoning goes into thinking
blocks and the visible output stays clean, which is exactly what we want (JSON only). Two tweaks:

1. Keep/strengthen the final line of `ANALYSIS_SYSTEM_PROMPT`: *"Your visible output is ONE JSON object
   and nothing else — no preamble, no commentary, no fences. All reasoning belongs in thinking."*
2. Give intent (Opus 4.8 uses it): the `<task>` already states the decision + N; leave it — it's the
   "why" the model leverages. No other prose changes needed; our rules are already explicit, which 4.8
   rewards.

---

## Sequencing

**Phase 1 — switch + safety (0.5 day).** Analysis model resolver → `claude-opus-4-8`; add
`thinking: {type: "adaptive"}` + `output_config: {effort: "high"}`; **apply the P0 text-block fix**;
confirm `temperature_kwargs()` drops temperature (no 400); keep the `stop_reason == "max_tokens"` guard.
Leave the call non-streaming at first with `max_tokens` 12288 and run a real study. **Gate:** a live
analysis returns valid JSON and reads better than the Sonnet baseline.

**Phase 2 — streaming + headroom (0.5 day).** Convert both calls to `client.messages.stream(...)` +
`get_final_message()`; raise `max_tokens` to 24–32K. **Gate:** the richest available study completes
without truncation or SDK timeout.

**Phase 3 — structured output (1 day).** Author `REPORT_SCHEMA`; add `output_config.format`; delete the
fence-stripping + parse-failure handling. **Gate:** a planted "messy" model output still yields a valid
object; the verifier + renderer are unchanged downstream.

**Phase 4 — tune + guard (0.5 day).** Decide `high` vs `xhigh` per path (suggest `high` for v1,
`xhigh` for `run_refined_analysis`, which is the researcher's high-stakes pass); prompt line tweak;
re-baseline cost. Total ≈ **2.5 days**, layered cleanly on top of Plans A–C.

---

## Cost & operability

- **Rates:** Opus 4.8 is $5/$25 per M vs Sonnet 4.6 $3/$15. With thinking + `high`/`xhigh`, expect
  roughly **$0.15–0.40 per analysis** vs ~$0.05 on Sonnet. Infrequent op → acceptable; still tiny
  per study. `services/usage_logger.py::_CLAUDE_RATES` is already model-aware (Opus/Sonnet/Haiku) — cost
  logging picks up Opus automatically; **verify the Opus row exists and is current.**
- **Cost control:** the env-overridable analysis-model pin lets us flip back to Sonnet instantly, and
  effort is a per-call dial. *(Optional product lever: Opus analysis for paid tiers, Sonnet for trial —
  a business decision, not required for this plan.)*
- **Cache:** prompt caches are model-scoped, so the first Opus call writes a cold cache; our stable
  static prefix keeps every subsequent call warm. No action needed beyond expecting one cold write.
- **Tokenizer:** Opus 4.8 uses a different tokenizer than Sonnet 4.6 — token *counts* shift (re-baseline
  any dashboards), but nothing in our code keys on absolute counts except `max_tokens` headroom, which
  Phase 2 already handles.

---

## Risks

| Risk | Mitigation |
|---|---|
| `content[0].text` breaks with thinking on | P0 fix — select the `type=="text"` block; ships in Phase 1 |
| Truncation from thinking + rich schema sharing `max_tokens` | Phase 2 streaming + 24–32K headroom; `stop_reason` guard stays |
| Structured-output schema rejects an edge value | Nullable/empty-allowed optional sections; SDK strips unsupported constraints; test the honest-empty paths |
| Cost creep | env pin to Sonnet; effort dial; Opus reserved to analysis path only |
| Behavior drift vs Sonnet baseline | Phase 1 gate = side-by-side read on a real study before rollout |

---

## Definition of done

- Both analysis paths run on Opus 4.8 with adaptive thinking + effort, streamed, temperature dropped.
- The text-block extraction is thinking-safe; the `max_tokens` guard still fires cleanly.
- Structured output guarantees a valid report object; fence-stripping/parse-failure code is gone.
- Quote verifier, renderer (Plans A–C), and downstream consumers are untouched and green.
- Cost logging attributes Opus correctly; an env pin can revert to Sonnet in one change.
