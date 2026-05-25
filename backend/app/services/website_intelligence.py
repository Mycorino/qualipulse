"""Generate a short business summary for an onboarding company URL.

**Fetch-first strategy**: we always fetch the actual website HTML, extract
readable text, and feed it to Claude for summarization. This eliminates
hallucination from pattern-matching on similar-sounding domains (e.g.
``qualipulse.com`` was described as "Ideagen Q-Pulse" when we relied on
web_search alone).

1. **Direct fetch** — HTTP GET the URL, extract visible text from the HTML.
   If successful, Claude summarizes the *actual page content* — no web
   search needed, no hallucination possible.

2. **Web search fallback** — If the direct fetch fails (blocked, timeout,
   non-HTML response), fall back to Claude + ``web_search`` tool as before.

3. **Manual fallback** — On total failure the UI flips into ``manualMode``
   and the user describes their business in the textarea we already render.

Returns a structured ``{"summary": str, "industry": str | None}`` so the
onboarding UI can auto-preselect the industry chip in addition to populating
the free-text summary.
"""

import json
import logging
import re
from html.parser import HTMLParser

import httpx
from anthropic import Anthropic

from app.config import settings

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-20250514"
_MAX_TOKENS = 500

# Sentinel Claude returns when it has no useful knowledge of the URL/brand.
_UNKNOWN_SENTINEL = "UNKNOWN"

# Max chars of page text to send to Claude (keeps tokens reasonable).
_MAX_PAGE_TEXT_CHARS = 12_000

# Predefined industries the frontend shows as selectable chips. We ask Claude
# to prefer one of these when possible, but it can return a custom label and
# the UI will render it as a new chip.
_PREDEFINED_INDUSTRIES = [
    "SaaS / Software",
    "Fintech / Banking / Insurance",
    "E-commerce / Retail",
    "Consumer goods / D2C",
    "Healthcare / Pharma / Biotech",
    "Media / Entertainment",
    "Education / EdTech",
    "Construction / Real estate / PropTech",
    "Manufacturing / Industrial",
    "Transportation / Logistics / Mobility",
    "Energy / Utilities / Sustainability",
    "Public sector / NGO / Non-profit",
    "Professional services / Consulting",
    "Hospitality / Travel / F&B",
    "Telecoms",
    "Agriculture / Food production",
    "Other",
]

_LANGUAGE_DIRECTIVES = {
    "en": "Write the summary in English.",
    "fr": "Écris le résumé en français (le JSON et les clés restent en anglais, seule la valeur du champ \"summary\" est en français).",
}

_BASE_INSTRUCTIONS = (
    "You are helping onboard a researcher onto a user-research SaaS. They just typed "
    "their company's website URL. Extract — do NOT pattern-match on similar-sounding "
    "brands and do NOT use marketing copy verbatim. Your job is to surface three things: "
    "(1) what this company sells, (2) who they sell it to, (3) what makes them different "
    "(if anything is clearly stated). The output is a 2-3 sentence factual summary and "
    "an industry classification."
)

_OUTPUT_SPEC = (
    "Respond with ONLY a single JSON object (no prose, no markdown fences) "
    "with this exact shape:\n"
    "{\n"
    '  "summary": "<2-3 sentence factual description: what the company does, '
    'who their customers are, what market they operate in. Third person, no '
    'marketing fluff, no emojis.>",\n'
    '  "industry": "<one of: SaaS / Software | Fintech / Banking / Insurance | '
    'E-commerce / Retail | Consumer goods / D2C | Healthcare / Pharma / Biotech | '
    'Media / Entertainment | Education / EdTech | Construction / Real estate / '
    'PropTech | Manufacturing / Industrial | Transportation / Logistics / '
    'Mobility | Energy / Utilities / Sustainability | Public sector / NGO / '
    'Non-profit | Professional services / Consulting | Hospitality / Travel / '
    'F&B | Telecoms | Agriculture / Food production | Other. Classify by the '
    'business\'s primary revenue activity, NOT by whether it uses software, has '
    'a website, or operates digitally. A transport operator with a mobile app '
    'is Transportation, not SaaS. A bank that builds fintech products is '
    'Fintech, not SaaS. Quote the deciding evidence from the summary before '
    'answering. When sparse, return \\"Other\\" rather than confabulating.>",\n'
    '  "primary_country": "<the company\'s main market as one of: fr | be | '
    'ch | de | uk | es | it | nl | pt | europe | us | ca | global | other. '
    'Use the lowercase ISO alpha-2 code for a single country; use '
    '\\"europe\\" if they serve multiple European countries without one '
    'clearly dominant; use \\"global\\" if they operate worldwide; use '
    '\\"other\\" for a single non-listed country.>"\n'
    "}\n\n"
    "Prefer one of the predefined industry values when it reasonably fits. "
    "Only invent a custom label (e.g. \"Retail\", \"Banking\", \"Energy\") "
    "when the predefined list is clearly wrong.\n\n"
    "For primary_country, use the domain TLD, language, currency, physical "
    "store locations, and any \"about\" page as signal. A .fr domain with "
    "French prose is almost certainly fr; a .com SaaS selling to US "
    "enterprises is us; a multinational retailer is europe or global.\n\n"
    "**The summary value must be plain prose only.** Do NOT include HTML "
    "tags, markdown, footnotes, citation markers, ``<cite>`` blocks, or "
    "``[1]`` style references. Return clean sentences with no source "
    "attribution embedded in the text."
)

