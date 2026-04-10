"""Generate a short business summary for an onboarding company URL.

Single-pass strategy using Claude + the ``web_search`` server tool. We used
to do a "knowledge-first" pass (no tools) to save ~$0.01 on famous brands,
but Claude would confidently hallucinate on similar-sounding domains — e.g.
``qualipulse.com`` got described as "Ideagen Q-Pulse" (an unrelated UK
quality-management vendor). Always forcing a real web search trades ~$0.01
and ~1s of latency for dramatically higher correctness, which is the right
call for a first-impression onboarding flow.

1. **Web search pass** — Claude is given the URL plus the ``web_search``
   tool and asked to return a structured ``{"summary", "industry"}`` JSON
   payload. If after searching Claude still can't identify the business,
   it returns the ``UNKNOWN`` sentinel and we raise.

2. **Manual fallback** — On failure the UI flips into ``manualMode`` and
   the user describes their business in the textarea we already render.

Returns a structured ``{"summary": str, "industry": str | None}`` so the
onboarding UI can auto-preselect the industry chip in addition to populating
the free-text summary.
"""

import json
import logging
import re

from anthropic import Anthropic

from app.config import settings

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-20250514"
_MAX_TOKENS = 500

# Sentinel Claude returns when it has no useful knowledge of the URL/brand.
_UNKNOWN_SENTINEL = "UNKNOWN"

# Predefined industries the frontend shows as selectable chips. We ask Claude
# to prefer one of these when possible, but it can return a custom label and
# the UI will render it as a new chip.
_PREDEFINED_INDUSTRIES = [
    "Consumer Brands",
    "SaaS / Tech",
    "Agency",
    "Healthcare",
    "Academia",
    "Government",
    "Other",
]

_LANGUAGE_DIRECTIVES = {
    "en": "Write the summary in English.",
    "fr": "Écris le résumé en français (le JSON et les clés restent en anglais, seule la valeur du champ \"summary\" est en français).",
}

_BASE_INSTRUCTIONS = (
    "You are helping onboard a researcher onto a user-research SaaS. They "
    "just typed their company's website URL. Your job is to produce a short "
    "business summary AND classify the company into an industry bucket."
)

_OUTPUT_SPEC = (
    "Respond with ONLY a single JSON object (no prose, no markdown fences) "
    "with this exact shape:\n"
    "{\n"
    '  "summary": "<2-3 sentence factual description: what the company does, '
    'who their customers are, what market they operate in. Third person, no '
    'marketing fluff, no emojis.>",\n'
    '  "industry": "<one of: Consumer Brands | SaaS / Tech | Agency | '
    'Healthcare | Academia | Government | Other — OR a short custom label '
    '(max 3 words) if none of the predefined options fit.>"\n'
    "}\n\n"
    "Prefer one of the predefined industry values when it reasonably fits. "
    "Only invent a custom label (e.g. \"Retail\", \"Banking\", \"Energy\") "
    "when the predefined list is clearly wrong.\n\n"
    "**The summary value must be plain prose only.** Do NOT include HTML "
    "tags, markdown, footnotes, citation markers, ``<cite>`` blocks, or "
    "``[1]`` style references. Even if you used web_search, return clean "
    "sentences with no source attribution embedded in the text."
)


