"""Question coach — Sprint 13.

A two-layer linter:

  Layer 1 (regex): catches obvious methodological issues fast + free —
    double-barreled questions, leading adjectives, vague intensifiers,
    unbalanced Likert scales. Runs server-side so the same rules
    apply regardless of where lint is triggered from.

  Layer 2 (Claude Haiku): on demand, generates a PRESCRIPTIVE rewrite
    of the offending prompt. Per the consultant audit: the coach
    should feel like a research-quality advisor, not a grammar
    checker. We use Haiku, not Sonnet, because the task is short and
    we want to keep inline latency under 1s + cost negligible.

Constraints baked in (per the methodology contract):
  - Coach is ADVISORY ONLY. Never blocks a save. The researcher always
    decides whether to apply a suggestion.
  - Claude proposes replacement copy; Claude does NOT propose statistical
    claims, sample-size recommendations, or interpretations.
  - Replacement copy is generated only when there's a flag. We never
    burn Haiku tokens on questions that already look clean.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

Tone = str  # "warn" | "info"


@dataclass
class LintFlag:
    """One actionable advisory note about a question's prompt or config."""

    code: str  # stable ID, e.g. "double_barreled"
    tone: Tone
    label: str
    detail: str
    suggested_replacement: str | None = None  # Claude-generated rewrite


@dataclass
class LintResult:
    flags: list[LintFlag] = field(default_factory=list)


# ── Layer 1: regex flags ─────────────────────────────────────────────


_LEADING_ADJECTIVES = re.compile(
    r"\b(love|hate|amazing|terrible|brilliant|awful|fantastic|atrocious|"
    r"wonderful|abysmal|stellar|horrible|delightful)\b",
    re.IGNORECASE,
)
_DOUBLE_BARREL_CONNECTORS = re.compile(
    r"\b(and|or)\b", re.IGNORECASE
)
_VAGUE_INTENSIFIERS = re.compile(
    r"\b(very|really|extremely|highly|quite|rather|pretty)\b", re.IGNORECASE
)
_AGREE_DISAGREE_BIAS = re.compile(
    r"\b(don't you (think|agree)|wouldn't you (say|agree)|isn't it true)\b",
    re.IGNORECASE,
)


def _regex_flags(prompt: str, question_type: str, config: dict[str, Any]) -> list[LintFlag]:
    flags: list[LintFlag] = []
    text = prompt.strip()
    word_count = len(text.split())

    # Double-barreled — only fire when the prompt is long enough that
    # an "and" probably connects two substantive constructs (rather than
    # a discourse marker like "and then").
    if word_count >= 7 and _DOUBLE_BARREL_CONNECTORS.search(text):
        flags.append(
            LintFlag(
                code="double_barreled",
                tone="warn",
                label="Possible double-barreled question",
                detail=(
                    "This question may be asking about two things at once. Split it into two "
                    "separate questions so you know which factor matters to respondents."
                ),
            )
        )

    if _LEADING_ADJECTIVES.search(text):
        flags.append(
            LintFlag(
                code="leading_wording",
                tone="warn",
                label="Leading wording detected",
                detail=(
                    "Loaded adjectives nudge respondents toward a specific answer. Try a "
                    "neutral framing that doesn't telegraph the desired response."
                ),
            )
        )

    if _AGREE_DISAGREE_BIAS.search(text):
        flags.append(
            LintFlag(
                code="agree_disagree_bias",
                tone="warn",
                label="Acquiescence-bias phrasing",
                detail=(
                    "Phrases like \"Don't you agree…\" prime agreement. Reword as a neutral "
                    "question that asks the respondent for their actual view."
                ),
            )
        )

    if _VAGUE_INTENSIFIERS.search(text) and word_count < 12:
        flags.append(
            LintFlag(
                code="vague_intensifier",
                tone="info",
                label="Vague intensifier",
                detail=(
                    "Words like \"very\" or \"really\" mean different things to different "
                    "respondents. A more specific anchor (frequency, time, money) makes "
                    "answers comparable across people."
                ),
            )
        )

    if 0 < word_count < 4:
        flags.append(
            LintFlag(
                code="too_short",
                tone="info",
                label="Prompt is very short",
                detail=(
                    "Questions under 4 words often miss context. Add the specific behaviour, "
                    "timeframe, or scope you're asking about."
                ),
            )
        )

    # Likert scale balance — config validator already enforces this, but a
    # researcher may pass a custom config that slipped through. Surface it.
    if question_type == "likert":
        scale = config.get("scale", 5)
        if scale not in (5, 7):
            flags.append(
                LintFlag(
                    code="unbalanced_scale",
                    tone="warn",
                    label="Likert scale is unbalanced",
                    detail=(
                        f"Scale length {scale} is unusual. 5- and 7-point scales are the "
                        "validated defaults — unbalanced or non-standard scales bias responses."
                    ),
                )
            )

    return flags


