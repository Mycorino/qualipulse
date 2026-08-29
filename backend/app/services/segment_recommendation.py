"""Segment recommendation — "of the N segments we found, start HERE."

The discoveries list (segment_discoveries.py) already ranks candidates by
confidence then effect size, but a wall of 6 similar cards gives the
researcher no clue what to click. This service turns the ranking into one
explicit, argued-for recommendation:

- **The pick is deterministic** — always the top-ranked discovery. AI
  detects patterns, researchers decide; the model never chooses which
  segment matters.
- **The argument is Haiku-written** — a short "why interview these people
  first" rationale plus 2-3 open, non-leading interview probes, grounded
  ONLY in the stats we hand it. On any failure (no API key, timeout, bad
  JSON) we fall back to a localized deterministic template, so the card
  always renders.

Results are cached in-process keyed on (survey, discovery, respondent
count, language) — the recommendation only changes when new responses
change the top discovery, and a Haiku call per dashboard load would be
wasteful. Cloud Run instances each warm their own cache; that's fine,
the call costs a fraction of a cent.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy.orm import Session

from app.config import settings
from app.models.survey import Survey
from app.services import ai_models
from app.services.segment_discoveries import Discovery

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 6 * 3600
_CACHE_MAX_ENTRIES = 256
_cache: dict[tuple, tuple[float, "SegmentRecommendation"]] = {}

_RECO_STRINGS = {
    "en": {
        "definition": 'People who answered "{choice}" to "{seg_q}"',
        "why_numeric": (
            "This is the clearest gap in your survey: this segment averages "
            "{seg_mean} on \"{metric_q}\" against {overall_mean} overall. The "
            "numbers show how big the gap is, but not why it exists — a few "
            "interviews with these respondents can."
        ),
        "why_categorical": (
            "This segment over-indexes more than any other in your survey on "
            "\"{metric_q}\". The numbers show the gap, but not what drives it — "
            "a few interviews with these respondents can."
        ),
        "directional_caveat": (
            " The sample is small, so treat the number as a lead, not a "
            "conclusion — which is exactly what interviews are for."
        ),
    },
    "fr": {
        "definition": "Les personnes ayant répondu « {choice} » à « {seg_q} »",
        "why_numeric": (
            "C'est l'écart le plus net de votre enquête : ce segment obtient "
            "{seg_mean} de moyenne sur « {metric_q} » contre {overall_mean} au "
            "global. Les chiffres montrent l'ampleur de l'écart, pas sa cause — "
            "quelques entretiens avec ces répondants le peuvent."
        ),
        "why_categorical": (
            "Ce segment se démarque plus que tout autre de votre enquête sur "
            "« {metric_q} ». Les chiffres montrent l'écart, pas ce qui le "
            "provoque — quelques entretiens avec ces répondants le peuvent."
        ),
        "directional_caveat": (
            " L'échantillon est petit : considérez ce chiffre comme une piste, "
            "pas une conclusion — c'est précisément le rôle des entretiens."
        ),
    },
}


@dataclass
class SegmentRecommendation:
    """The argued-for 'start here' pick shown above the discovery list."""

    discovery_id: str
    definition: str  # plain-language "who they are" (deterministic, localized)
    why: str  # the argument for interviewing this segment first
    probes: list[str] = field(default_factory=list)  # suggested interview questions
    source: Literal["ai", "fallback"] = "fallback"


def _lang(lang: str | None) -> str:
    return "fr" if (lang or "en").lower().startswith("fr") else "en"


def _fmt(value: float | None, lg: str) -> str:
    if value is None:
        return "?"
    s = f"{value:.1f}"
    return s.replace(".", ",") if lg == "fr" else s


def _fallback(d: Discovery, lg: str) -> SegmentRecommendation:
    L = _RECO_STRINGS[lg]
    if d.mean_delta is not None:
        why = L["why_numeric"].format(
            seg_mean=_fmt(d.segment_mean, lg),
            overall_mean=_fmt(d.overall_mean, lg),
            metric_q=d.metric_question_prompt,
        )
    else:
        why = L["why_categorical"].format(metric_q=d.metric_question_prompt)
    if d.confidence == "directional":
        why += L["directional_caveat"]
    return SegmentRecommendation(
        discovery_id=d.id,
        definition=L["definition"].format(
            choice=d.segment_choice_label, seg_q=d.segment_question_prompt
        ),
        why=why,
        probes=[],
        source="fallback",
    )


def _haiku_argument(survey: Survey, d: Discovery, lg: str, db: Session | None) -> tuple[str, list[str]] | None:
    """Ask Haiku for the why + probes. Returns None on any failure."""

    if not settings.ANTHROPIC_API_KEY:
        return None

    lang_label = "FRENCH" if lg == "fr" else "ENGLISH"
    if d.mean_delta is not None:
        stats = (
            f'- Metric question: "{d.metric_question_prompt}"\n'
            f"- Segment average: {d.segment_mean:.1f} vs {d.overall_mean:.1f} overall\n"
            f"- Segment size: {d.segment_n} of {d.overall_n} respondents"
        )
    else:
        stats = (
            f'- Metric question: "{d.metric_question_prompt}"\n'
            f'- Over/under-selected answer: "{d.metric_choice_label}" (lift {d.lift_ratio:.1f}× vs overall)\n'
            f"- Segment size: {d.segment_n} of {d.overall_n} respondents"
        )

    system = (
        "You help a qualitative researcher decide which survey segment to "
        "interview first. You are given ONE pre-selected segment and its "
        "stats. Write the argument for interviewing it — do not question "
        "the selection, do not invent facts beyond the stats given.\n\n"
        f"WRITE IN {lang_label} ONLY.\n\n"
        "Output JSON with EXACTLY this shape:\n"
        '{"why": "<2-3 plain sentences: what the gap is and what an interview '
        'would uncover that the survey cannot. Calibrate to the evidence '
        "strength: 'directional' means a small sample, so hedge accordingly. "
        'No jargon, no sigma, no p-values.>",\n'
        '"probes": ["<2-3 short, open, non-leading interview questions a '
        'researcher could ask this segment to explain the gap. No yes/no '
        'questions.>"]}\n\n'
        "Return ONLY the JSON object, no prose, no markdown fences."
    )
    user = (
        f'Survey: "{survey.name}"\n'
        f'Segment: answered "{d.segment_choice_label}" to "{d.segment_question_prompt}"\n'
        f"{stats}\n"
        f"- Evidence strength: {d.confidence}"
    )

    try:
        from app.services._clients import get_anthropic_client

        model = ai_models.haiku()
        client = get_anthropic_client(15.0)
        resp = client.messages.create(
            model=model,
            max_tokens=500,
            **ai_models.sampling_kwargs(model, 0.2),
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        if db is not None:
            from app.services.usage_logger import log_claude_usage

            log_claude_usage(db, resp, "segment_reco", company_id=survey.company_id)
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = "\n".join(
                l for l in raw.split("\n") if not l.strip().startswith("```")
            ).strip()
        parsed = json.loads(raw)
        why = parsed.get("why")
        probes = parsed.get("probes")
        if not isinstance(why, str) or not why.strip():
            return None
        if not isinstance(probes, list):
            probes = []
        probes = [p.strip() for p in probes if isinstance(p, str) and p.strip()][:3]
        return why.strip(), probes
    except Exception:  # noqa: BLE001 — the fallback template always renders
        logger.exception("Segment recommendation via Haiku failed")
        return None


def build_recommendation(
    db: Session,
    survey: Survey,
    discoveries: list[Discovery],
    *,
    lang: str = "en",
) -> SegmentRecommendation | None:
    """Return the argued-for pick, or None when there are no discoveries."""

    if not discoveries:
        return None
    top = discoveries[0]
    lg = _lang(lang)

    cache_key = (survey.id, top.id, top.overall_n, lg)
    cached = _cache.get(cache_key)
    if cached and time.time() - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    reco = _fallback(top, lg)
    ai = _haiku_argument(survey, top, lg, db)
    if ai is not None:
        reco.why, reco.probes = ai
        reco.source = "ai"

    if len(_cache) >= _CACHE_MAX_ENTRIES:
        _cache.clear()
    _cache[cache_key] = (time.time(), reco)
    return reco