# Allowed primary_country values — must stay in sync with REGION_VALUES in
# frontend/src/pages/Welcome.tsx.
_ALLOWED_COUNTRIES = {
    "fr", "be", "ch", "de", "uk", "es", "it", "nl", "pt",
    "europe", "us", "ca", "global", "other",
}


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


# ---------------------------------------------------------------------------
# HTML → plain text extractor
# ---------------------------------------------------------------------------

class _HTMLTextExtractor(HTMLParser):
    """Lightweight HTML→text converter. Strips scripts, styles, and tags;
    keeps the visible prose that a human would read on the page."""

    _SKIP_TAGS = frozenset({"script", "style", "noscript", "svg", "head"})

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, _attrs):
        if tag.lower() in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            text = data.strip()
            if text:
                self._parts.append(text)

    def get_text(self) -> str:
        return " ".join(self._parts)


def _html_to_text(html: str) -> str:
    """Extract readable text from an HTML string."""
    extractor = _HTMLTextExtractor()
    try:
        extractor.feed(html)
    except Exception:
        pass
    return extractor.get_text()


# ---------------------------------------------------------------------------
# Direct page fetch
# ---------------------------------------------------------------------------

_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; QualiPulseBot/1.0; "
        "+https://qualipulse.com/about)"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
}


async def _fetch_page_text(url: str) -> str | None:
    """Fetch a URL and return its visible text content, or None on failure.

    Follows redirects (up to 5), respects a 10s timeout, and only processes
    HTML responses. Returns None (triggering web_search fallback) for:
    - network errors, timeouts, non-2xx status
    - non-HTML content types (PDFs, images, etc.)
    - pages with too little visible text (< 50 chars — likely a JS-only SPA)
    """
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            max_redirects=5,
            timeout=httpx.Timeout(10.0, connect=5.0),
            headers=_FETCH_HEADERS,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "html" not in content_type.lower():
                logger.info(
                    "website_intel.fetch_not_html",
                    extra={"url": url, "content_type": content_type},
                )
                return None

            html = resp.text
            text = _html_to_text(html)

            if len(text) < 50:
                logger.info(
                    "website_intel.fetch_too_short",
                    extra={"url": url, "text_len": len(text)},
                )
                return None

            # Truncate to keep Claude prompt tokens reasonable
            if len(text) > _MAX_PAGE_TEXT_CHARS:
                text = text[:_MAX_PAGE_TEXT_CHARS] + "…"

            logger.info(
                "website_intel.fetch_ok",
                extra={"url": url, "text_len": len(text)},
            )
            return text

    except Exception as exc:
        logger.info(
            "website_intel.fetch_failed",
            extra={"url": url, "error": str(exc)},
        )
        return None


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

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
_CITE_OPEN_RE = re.compile(r"<cite\b[^>]*>", flags=re.IGNORECASE)
_CITE_CLOSE_RE = re.compile(r"</cite\s*>", flags=re.IGNORECASE)


def _strip_citation_tags(text: str) -> str:
    """Remove ``<cite index="...">…</cite>`` markup from a summary string."""
    if not text:
        return text
    cleaned = _CITE_OPEN_RE.sub("", text)
    cleaned = _CITE_CLOSE_RE.sub("", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def _parse_response(text: str) -> dict | None:
    """Parse Claude's JSON response. Returns dict or None if unparseable."""
    if not text:
        return None
    if _is_unknown(text):
        return None

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)

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
    primary_country = payload.get("primary_country")

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

    cleaned_country: str | None = None
    if isinstance(primary_country, str):
        code = primary_country.strip().lower()
        if code in _ALLOWED_COUNTRIES:
            cleaned_country = code

    return {
        "summary": summary,
        "industry": cleaned_industry,
        "primary_country": cleaned_country,
    }


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_prompt_with_content(url: str, page_text: str, language: str) -> str:
    """Build a prompt that includes the actual fetched page content.

    Claude has no excuse to hallucinate here — the website text is right
    in front of it. We explicitly tell it to describe ONLY what the page
    says, not what it might recall from training.
    """
    lang_directive = _LANGUAGE_DIRECTIVES.get(language, _LANGUAGE_DIRECTIVES["en"])
    return (
        f"{_BASE_INSTRUCTIONS}\n\n"
        f"{lang_directive}\n\n"
        "Below is the actual text content fetched from the company's website. "
        "Base your summary EXCLUSIVELY on this content. Do NOT use your "
        "training knowledge about similarly-named companies — describe only "
        "what is evident from the page text below.\n\n"
        f"If the page text is too generic or unclear to determine what the "
        f"business does, return the single word {_UNKNOWN_SENTINEL} (no JSON).\n\n"
        f"{_OUTPUT_SPEC}\n\n"
        f"Company URL: {url}\n\n"
        f"--- BEGIN PAGE CONTENT ---\n{page_text}\n--- END PAGE CONTENT ---"
    )


