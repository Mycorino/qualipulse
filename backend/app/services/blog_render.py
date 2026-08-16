"""Server-rendered HTML for the public blog (crawlers + link unfurlers).

The SPA still renders /blog and /blog/:slug for in-app navigation, but the
frontend nginx proxies direct hits on those URLs here so search engines, AI
search tools, and social scrapers get complete HTML with per-post meta and
Article JSON-LD, no JavaScript required. Same content either way, different
entry path.

Rendering rules:
- Every field is HTML-escaped except ``post.content``, which was sanitized by
  the admin blog router (bleach) when it was written.
- No <script> except the JSON-LD data block, which browsers never execute,
  so the API's strict HTML CSP (style-src 'unsafe-inline' only) is enough.
"""

import html
import json
from datetime import datetime

from app.models.blog import BlogPost

_STYLE = """
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: Georgia, 'Times New Roman', serif; color: #1a202c;
         line-height: 1.65; background: #fff; }
  .qp-shell { max-width: 720px; margin: 0 auto; padding: 0 20px 64px; }
  .qp-nav { display: flex; align-items: center; justify-content: space-between;
            padding: 20px 0; font-family: system-ui, -apple-system, sans-serif; }
  .qp-nav a { color: #4f46e5; text-decoration: none; font-weight: 600; }
  .qp-brand { font-size: 1.05rem; color: #0f172a !important; }
  h1 { font-size: 1.9rem; line-height: 1.25; margin: 18px 0 8px; }
  .qp-subtitle { color: #475569; font-style: italic; margin: 0 0 8px; font-size: 1.05rem; }
  .qp-byline { color: #94a3b8; font-size: 0.85rem; font-family: system-ui, sans-serif;
               margin: 0 0 28px; }
  article h2 { font-size: 1.3rem; margin-top: 1.7em; }
  article img { max-width: 100%; height: auto; }
  article blockquote { border-left: 3px solid #4f46e5; margin-left: 0; padding-left: 16px;
                       color: #475569; font-style: italic; }
  article a { color: #4f46e5; }
  .qp-cta { margin-top: 48px; padding: 22px 24px; background: #eef2ff; border-radius: 12px;
            font-family: system-ui, sans-serif; }
  .qp-cta a { display: inline-block; margin-top: 10px; background: #4f46e5; color: #fff;
              text-decoration: none; padding: 10px 22px; border-radius: 8px; font-weight: 600; }
  .qp-card { display: block; padding: 18px 0; border-bottom: 1px solid #e2e8f0;
             text-decoration: none; color: inherit; }
  .qp-card h2 { margin: 0 0 6px; font-size: 1.2rem; color: #4f46e5; }
  .qp-card p { margin: 0; color: #475569; }
  footer { margin-top: 48px; color: #94a3b8; font-size: 0.8rem;
           font-family: system-ui, sans-serif; }
  footer a { color: #64748b; }
"""


def _e(value: str | None) -> str:
    return html.escape(value or "", quote=True)


def _document(*, lang: str, title: str, metas: str, body: str) -> str:
    return (
        f'<!doctype html>\n<html lang="{lang}">\n<head>\n<meta charset="utf-8" />\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1" />\n'
        f"<title>{_e(title)}</title>\n{metas}\n<style>{_STYLE}</style>\n</head>\n"
        f"<body><div class=\"qp-shell\">\n"
        '<nav class="qp-nav"><a class="qp-brand" href="/">QualiPulse</a>'
        '<a href="/blog">Blog</a></nav>\n'
        f"{body}\n"
        '<footer><a href="/">qualipulse.com</a> · <a href="/privacy">Confidentialité</a>'
        " · <a href=\"/terms\">Conditions</a></footer>\n"
        "</div></body>\n</html>"
    )


def _iso(dt: datetime | None) -> str:
    return dt.strftime("%Y-%m-%d") if dt else ""


def render_blog_post_html(post: BlogPost, base_url: str) -> str:
    canonical = f"{base_url}/blog/{post.slug}"
    meta_title = post.meta_title or post.title
    description = post.meta_description or post.excerpt or ""
    og_image = post.og_image_url or post.cover_image_url or f"{base_url}/og-image.png"

    json_ld = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": post.title,
        "description": description,
        "url": canonical,
        "image": og_image,
        "author": {"@type": "Organization", "name": post.author_name},
        "publisher": {"@type": "Organization", "name": "QualiPulse", "url": base_url},
    }
    if post.published_at:
        json_ld["datePublished"] = _iso(post.published_at)
    if post.updated_at:
        json_ld["dateModified"] = _iso(post.updated_at)

    metas = "\n".join(
        [
            f'<meta name="description" content="{_e(description)}" />',
            f'<link rel="canonical" href="{_e(canonical)}" />',
            '<meta property="og:site_name" content="QualiPulse" />',
            '<meta property="og:type" content="article" />',
            f'<meta property="og:title" content="{_e(meta_title)}" />',
            f'<meta property="og:description" content="{_e(description)}" />',
            f'<meta property="og:url" content="{_e(canonical)}" />',
            f'<meta property="og:image" content="{_e(og_image)}" />',
            f'<script type="application/ld+json">{json.dumps(json_ld, ensure_ascii=False)}</script>',
        ]
    )

    byline_parts = [_e(post.author_name)]
    if post.published_at:
        byline_parts.append(_e(_iso(post.published_at)))
    subtitle = f'<p class="qp-subtitle">{_e(post.subtitle)}</p>' if post.subtitle else ""
    cover = (
        f'<p><img src="{_e(post.cover_image_url)}" alt="" /></p>' if post.cover_image_url else ""
    )

    body = (
        f"<article>\n<h1>{_e(post.title)}</h1>\n{subtitle}"
        f'<p class="qp-byline">{" · ".join(byline_parts)}</p>\n'
        f"{cover}{post.content}\n</article>\n"
        '<div class="qp-cta">Menez vos propres entretiens qualitatifs avec QualiPulse.'
        " Les 3 premiers entretiens terminés sont gratuits, sans carte bancaire."
        '<br /><a href="/signup">Créer un projet</a></div>'
    )
    return _document(lang="fr", title=meta_title, metas=metas, body=body)


def render_blog_listing_html(posts: list[BlogPost], base_url: str) -> str:
    canonical = f"{base_url}/blog"
    description = (
        "Méthodes d'entretien qualitatif, recherche UX et analyse thématique : "
        "le blog QualiPulse."
    )
    metas = "\n".join(
        [
            f'<meta name="description" content="{_e(description)}" />',
            f'<link rel="canonical" href="{_e(canonical)}" />',
            '<meta property="og:site_name" content="QualiPulse" />',
            '<meta property="og:type" content="website" />',
            '<meta property="og:title" content="Blog QualiPulse" />',
            f'<meta property="og:description" content="{_e(description)}" />',
            f'<meta property="og:url" content="{_e(canonical)}" />',
        ]
    )

    cards = []
    for post in posts:
        excerpt = _e(post.excerpt or post.meta_description or "")
        cards.append(
            f'<a class="qp-card" href="/blog/{_e(post.slug)}">'
            f"<h2>{_e(post.title)}</h2><p>{excerpt}</p></a>"
        )
    if not cards:
        cards.append("<p>Les premiers articles arrivent bientôt.</p>")

    body = "<h1>Blog</h1>\n" + "\n".join(cards)
    return _document(lang="fr", title="Blog · QualiPulse", metas=metas, body=body)