class WebsiteIntelligenceError(Exception):
    """Raised when we can't produce a meaningful summary for a URL."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code  # unreachable | blocked | empty | ai_failed
        self.message = message


def _normalize_url(url: str) -> str:
    """Trim + add https:// if missing. We keep the full URL because web_search
    handles subpaths better than a bare domain."""
    url = (url or "").strip()
    if not url:
        return url
    if not re.match(r"^https?://", url, flags=re.IGNORECASE):
        url = "https://" + url
    return url


def _extract_text(message) -> str:
    """Concatenate all text blocks from an Anthropic response, ignoring
    tool-use / tool-result / citation blocks."""
    parts: list[str] = []
    for block in getattr(message, "content", []) or []:
        if getattr(block, "type", None) == "text":
            text = getattr(block, "text", "") or ""
            if text:
                parts.append(text)
    return " ".join(parts).strip()


def _is_unknown(text: str) -> bool:
    """Claude's UNKNOWN sentinel check — tolerant of trailing punctuation and
    the model wrapping it in a short sentence ('UNKNOWN.' or 'UNKNOWN — I ...')."""
    if not text:
        return True
    stripped = text.strip().upper()
    if stripped == _UNKNOWN_SENTINEL:
        return True
    if re.match(rf"^{_UNKNOWN_SENTINEL}\b", stripped):
        return True
    return False


# Citation tags Claude inlines into the prose when web_search produces a hit.
# Looks like: <cite index="11-1,11-6">E.Leclerc is...</cite>
# We strip the wrapping tags but keep the inner text — those tags are an
# artifact of the search tool and pollute the user-facing summary.
_CITE_OPEN_RE = re.compile(r"<cite\b[^>]*>", flags=re.IGNORECASE)
_CITE_CLOSE_RE = re.compile(r"</cite\s*>", flags=re.IGNORECASE)


def _strip_citation_tags(text: str) -> str:
    """Remove ``<cite index="...">…</cite>`` markup from a summary string.

    Claude's web_search tool wraps cited spans in inline ``<cite>`` tags. We
    keep the inner prose but drop the tag wrappers so the user sees clean
    sentences in the onboarding textarea.
    """
    if not text:
        return text
    cleaned = _CITE_OPEN_RE.sub("", text)
    cleaned = _CITE_CLOSE_RE.sub("", cleaned)
    # Collapse the double-spaces left behind by removed tags.
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def _parse_response(text: str) -> dict | None:
    """Parse Claude's JSON response. Returns ``{"summary": str, "industry": str | None}``
    or ``None`` if the payload is unparseable / contains the UNKNOWN sentinel.

    Tolerant of:
      - stray markdown fences (```json ... ```)
      - leading/trailing prose
      - Claude returning the bare UNKNOWN sentinel instead of JSON
      - inline ``<cite index="…">…</cite>`` tags in the summary value
    """
    if not text:
        return None
    if _is_unknown(text):
        return None

    # Strip markdown fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Remove opening fence (```json or ```)
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)

    # Find first { ... } block (Claude may emit a trailing sentence).
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        return None

    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None

    summary = payload.get("summary")
    industry = payload.get("industry")

    if not isinstance(summary, str) or not summary.strip():
        return None
    if _is_unknown(summary):
        return None

    summary = _strip_citation_tags(summary)
    if not summary:
        return None

    cleaned_industry: str | None = None
    if isinstance(industry, str) and industry.strip() and not _is_unknown(industry):
        cleaned_industry = _strip_citation_tags(industry.strip())

    return {"summary": summary, "industry": cleaned_industry}


def _build_prompt(url: str, language: str, *, with_search: bool) -> str:
    lang_directive = _LANGUAGE_DIRECTIVES.get(language, _LANGUAGE_DIRECTIVES["en"])
    if with_search:
        retrieval = (
            "**You must fetch the actual website before answering.** Use the "
            "web_search tool to search for information about the EXACT domain "
            "in the URL below — not a similar-sounding brand, not a company "
            "with a related name. The summary must describe whatever business "
            "actually operates at that specific domain.\n\n"
            "Do NOT pattern-match on the company name. For example, if the "
            "URL is ``foo-pulse.com``, do not describe a different product "
            "also called ``Pulse``. Search for ``foo-pulse.com`` directly "
            "and read the site.\n\n"
            "If after searching you still cannot determine what the business "
            f"at this exact domain does, return the single word {_UNKNOWN_SENTINEL} "
            "(no JSON)."
        )
    else:
        retrieval = (
            "If you are NOT confident about what this specific company does — "
            "for example you've never heard of them, or the URL is too generic "
            "to identify a single business — return the single word "
            f"{_UNKNOWN_SENTINEL} (no JSON). Do not guess. Do not describe what "
            "a company at a similar-sounding domain might do."
        )
    return (
        f"{_BASE_INSTRUCTIONS}\n\n"
        f"{lang_directive}\n\n"
        f"{retrieval}\n\n"
        f"{_OUTPUT_SPEC}\n\n"
        f"Company URL: {url}"
    )


def _log_usage(db, message, company_id) -> None:
    if db is None:
        return
    try:
        from app.services.usage_logger import log_claude_usage
        log_claude_usage(db, message, "website_intel", company_id=company_id)
    except Exception:  # pragma: no cover — logging must never break the flow
        pass


async def fetch_website_summary(
    url: str,
    language: str = "en",
    db=None,
    company_id=None,
) -> dict:
    """Produce a business summary and industry classification for ``url``
    using Claude with the ``web_search`` tool.

    Args:
        url: The company website URL the user typed.
        language: ISO language code for the summary prose (``"en"`` or ``"fr"``).
        db: Optional DB session for AI usage logging.
        company_id: Optional company ID for AI usage logging.

    Returns:
        A dict with keys ``summary`` (str) and ``industry`` (str | None).

    Raises:
        WebsiteIntelligenceError: if Claude can't identify the business
        even after searching.
    """
    clean_url = _normalize_url(url)
    if not clean_url:
        raise WebsiteIntelligenceError("empty", "No URL provided.")

    if not settings.ANTHROPIC_API_KEY:
        logger.warning("website_intel.no_api_key")
        raise WebsiteIntelligenceError(
            "ai_failed", "The AI service is not configured."
        )

    lang = language if language in _LANGUAGE_DIRECTIVES else "en"
    ai_client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    # Single pass: always use web_search. A knowledge-only pre-pass was
    # tried but Claude pattern-matched similar-sounding domains into
    # confident wrong answers (e.g. qualipulse.com → "Ideagen Q-Pulse").
    try:
        search_msg = ai_client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            tools=[{
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 3,
            }],
            messages=[{
                "role": "user",
                "content": _build_prompt(clean_url, lang, with_search=True),
            }],
        )
    except Exception as exc:
        logger.warning(
            "website_intel.search_pass_failed",
            extra={"url": clean_url, "error": str(exc)},
        )
        raise WebsiteIntelligenceError(
            "ai_failed",
            "We couldn't generate a summary right now. Please describe your "
            "business manually below.",
        )

    _log_usage(db, search_msg, company_id)
    search_text = _extract_text(search_msg)
    parsed = _parse_response(search_text)

    if parsed is not None:
        logger.info(
            "website_intel.search_hit",
            extra={"url": clean_url, "industry": parsed.get("industry")},
        )
        return parsed

    logger.info("website_intel.search_miss", extra={"url": clean_url})
    raise WebsiteIntelligenceError(
        "empty",
        "We couldn't identify what this business does from their website. "
        "Please describe it manually below.",
    )


__all__ = ["fetch_website_summary", "WebsiteIntelligenceError", "_PREDEFINED_INDUSTRIES"]
