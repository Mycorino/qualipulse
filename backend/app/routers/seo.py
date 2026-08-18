"""Machine-readable SEO surfaces served from the backend.

``/sitemap.xml`` used to be a static file in ``frontend/public``. It listed
the public routes but not the blog articles (crawlers could only find those
by following links on /blog) and it carried no ``lastmod``, so Google had no
signal to re-crawl an edited page. Generating it here keeps it in sync with
the ``blog_posts`` table for free: publish an article and it is in the
sitemap on the next fetch.

The frontend nginx proxies ``/sitemap.xml`` here so the file stays on the
public origin (app.qualipulse.com), which is what robots.txt advertises and
what Search Console expects.
"""

from datetime import datetime
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_db
from app.models.blog import BlogPost

router = APIRouter(tags=["seo"])

# Genuinely public, indexable routes. Everything else is either auth-walled
# or token-scoped and is disallowed in robots.txt.
_STATIC_ROUTES: list[tuple[str, str, str]] = [
    ("/", "weekly", "1.0"),
    ("/signup", "monthly", "0.9"),
    ("/blog", "weekly", "0.8"),
    ("/login", "monthly", "0.4"),
    ("/terms", "yearly", "0.3"),
    ("/privacy", "yearly", "0.3"),
    ("/dpa", "yearly", "0.2"),
    ("/subprocessors", "yearly", "0.2"),
    ("/participant-notice", "yearly", "0.2"),
    ("/ai-use-policy", "yearly", "0.2"),
    ("/retention-policy", "yearly", "0.2"),
]


def _url(loc: str, changefreq: str, priority: str, lastmod: datetime | None = None) -> str:
    parts = [f"    <loc>{escape(loc)}</loc>"]
    if lastmod is not None:
        parts.append(f"    <lastmod>{lastmod.strftime('%Y-%m-%d')}</lastmod>")
    parts.append(f"    <changefreq>{changefreq}</changefreq>")
    parts.append(f"    <priority>{priority}</priority>")
    body = "\n".join(parts)
    return f"  <url>\n{body}\n  </url>"


@router.get("/sitemap.xml")
def sitemap(db: Session = Depends(get_db)) -> Response:
    base = settings.APP_BASE_URL.rstrip("/")
    posts = (
        db.query(BlogPost)
        .filter(BlogPost.status == "published")
        .order_by(BlogPost.published_at.desc())
        .all()
    )
    # The listing page changes whenever any article does.
    newest = max(
        (p.updated_at or p.published_at for p in posts if (p.updated_at or p.published_at)),
        default=None,
    )

    urls = [
        _url(f"{base}{path}" if path != "/" else f"{base}/", freq, prio,
             newest if path == "/blog" else None)
        for path, freq, prio in _STATIC_ROUTES
    ]
    urls += [
        _url(f"{base}/blog/{p.slug}", "monthly", "0.7", p.updated_at or p.published_at)
        for p in posts
    ]

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )
    return Response(content=xml, media_type="application/xml")
