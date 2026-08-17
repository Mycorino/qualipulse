"""Server-rendered HTML for the public blog (crawlers + real visitors).

The frontend nginx proxies direct hits on /blog and /blog/{slug} here, so
this is what everyone arriving from search or a shared link actually reads,
not just Googlebot. The chrome therefore mirrors the SPA blog page
(``frontend/src/pages/Blog.tsx``): same header, hero, card grid and footer,
same FR copy from ``locales/fr/blog.json``. The SPA still renders these
routes for in-app navigation.

Because the page is standalone (it does not load the app's index.css), the
palette below repeats the design tokens' literal values. Keep them in sync
with ``frontend/src/index.css`` if the brand colours change.

Rendering rules:
- Every field is HTML-escaped except ``post.content``, which the admin blog
  router already sanitized with bleach when it was written.
- No <script> except the JSON-LD data block, which browsers never execute,
  so the API's strict HTML CSP (style-src 'unsafe-inline' only) suffices.
"""

import html
import json
from datetime import datetime

from app.models.blog import BlogPost

_STYLE = """
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body { margin: 0; background: #f5f5f7; color: #0d0f1a;
         font-family: system-ui, -apple-system, 'Segoe UI', sans-serif; }
  a { color: #4369f5; }

  /* ---- Header (mirrors the SPA blog header) ---- */
  .qp-header { background: #fff; border-bottom: 1px solid #e2e4ed; padding: 16px 24px;
               display: flex; align-items: center; justify-content: space-between;
               flex-wrap: wrap; gap: 12px; }
  .qp-brand { font-weight: 700; font-size: 18px; color: #0d0f1a; text-decoration: none; }
  .qp-header nav { display: flex; gap: 24px; align-items: center; flex-wrap: wrap; }
  .qp-header nav a { font-size: 14px; text-decoration: none; color: #5a6076; }
  .qp-header nav a.active { color: #4369f5; font-weight: 500; }
  .qp-cta-btn { background: #4369f5; color: #fff !important; padding: 8px 16px;
                border-radius: 8px; font-weight: 500; }

  /* ---- Hero ---- */
  .qp-hero { max-width: 800px; margin: 0 auto; padding: 64px 24px 32px; text-align: center; }
  .qp-hero h1 { font-size: 36px; font-weight: 700; margin: 0 0 12px; line-height: 1.2; }
  .qp-hero p { font-size: 18px; color: #5a6076; line-height: 1.6; margin: 0; }

  /* ---- Listing cards ---- */
  .qp-grid { max-width: 1100px; margin: 0 auto; padding: 0 24px 64px;
             display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
             gap: 24px; }
  .qp-card { display: block; background: #fff; border: 1px solid #e2e4ed; border-radius: 12px;
             padding: 24px; text-decoration: none; color: inherit; }
  .qp-card-cover { width: 100%; height: 180px; object-fit: cover; border-radius: 8px;
                   display: block; margin-bottom: 16px; }
  .qp-card h2 { font-size: 20px; margin: 0 0 8px; color: #0d0f1a; line-height: 1.3; }
  .qp-card p { margin: 0 0 12px; color: #5a6076; font-size: 15px; line-height: 1.55; }
  .qp-card .qp-meta { color: #6c7386; font-size: 13px; }
  .qp-empty { max-width: 800px; margin: 0 auto; padding: 40px 24px 80px; text-align: center; }
  .qp-empty p { color: #5a6076; }

  /* ---- Article ---- */
  .qp-article-wrap { background: #fff; border-top: 1px solid #e2e4ed; }
  .qp-article { max-width: 720px; margin: 0 auto; padding: 40px 24px 64px; }
  .qp-back { font-size: 14px; text-decoration: none; }
  .qp-article h1 { font-size: 34px; line-height: 1.2; margin: 20px 0 10px; }
  .qp-subtitle { color: #5a6076; font-size: 18px; font-style: italic; margin: 0 0 8px; }
  .qp-byline { color: #6c7386; font-size: 14px; margin: 0 0 32px; }
  .qp-body { font-family: Georgia, 'Times New Roman', serif; font-size: 18px;
             line-height: 1.7; color: #1a202c; }
  .qp-body h2 { font-family: system-ui, -apple-system, sans-serif; font-size: 24px;
                margin-top: 1.8em; line-height: 1.3; }
  .qp-body h3 { font-family: system-ui, -apple-system, sans-serif; font-size: 19px;
                margin-top: 1.6em; }
  .qp-body img { max-width: 100%; height: auto; border-radius: 8px; }
  .qp-body blockquote { border-left: 3px solid #4369f5; margin-left: 0; padding-left: 18px;
                        color: #5a6076; font-style: italic; }
  .qp-body ul, .qp-body ol { padding-left: 24px; }
  .qp-body li { margin-bottom: 6px; }
  .qp-cta-card { margin-top: 48px; padding: 24px; background: #eef1fe; border-radius: 12px;
                 font-family: system-ui, -apple-system, sans-serif; font-size: 15px;
                 color: #0d0f1a; line-height: 1.6; }
  .qp-cta-card a { display: inline-block; margin-top: 12px; background: #4369f5; color: #fff;
                   text-decoration: none; padding: 10px 22px; border-radius: 8px;
                   font-weight: 600; }

  /* ---- Footer (mirrors the SPA blog footer) ---- */
  .qp-footer { background: #fff; border-top: 1px solid #e2e4ed; padding: 32px 24px;
               text-align: center; font-size: 13px; color: #6c7386; }
  .qp-footer-links { display: flex; gap: 24px; justify-content: center; flex-wrap: wrap;
                     margin-bottom: 12px; }
  .qp-footer-links a { color: #5a6076; text-decoration: none; }

  @media (max-width: 600px) {
    .qp-hero { padding: 40px 20px 24px; }
    .qp-hero h1 { font-size: 28px; }
    .qp-article h1 { font-size: 27px; }
    .qp-body { font-size: 17px; }
  }
"""