# ── Layer 2: Claude rewrites ─────────────────────────────────────────


_REWRITE_PROMPT = """\
You are a senior survey methodologist coaching a researcher. They wrote
a survey question that needs improvement. Your job is to propose a
single rewritten version of the prompt that addresses the issues listed,
following standard methodology (neutral framing, no double-barrel, no
loaded adjectives, no acquiescence bias).

Output STRICT JSON with this shape, nothing else:

{
  "rewrite": "<the rewritten prompt sentence>"
}

Rules:
- Keep the topic the researcher cares about. Do not invent a new subject.
- Stay under 30 words.
- Plain language. No academic jargon. No "Please rate…" preamble.
- Never propose multiple alternatives. One rewrite only.
"""


def _maybe_call_claude_for_rewrite(prompt: str, flag_codes: list[str]) -> str | None:
    """Ask Claude Haiku for ONE rewritten prompt.

    Returns None when the API key is absent (tests / dev), so the coach
    still surfaces the regex flag with no replacement copy. Real Haiku
    calls are cheap (~$0.0001 per call) and fast (~400ms).
    """

    if not settings.ANTHROPIC_API_KEY:
        return None
    if not flag_codes:
        return None

    try:
        import anthropic  # noqa: WPS433 — keep import lazy for test environments
        import httpx
    except ImportError:
        return None

    user = (
        f"<original_prompt>{prompt}</original_prompt>\n"
        f"<flagged_issues>{', '.join(flag_codes)}</flagged_issues>\n\n"
        "Return the JSON object now. No prose around it."
    )
    try:
        client = anthropic.Anthropic(
            api_key=settings.ANTHROPIC_API_KEY, timeout=httpx.Timeout(10.0)
        )
        resp = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=200,
            temperature=0.2,
            system=_REWRITE_PROMPT,
            messages=[{"role": "user", "content": user}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            lines = [l for l in raw.split("\n") if not l.strip().startswith("```")]
            raw = "\n".join(lines).strip()
        import json as _json
        parsed = _json.loads(raw)
        rewrite = parsed.get("rewrite")
        if isinstance(rewrite, str) and rewrite.strip():
            return rewrite.strip()
    except Exception:  # noqa: BLE001 — never break the editor on a coach failure
        logger.exception("Question coach Haiku rewrite failed")
    return None


# ── Public entry point ───────────────────────────────────────────────


def lint_question(
    *,
    prompt: str,
    question_type: str,
    config: dict[str, Any] | None = None,
    with_rewrite: bool = True,
) -> LintResult:
    """Lint a question prompt + config; optionally add a Claude rewrite.

    Always returns the regex flag list. Rewrite is attached to the first
    rewriteable flag (we never propose more than one rewrite per call —
    multiple rewrites are noise).
    """

    flags = _regex_flags(prompt, question_type, config or {})

    rewriteable_codes = [
        f.code for f in flags if f.code in {
            "double_barreled", "leading_wording", "agree_disagree_bias",
        }
    ]
    if with_rewrite and rewriteable_codes:
        rewrite = _maybe_call_claude_for_rewrite(prompt, rewriteable_codes)
        if rewrite:
            for f in flags:
                if f.code in rewriteable_codes:
                    f.suggested_replacement = rewrite
                    break

    return LintResult(flags=flags)
