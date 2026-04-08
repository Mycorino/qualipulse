"""Website scraping + Claude summarization for onboarding business intelligence."""

import httpx
from bs4 import BeautifulSoup
from anthropic import Anthropic

from app.config import settings


async def fetch_website_summary(url: str) -> str:
    """Fetch a website and use Claude to generate a 2-3 sentence business summary."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            html = resp.text
    except Exception:
        return ""

    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.string if soup.title else ""
    meta_desc = ""
    meta = soup.find("meta", attrs={"name": "description"})
    if meta:
        meta_desc = meta.get("content", "")
    headings = " ".join(h.get_text() for h in soup.find_all(["h1", "h2"])[:5])
    body_text = soup.get_text(separator=" ", strip=True)[:2000]

    content = (
        f"Title: {title}\n"
        f"Meta description: {meta_desc}\n"
        f"Headings: {headings}\n"
        f"Content: {body_text}"
    )

    ai_client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    message = ai_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": (
                "Based on this website content, write a 2-3 sentence summary of what this "
                "company does, who their customers are, and what market they operate in. "
                "Be specific and factual. Write in third person.\n\n"
                f"{content}\n\n"
                "Summary:"
            ),
        }],
    )
    return message.content[0].text.strip()