_FR_MONTHS = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def _e(value: str | None) -> str:
    return html.escape(value or "", quote=True)


def _iso(dt: datetime | None) -> str:
    return dt.strftime("%Y-%m-%d") if dt else ""


def _fr_date(dt: datetime | None) -> str:
    return f"{dt.day} {_FR_MONTHS[dt.month - 1]} {dt.year}" if dt else ""


def _header(*, blog_active: bool) -> str:
    blog_class = ' class="active"' if blog_active else ""
    return (
        '<header class="qp-header">'
        '<a class="qp-brand" href="/">QualiPulse</a>'
        "<nav>"
        f'<a href="/blog"{blog_class}>Blog</a>'
        '<a href="/#pricing">Tarifs</a>'
        '<a href="/login">Se connecter</a>'
        '<a class="qp-cta-btn" href="/signup">Commencer gratuitement</a>'
        "</nav></header>"
    )


def _footer(year: int) -> str:
    return (
        '<footer class="qp-footer"><div class="qp-footer-links">'
        '<a href="/">Accueil</a><a href="/blog">Blog</a>'
        '<a href="/terms">Conditions</a><a href="/privacy">Confidentialité</a>'
        "</div>"
        f"© {year} QualiPulse. Tous droits réservés."
        "</footer>"
    )


def _document(*, title: str, metas: str, body: str, blog_active: bool) -> str:
    year = datetime.utcnow().year
    return (
        '<!doctype html>\n<html lang="fr">\n<head>\n<meta charset="utf-8" />\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1" />\n'
        f"<title>{_e(title)}</title>\n{metas}\n<style>{_STYLE}</style>\n</head>\n<body>\n"
        f"{_header(blog_active=blog_active)}\n{body}\n{_footer(year)}\n</body>\n</html>"
    )


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

    byline = _e(post.author_name)
    if post.published_at:
        byline += f" · {_e(_fr_date(post.published_at))}"
    subtitle = f'<p class="qp-subtitle">{_e(post.subtitle)}</p>' if post.subtitle else ""
    cover = (
        f'<p><img src="{_e(post.cover_image_url)}" alt="" /></p>' if post.cover_image_url else ""
    )

    body = (
        '<div class="qp-article-wrap"><article class="qp-article">\n'
        '<a class="qp-back" href="/blog">← Retour à tous les articles</a>\n'
        f"<h1>{_e(post.title)}</h1>\n{subtitle}"
        f'<p class="qp-byline">{byline}</p>\n'
        f'<div class="qp-body">{cover}{post.content}</div>\n'
        '<div class="qp-cta-card">Menez vos propres entretiens qualitatifs avec QualiPulse. '
        "Les 3 premiers entretiens terminés sont gratuits, sans carte bancaire."
        '<br /><a href="/signup">Créer un projet</a></div>\n'
        "</article></div>"
    )
    return _document(title=meta_title, metas=metas, body=body, blog_active=True)


def render_blog_listing_html(posts: list[BlogPost], base_url: str) -> str:
    canonical = f"{base_url}/blog"
    title = "Blog, QualiPulse"
    description = (
        "Conseils et analyses sur la recherche qualitative, les entretiens assistés "
        "par IA et la découverte produit, par l'équipe QualiPulse."
    )
    metas = "\n".join(
        [
            f'<meta name="description" content="{_e(description)}" />',
            f'<link rel="canonical" href="{_e(canonical)}" />',
            '<meta property="og:site_name" content="QualiPulse" />',
            '<meta property="og:type" content="website" />',
            f'<meta property="og:title" content="{_e(title)}" />',
            f'<meta property="og:description" content="{_e(description)}" />',
            f'<meta property="og:url" content="{_e(canonical)}" />',
        ]
    )

    hero = (
        '<section class="qp-hero"><h1>Le blog QualiPulse</h1>'
        "<p>Des guides concrets pour mener votre recherche qualitative, conduire des "
        "entretiens assistés par IA et transformer la voix de vos utilisateurs en "
        "décisions produit.</p></section>"
    )

    if not posts:
        body = (
            hero + '<div class="qp-empty"><p>Aucun article pour le moment</p>'
            "<p>Nous préparons de nouveaux articles. Revenez bientôt.</p></div>"
        )
        return _document(title=title, metas=metas, body=body, blog_active=True)

    cards = []
    for post in posts:
        excerpt = _e(post.excerpt or post.meta_description or "")
        meta = _e(post.author_name)
        if post.published_at:
            meta += f" · {_e(_fr_date(post.published_at))}"
        cover = (
            f'<img class="qp-card-cover" src="{_e(post.cover_image_url)}" alt="" />'
            if post.cover_image_url
            else ""
        )
        cards.append(
            f'<a class="qp-card" href="/blog/{_e(post.slug)}">{cover}'
            f"<h2>{_e(post.title)}</h2><p>{excerpt}</p>"
            f'<div class="qp-meta">{meta}</div></a>'
        )

    body = hero + '<section class="qp-grid">' + "\n".join(cards) + "</section>"
    return _document(title=title, metas=metas, body=body, blog_active=True)
