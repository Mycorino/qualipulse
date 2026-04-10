"""Generate a short business summary for an onboarding company URL.

Two-tier strategy (no HTTP scraping):

1. **Knowledge pass** — Ask Claude directly, without tools, whether it already
   knows the site from training data. For famous brands (stripe.com,
   airbnb.com, e.leclerc, university.edu, ...) this returns a clean summary
   in ~1–2s and costs about $0.001.

2. **Web search fallback** — If Claude responds ``UNKNOWN``, retry the same
   request with Anthropic's ``web_search`` server tool enabled. Claude
   executes the search itself, reads the results, and synthesizes. This
   handles modern JS-only SPAs, Cloudflare-protected sites, and anything a
   real browser could see. Costs ~$0.01 per call (one search) + tokens.

3. **Manual fallback** — If both passes fail we raise
   ``WebsiteIntelligenceError`` and the UI prompts the user to describe their
   business in the textarea we already render.

This replaces the previous httpx + BeautifulSoup pipeline, which blindly
passed raw HTML to Claude and hallucinated summaries of 403 pages and cookie
walls.
"""

import logging
import re

from anthropic import Anthropic

from app.config import settings

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-20250514"
_MAX_TOKENS = 300

# Sentinel Claude returns when it has no useful knowledge of the URL/brand.
_UNKNOWN_SENTINEL = "UNKNOWN"

_BASE_INSTRUCTIONS = (
    "You are helping onboard a researcher onto a user-research SaaS. They "
    "just typed their company's website URL. Write a 2-3 sentence summary of "
    "what this company does, who their customers are, and what market they "
    "operate in. Be specific and factual. Third person, no marketing fluff, "
    "no emojis, no quotation marks around the URL."
)

_KNOWLEDGE_PROMPT = (
    _BASE_INSTRUCTIONS
    + "\n\n"
    + "If you are NOT confident about what this specific company does — for "
    + "example you've never heard of them, or the URL is too generic to "
    + "identify a single business — respond with exactly the single word "
    + f"{_UNKNOWN_SENTINEL} and nothing else. Do not guess. Do not describe "
    + "what a company at a similar-sounding domain might do.\n\n"
    + "Company URL: {url}\n\nSummary:"
)

_SEARCH_PROMPT = (
    _BASE_INSTRUCTIONS
    + "\n\n"
    + "Search the web for information about the company at this URL, then "
    + "write the summary. If after searching you still cannot determine what "
    + f"this business does, respond with exactly the single word {_UNKNOWN_SENTINEL}.\n\n"
    + "Company URL: {url}\n\nSummary:"
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
    # First word is UNKNOWN, followed by space/punctuation
    if re.match(rf"^{_UNKNOWN_SENTINEL}\b", stripped):
        return True
    return False


def _log_usage(db, message, company_id) -> None:
    if db is None:
        return
    try:
        from app.services.usage_logger import log_claude_usage
        log_claude_usage(db, message, "website_intel", company_id=company_id)
    except Exception:  # pragma: no cover — logging must never break the flow
        pass


async def fetch_website_summary(url: str, db=None, company_id=None) -> str:
    """Produce a business summary for ``url`` using Claude's knowledge first,
    then the ``web_search`` tool as a fallback.

    Raises ``WebsiteIntelligenceError`` if neither pass yields a usable
    summary so the UI can surface a localized message and let the user
    describe their business manually.
    """
    clean_url = _normalize_url(url)
    if not clean_url:
        raise WebsiteIntelligenceError("empty", "No URL provided.")

    if not settings.ANTHROPIC_API_KEY:
        logger.warning("website_intel.no_api_key")
        raise WebsiteIntelligenceError(
            "ai_failed", "The AI service is not configured."
        )

    ai_client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    # ── Pass 1: knowledge-only ────────────────────────────────────────────
    try:
        knowledge_msg = ai_client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            messages=[{
                "role": "user",
                "content": _KNOWLEDGE_PROMPT.format(url=clean_url),
            }],
        )
    except Exception as exc:
        logger.warning(
            "website_intel.knowledge_pass_failed",
            extra={"url": clean_url, "error": str(exc)},
        )
        raise WebsiteIntelligenceError(
            "ai_failed",
            "We couldn't generate a summary right now. Please describe your "
            "business manually below.",
        )

    _log_usage(db, knowledge_msg, company_id)
    knowledge_text = _extract_text(knowledge_msg)

    if knowledge_text and not _is_unknown(knowledge_text):
        logger.info("website_intel.knowledge_hit", extra={"url": clean_url})
        return knowledge_text

    logger.info("website_intel.knowledge_miss", extra={"url": clean_url})

    # ── Pass 2: web_search fallback ───────────────────────────────────────
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
                "content": _SEARCH_PROMPT.format(url=clean_url),
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

    if search_text and not _is_unknown(search_text):
        logger.info("website_intel.search_hit", extra={"url": clean_url})
        return search_text

    logger.info("website_intel.search_miss", extra={"url": clean_url})
    raise WebsiteIntelligenceError(
        "empty",
        "We couldn't identify what this business does from their website. "
        "Please describe it manually below.",
    )