def _build_prompt_web_search(url: str, language: str) -> str:
    """Build a web-search prompt (fallback when direct fetch fails)."""
    lang_directive = _LANGUAGE_DIRECTIVES.get(language, _LANGUAGE_DIRECTIVES["en"])
    retrieval = (
        "**You must search the web for this exact website before answering.** "
        "Use the web_search tool to search for the EXACT domain in the URL "
        "below — not a similar-sounding brand, not a company with a related "
        "name. The summary must describe whatever business actually operates "
        "at that specific domain.\n\n"
        "Do NOT pattern-match on the company name. For example, if the URL "
        "is ``foo-pulse.com``, do not describe a different product also "
        "called ``Pulse``. Search for ``foo-pulse.com`` directly.\n\n"
        "If after searching you still cannot determine what the business at "
        f"this exact domain does, return the single word {_UNKNOWN_SENTINEL} "
        "(no JSON)."
    )
    return (
        f"{_BASE_INSTRUCTIONS}\n\n"
        f"{lang_directive}\n\n"
        f"{retrieval}\n\n"
        f"{_OUTPUT_SPEC}\n\n"
        f"Company URL: {url}"
    )


# ---------------------------------------------------------------------------
# Usage logging
# ---------------------------------------------------------------------------

def _log_usage(db, message, company_id) -> None:
    if db is None:
        return
    try:
        from app.services.usage_logger import log_claude_usage
        log_claude_usage(db, message, "website_intel", company_id=company_id)
    except Exception:  # pragma: no cover — logging must never break the flow
        pass


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def fetch_website_summary(
    url: str,
    language: str = "en",
    db=None,
    company_id=None,
) -> dict:
    """Produce a business summary and industry classification for ``url``.

    Strategy:
      1. Fetch the actual page HTML → extract text → summarize with Claude.
         This is the most reliable path: Claude sees the real page content
         and cannot hallucinate from training data.
      2. If direct fetch fails (blocked, timeout, JS-only SPA), fall back
         to Claude + web_search tool.
      3. If both fail, raise WebsiteIntelligenceError → UI shows manual mode.

    Args:
        url: The company website URL the user typed.
        language: ISO language code for the summary prose (``"en"`` or ``"fr"``).
        db: Optional DB session for AI usage logging.
        company_id: Optional company ID for AI usage logging.

    Returns:
        A dict with keys ``summary`` (str), ``industry`` (str | None),
        and ``primary_country`` (str | None).

    Raises:
        WebsiteIntelligenceError: if Claude can't identify the business.
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

    # ── Strategy 1: Direct fetch → Claude summarization ──────────────────
    page_text = await _fetch_page_text(clean_url)

    if page_text:
        try:
            msg = ai_client.messages.create(
                model=_MODEL,
                max_tokens=_MAX_TOKENS,
                temperature=0.3,
                messages=[{
                    "role": "user",
                    "content": _build_prompt_with_content(
                        clean_url, page_text, lang
                    ),
                }],
            )
            _log_usage(db, msg, company_id)
            parsed = _parse_response(_extract_text(msg))
            if parsed is not None:
                logger.info(
                    "website_intel.direct_fetch_hit",
                    extra={
                        "url": clean_url,
                        "industry": parsed.get("industry"),
                    },
                )
                return parsed
            logger.info(
                "website_intel.direct_fetch_parse_fail",
                extra={"url": clean_url},
            )
        except Exception as exc:
            logger.warning(
                "website_intel.direct_summarize_failed",
                extra={"url": clean_url, "error": str(exc)},
            )

    # ── Strategy 2: Web search fallback ──────────────────────────────────
    logger.info(
        "website_intel.falling_back_to_search",
        extra={"url": clean_url, "had_page_text": page_text is not None},
    )
    try:
        search_msg = ai_client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            temperature=0.3,
            tools=[{
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 3,
            }],
            messages=[{
                "role": "user",
                "content": _build_prompt_web_search(clean_url, lang),
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
