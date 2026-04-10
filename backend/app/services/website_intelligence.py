"""Website scraping + Claude summarization for onboarding business intelligence."""

import logging

import httpx
from anthropic import Anthropic
from bs4 import BeautifulSoup

from app.config import settings

logger = logging.getLogger(__name__)

# A realistic desktop Chrome UA — bare "Mozilla/5.0" gets a 403 from Cloudflare
# and other WAFs, which used to end up as "403 Forbidden" being summarized as
# real company content.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}


class WebsiteIntelligenceError(Exception):
    """Raised when we can't produce a meaningful summary from a URL."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code  # unreachable | blocked | empty | ai_failed
        self.message = message


async def fetch_website_summary(url: str, db=None, company_id=None) -> str:
    """Fetch a website and use Claude to generate a 2-3 sentence business summary.

    Raises WebsiteIntelligenceError with a user-actionable code when the site
    can't be scraped (network failure, bot-protection block, empty page, etc.).
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        async with httpx.AsyncClient(
            timeout=10.0, follow_redirects=True, headers=_BROWSER_HEADERS
        ) as client:
            resp = await client.get(url)
    except httpx.TimeoutException:
        logger.info("website_intel.timeout", extra={"url": url})
        raise WebsiteIntelligenceError(
            "unreachable", "The website took too long to respond."
        )
    except httpx.HTTPError as exc:
        logger.info("website_intel.http_error", extra={"url": url, "error": str(exc)})
        raise WebsiteIntelligenceError(
            "unreachable", "We couldn't reach that website."
        )

    if resp.status_code >= 400:
        logger.info(
            "website_intel.bad_status",
            extra={"url": url, "status": resp.status_code},
        )
        if resp.status_code in (401, 403, 429) or resp.status_code == 503:
            raise WebsiteIntelligenceError(
                "blocked",
                "The website blocked our scraper (bot protection). "
                "Please describe your business manually below.",
            )
        raise WebsiteIntelligenceError(
            "unreachable",
            f"The website returned an error (HTTP {resp.status_code}).",
        )

    html = resp.text or ""
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.string or "").strip() if soup.title else ""
    meta_desc = ""
    meta = soup.find("meta", attrs={"name": "description"})
    if meta:
        meta_desc = (meta.get("content") or "").strip()
    og_desc = ""
    og = soup.find("meta", attrs={"property": "og:description"})
    if og:
        og_desc = (og.get("content") or "").strip()
    headings = " ".join(
        h.get_text(strip=True) for h in soup.find_all(["h1", "h2"])[:5]
    )
    body_text = soup.get_text(separator=" ", strip=True)[:2000]

    # If the page is essentially empty (JS-only SPA, cookie wall, etc.), bail
    # before calling Claude. Otherwise Claude cheerfully "summarizes" the
    # cookie banner.
    total_content_len = len((title + meta_desc + og_desc + headings + body_text).strip())
    if total_content_len < 80:
        logger.info(
            "website_intel.empty",
            extra={"url": url, "content_len": total_content_len},
        )
        raise WebsiteIntelligenceError(
            "empty",
            "We couldn't extract readable content from this website. "
            "Please describe your business manually below.",
        )

    content = (
        f"Title: {title}\n"
        f"Meta description: {meta_desc}\n"
        f"Open Graph description: {og_desc}\n"
        f"Headings: {headings}\n"
        f"Content: {body_text}"
    )

    try:
        ai_client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        message = ai_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": (
                    "Based on this website content, write a 2-3 sentence summary of "
                    "what this company does, who their customers are, and what market "
                    "they operate in. Be specific and factual. Write in third person. "
                    "If the content looks like an error page, a cookie banner, or a "
                    "blank landing page with no business information, respond with "
                    "exactly: UNUSABLE\n\n"
                    f"{content}\n\n"
                    "Summary:"
                ),
            }],
        )
    except Exception as exc:
        logger.warning("website_intel.ai_failed", extra={"url": url, "error": str(exc)})
        raise WebsiteIntelligenceError(
            "ai_failed",
            "We couldn't generate a summary for this website. "
            "Please describe your business manually below.",
        )

    if db is not None:
        try:
            from app.services.usage_logger import log_claude_usage
            log_claude_usage(db, message, "website_intel", company_id=company_id)
        except Exception:
            pass

    summary = (message.content[0].text or "").strip()
    if not summary or "UNUSABLE" in summary.upper():
        raise WebsiteIntelligenceError(
            "empty",
            "We couldn't identify what this business does from their website. "
            "Please describe it manually below.",
        )
    return summary
